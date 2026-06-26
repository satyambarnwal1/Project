"""Crawl a single company website and collect emails.

Given a starting URL, the crawler:
  * reads the site's robots.txt (and obeys it, if enabled),
  * fetches the homepage and looks for links whose URL or anchor text suggest a
    contact/about/team/imprint page,
  * visits up to ``max_pages_per_site`` pages, contact/about pages first,
  * stays on the same registered domain,
  * extracts emails from each page (mailto links + text),
  * sleeps ``delay_between_requests`` seconds between requests.

Returns a list of ``EmailHit`` (email + the page it was found on).
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse, urldefrag
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

import tldextract

from .config import Settings
from .extractor import extract_from_anchors, extract_from_text

# Use the suffix list bundled with tldextract instead of fetching it over the
# network on first use (offline, deterministic, no startup latency).
_tld = tldextract.TLDExtract(suffix_list_urls=())


# Keywords that, when present in a link's URL or visible text, mark it as a
# high-priority page (likely to contain contact details).
_PRIORITY_KEYWORDS = (
    "contact", "about", "team", "company", "imprint", "impressum", "kontakt",
    "contacto", "contato", "get-in-touch", "getintouch", "reach", "support",
    "info", "leadership", "staff", "people", "directory", "enquir", "inquir",
    "connect", "find-us", "locations", "offices", "help",
)

# File extensions we never want to fetch (not HTML).
_SKIP_EXTENSIONS = (
    ".pdf", ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".bmp", ".ico",
    ".zip", ".gz", ".tar", ".rar", ".7z", ".mp3", ".mp4", ".mov", ".avi",
    ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".css", ".js", ".rss",
    ".xml", ".json", ".woff", ".woff2", ".ttf", ".eot",
)


@dataclass
class EmailHit:
    email: str
    source_url: str


def registered_domain(url: str) -> str:
    """e.g. https://www.foo.co.uk/x -> foo.co.uk (empty string if unparseable)."""
    ext = _tld(url)
    if not ext.domain or not ext.suffix:
        return ""
    return f"{ext.domain}.{ext.suffix}".lower()


class SiteCrawler:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": settings.user_agent})

    # -- robots.txt -------------------------------------------------------
    def _robots(self, start_url: str) -> RobotFileParser | None:
        if not self.settings.respect_robots_txt:
            return None
        parsed = urlparse(start_url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        rp = RobotFileParser()
        try:
            resp = self.session.get(robots_url, timeout=self.settings.request_timeout)
            if resp.status_code >= 400:
                return None  # no robots.txt -> nothing disallowed
            rp.parse(resp.text.splitlines())
            return rp
        except Exception:
            return None  # unreachable robots.txt: don't block the crawl

    def _allowed(self, rp: RobotFileParser | None, url: str) -> bool:
        if rp is None:
            return True
        try:
            return rp.can_fetch(self.settings.user_agent, url)
        except Exception:
            return True

    # -- fetching ---------------------------------------------------------
    def _fetch(self, url: str) -> str | None:
        try:
            resp = self.session.get(
                url, timeout=self.settings.request_timeout,
                allow_redirects=True, stream=True,
            )
        except requests.RequestException:
            return None

        content_type = resp.headers.get("Content-Type", "")
        if "html" not in content_type.lower() and content_type:
            resp.close()
            return None

        length = resp.headers.get("Content-Length")
        if length and length.isdigit() and int(length) > self.settings.max_page_bytes:
            resp.close()
            return None

        try:
            # Cap how much we read even when no Content-Length is sent.
            chunks, total = [], 0
            for chunk in resp.iter_content(chunk_size=65536, decode_unicode=False):
                chunks.append(chunk)
                total += len(chunk)
                if total > self.settings.max_page_bytes:
                    break
            raw = b"".join(chunks)
        except requests.RequestException:
            return None
        finally:
            resp.close()

        encoding = resp.encoding or "utf-8"
        try:
            return raw.decode(encoding, errors="replace")
        except (LookupError, UnicodeDecodeError):
            return raw.decode("utf-8", errors="replace")

    # -- link discovery ---------------------------------------------------
    def _links(self, html_text: str, base_url: str, domain: str):
        """Return (priority_links, other_links, hrefs) found on the page."""
        soup = BeautifulSoup(html_text, "html.parser")
        priority, other, hrefs = [], [], []
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            hrefs.append(href)
            if href.lower().startswith(("mailto:", "tel:", "javascript:", "#")):
                continue
            absolute = urldefrag(urljoin(base_url, href)).url
            if not absolute.lower().startswith(("http://", "https://")):
                continue
            if registered_domain(absolute) != domain:
                continue  # stay on the same site
            if absolute.lower().endswith(_SKIP_EXTENSIONS):
                continue
            text = (a.get_text() or "").lower()
            target = absolute.lower() + " " + text
            if any(k in target for k in _PRIORITY_KEYWORDS):
                priority.append(absolute)
            else:
                other.append(absolute)
        return priority, other, hrefs

    @staticmethod
    def _page_text(html_text: str) -> str:
        soup = BeautifulSoup(html_text, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        # Keep raw html too (some emails hide in attributes/JSON); but text is
        # the primary signal. We pass the whole decoded html to the extractor
        # elsewhere, so here just return visible text.
        return soup.get_text(separator=" ")

    # -- main entry -------------------------------------------------------
    def crawl(self, start_url: str) -> list[EmailHit]:
        if not start_url.lower().startswith(("http://", "https://")):
            start_url = "https://" + start_url
        domain = registered_domain(start_url)
        if not domain:
            return []

        rp = self._robots(start_url)
        hits: dict[str, str] = {}          # email -> first source url
        visited: set[str] = set()
        # Two-tier queue: priority pages (contact/about) drain before others.
        priority_q: deque[str] = deque([start_url])
        other_q: deque[str] = deque()

        first_request = True
        while (priority_q or other_q) and len(visited) < self.settings.max_pages_per_site:
            url = priority_q.popleft() if priority_q else other_q.popleft()
            url = urldefrag(url).url
            if url in visited:
                continue
            visited.add(url)

            if not self._allowed(rp, url):
                continue

            if not first_request:
                time.sleep(self.settings.delay_between_requests)
            first_request = False

            html_text = self._fetch(url)
            if html_text is None:
                continue

            blocked = self.settings.blocked_email_substrings
            # Extract from both raw html (catches attributes/entities) and the
            # cleaned visible text + anchor hrefs.
            priority, other, hrefs = self._links(html_text, url, domain)
            page_emails = extract_from_anchors(hrefs, blocked)
            page_emails |= extract_from_text(html_text, blocked)
            for email in page_emails:
                hits.setdefault(email, url)

            for link in priority:
                if link not in visited:
                    priority_q.append(link)
            for link in other:
                if link not in visited:
                    other_q.append(link)

        return [EmailHit(email=e, source_url=src) for e, src in hits.items()]
