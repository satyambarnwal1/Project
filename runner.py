"""The orchestration loop.

Ties the pieces together and runs until the user stops it (Ctrl+C / SIGTERM)
or until ``max_sites`` companies have been processed.

Flow:
    for each generated query:
        for each result URL the search backend returns:
            resolve its registered domain
            skip if we've already crawled that domain
            crawl up to N pages, extract emails
            store new emails
    ... and the query generator never runs dry, so the loop continues until
    interrupted.

A signal handler flips a stop flag; the loop finishes the current site, flushes,
prints a summary, and exits cleanly.
"""

from __future__ import annotations

import signal
import time

from .config import Settings
from .crawler import SiteCrawler, registered_domain
from .extractor import is_low_value
from .query import SearchQuery, generate_queries
from .search import get_backend
from .storage import CSVStore, LeadRow


class HarvestRunner:
    def __init__(self, query: SearchQuery, settings: Settings) -> None:
        settings.validate()
        self.query = query
        self.settings = settings
        self.backend = get_backend(settings)
        self.crawler = SiteCrawler(settings)
        self.store = CSVStore(settings.output_path, query)

        self._stop = False
        self.sites_processed = 0
        self.emails_written = 0
        self._started = time.monotonic()

    # -- graceful shutdown ------------------------------------------------
    def _install_signal_handlers(self) -> None:
        def handler(signum, _frame):
            if not self._stop:
                print("\n[stopping] finishing the current site, then exiting "
                      "(press Ctrl+C again to force quit)...")
                self._stop = True
            else:
                raise KeyboardInterrupt
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, handler)
            except (ValueError, OSError):
                pass  # not in main thread / unsupported platform

    # -- main loop --------------------------------------------------------
    def run(self) -> None:
        self._install_signal_handlers()
        print(f"Harvesting: {self.query.describe()}")
        print(f"Backend: {self.settings.backend} | output: {self.settings.output_path}")
        print(f"Up to {self.settings.max_pages_per_site} pages per site. "
              f"Press Ctrl+C to stop.\n")

        try:
            for query_text in generate_queries(self.query):
                if self._stop:
                    break
                print(f"[search] {query_text}")
                for url in self.backend.search(query_text):
                    if self._stop:
                        break
                    self._process_url(url, query_text)
                    if self._reached_limit():
                        self._stop = True
                        break
                # Pause between queries to stay polite to the search engine.
                if not self._stop:
                    time.sleep(self.settings.delay_between_sites)
        except KeyboardInterrupt:
            print("\n[forced quit]")
        finally:
            self._summary()

    def _process_url(self, url: str, query_text: str) -> None:
        domain = registered_domain(url)
        if not domain or self.store.domain_done(domain):
            return
        self.store.mark_domain(domain)

        print(f"   -> crawling {domain} ...", end=" ", flush=True)
        try:
            hits = self.crawler.crawl(url)
        except Exception as exc:
            print(f"error ({exc})")
            return

        rows = [
            LeadRow(
                email=h.email,
                domain=registered_domain(h.source_url) or domain,
                source_url=h.source_url,
                company_url=url,
                low_value=is_low_value(h.email, self.settings.low_value_local_parts),
            )
            for h in hits
        ]
        written = self.store.save(query_text, rows)
        self.emails_written += written
        self.sites_processed += 1
        print(f"{len(hits)} email(s), {written} new "
              f"(total new: {self.emails_written})")

        time.sleep(self.settings.delay_between_sites)

    def _reached_limit(self) -> bool:
        return self.settings.max_sites > 0 and self.sites_processed >= self.settings.max_sites

    def _summary(self) -> None:
        elapsed = time.monotonic() - self._started
        print("\n" + "-" * 48)
        print(f"Sites crawled : {self.sites_processed}")
        print(f"New emails    : {self.emails_written}")
        print(f"Output file   : {self.settings.output_path}")
        print(f"Elapsed       : {elapsed:,.0f}s")
        print("-" * 48)
