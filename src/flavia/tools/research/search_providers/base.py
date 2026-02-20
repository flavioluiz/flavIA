"""Base classes for search providers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SearchResult:
    """A single search result."""

    title: str
    url: str
    snippet: str
    position: int


@dataclass
class SearchResponse:
    """Response from a search provider."""

    query: str
    results: list[SearchResult] = field(default_factory=list)
    provider: str = ""
    total_results: Optional[int] = None


class BaseSearchProvider(ABC):
    """Abstract base class for search providers."""

    name: str = ""

    @abstractmethod
    def search(
        self,
        query: str,
        num_results: int = 10,
        region: Optional[str] = None,
        time_range: Optional[str] = None,
    ) -> SearchResponse:
        """Execute a search query.

        Args:
            query: The search query string.
            num_results: Maximum number of results to return.
            region: Optional region/locale code (e.g., "us", "br").
            time_range: Optional time filter: "day", "week", "month", "year".

        Returns:
            SearchResponse with results.
        """
        pass

    @abstractmethod
    def is_configured(self) -> bool:
        """Check if this provider is properly configured and ready to use."""
        pass
