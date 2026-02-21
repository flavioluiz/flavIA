"""Brave Search provider."""

import logging
from typing import Optional

import httpx

from .base import BaseSearchProvider, SearchResponse, SearchResult, error_excerpt, query_preview

logger = logging.getLogger(__name__)

API_URL = "https://api.search.brave.com/res/v1/web/search"

# Map time_range to Brave freshness values
TIME_RANGE_MAP = {
    "day": "pd",
    "week": "pw",
    "month": "pm",
    "year": "py",
}


class BraveSearchProvider(BaseSearchProvider):
    """Search provider using Brave Search API."""

    name = "brave"

    def _get_api_key(self) -> str:
        """Get API key from settings."""
        try:
            from flavia.config import get_settings

            return get_settings().brave_search_api_key
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
        """Search using Brave Search API."""
        q_preview = query_preview(query)
        logger.debug(
            "Brave search request query=%r num_results=%s region=%s time_range=%s",
            q_preview,
            num_results,
            region,
            time_range,
        )
        api_key = self._get_api_key()
        if not api_key:
            logger.info("Brave search skipped: BRAVE_SEARCH_API_KEY is not configured")
            return SearchResponse(
                query=query,
                provider=self.name,
                error_message=(
                    "Brave search is not configured. Set BRAVE_SEARCH_API_KEY."
                ),
                results=[
                    SearchResult(
                        title="Configuration Error",
                        url="",
                        snippet=(
                            "Brave Search requires BRAVE_SEARCH_API_KEY to be configured."
                        ),
                        position=1,
                    )
                ],
            )

        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": api_key,
        }
        params: dict = {
            "q": query,
            "count": min(num_results, 20),
        }
        if region:
            params["country"] = region
        if time_range and time_range in TIME_RANGE_MAP:
            params["freshness"] = TIME_RANGE_MAP[time_range]

        try:
            resp = httpx.get(API_URL, headers=headers, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code if e.response is not None else "unknown"
            body_excerpt = error_excerpt(e.response.text if e.response is not None else "")
            logger.warning(
                "Brave search HTTP error status=%s query=%r region=%s time_range=%s body=%r",
                status_code,
                q_preview,
                region,
                time_range,
                body_excerpt,
            )
            return SearchResponse(
                query=query,
                provider=self.name,
                error_message=f"Brave search failed (HTTP {status_code}).",
                results=[
                    SearchResult(
                        title="Search Error",
                        url="",
                        snippet=f"Brave search failed (HTTP {status_code}).",
                        position=1,
                    )
                ],
            )
        except httpx.RequestError as e:
            logger.warning(
                "Brave search network error type=%s query=%r region=%s time_range=%s detail=%r",
                type(e).__name__,
                q_preview,
                region,
                time_range,
                error_excerpt(e),
            )
            return SearchResponse(
                query=query,
                provider=self.name,
                error_message="Brave search failed due to a network error.",
                results=[
                    SearchResult(
                        title="Search Error",
                        url="",
                        snippet="Brave search failed due to a network error.",
                        position=1,
                    )
                ],
            )
        except Exception as e:
            logger.warning(
                "Brave search unexpected error type=%s query=%r detail=%r",
                type(e).__name__,
                q_preview,
                error_excerpt(e),
            )
            return SearchResponse(
                query=query,
                provider=self.name,
                error_message="Brave search failed due to an unexpected error.",
                results=[
                    SearchResult(
                        title="Search Error",
                        url="",
                        snippet="Brave search failed due to an unexpected error.",
                        position=1,
                    )
                ],
            )

        results = []
        web_results = data.get("web", {}).get("results", [])
        for i, item in enumerate(web_results, start=1):
            results.append(
                SearchResult(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    snippet=item.get("description", ""),
                    position=i,
                )
            )

        logger.debug("Brave search success query=%r results=%d", q_preview, len(results))
        return SearchResponse(
            query=query,
            results=results,
            provider=self.name,
            total_results=len(results),
        )
