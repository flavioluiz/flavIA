"""Base classes for academic search providers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PaperResult:
    """A single paper search result."""

    title: str
    authors: list[str]  # ["Vaswani, A.", "Shazeer, N.", ...]
    year: Optional[int]
    venue: str  # Journal/conference name
    doi: Optional[str]
    abstract: str  # snippet or full abstract
    citation_count: Optional[int]
    open_access: bool
    open_access_url: Optional[str]
    external_ids: dict[str, str] = field(
        default_factory=dict
    )  # {"openalex": "W123", "s2": "abc", "arxiv": "1706.03762"}
    position: int = 0


@dataclass
class PaperDetail:
    """Full paper metadata."""

    title: str
    authors: list[str]
    year: Optional[int]
    venue: str
    doi: Optional[str]
    abstract: str
    citation_count: Optional[int]
    open_access: bool
    open_access_url: Optional[str]
    external_ids: dict[str, str] = field(default_factory=dict)
    author_affiliations: list[str] = field(
        default_factory=list
    )  # parallel to authors list
    references_count: Optional[int] = None
    related_works: list[str] = field(default_factory=list)  # IDs of related papers
    pdf_urls: list[str] = field(default_factory=list)
    tldr: Optional[str] = None  # Semantic Scholar TLDR
    topics: list[str] = field(default_factory=list)  # concepts/topics/fields


@dataclass
class AcademicSearchResponse:
    """Response from an academic search."""

    query: str
    results: list[PaperResult] = field(default_factory=list)
    provider: str = ""
    total_results: Optional[int] = None
    error_message: Optional[str] = None


@dataclass
class PaperDetailResponse:
    """Response for a paper detail request."""

    paper: Optional[PaperDetail] = None
    provider: str = ""
    error_message: Optional[str] = None


@dataclass
class CitationResponse:
    """Response for citations/references request."""

    paper_id: str = ""
    citations: list[PaperResult] = field(default_factory=list)
    provider: str = ""
    total_results: Optional[int] = None
    error_message: Optional[str] = None


class BaseAcademicProvider(ABC):
    """Abstract base class for academic search providers."""

    name: str = ""

    @abstractmethod
    def search(
        self,
        query: str,
        num_results: int = 10,
        year_range: Optional[tuple[int, int]] = None,
        fields: Optional[str] = None,
        sort_by: str = "relevance",
    ) -> AcademicSearchResponse:
        """Search for academic papers."""

    @abstractmethod
    def get_details(self, paper_id: str) -> PaperDetailResponse:
        """Get full metadata for a specific paper."""

    @abstractmethod
    def get_citations(
        self,
        paper_id: str,
        num_results: int = 10,
        sort_by: str = "relevance",
    ) -> CitationResponse:
        """Get papers that cite the given paper."""

    @abstractmethod
    def get_references(
        self,
        paper_id: str,
        num_results: int = 10,
    ) -> CitationResponse:
        """Get papers referenced by the given paper."""

    @abstractmethod
    def find_similar(
        self,
        paper_id: str,
        num_results: int = 10,
    ) -> AcademicSearchResponse:
        """Find papers similar to the given paper."""

    @abstractmethod
    def is_configured(self) -> bool:
        """Check if this provider is properly configured and ready to use."""


def query_preview(query: str, max_len: int = 80) -> str:
    """Return a compact query preview safe for logs."""
    normalized = (query or "").strip().replace("\n", " ")
    if len(normalized) <= max_len:
        return normalized
    return normalized[: max_len - 3] + "..."


def error_excerpt(value: object, max_len: int = 220) -> str:
    """Return a compact one-line excerpt from an error/detail value."""
    if value is None:
        return ""
    text = str(value).strip().replace("\n", " ")
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."
