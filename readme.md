# email-harvester

Take a structured query — **industry + country** (with optional **state**,
**district**, **zip code**) — search the web for matching companies, visit up
to ~10 pages of each company's site (contact / about / team pages first), and
collect their public contact email addresses into a CSV. The run continues
until you stop it.

```
{industry} {country} {state} {district} {zip}
   ▲          ▲         └────── all optional (leave out / pass null) ──────┘
   required   required
```

---

## How it works

```
generate search queries ─▶ search engine ─▶ result URLs
                                              │
                                              ▼
                              for each NEW company domain:
                                  read robots.txt (and obey it)
                                  crawl ≤10 pages, contact/about first
                                  pull emails from mailto links + text
                                  (also de-obfuscates "name [at] site [dot] com")
                                  ▼
                              append new, de-duplicated rows to CSV
```

When you give only a country, the query generator sweeps the country's regions
(all 50 US states, Indian states, UK regions, etc. — see `harvester/locations.py`)
so coverage isn't limited to whatever the search engine returns for the bare
country name. The generator never runs dry, which is what lets the process
"continue until someone stops it."

---

## Install

Requires Python 3.10+.

```bash
pip install -r requirements.txt
```

Dependencies: `requests`, `beautifulsoup4`, `tldextract`, and `ddgs`
(the maintained DuckDuckGo search client — free, no API key).

---

## Quick start

The example from the brief — real estate companies in the USA, run until stopped:

```bash
python run.py --industry "real estate" --country USA
```

Press **Ctrl+C** once to stop gracefully (it finishes the current site, flushes
the CSV, and prints a summary). Press Ctrl+C twice to force-quit.

Narrow it down and write to a specific file:

```bash
python run.py --industry "real estate" --country USA \
    --state California --district "Los Angeles" --zip 90001 \
    --output la_realtors.csv
```

Run with no arguments to be prompted interactively:

```bash
python run.py
# Industry (required): real estate
# Country (required): USA
# State/province (optional, Enter to skip):
# ...
```

Stop automatically after 50 newly-crawled sites:

```bash
python run.py --industry "law firms" --country USA --max-sites 50
```

---

## Output

A CSV (default `leads.csv`) with one row per unique email:

| column | meaning |
|---|---|
| `email` | the address found |
| `domain` | registered domain it was found on |
| `source_url` | the exact page it came from |
| `company_url` | the search result that led to the company |
| `low_value` | `yes` for system addresses (noreply@, postmaster@, …) |
| `industry`, `country`, `state`, `district`, `zip_code` | your query context |
| `search_query` | the query string that surfaced this company |
| `found_at` | UTC timestamp |

De-duplication is on `email` and persists across runs: re-running against the
same CSV won't duplicate rows, and already-crawled domains are skipped. So you
can stop and resume freely.

---

## Common options

| flag | default | description |
|---|---|---|
| `--industry` | – | industry (required) |
| `--country` | – | country (required) |
| `--state` / `--district` / `--zip` | none | optional location narrowing |
| `--output` | `leads.csv` | output CSV path |
| `--max-pages` | `10` | pages to crawl per company site |
| `--max-sites` | `0` | stop after N newly-crawled sites (0 = run until stopped) |
| `--backend` | `duckduckgo` | `duckduckgo`, `serper`, or `serpapi` |
| `--api-key` | none | API key for `serper` / `serpapi` |
| `--delay` | `1.5` | seconds between requests to the same site |
| `--site-delay` | `2.0` | seconds between sites / queries |
| `--region` | `us-en` | DuckDuckGo region code |
| `--ignore-robots` | off | skip robots.txt (not recommended) |

---

## Search backends

* **`duckduckgo`** (default) — free, no key. DuckDuckGo rate-limits scripted
  access fairly aggressively; if results dry up, slow down (`--site-delay 5`)
  or switch to a paid backend.
* **`serper`** ([serper.dev](https://serper.dev)) — Google results as JSON.
  `--backend serper --api-key $SERPER_KEY`
* **`serpapi`** ([serpapi.com](https://serpapi.com)) — Google results as JSON.
  `--backend serpapi --api-key $SERPAPI_KEY`

Paid backends are far more reliable for large, long-running jobs.

---

## Responsible use

This tool collects business contact addresses that companies publish on their
own websites. Please use it accordingly:

* **It honors `robots.txt` by default** and rate-limits itself. Keep it that way.
* **Identify yourself** — edit the contact address in the default user-agent
  (`harvester/config.py`) so site owners can reach you.
* **Sending to collected addresses is regulated.** Anti-spam / data-protection
  laws (e.g. US CAN-SPAM, EU/UK GDPR, Canada CASL) govern unsolicited email and,
  in some places, the storage of business contact data. Make sure your outreach
  complies — honor unsubscribe requests, identify yourself, and don't email
  people who haven't consented where consent is required.
* Respect each site's terms of service.

---

## Limitations

* **JavaScript-rendered sites:** the crawler uses `requests` + `BeautifulSoup`,
  so emails injected by client-side JS won't be seen. To handle those, swap the
  fetch step for a headless browser (Playwright/Selenium).
* **No deliverability check:** addresses are extracted as written, not verified.
  Pipe the CSV through an email-verification step before using it.
* **Rate limits / blocking:** heavy use of the free DuckDuckGo backend will get
  throttled. Use delays and/or a paid backend for scale.
* **Single-threaded** by design (politeness + simplicity).

---

## Project layout

```
email-harvester/
├── run.py                 # CLI entry point
├── requirements.txt
├── selftest.py            # offline tests: extraction, query gen, link parsing
├── integration_test.py    # end-to-end loop test with fakes (no network)
└── harvester/
    ├── config.py          # Settings (limits, delays, filters)
    ├── query.py           # SearchQuery + endless query-string generator
    ├── locations.py       # country -> regions (for country-wide sweeps)
    ├── search.py          # search backends (DuckDuckGo / Serper / SerpAPI)
    ├── crawler.py         # per-site robots-aware crawler
    ├── extractor.py       # email extraction + de-obfuscation + filtering
    ├── storage.py         # CSV output + cross-run de-duplication
    └── runner.py          # orchestration loop + graceful shutdown
```

Run the tests:

```bash
python selftest.py
python integration_test.py
```
