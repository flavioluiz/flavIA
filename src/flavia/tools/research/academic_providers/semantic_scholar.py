"""Semantic Scholar academic search provider."""

import logging
from typing import Optional

import httpx

from .base import (
    AcademicSearchResponse,
    BaseAcademicProvider,
    CitationResponse,
    PaperDetail,
    PaperDetailResponse,
    PaperResult,
    error_excerpt,
    query_preview,
)

logger = logging.getLogger(__name__)

GRAPH_API = "https://api.semanticscholar.org/graph/v1"
RECOMMENDATIONS_API = "https://api.semanticscholar.org/recommendations/v1"

PAPER_FIELDS = (
    "title,authors,year,venue,externalIds,abstract,"
    "citationCount,isOpenAccess,openAccessPdf"
)

DETAIL_FIELDS = (
    "title,authors,year,venue,externalIds,abstract,"
    "citationCount,isOpenAccess,openAccessPdf,"
    "referenceCount,tldr,fieldsOfStudy,references,citations"
)

SORT_MAP = {
    "citations": "citationCount:desc",
    "date": "publicationDate:desc",
}


def _extract_paper(item: dict, position: int) -> PaperResult:
    """Extract a PaperResult from a Semantic Scholar paper object."""
    # Handle citation/reference wrapper: {citingPaper: {...}} or {citedPaper: {...}}
    if "citingPaper" in item:
        item = item["citingPaper"]
    elif "citedPaper" in item:
        item = item["citedPaper"]

    authors = []
    for author in item.get("authors", []):
        name = author.get("name", "")
        if name:
            authors.append(name)

    ext_ids = item.get("externalIds") or {}
    external_ids: dict[str, str] = {}
    if ext_ids.get("DOI"):
        external_ids["doi"] = ext_ids["DOI"]
    if ext_ids.get("ArXiv"):
        external_ids["arxiv"] = ext_ids["ArXiv"]
    if ext_ids.get("CorpusId"):
        external_ids["s2"] = str(ext_ids["CorpusId"])
    s2_id = item.get("paperId", "")
    if s2_id:
        external_ids["s2_id"] = s2_id

    oa_pdf = item.get("openAccessPdf") or {}
    oa_url = oa_pdf.get("url", "")

    return PaperResult(
        title=item.get("title") or "",
        authors=authors,
        year=item.get("year"),
        venue=item.get("venue") or "",
        doi=ext_ids.get("DOI"),
        abstract=item.get("abstract") or "",
        citation_count=item.get("citationCount"),
        open_access=item.get("isOpenAccess", False),
        open_access_url=oa_url if oa_url else None,
        external_ids=external_ids,
        position=position,
    )


