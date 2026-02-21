"""Academic search provider registry."""

from typing import Optional

from .base import (
    AcademicSearchResponse,
    BaseAcademicProvider,
    CitationResponse,
    PaperDetail,
    PaperDetailResponse,
    PaperResult,
)
from .openalex import OpenAlexProvider
from .semantic_scholar import SemanticScholarProvider

ACADEMIC_PROVIDERS: dict[str, type[BaseAcademicProvider]] = {
    "openalex": OpenAlexProvider,
    "semantic_scholar": SemanticScholarProvider,
}


def get_academic_provider(name: str) -> Optional[BaseAcademicProvider]:
    """Get an academic search provider instance by name.

    Args:
        name: Provider name (openalex, semantic_scholar).

    Returns:
        Provider instance, or None if name is unknown.
    """
    cls = ACADEMIC_PROVIDERS.get(name)
    if cls is None:
        return None
    return cls()


__all__ = [
    "AcademicSearchResponse",
    "BaseAcademicProvider",
    "CitationResponse",
    "PaperDetail",
    "PaperDetailResponse",
    "PaperResult",
    "ACADEMIC_PROVIDERS",
    "get_academic_provider",
]
