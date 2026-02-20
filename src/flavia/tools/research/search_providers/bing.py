"""Bing Web Search provider."""

import logging
from typing import Optional

import httpx

from .base import BaseSearchProvider, SearchResponse, SearchResult

logger = logging.getLogger(__name__)

API_URL = "https://api.bing.microsoft.com/v7.0/search"

# Map time_range to Bing freshness values
TIME_RANGE_MAP = {
    "day": "Day",
    "week": "Week",
    "month": "Month",
}


class BingSearchProvider(BaseSearchProvider):
    """Search provider using Bing Web Search API."""

    name = "bing"

    def _get_api_key(self) -> str:
        """Get API key from settings."""
        try:
            from flavia.config import get_settings

            return get_settings().bing_search_api_key
        except Exception:
            return ""

    def is_configured(self) -> bool:
        """Check if API key is set."""
        return bool(self._get_api_key())

    def search(
        self,
        query: str,
        num_results: int = 10,
        region: Optional[str] = None,
        time_range: Optional[str] = None,
    ) -> SearchResponse:
        """Search using Bing Web Search API."""
        api_key = self._get_api_key()
        if not api_key:
            return SearchResponse(
                query=query,
                provider=self.name,
                error_message="Bing search is not configured. Set BING_SEARCH_API_KEY.",
                results=[
                    SearchResult(
                        title="Configuration Error",
                        url="",
                        snippet=(
                            "Bing Search requires BING_SEARCH_API_KEY to be configured."
                        ),
                        position=1,
                    )
                ],
            )

        headers = {
            "Ocp-Apim-Subscription-Key": api_key,
        }
        params: dict = {
            "q": query,
            "count": min(num_results, 50),
            "textDecorations": "false",
            "textFormat": "Raw",
        }
        if region:
            params["mkt"] = f"{region}-{region.upper()}" if len(region) == 2 else region
        if time_range and time_range in TIME_RANGE_MAP:
            params["freshness"] = TIME_RANGE_MAP[time_range]

        try:
            resp = httpx.get(API_URL, headers=headers, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code if e.response is not None else "unknown"
            logger.warning("Bing search failed with HTTP status %s", status_code)
            return SearchResponse(
                query=query,
                provider=self.name,
                error_message=f"Bing search failed (HTTP {status_code}).",
                results=[
                    SearchResult(
                        title="Search Error",
                        url="",
                        snippet=f"Bing search failed (HTTP {status_code}).",
                        position=1,
                    )
                ],
            )
        except httpx.RequestError:
            logger.warning("Bing search failed due to network error")
            return SearchResponse(
                query=query,
                provider=self.name,
                error_message="Bing search failed due to a network error.",
                results=[
                    SearchResult(
                        title="Search Error",
                        url="",
                        snippet="Bing search failed due to a network error.",
                        position=1,
                    )
                ],
            )
        except Exception as e:
            logger.warning("Bing search failed (%s)", type(e).__name__)
            return SearchResponse(
                query=query,
                provider=self.name,
                error_message="Bing search failed due to an unexpected error.",
                results=[
                    SearchResult(
                        title="Search Error",
                        url="",
                        snippet="Bing search failed due to an unexpected error.",
                        position=1,
                    )
                ],
            )

        results = []
        web_pages = data.get("webPages", {}).get("value", [])
        for i, item in enumerate(web_pages, start=1):
            results.append(
                SearchResult(
                    title=item.get("name", ""),
                    url=item.get("url", ""),
                    snippet=item.get("snippet", ""),
                    position=i,
                )
            )

        total = data.get("webPages", {}).get("totalEstimatedMatches")

        return SearchResponse(
            query=query,
            results=results,
            provider=self.name,
            total_results=total,
        )
