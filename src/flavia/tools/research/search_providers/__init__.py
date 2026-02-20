"""Search provider registry."""

from typing import Optional

from .base import BaseSearchProvider, SearchResponse, SearchResult
from .brave import BraveSearchProvider
from .bing import BingSearchProvider
from .duckduckgo import DuckDuckGoSearchProvider
from .google import GoogleSearchProvider

PROVIDERS: dict[str, type[BaseSearchProvider]] = {
    "duckduckgo": DuckDuckGoSearchProvider,
    "google": GoogleSearchProvider,
    "brave": BraveSearchProvider,
    "bing": BingSearchProvider,
}


def get_provider(name: str) -> Optional[BaseSearchProvider]:
    """Get a search provider instance by name.

    Args:
        name: Provider name (duckduckgo, google, brave, bing).

    Returns:
        Provider instance, or None if name is unknown.
    """
    cls = PROVIDERS.get(name)
    if cls is None:
        return None
    return cls()


__all__ = [
    "BaseSearchProvider",
    "SearchResult",
    "SearchResponse",
    "PROVIDERS",
    "get_provider",
]
