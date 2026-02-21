"""OpenAlex academic search provider."""

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

API_BASE = "https://api.openalex.org"

SORT_MAP = {
    "relevance": "relevance_score:desc",
    "date": "publication_date:desc",
    "citations": "cited_by_count:desc",
}


def _reconstruct_abstract(inverted_index: Optional[dict]) -> str:
    """Reconstruct abstract from OpenAlex inverted index format."""
    if not inverted_index:
        return ""
    word_positions: list[tuple[int, str]] = []
    for word, positions in inverted_index.items():
        for pos in positions:
            word_positions.append((pos, word))
    word_positions.sort(key=lambda x: x[0])
    return " ".join(w for _, w in word_positions)


def _extract_paper(item: dict, position: int) -> PaperResult:
    """Extract a PaperResult from an OpenAlex work object."""
    authors = []
    for authorship in item.get("authorships", []):
        author = authorship.get("author", {})
        name = author.get("display_name", "")
        if name:
            authors.append(name)

    venue = ""
    primary_location = item.get("primary_location") or {}
    source = primary_location.get("source") or {}
    venue = source.get("display_name", "")

    doi = item.get("doi", "")
    if doi and doi.startswith("https://doi.org/"):
        doi = doi[len("https://doi.org/"):]

    oa = item.get("open_access", {})
    oa_url = oa.get("oa_url", "")

    external_ids: dict[str, str] = {}
    openalex_id = item.get("id", "")
    if openalex_id:
        external_ids["openalex"] = openalex_id
    ids_block = item.get("ids", {})
    if ids_block.get("doi"):
        external_ids["doi"] = ids_block["doi"]
    if ids_block.get("openalex"):
        external_ids["openalex"] = ids_block["openalex"]

    abstract = _reconstruct_abstract(item.get("abstract_inverted_index"))

    return PaperResult(
        title=item.get("title") or item.get("display_name") or "",
        authors=authors,
        year=item.get("publication_year"),
        venue=venue,
        doi=doi if doi else None,
        abstract=abstract,
        citation_count=item.get("cited_by_count"),
        open_access=oa.get("is_oa", False),
        open_access_url=oa_url if oa_url else None,
        external_ids=external_ids,
        position=position,
    )