class SemanticScholarProvider(BaseAcademicProvider):
    """Academic search provider using Semantic Scholar API."""

    name = "semantic_scholar"

    def _get_api_key(self) -> str:
        """Get optional API key for higher rate limits."""
        try:
            from flavia.config import get_settings

            return get_settings().semantic_scholar_api_key
        except Exception:
            return ""

    def _build_headers(self) -> dict[str, str]:
        """Build request headers with optional API key."""
        headers = {"Accept": "application/json", "User-Agent": "flavIA/1.0"}
        api_key = self._get_api_key()
        if api_key:
            headers["x-api-key"] = api_key
        return headers

    def is_configured(self) -> bool:
        """Semantic Scholar is always available (API key optional)."""
        return True

    def search(
        self,
        query: str,
        num_results: int = 10,
        year_range: Optional[tuple[int, int]] = None,
        fields: Optional[str] = None,
        sort_by: str = "relevance",
    ) -> AcademicSearchResponse:
        """Search Semantic Scholar for papers."""
        q_preview = query_preview(query)
        logger.debug(
            "Semantic Scholar search request query=%r num_results=%s year_range=%s fields=%s sort=%s",
            q_preview,
            num_results,
            year_range,
            fields,
            sort_by,
        )

        params: dict[str, str] = {
            "query": query,
            "limit": str(min(num_results, 100)),
            "fields": PAPER_FIELDS,
        }

        if year_range:
            params["year"] = f"{year_range[0]}-{year_range[1]}"

        if fields:
            params["fieldsOfStudy"] = fields

        if sort_by in SORT_MAP:
            params["sort"] = SORT_MAP[sort_by]

        try:
            resp = httpx.get(
                f"{GRAPH_API}/paper/search",
                params=params,
                headers=self._build_headers(),
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as e:
            status_code = (
                e.response.status_code if e.response is not None else "unknown"
            )
            logger.warning(
                "Semantic Scholar search HTTP error status=%s query=%r",
                status_code,
                q_preview,
            )
            return AcademicSearchResponse(
                query=query,
                provider=self.name,
                error_message=f"Semantic Scholar search failed (HTTP {status_code}).",
            )
        except httpx.RequestError as e:
            logger.warning(
                "Semantic Scholar search network error type=%s query=%r detail=%r",
                type(e).__name__,
                q_preview,
                error_excerpt(e),
            )
            return AcademicSearchResponse(
                query=query,
                provider=self.name,
                error_message="Semantic Scholar search failed due to a network error.",
            )
        except Exception as e:
            logger.warning(
                "Semantic Scholar search unexpected error type=%s query=%r detail=%r",
                type(e).__name__,
                q_preview,
                error_excerpt(e),
            )
            return AcademicSearchResponse(
                query=query,
                provider=self.name,
                error_message="Semantic Scholar search failed due to an unexpected error.",
            )

        results = []
        for i, item in enumerate(data.get("data", []), start=1):
            results.append(_extract_paper(item, position=i))

        total = data.get("total")

        return AcademicSearchResponse(
            query=query,
            results=results,
            provider=self.name,
            total_results=total,
        )

    def get_details(self, paper_id: str) -> PaperDetailResponse:
        """Get full metadata for a paper from Semantic Scholar."""
        logger.debug("Semantic Scholar get_details paper_id=%r", paper_id)

        resolved_id = self._resolve_paper_id(paper_id)

        params = {"fields": DETAIL_FIELDS}

        try:
            resp = httpx.get(
                f"{GRAPH_API}/paper/{resolved_id}",
                params=params,
                headers=self._build_headers(),
                timeout=15,
            )
            resp.raise_for_status()
            item = resp.json()
        except httpx.HTTPStatusError as e:
            status_code = (
                e.response.status_code if e.response is not None else "unknown"
            )
            logger.warning(
                "Semantic Scholar get_details HTTP error status=%s paper_id=%r",
                status_code,
                paper_id,
            )
            return PaperDetailResponse(
                provider=self.name,
                error_message=f"Semantic Scholar paper lookup failed (HTTP {status_code}).",
            )
        except httpx.RequestError as e:
            logger.warning(
                "Semantic Scholar get_details network error type=%s paper_id=%r detail=%r",
                type(e).__name__,
                paper_id,
                error_excerpt(e),
            )
            return PaperDetailResponse(
                provider=self.name,
                error_message="Semantic Scholar paper lookup failed due to a network error.",
            )
        except Exception as e:
            logger.warning(
                "Semantic Scholar get_details unexpected error type=%s paper_id=%r detail=%r",
                type(e).__name__,
                paper_id,
                error_excerpt(e),
            )
            return PaperDetailResponse(
                provider=self.name,
                error_message="Semantic Scholar paper lookup failed due to an unexpected error.",
            )

        paper = self._parse_paper_detail(item)
        return PaperDetailResponse(paper=paper, provider=self.name)

    def get_citations(
        self,
        paper_id: str,
        num_results: int = 10,
        sort_by: str = "relevance",
    ) -> CitationResponse:
        """Get papers that cite this paper."""
        logger.debug(
            "Semantic Scholar get_citations paper_id=%r num_results=%s",
            paper_id,
            num_results,
        )

        resolved_id = self._resolve_paper_id(paper_id)

        params: dict[str, str] = {
            "fields": PAPER_FIELDS,
            "limit": str(min(num_results, 100)),
        }

        try:
            resp = httpx.get(
                f"{GRAPH_API}/paper/{resolved_id}/citations",
                params=params,
                headers=self._build_headers(),
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPStatusError, httpx.RequestError, Exception) as e:
            logger.warning(
                "Semantic Scholar get_citations error type=%s paper_id=%r detail=%r",
                type(e).__name__,
                paper_id,
                error_excerpt(e),
            )
            return CitationResponse(
                paper_id=paper_id,
                provider=self.name,
                error_message="Semantic Scholar citation lookup failed.",
            )

        results = []
        for i, item in enumerate(data.get("data", []), start=1):
            results.append(_extract_paper(item, position=i))

        total = data.get("total")

        return CitationResponse(
            paper_id=paper_id,
            citations=results,
            provider=self.name,
            total_results=total,
        )

    def get_references(
        self,
        paper_id: str,
        num_results: int = 10,
    ) -> CitationResponse:
        """Get papers referenced by this paper."""
        logger.debug(
            "Semantic Scholar get_references paper_id=%r num_results=%s",
            paper_id,
            num_results,
        )

        resolved_id = self._resolve_paper_id(paper_id)

        params: dict[str, str] = {
            "fields": PAPER_FIELDS,
            "limit": str(min(num_results, 100)),
        }

        try:
            resp = httpx.get(
                f"{GRAPH_API}/paper/{resolved_id}/references",
                params=params,
                headers=self._build_headers(),
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPStatusError, httpx.RequestError, Exception) as e:
            logger.warning(
                "Semantic Scholar get_references error type=%s paper_id=%r detail=%r",
                type(e).__name__,
                paper_id,
                error_excerpt(e),
            )
            return CitationResponse(
                paper_id=paper_id,
                provider=self.name,
                error_message="Semantic Scholar reference lookup failed.",
            )

        results = []
        for i, item in enumerate(data.get("data", []), start=1):
            results.append(_extract_paper(item, position=i))

        total = data.get("total")

        return CitationResponse(
            paper_id=paper_id,
            citations=results,
            provider=self.name,
            total_results=total,
        )

    def find_similar(
        self,
        paper_id: str,
        num_results: int = 10,
    ) -> AcademicSearchResponse:
        """Find similar papers using Semantic Scholar recommendations API."""
        logger.debug(
            "Semantic Scholar find_similar paper_id=%r num_results=%s",
            paper_id,
            num_results,
        )

        resolved_id = self._resolve_paper_id(paper_id)

        params: dict[str, str] = {
            "fields": PAPER_FIELDS,
            "limit": str(min(num_results, 100)),
        }

        try:
            resp = httpx.get(
                f"{RECOMMENDATIONS_API}/papers/forpaper/{resolved_id}",
                params=params,
                headers=self._build_headers(),
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPStatusError, httpx.RequestError, Exception) as e:
            logger.warning(
                "Semantic Scholar find_similar error type=%s paper_id=%r detail=%r",
                type(e).__name__,
                paper_id,
                error_excerpt(e),
            )
            return AcademicSearchResponse(
                query=f"similar to {paper_id}",
                provider=self.name,
                error_message="Semantic Scholar similar papers lookup failed.",
            )

        results = []
        for i, item in enumerate(data.get("recommendedPapers", []), start=1):
            results.append(_extract_paper(item, position=i))

        return AcademicSearchResponse(
            query=f"similar to {paper_id}",
            results=results,
            provider=self.name,
        )

    # --- Helpers ---

    def _resolve_paper_id(self, paper_id: str) -> str:
        """Resolve a paper_id to a Semantic Scholar-compatible ID.

        Semantic Scholar accepts: S2 paper IDs, DOIs (with DOI: prefix),
        ArXiv IDs (with ARXIV: prefix), and more.
        """
        pid = paper_id.strip()
        # DOI
        if pid.startswith("10."):
            return f"DOI:{pid}"
        if pid.startswith("https://doi.org/"):
            return f"DOI:{pid.replace('https://doi.org/', '')}"
        # ArXiv
        if pid.startswith("arxiv:") or pid.startswith("ARXIV:"):
            return f"ARXIV:{pid.split(':', 1)[1]}"
        # OpenAlex ID — try to resolve via DOI
        if pid.startswith("W") or pid.startswith("https://openalex.org/"):
            return pid  # Will likely fail, but let S2 try
        # Already an S2 ID or other format
        return pid

    def _parse_paper_detail(self, item: dict) -> PaperDetail:
        """Parse a full Semantic Scholar paper object into PaperDetail."""
        authors = []
        for author in item.get("authors", []):
            name = author.get("name", "")
            if name:
                authors.append(name)

        ext_ids = item.get("externalIds") or {}
        external_ids: dict[str, str] = {}
        if ext_ids.get("DOI"):
            external_ids["doi"] = ext_ids["DOI"]
        if ext_ids.get("ArXiv"):
            external_ids["arxiv"] = ext_ids["ArXiv"]
        if ext_ids.get("CorpusId"):
            external_ids["s2"] = str(ext_ids["CorpusId"])
        s2_id = item.get("paperId", "")
        if s2_id:
            external_ids["s2_id"] = s2_id

        oa_pdf = item.get("openAccessPdf") or {}
        oa_url = oa_pdf.get("url", "")

        pdf_urls = []
        if oa_url:
            pdf_urls.append(oa_url)

        # TLDR
        tldr_obj = item.get("tldr") or {}
        tldr = tldr_obj.get("text", "")

        # Fields of study
        topics = item.get("fieldsOfStudy") or []

        return PaperDetail(
            title=item.get("title") or "",
            authors=authors,
            year=item.get("year"),
            venue=item.get("venue") or "",
            doi=ext_ids.get("DOI"),
            abstract=item.get("abstract") or "",
            citation_count=item.get("citationCount"),
            open_access=item.get("isOpenAccess", False),
            open_access_url=oa_url if oa_url else None,
            external_ids=external_ids,
            author_affiliations=[],  # S2 doesn't provide affiliations in basic fields
            references_count=item.get("referenceCount"),
            related_works=[],
            pdf_urls=pdf_urls,
            tldr=tldr if tldr else None,
            topics=topics,
        )
