"""Google Custom Search provider."""

import logging
from typing import Optional

import httpx

from .base import BaseSearchProvider, SearchResponse, SearchResult, error_excerpt, query_preview

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
        q_preview = query_preview(query)
        logger.debug(
            "Google search request query=%r num_results=%s region=%s time_range=%s",
            q_preview,
            num_results,
            region,
            time_range,
        )
        api_key, cx = self._get_credentials()
        if not api_key or not cx:
            logger.info(
                "Google search skipped: missing credentials api_key_present=%s cx_present=%s",
                bool(api_key),
                bool(cx),
            )
            return SearchResponse(
                query=query,
                provider=self.name,
                error_message=(
                    "Google search is not configured. Set GOOGLE_SEARCH_API_KEY and "
                    "GOOGLE_SEARCH_CX."
                ),
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
        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code if e.response is not None else "unknown"
            body_excerpt = error_excerpt(e.response.text if e.response is not None else "")
            logger.warning(
                "Google search HTTP error status=%s query=%r region=%s time_range=%s body=%r",
                status_code,
                q_preview,
                region,
                time_range,
                body_excerpt,
            )
            return SearchResponse(
                query=query,
                provider=self.name,
                error_message=f"Google search failed (HTTP {status_code}).",
                results=[
                    SearchResult(
                        title="Search Error",
                        url="",
                        snippet=f"Google search failed (HTTP {status_code}).",
                        position=1,
                    )
                ],
            )
        except httpx.RequestError as e:
            logger.warning(
                "Google search network error type=%s query=%r region=%s time_range=%s detail=%r",
                type(e).__name__,
                q_preview,
                region,
                time_range,
                error_excerpt(e),
            )
            return SearchResponse(
                query=query,
                provider=self.name,
                error_message="Google search failed due to a network error.",
                results=[
                    SearchResult(
                        title="Search Error",
                        url="",
                        snippet="Google search failed due to a network error.",
                        position=1,
                    )
                ],
            )
        except Exception as e:
            logger.warning(
                "Google search unexpected error type=%s query=%r detail=%r",
                type(e).__name__,
                q_preview,
                error_excerpt(e),
            )
            return SearchResponse(
                query=query,
                provider=self.name,
                error_message="Google search failed due to an unexpected error.",
                results=[
                    SearchResult(
                        title="Search Error",
                        url="",
                        snippet="Google search failed due to an unexpected error.",
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

        logger.debug(
            "Google search success query=%r results=%d total=%s",
            q_preview,
            len(results),
            total,
        )
        return SearchResponse(
            query=query,
            results=results,
            provider=self.name,
            total_results=total,
        )
