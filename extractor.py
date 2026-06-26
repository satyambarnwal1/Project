"""Find and clean email addresses in a web page.

Sources, in rough order of reliability:
  1. ``mailto:`` links in anchor hrefs (cleanest signal).
  2. Plain-text addresses matching a standard pattern.
  3. Lightly obfuscated addresses like ``name [at] domain [dot] com``.

HTML entities (e.g. ``&#64;`` for ``@``) are decoded before matching. Results
are lower-cased, de-duplicated, and filtered against a junk list (image/asset
filenames that look like emails, placeholder/example addresses, etc.).
"""

from __future__ import annotations

import html
import re
from typing import Iterable
from urllib.parse import unquote

# Standard, reasonably strict address pattern.
_EMAIL_RE = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9](?:[a-zA-Z0-9\-]*[a-zA-Z0-9])?"
    r"(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9\-]*[a-zA-Z0-9])?)+"
)

# De-obfuscation is split into two deliberately conservative patterns so we do
# not turn ordinary prose like "meet the broker at jane.doe@..." into a bogus
# address.
#
# Pattern 1 - bracketed "at": [at] / (at) / {at}. Unambiguous, so the domain's
# dots may be literal "." or worded ([dot]/(dot)/{dot}/ dot ).
_OBFUSCATED_BRACKET_RE = re.compile(
    r"""
    ([a-zA-Z0-9._%+\-]+)                                   # local part
    \s*(?:\[\s*at\s*\]|\(\s*at\s*\)|\{\s*at\s*\})\s*        # bracketed @
    (                                                      # domain
        (?:[a-zA-Z0-9\-]+\s*
           (?:\[\s*dot\s*\]|\(\s*dot\s*\)|\{\s*dot\s*\}|\s+dot\s+|\.)\s*)+
        [a-zA-Z]{2,}
    )
    """,
    re.VERBOSE | re.IGNORECASE,
)

# Pattern 2 - fully spelled-out "at" with spelled-out "dot"(s) only. Requiring
# the dots to be worded (no literal ".") keeps normal sentences from matching.
_OBFUSCATED_WORD_RE = re.compile(
    r"""
    \b([a-zA-Z0-9_%+\-]+)                                  # local part
    \s+at\s+                                               # the word "at"
    (                                                      # domain
        (?:[a-zA-Z0-9\-]+\s*
           (?:\[\s*dot\s*\]|\(\s*dot\s*\)|\{\s*dot\s*\}|\s+dot\s+)\s*)+
        [a-zA-Z]{2,}
    )
    """,
    re.VERBOSE | re.IGNORECASE,
)

_TLD_RE = re.compile(r"\.[a-zA-Z]{2,24}$")


def _decode(text: str) -> str:
    """Decode HTML entities and percent-encoding so hidden @ / . surface."""
    return html.unescape(unquote(text))


def _normalise_obfuscated(local: str, domain: str) -> str:
    domain = re.sub(r"\s*(?:\[\s*dot\s*\]|\(\s*dot\s*\)|\{\s*dot\s*\}|\s+dot\s+)\s*",
                    ".", domain, flags=re.IGNORECASE)
    domain = re.sub(r"\s+", "", domain)
    return f"{local.strip()}@{domain}".lower()


def _looks_valid(email: str, blocked_substrings: Iterable[str]) -> bool:
    if email.count("@") != 1:
        return False
    local, _, domain = email.partition("@")
    if not local or not domain or "." not in domain:
        return False
    if domain.startswith(".") or domain.endswith(".") or ".." in domain:
        return False
    if not _TLD_RE.search(domain):
        return False
    if len(email) > 254:
        return False
    low = email.lower()
    return not any(bad in low for bad in blocked_substrings)


def extract_from_anchors(hrefs: Iterable[str], blocked_substrings: Iterable[str]) -> set[str]:
    """Pull addresses out of ``mailto:`` hrefs."""
    found: set[str] = set()
    for href in hrefs:
        if not href:
            continue
        h = _decode(href).strip()
        if h.lower().startswith("mailto:"):
            addr = h[7:].split("?", 1)[0].strip()  # drop ?subject=... etc.
            for candidate in addr.split(","):       # mailto can list several
                candidate = candidate.strip()
                if _looks_valid(candidate, blocked_substrings):
                    found.add(candidate.lower())
    return found


def extract_from_text(text: str, blocked_substrings: Iterable[str]) -> set[str]:
    """Pull addresses (plain + obfuscated) out of arbitrary text/HTML."""
    found: set[str] = set()
    decoded = _decode(text)

    for match in _EMAIL_RE.findall(decoded):
        if _looks_valid(match, blocked_substrings):
            found.add(match.lower())

    for local, domain in _OBFUSCATED_BRACKET_RE.findall(decoded):
        candidate = _normalise_obfuscated(local, domain)
        if _looks_valid(candidate, blocked_substrings):
            found.add(candidate)

    for local, domain in _OBFUSCATED_WORD_RE.findall(decoded):
        candidate = _normalise_obfuscated(local, domain)
        if _looks_valid(candidate, blocked_substrings):
            found.add(candidate)

    return found


def extract_emails(
    html_text: str,
    hrefs: Iterable[str],
    blocked_substrings: Iterable[str],
) -> set[str]:
    """Convenience wrapper combining anchor + text extraction."""
    emails = extract_from_anchors(hrefs, blocked_substrings)
    emails |= extract_from_text(html_text, blocked_substrings)
    return emails


def is_low_value(email: str, low_value_local_parts: Iterable[str]) -> bool:
    """True for system-ish addresses (noreply@, postmaster@, ...)."""
    local = email.split("@", 1)[0]
    return any(local == part or local.startswith(part) for part in low_value_local_parts)
