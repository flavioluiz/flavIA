"""DuckDuckGo search provider using duckduckgo-search library."""

import logging
from typing import Optional

from .base import BaseSearchProvider, SearchResponse, SearchResult

logger = logging.getLogger(__name__)

# Map time_range to DDGS timelimit values
TIME_RANGE_MAP = {
    "day": "d",
    "week": "w",
    "month": "m",
    "year": "y",
}

# Map common region codes to DDGS format
REGION_MAP = {
    "br": "br-pt",
    "us": "us-en",
    "uk": "uk-en",
    "gb": "uk-en",
    "de": "de-de",
    "fr": "fr-fr",
    "es": "es-es",
    "it": "it-it",
    "jp": "jp-jp",
    "pt": "pt-pt",
}


class DuckDuckGoSearchProvider(BaseSearchProvider):
    """Search provider using DuckDuckGo via duckduckgo-search library."""

    name = "duckduckgo"

    def is_configured(self) -> bool:
        """Check if duckduckgo-search library is available."""
        try:
            import duckduckgo_search  # noqa: F401

            return True
        except ImportError:
            return False

    def search(
        self,
        query: str,
        num_results: int = 10,
        region: Optional[str] = None,
        time_range: Optional[str] = None,
    ) -> SearchResponse:
        """Search using DuckDuckGo."""
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            return SearchResponse(
                query=query,
                provider=self.name,
                error_message=(
                    "duckduckgo-search is not installed in the current Python environment. "
                    "Install with: pip install -e '.[research]' (project repo) "
                    "or pip install 'duckduckgo-search>=6.0'"
                ),
                results=[
                    SearchResult(
                        title="Error",
                        url="",
                        snippet=(
                            "duckduckgo-search is not installed in the current Python "
                            "environment."
                        ),
                        position=1,
                    )
                ],
            )

        timelimit = TIME_RANGE_MAP.get(time_range) if time_range else None
        ddgs_region = REGION_MAP.get(region, region) if region else None

        try:
            with DDGS() as ddgs:
                raw_results = list(
                    ddgs.text(
                        query,
                        max_results=num_results,
                        region=ddgs_region or "wt-wt",
                        timelimit=timelimit,
                    )
                )
        except Exception as e:
            err_text = str(e).strip()
            lowered = err_text.lower()
            if "ratelimit" in lowered or "rate limit" in lowered:
                logger.warning("DuckDuckGo search rate limited")
                return SearchResponse(
                    query=query,
                    provider=self.name,
                    error_message=(
                        "DuckDuckGo search is temporarily rate limited. "
                        "Try again in a few minutes or use another provider."
                    ),
                    results=[
                        SearchResult(
                            title="Search Error",
                            url="",
                            snippet=(
                                "DuckDuckGo search is temporarily rate limited. "
                                "Try again in a few minutes."
                            ),
                            position=1,
                        )
                    ],
                )

            logger.warning("DuckDuckGo search failed (%s)", type(e).__name__)
            return SearchResponse(
                query=query,
                provider=self.name,
                error_message="DuckDuckGo search failed due to an unexpected error.",
                results=[
                    SearchResult(
                        title="Search Error",
                        url="",
                        snippet="DuckDuckGo search failed due to an unexpected error.",
                        position=1,
                    )
                ],
            )

        results = []
        for i, r in enumerate(raw_results, start=1):
            results.append(
                SearchResult(
                    title=r.get("title", ""),
                    url=r.get("href", r.get("link", "")),
                    snippet=r.get("body", r.get("snippet", "")),
                    position=i,
                )
            )

        return SearchResponse(
            query=query,
            results=results,
            provider=self.name,
            total_results=len(results),
        )
