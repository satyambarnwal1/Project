"""Turn the structured request into a stream of search-engine queries.

The user supplies: industry + country (required), and optionally state,
district, and zip code. From that we generate concrete query strings.

Because the run is meant to continue "until someone stops it", the generator
yields an effectively endless stream of *distinct* queries by combining:
  * the location the user gave (if any), OR
  * each region of the country (when only the country is known), and
  * a rotating set of intent modifiers ("contact email", "directory", ...).

This keeps surfacing new companies instead of re-requesting the same page.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Iterator

from .locations import regions_for_country


@dataclass
class SearchQuery:
    industry: str
    country: str
    state: str | None = None
    district: str | None = None
    zip_code: str | None = None

    def __post_init__(self) -> None:
        # Normalise whitespace; treat empty strings as "not provided".
        self.industry = (self.industry or "").strip()
        self.country = (self.country or "").strip()
        self.state = _clean_optional(self.state)
        self.district = _clean_optional(self.district)
        self.zip_code = _clean_optional(self.zip_code)
        if not self.industry:
            raise ValueError("industry is required")
        if not self.country:
            raise ValueError("country is required")

    def base_location(self) -> str | None:
        """The most specific location the user explicitly provided, if any."""
        parts = [p for p in (self.zip_code, self.district, self.state) if p]
        return ", ".join(parts) if parts else None

    def describe(self) -> str:
        loc = self.base_location() or self.country
        return f"{self.industry} companies in {loc}"


# Intent modifiers appended to each "{industry} companies {location}" phrase.
# They steer the search engine toward pages that tend to list contact emails.
_MODIFIERS = [
    "contact email",
    "email address",
    '"@" contact us',
    "directory",
    "association members",
    "get in touch",
    "about us",
    "headquarters office",
    "top companies list",
    "agencies",
]


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value or value.lower() in {"null", "none", "na", "n/a", "-"}:
        return None
    return value


def generate_queries(query: SearchQuery) -> Iterator[str]:
    """Yield distinct search strings forever (caller decides when to stop).

    Strategy:
      1. If the user gave a location, iterate modifiers over that location.
      2. Otherwise iterate over every (region x modifier) pair for the country,
         then fall back to country-level queries. After exhausting the planned
         combinations we keep going by pairing regions with generic page-type
         hints so the stream never runs dry.
    """
    seen: set[str] = set()

    def emit(industry: str, location: str, modifier: str) -> Iterator[str]:
        q = f"{industry} companies {location} {modifier}".strip()
        q = " ".join(q.split())
        if q not in seen:
            seen.add(q)
            yield q

    fixed_location = query.base_location()

    if fixed_location:
        # User pinned a location: just rotate modifiers (and then loop with an
        # appended page number to coax more results out of the engine).
        for modifier in _MODIFIERS:
            yield from emit(query.industry, fixed_location, modifier)
        for n in itertools.count(2):
            for modifier in _MODIFIERS:
                yield from emit(
                    query.industry, fixed_location, f"{modifier} page {n}"
                )
        return

    # Only the country is known -> sweep its regions.
    regions = regions_for_country(query.country)
    locations = [f"{r}, {query.country}" for r in regions] if regions else []
    locations.append(query.country)  # always include the bare country too

    for location, modifier in itertools.product(locations, _MODIFIERS):
        yield from emit(query.industry, location, modifier)

    # Keep the stream alive: pair regions with page hints indefinitely.
    for n in itertools.count(2):
        for location in locations:
            yield from emit(query.industry, location, f"directory page {n}")
