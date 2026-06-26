"""Search backends. Each takes a query string and yields result URLs.

* ``DuckDuckGoBackend`` - free, no API key. Uses the maintained ``ddgs``
  package (falls back to the older ``duckduckgo_search`` if that's what's
  installed). DuckDuckGo rate-limits aggressively, so keep the delays in
  ``Settings`` reasonable.
* ``SerperBackend`` / ``SerpApiBackend`` - paid Google-results APIs. More
  reliable at volume. Require an API key.

Pick a backend with ``get_backend(settings)``.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Iterator

import requests

from .config import Settings


class SearchBackend(ABC):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @abstractmethod
    def search(self, query: str) -> Iterator[str]:
        """Yield result URLs for a single query."""
        raise NotImplementedError


class DuckDuckGoBackend(SearchBackend):
    name = "duckduckgo"

    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        self._DDGS = _import_ddgs()

    def search(self, query: str) -> Iterator[str]:
        try:
            with self._DDGS() as ddgs:
                results = ddgs.text(
                    query,
                    region=self.settings.search_region,
                    safesearch="moderate",
                    max_results=self.settings.results_per_query,
                )
        except Exception as exc:  # network hiccup, rate limit, parse change...
            print(f"   [search] DuckDuckGo error for {query!r}: {exc}")
            # Brief backoff so we don't spin on a rate limit.
            time.sleep(5)
            return
        for row in results or []:
            url = row.get("href") or row.get("url")
            if url:
                yield url


class _ApiBackend(SearchBackend):
    """Shared HTTP plumbing for JSON search APIs."""

    endpoint: str = ""

    def _post(self, payload: dict, headers: dict) -> dict | None:
        try:
            resp = requests.post(
                self.endpoint, json=payload, headers=headers,
                timeout=self.settings.request_timeout,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            print(f"   [search] {self.name} error: {exc}")
            return None

    def _get(self, params: dict) -> dict | None:
        try:
            resp = requests.get(
                self.endpoint, params=params,
                timeout=self.settings.request_timeout,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            print(f"   [search] {self.name} error: {exc}")
            return None


class SerperBackend(_ApiBackend):
    """serper.dev - Google search results as JSON."""

    name = "serper"
    endpoint = "https://google.serper.dev/search"

    def search(self, query: str) -> Iterator[str]:
        data = self._post(
            {"q": query, "num": self.settings.results_per_query},
            {"X-API-KEY": self.settings.api_key or "", "Content-Type": "application/json"},
        )
        for item in (data or {}).get("organic", []):
            link = item.get("link")
            if link:
                yield link


class SerpApiBackend(_ApiBackend):
    """serpapi.com - Google search results as JSON."""

    name = "serpapi"
    endpoint = "https://serpapi.com/search.json"

    def search(self, query: str) -> Iterator[str]:
        data = self._get({
            "q": query,
            "engine": "google",
            "num": self.settings.results_per_query,
            "api_key": self.settings.api_key or "",
        })
        for item in (data or {}).get("organic_results", []):
            link = item.get("link")
            if link:
                yield link


_BACKENDS = {
    "duckduckgo": DuckDuckGoBackend,
    "ddg": DuckDuckGoBackend,
    "serper": SerperBackend,
    "serpapi": SerpApiBackend,
}


def get_backend(settings: Settings) -> SearchBackend:
    key = settings.backend.strip().lower()
    if key not in _BACKENDS:
        raise ValueError(
            f"unknown backend {settings.backend!r}; "
            f"choose one of: {', '.join(sorted(set(_BACKENDS)))}"
        )
    return _BACKENDS[key](settings)


def _import_ddgs():
    """Import the DDGS class, preferring the maintained ``ddgs`` package."""
    try:
        from ddgs import DDGS  # maintained package
        return DDGS
    except ImportError:
        pass
    try:
        from duckduckgo_search import DDGS  # legacy name (frozen)
        return DDGS
    except ImportError as exc:
        raise ImportError(
            "No DuckDuckGo client found. Install it with: pip install ddgs"
        ) from exc
