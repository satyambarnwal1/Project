"""Runtime configuration.

Everything the crawler/searcher needs to behave politely and predictably lives
here. Defaults are deliberately conservative (slow and respectful) so the tool
does not hammer other people's servers. The CLI in ``run.py`` overrides these.
"""

from __future__ import annotations

from dataclasses import dataclass, field


# A user-agent that honestly identifies the bot. Replace the contact address
# with your own so site owners can reach you. Being identifiable is part of
# scraping responsibly.
DEFAULT_USER_AGENT = (
    "email-harvester/1.0 (+contact: set-your-email@example.com) "
    "Python-requests"
)


@dataclass
class Settings:
    # --- crawling limits -------------------------------------------------
    max_pages_per_site: int = 10          # how many pages to visit per company
    request_timeout: float = 15.0         # seconds per HTTP request
    max_page_bytes: int = 3_000_000       # skip pages larger than this (~3 MB)

    # --- politeness ------------------------------------------------------
    delay_between_requests: float = 1.5   # seconds between requests to one site
    delay_between_sites: float = 2.0      # seconds between two different sites
    respect_robots_txt: bool = True       # obey robots.txt (recommended: True)
    user_agent: str = DEFAULT_USER_AGENT

    # --- search ----------------------------------------------------------
    backend: str = "duckduckgo"           # duckduckgo | serper | serpapi
    results_per_query: int = 25           # results to pull per search query
    search_region: str = "us-en"          # ddgs region code
    api_key: str | None = None            # for serper / serpapi backends

    # --- run control -----------------------------------------------------
    max_sites: int = 0                    # 0 = unlimited (run until stopped)
    output_path: str = "leads.csv"        # where results are appended

    # --- email filtering -------------------------------------------------
    # Domains/substrings that almost always indicate junk, examples, or
    # tracking addresses rather than a real business contact.
    blocked_email_substrings: list[str] = field(
        default_factory=lambda: [
            "example.com", "example.org", "example.net", "yourdomain",
            "domain.com", "email.com", "sentry.io", "wixpress.com",
            "@2x", "@3x", ".png", ".jpg", ".jpeg", ".gif", ".webp",
            ".svg", ".bmp", ".ico", ".css", ".js",
        ]
    )
    # Local-parts that are usually system addresses; kept but flagged so you
    # can choose to ignore them downstream.
    low_value_local_parts: list[str] = field(
        default_factory=lambda: ["noreply", "no-reply", "donotreply", "postmaster"]
    )

    def validate(self) -> None:
        if self.max_pages_per_site < 1:
            raise ValueError("max_pages_per_site must be >= 1")
        if self.delay_between_requests < 0 or self.delay_between_sites < 0:
            raise ValueError("delays cannot be negative")
        if self.backend in {"serper", "serpapi"} and not self.api_key:
            raise ValueError(f"backend '{self.backend}' requires --api-key")
