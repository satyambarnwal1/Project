#!/usr/bin/env python3
"""Command-line entry point for the email harvester.

Examples
--------
# the example from the brief: real estate companies in the USA, run until stopped
python run.py --industry "real estate" --country USA

# narrow to a state / district / zip, write somewhere specific, go slower
python run.py --industry "real estate" --country USA \
    --state California --district "Los Angeles" --zip 90001 \
    --output la_realtors.csv --delay 2.5

# stop automatically after 50 sites, using a paid search API
python run.py --industry "law firms" --country USA \
    --backend serper --api-key $SERPER_KEY --max-sites 50

Run with no --industry/--country and you'll be prompted for them.
"""

from __future__ import annotations

import argparse
import sys

from harvester.config import Settings, DEFAULT_USER_AGENT
from harvester.query import SearchQuery
from harvester.runner import HarvestRunner


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Search the web for companies in an industry/location and "
                    "collect their public contact emails.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    # query
    p.add_argument("--industry", help="industry to search for (required)")
    p.add_argument("--country", help="country to search in (required)")
    p.add_argument("--state", default=None, help="state / province (optional)")
    p.add_argument("--district", default=None, help="district / city (optional)")
    p.add_argument("--zip", dest="zip_code", default=None, help="zip / postal code (optional)")
    # output / limits
    p.add_argument("--output", default="leads.csv", help="CSV output path")
    p.add_argument("--max-pages", type=int, default=10,
                   help="max pages to crawl per company website")
    p.add_argument("--max-sites", type=int, default=0,
                   help="stop after this many sites (0 = run until stopped)")
    # search
    p.add_argument("--backend", default="duckduckgo",
                   choices=["duckduckgo", "ddg", "serper", "serpapi"],
                   help="search backend")
    p.add_argument("--api-key", default=None, help="API key for serper/serpapi")
    p.add_argument("--results-per-query", type=int, default=25,
                   help="how many search results to pull per query")
    p.add_argument("--region", default="us-en", help="DuckDuckGo region code")
    # politeness
    p.add_argument("--delay", type=float, default=1.5,
                   help="seconds between requests to the same site")
    p.add_argument("--site-delay", type=float, default=2.0,
                   help="seconds between different sites/queries")
    p.add_argument("--timeout", type=float, default=15.0, help="HTTP timeout (s)")
    p.add_argument("--user-agent", default=DEFAULT_USER_AGENT, help="HTTP User-Agent")
    p.add_argument("--ignore-robots", action="store_true",
                   help="do NOT honor robots.txt (not recommended)")
    return p


def prompt(label: str, required: bool = False) -> str | None:
    while True:
        value = input(label).strip()
        if value or not required:
            return value or None
        print("  (this field is required)")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    industry = args.industry or prompt("Industry (required): ", required=True)
    country = args.country or prompt("Country (required): ", required=True)
    state = args.state
    district = args.district
    zip_code = args.zip_code
    # Only prompt for optional fields when running interactively (no industry arg).
    if args.industry is None:
        state = prompt("State/province (optional, Enter to skip): ")
        district = prompt("District/city (optional, Enter to skip): ")
        zip_code = prompt("Zip/postal code (optional, Enter to skip): ")

    try:
        query = SearchQuery(
            industry=industry, country=country,
            state=state, district=district, zip_code=zip_code,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    settings = Settings(
        max_pages_per_site=args.max_pages,
        max_sites=args.max_sites,
        output_path=args.output,
        backend=args.backend,
        api_key=args.api_key,
        results_per_query=args.results_per_query,
        search_region=args.region,
        delay_between_requests=args.delay,
        delay_between_sites=args.site_delay,
        request_timeout=args.timeout,
        user_agent=args.user_agent,
        respect_robots_txt=not args.ignore_robots,
    )

    try:
        HarvestRunner(query, settings).run()
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
