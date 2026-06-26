"""Append results to a CSV and de-duplicate across runs.

On startup the store reads any existing output file so that restarting the
harvester does not re-write rows it already has, and so already-crawled domains
can be skipped. Each row records the email, where it came from, and the query
context that produced it.
"""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from datetime import datetime, timezone

from .query import SearchQuery

_FIELDS = [
    "email",
    "domain",
    "source_url",
    "company_url",
    "low_value",
    "industry",
    "country",
    "state",
    "district",
    "zip_code",
    "search_query",
    "found_at",
]


@dataclass
class LeadRow:
    email: str
    domain: str
    source_url: str
    company_url: str
    low_value: bool


class CSVStore:
    def __init__(self, path: str, query: SearchQuery) -> None:
        self.path = path
        self.query = query
        self.seen_emails: set[str] = set()
        self.seen_domains: set[str] = set()
        self._load_existing()
        self._ensure_header()

    def _load_existing(self) -> None:
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, newline="", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    if row.get("email"):
                        self.seen_emails.add(row["email"].lower())
                    if row.get("domain"):
                        self.seen_domains.add(row["domain"].lower())
        except (OSError, csv.Error):
            pass  # start fresh if the file is unreadable

    def _ensure_header(self) -> None:
        if os.path.exists(self.path) and os.path.getsize(self.path) > 0:
            return
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        with open(self.path, "w", newline="", encoding="utf-8") as fh:
            csv.DictWriter(fh, fieldnames=_FIELDS).writeheader()

    def domain_done(self, domain: str) -> bool:
        return domain.lower() in self.seen_domains

    def mark_domain(self, domain: str) -> None:
        if domain:
            self.seen_domains.add(domain.lower())

    def save(self, query_text: str, rows: list[LeadRow]) -> int:
        """Append the not-yet-seen rows. Returns how many were newly written."""
        new_rows = [r for r in rows if r.email.lower() not in self.seen_emails]
        if not new_rows:
            return 0
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with open(self.path, "a", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=_FIELDS)
            for r in new_rows:
                self.seen_emails.add(r.email.lower())
                writer.writerow({
                    "email": r.email,
                    "domain": r.domain,
                    "source_url": r.source_url,
                    "company_url": r.company_url,
                    "low_value": "yes" if r.low_value else "",
                    "industry": self.query.industry,
                    "country": self.query.country,
                    "state": self.query.state or "",
                    "district": self.query.district or "",
                    "zip_code": self.query.zip_code or "",
                    "search_query": query_text,
                    "found_at": now,
                })
        return len(new_rows)
