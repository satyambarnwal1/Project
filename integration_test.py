"""End-to-end test of the runner loop using fakes (no network)."""

import csv
import os
import tempfile

import harvester.runner as runner_mod
from harvester.config import Settings
from harvester.query import SearchQuery
from harvester.runner import HarvestRunner
from harvester.crawler import EmailHit

# Bound the otherwise-infinite query generator so the test terminates even when
# no new domains appear (e.g. on restart). Two queries is enough here.
runner_mod.generate_queries = lambda q: iter(["query one", "query two"])


class FakeBackend:
    """Yields a fixed set of result URLs regardless of the query."""
    def __init__(self):
        self.calls = 0

    def search(self, query):
        self.calls += 1
        # Two companies the first time, one repeat + one new the second time.
        if self.calls == 1:
            yield "https://acme-realty.com/"
            yield "https://bluesky-homes.com/about"
        else:
            yield "https://acme-realty.com/contact"   # same domain -> skipped
            yield "https://cedar-properties.io/"


class FakeCrawler:
    """Returns canned emails per domain instead of hitting the web."""
    DATA = {
        "acme-realty.com": ["sales@acme-realty.com", "info@acme-realty.com"],
        "bluesky-homes.com": ["hello@bluesky-homes.com", "sales@acme-realty.com"],  # dup email
        "cedar-properties.io": ["team@cedar-properties.io"],
    }

    def crawl(self, url):
        from harvester.crawler import registered_domain
        d = registered_domain(url)
        return [EmailHit(email=e, source_url=url) for e in self.DATA.get(d, [])]


def main():
    tmp = tempfile.mkdtemp()
    out = os.path.join(tmp, "leads.csv")

    settings = Settings(
        output_path=out,
        delay_between_requests=0,    # no waiting in the test
        delay_between_sites=0,
    )
    query = SearchQuery(industry="real estate", country="USA")

    runner = HarvestRunner(query, settings)
    runner.backend = FakeBackend()   # inject fakes
    runner.crawler = FakeCrawler()
    runner.run()

    print("\n=== CSV CONTENTS ===")
    with open(out, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        print(f"  {r['email']:32} domain={r['domain']:22} src={r['source_url']}")

    emails = [r["email"] for r in rows]
    print("\nTotal rows:", len(rows))
    print("Unique emails == rows? ", len(emails) == len(set(emails)))
    print("Duplicate 'sales@acme-realty.com' written once? ",
          emails.count("sales@acme-realty.com") == 1)
    print("acme crawled once despite 2 hits (domain dedup)? ", runner.sites_processed == 3)

    # Second run on the same file should add nothing (cross-run dedup).
    print("\n=== RESTART (should add 0 new) ===")
    runner2 = HarvestRunner(query, Settings(output_path=out,
                                            delay_between_requests=0, delay_between_sites=0))
    runner2.backend = FakeBackend()
    runner2.crawler = FakeCrawler()
    runner2.run()
    print("New emails on restart:", runner2.emails_written, "(expected 0)")


if __name__ == "__main__":
    main()
