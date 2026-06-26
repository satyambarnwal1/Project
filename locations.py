"""Minimal country -> regions lookup.

Used to broaden coverage when the user gives only a country. This is not meant
to be exhaustive geography; it just gives the query generator a set of regional
terms to sweep so a country-wide run finds companies across the whole country
instead of only the few the search engine surfaces for the bare country name.

Add your own countries/regions freely.
"""

from __future__ import annotations

_US_STATES = [
    "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado",
    "Connecticut", "Delaware", "Florida", "Georgia", "Hawaii", "Idaho",
    "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky", "Louisiana", "Maine",
    "Maryland", "Massachusetts", "Michigan", "Minnesota", "Mississippi",
    "Missouri", "Montana", "Nebraska", "Nevada", "New Hampshire", "New Jersey",
    "New Mexico", "New York", "North Carolina", "North Dakota", "Ohio",
    "Oklahoma", "Oregon", "Pennsylvania", "Rhode Island", "South Carolina",
    "South Dakota", "Tennessee", "Texas", "Utah", "Vermont", "Virginia",
    "Washington", "West Virginia", "Wisconsin", "Wyoming",
]

_INDIA_STATES = [
    "Andhra Pradesh", "Assam", "Bihar", "Chhattisgarh", "Delhi", "Goa",
    "Gujarat", "Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka",
    "Kerala", "Madhya Pradesh", "Maharashtra", "Odisha", "Punjab",
    "Rajasthan", "Tamil Nadu", "Telangana", "Uttar Pradesh", "Uttarakhand",
    "West Bengal",
]

_UK_REGIONS = [
    "London", "South East England", "South West England", "East of England",
    "West Midlands", "East Midlands", "Yorkshire", "North West England",
    "North East England", "Scotland", "Wales", "Northern Ireland",
]

_CANADA_REGIONS = [
    "Ontario", "Quebec", "British Columbia", "Alberta", "Manitoba",
    "Saskatchewan", "Nova Scotia", "New Brunswick", "Newfoundland and Labrador",
    "Prince Edward Island",
]

_AUSTRALIA_REGIONS = [
    "New South Wales", "Victoria", "Queensland", "Western Australia",
    "South Australia", "Tasmania", "Australian Capital Territory",
    "Northern Territory",
]

# Keys are matched case-insensitively against a few common spellings.
_COUNTRY_REGIONS: dict[str, list[str]] = {}
for _aliases, _regions in [
    (("usa", "us", "united states", "united states of america", "u.s.", "u.s.a."), _US_STATES),
    (("india", "in", "bharat"), _INDIA_STATES),
    (("uk", "united kingdom", "great britain", "england", "britain"), _UK_REGIONS),
    (("canada", "ca"), _CANADA_REGIONS),
    (("australia", "au"), _AUSTRALIA_REGIONS),
]:
    for _alias in _aliases:
        _COUNTRY_REGIONS[_alias] = _regions


def regions_for_country(country: str) -> list[str]:
    """Return a list of region names for the country, or [] if unknown."""
    if not country:
        return []
    return _COUNTRY_REGIONS.get(country.strip().lower(), [])