class OpenAlexProvider(BaseAcademicProvider):
    """Academic search provider using OpenAlex REST API."""

    name = "openalex"

    def _get_email(self) -> str:
        """Get email for polite pool from settings."""
        try:
            from flavia.config import get_settings

            return get_settings().openalex_email
        except Exception:
            return ""

    def _build_headers(self) -> dict[str, str]:
        """Build request headers."""
        return {"Accept": "application/json", "User-Agent": "flavIA/1.0"}

    def _build_params(self, **extra) -> dict[str, str]:
        """Build base query params with optional mailto."""
        params: dict[str, str] = {}
        email = self._get_email()
        if email:
            params["mailto"] = email
        params.update(extra)
        return params

    def is_configured(self) -> bool:
        """OpenAlex is always available (no key required)."""
        return True

    def search(
        self,
        query: str,
        num_results: int = 10,
        year_range: Optional[tuple[int, int]] = None,
        fields: Optional[str] = None,
        sort_by: str = "relevance",
    ) -> AcademicSearchResponse:
        """Search OpenAlex for papers."""
        q_preview = query_preview(query)
        logger.debug(
            "OpenAlex search request query=%r num_results=%s year_range=%s fields=%s sort=%s",
            q_preview,
            num_results,
            year_range,
            fields,
            sort_by,
        )

        params = self._build_params(
            search=query,
            per_page=str(min(num_results, 50)),
        )

        sort_value = SORT_MAP.get(sort_by, "relevance_score:desc")
        params["sort"] = sort_value

        filters: list[str] = []
        if year_range:
            filters.append(f"publication_year:{year_range[0]}-{year_range[1]}")
        if fields:
            filters.append(f"concepts.display_name.search:{fields}")
        if filters:
            params["filter"] = ",".join(filters)

        try:
            resp = httpx.get(
                f"{API_BASE}/works",
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
                "OpenAlex search HTTP error status=%s query=%r",
                status_code,
                q_preview,
            )
            return AcademicSearchResponse(
                query=query,
                provider=self.name,
                error_message=f"OpenAlex search failed (HTTP {status_code}).",
            )
        except httpx.RequestError as e:
            logger.warning(
                "OpenAlex search network error type=%s query=%r detail=%r",
                type(e).__name__,
                q_preview,
                error_excerpt(e),
            )
            return AcademicSearchResponse(
                query=query,
                provider=self.name,
                error_message="OpenAlex search failed due to a network error.",
            )
        except Exception as e:
            logger.warning(
                "OpenAlex search unexpected error type=%s query=%r detail=%r",
                type(e).__name__,
                q_preview,
                error_excerpt(e),
            )
            return AcademicSearchResponse(
                query=query,
                provider=self.name,
                error_message="OpenAlex search failed due to an unexpected error.",
            )

        results = []
        for i, item in enumerate(data.get("results", []), start=1):
            results.append(_extract_paper(item, position=i))

        total = data.get("meta", {}).get("count")

        return AcademicSearchResponse(
            query=query,
            results=results,
            provider=self.name,
            total_results=total,
        )

    def get_details(self, paper_id: str) -> PaperDetailResponse:
        """Get full metadata for a paper from OpenAlex."""
        logger.debug("OpenAlex get_details paper_id=%r", paper_id)

        # Determine URL path: DOI or OpenAlex ID
        url = self._resolve_paper_url(paper_id)

        params = self._build_params()

        try:
            resp = httpx.get(
                url, params=params, headers=self._build_headers(), timeout=15
            )
            resp.raise_for_status()
            item = resp.json()
        except httpx.HTTPStatusError as e:
            status_code = (
                e.response.status_code if e.response is not None else "unknown"
            )
            logger.warning(
                "OpenAlex get_details HTTP error status=%s paper_id=%r",
                status_code,
                paper_id,
            )
            return PaperDetailResponse(
                provider=self.name,
                error_message=f"OpenAlex paper lookup failed (HTTP {status_code}).",
            )
        except httpx.RequestError as e:
            logger.warning(
                "OpenAlex get_details network error type=%s paper_id=%r detail=%r",
                type(e).__name__,
                paper_id,
                error_excerpt(e),
            )
            return PaperDetailResponse(
                provider=self.name,
                error_message="OpenAlex paper lookup failed due to a network error.",
            )
        except Exception as e:
            logger.warning(
                "OpenAlex get_details unexpected error type=%s paper_id=%r detail=%r",
                type(e).__name__,
                paper_id,
                error_excerpt(e),
            )
            return PaperDetailResponse(
                provider=self.name,
                error_message="OpenAlex paper lookup failed due to an unexpected error.",
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
            "OpenAlex get_citations paper_id=%r num_results=%s", paper_id, num_results
        )

        openalex_id = self._resolve_openalex_id(paper_id)
        if not openalex_id:
            return CitationResponse(
                paper_id=paper_id,
                provider=self.name,
                error_message=f"Could not resolve OpenAlex ID for: {paper_id}",
            )

        params = self._build_params(
            filter=f"cites:{openalex_id}",
            per_page=str(min(num_results, 50)),
            sort=SORT_MAP.get(sort_by, "relevance_score:desc"),
        )

        try:
            resp = httpx.get(
                f"{API_BASE}/works",
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
                "OpenAlex get_citations HTTP error status=%s paper_id=%r",
                status_code,
                paper_id,
            )
            return CitationResponse(
                paper_id=paper_id,
                provider=self.name,
                error_message=f"OpenAlex citation lookup failed (HTTP {status_code}).",
            )
        except httpx.RequestError as e:
            logger.warning(
                "OpenAlex get_citations network error type=%s paper_id=%r detail=%r",
                type(e).__name__,
                paper_id,
                error_excerpt(e),
            )
            return CitationResponse(
                paper_id=paper_id,
                provider=self.name,
                error_message=(
                    "OpenAlex citation lookup failed due to a network error "
                    f"({type(e).__name__})."
                ),
            )
        except Exception as e:
            logger.warning(
                "OpenAlex get_citations unexpected error type=%s paper_id=%r detail=%r",
                type(e).__name__,
                paper_id,
                error_excerpt(e),
            )
            return CitationResponse(
                paper_id=paper_id,
                provider=self.name,
                error_message="OpenAlex citation lookup failed due to an unexpected error.",
            )

        results = []
        for i, item in enumerate(data.get("results", []), start=1):
            results.append(_extract_paper(item, position=i))

        total = data.get("meta", {}).get("count")

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
            "OpenAlex get_references paper_id=%r num_results=%s",
            paper_id,
            num_results,
        )

        openalex_id = self._resolve_openalex_id(paper_id)
        if not openalex_id:
            return CitationResponse(
                paper_id=paper_id,
                provider=self.name,
                error_message=f"Could not resolve OpenAlex ID for: {paper_id}",
            )

        params = self._build_params(
            filter=f"cited_by:{openalex_id}",
            per_page=str(min(num_results, 50)),
        )

        try:
            resp = httpx.get(
                f"{API_BASE}/works",
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
                "OpenAlex get_references HTTP error status=%s paper_id=%r",
                status_code,
                paper_id,
            )
            return CitationResponse(
                paper_id=paper_id,
                provider=self.name,
                error_message=f"OpenAlex reference lookup failed (HTTP {status_code}).",
            )
        except httpx.RequestError as e:
            logger.warning(
                "OpenAlex get_references network error type=%s paper_id=%r detail=%r",
                type(e).__name__,
                paper_id,
                error_excerpt(e),
            )
            return CitationResponse(
                paper_id=paper_id,
                provider=self.name,
                error_message=(
                    "OpenAlex reference lookup failed due to a network error "
                    f"({type(e).__name__})."
                ),
            )
        except Exception as e:
            logger.warning(
                "OpenAlex get_references unexpected error type=%s paper_id=%r detail=%r",
                type(e).__name__,
                paper_id,
                error_excerpt(e),
            )
            return CitationResponse(
                paper_id=paper_id,
                provider=self.name,
                error_message="OpenAlex reference lookup failed due to an unexpected error.",
            )

        results = []
        for i, item in enumerate(data.get("results", []), start=1):
            results.append(_extract_paper(item, position=i))

        total = data.get("meta", {}).get("count")

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
        """Find similar papers using OpenAlex related works."""
        logger.debug(
            "OpenAlex find_similar paper_id=%r num_results=%s", paper_id, num_results
        )

        openalex_id = self._resolve_openalex_id(paper_id)
        if not openalex_id:
            return AcademicSearchResponse(
                query=f"similar to {paper_id}",
                provider=self.name,
                error_message=f"Could not resolve OpenAlex ID for: {paper_id}",
            )

        params = self._build_params(
            filter=f"related_to:{openalex_id}",
            per_page=str(min(num_results, 50)),
            sort="relevance_score:desc",
        )

        try:
            resp = httpx.get(
                f"{API_BASE}/works",
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
                "OpenAlex find_similar HTTP error status=%s paper_id=%r",
                status_code,
                paper_id,
            )
            return AcademicSearchResponse(
                query=f"similar to {paper_id}",
                provider=self.name,
                error_message=f"OpenAlex similar papers lookup failed (HTTP {status_code}).",
            )
        except httpx.RequestError as e:
            logger.warning(
                "OpenAlex find_similar network error type=%s paper_id=%r detail=%r",
                type(e).__name__,
                paper_id,
                error_excerpt(e),
            )
            return AcademicSearchResponse(
                query=f"similar to {paper_id}",
                provider=self.name,
                error_message=(
                    "OpenAlex similar papers lookup failed due to a network error "
                    f"({type(e).__name__})."
                ),
            )
        except Exception as e:
            logger.warning(
                "OpenAlex find_similar unexpected error type=%s paper_id=%r detail=%r",
                type(e).__name__,
                paper_id,
                error_excerpt(e),
            )
            return AcademicSearchResponse(
                query=f"similar to {paper_id}",
                provider=self.name,
                error_message="OpenAlex similar papers lookup failed due to an unexpected error.",
            )

        results = []
        for i, item in enumerate(data.get("results", []), start=1):
            results.append(_extract_paper(item, position=i))

        total = data.get("meta", {}).get("count")

        return AcademicSearchResponse(
            query=f"similar to {paper_id}",
            results=results,
            provider=self.name,
            total_results=total,
        )

    # --- Helpers ---

    def _resolve_paper_url(self, paper_id: str) -> str:
        """Build the API URL for a paper ID (DOI, OpenAlex ID, or URL)."""
        pid = paper_id.strip()
        if pid.startswith("https://openalex.org/") or pid.startswith("W"):
            return f"{API_BASE}/works/{pid.split('/')[-1]}"
        if pid.startswith("10.") or pid.startswith("https://doi.org/"):
            doi = pid.replace("https://doi.org/", "")
            return f"{API_BASE}/works/doi:{doi}"
        # Fallback: try as-is
        return f"{API_BASE}/works/{pid}"

    def _resolve_openalex_id(self, paper_id: str) -> Optional[str]:
        """Resolve a paper_id to an OpenAlex work ID."""
        pid = paper_id.strip()
        # Already an OpenAlex ID
        if pid.startswith("W") and pid[1:].isdigit():
            return pid
        if pid.startswith("https://openalex.org/W"):
            return pid.split("/")[-1]

        # Need to look up by DOI or other ID
        detail = self.get_details(paper_id)
        if detail.paper and detail.paper.external_ids.get("openalex"):
            oa_id = detail.paper.external_ids["openalex"]
            # Extract just the ID part
            if "/" in oa_id:
                return oa_id.split("/")[-1]
            return oa_id
        return None

    def _parse_paper_detail(self, item: dict) -> PaperDetail:
        """Parse a full OpenAlex work object into PaperDetail."""
        authors = []
        affiliations = []
        for authorship in item.get("authorships", []):
            author = authorship.get("author", {})
            name = author.get("display_name", "")
            if name:
                authors.append(name)
            insts = authorship.get("institutions", [])
            aff = ", ".join(
                inst.get("display_name", "") for inst in insts if inst.get("display_name")
            )
            affiliations.append(aff)

        venue = ""
        primary_location = item.get("primary_location") or {}
        source = primary_location.get("source") or {}
        venue = source.get("display_name", "")

        doi = item.get("doi", "")
        if doi and doi.startswith("https://doi.org/"):
            doi = doi[len("https://doi.org/"):]

        oa = item.get("open_access", {})
        oa_url = oa.get("oa_url", "")

        external_ids: dict[str, str] = {}
        openalex_id = item.get("id", "")
        if openalex_id:
            external_ids["openalex"] = openalex_id
        ids_block = item.get("ids", {})
        if ids_block.get("doi"):
            external_ids["doi"] = ids_block["doi"]

        abstract = _reconstruct_abstract(item.get("abstract_inverted_index"))

        # References
        referenced_works = item.get("referenced_works", [])
        references_count = len(referenced_works) if referenced_works else item.get("referenced_works_count")

        # Related works
        related_works = item.get("related_works", [])

        # PDF URLs
        pdf_urls = []
        if oa_url:
            pdf_urls.append(oa_url)
        best_oa = primary_location.get("pdf_url")
        if best_oa and best_oa not in pdf_urls:
            pdf_urls.append(best_oa)

        # Topics/concepts
        topics = []
        for concept in item.get("concepts", []):
            name = concept.get("display_name", "")
            if name:
                topics.append(name)

        return PaperDetail(
            title=item.get("title") or item.get("display_name") or "",
            authors=authors,
            year=item.get("publication_year"),
            venue=venue,
            doi=doi if doi else None,
            abstract=abstract,
            citation_count=item.get("cited_by_count"),
            open_access=oa.get("is_oa", False),
            open_access_url=oa_url if oa_url else None,
            external_ids=external_ids,
            author_affiliations=affiliations,
            references_count=references_count,
            related_works=related_works[:10],  # Limit to first 10
            pdf_urls=pdf_urls,
            topics=topics[:10],  # Limit to first 10
        )
