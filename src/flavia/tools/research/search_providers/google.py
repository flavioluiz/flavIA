"""Google Custom Search provider."""

import logging
from typing import Optional

import httpx

from .base import BaseSearchProvider, SearchResponse, SearchResult

logger = logging.getLogger(__name__)

# Map time_range to Google dateRestrict values
TIME_RANGE_MAP = {
    "day": "d1",
    "week": "w1",
    "month": "m1",
    "year": "y1",
}

API_URL = "https://www.googleapis.com/customsearch/v1"


class GoogleSearchProvider(BaseSearchProvider):
    """Search provider using Google Custom Search JSON API."""

    name = "google"

    def _get_credentials(self) -> tuple[str, str]:
        """Get API key and CX from settings."""
        try:
            from flavia.config import get_settings

            s = get_settings()
            return s.google_search_api_key, s.google_search_cx
        except Exception:
            return "", ""

    def is_configured(self) -> bool:
        """Check if API key and CX are set."""
        api_key, cx = self._get_credentials()
        return bool(api_key and cx)

    def search(
        self,
        query: str,
        num_results: int = 10,
        region: Optional[str] = None,
        time_range: Optional[str] = None,
    ) -> SearchResponse:
        """Search using Google Custom Search API."""
        api_key, cx = self._get_credentials()
        if not api_key or not cx:
            return SearchResponse(
                query=query,
                provider=self.name,
                results=[
                    SearchResult(
                        title="Configuration Error",
                        url="",
                        snippet=(
                            "Google Search requires GOOGLE_SEARCH_API_KEY and "
                            "GOOGLE_SEARCH_CX to be configured."
                        ),
                        position=1,
                    )
                ],
            )

        params: dict = {
            "key": api_key,
            "cx": cx,
            "q": query,
            "num": min(num_results, 10),  # Google API max is 10 per request
        }
        if region:
            params["gl"] = region
        if time_range and time_range in TIME_RANGE_MAP:
            params["dateRestrict"] = TIME_RANGE_MAP[time_range]

        try:
            resp = httpx.get(API_URL, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning("Google search failed: %s", e)
            return SearchResponse(
                query=query,
                provider=self.name,
                results=[
                    SearchResult(
                        title="Search Error",
                        url="",
                        snippet=f"Google search failed: {e}",
                        position=1,
                    )
                ],
            )

        results = []
        for i, item in enumerate(data.get("items", []), start=1):
            results.append(
                SearchResult(
                    title=item.get("title", ""),
                    url=item.get("link", ""),
                    snippet=item.get("snippet", ""),
                    position=i,
                )
            )

        total = None
        search_info = data.get("searchInformation", {})
        if "totalResults" in search_info:
            try:
                total = int(search_info["totalResults"])
            except (ValueError, TypeError):
                pass

        return SearchResponse(
            query=query,
            results=results,
            provider=self.name,
            total_results=total,
        )
