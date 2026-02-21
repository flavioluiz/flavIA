"""Academic database search tools for flavIA.

Provides tools for searching academic databases (OpenAlex, Semantic Scholar)
with rich metadata: authors, DOIs, citation counts, abstracts, open access status.
"""

import logging
from typing import TYPE_CHECKING, Any, Optional

from ..base import BaseTool, ToolParameter, ToolSchema
from ..registry import register_tool
from .academic_providers import ACADEMIC_PROVIDERS, get_academic_provider

if TYPE_CHECKING:
    from flavia.agent.context import AgentContext

logger = logging.getLogger(__name__)

VALID_SORT_OPTIONS = ["relevance", "date", "citations"]


def _parse_year_range(value: Optional[str]) -> Optional[tuple[int, int]]:
    """Parse a year range string like '2020-2024' into a tuple."""
    if not value:
        return None
    value = value.strip()
    if "-" not in value:
        try:
            year = int(value)
            return (year, year)
        except ValueError:
            return None
    parts = value.split("-", 1)
    try:
        return (int(parts[0].strip()), int(parts[1].strip()))
    except ValueError:
        return None


def _get_default_provider() -> str:
    """Get default academic search provider from settings."""
    try:
        from flavia.config import get_settings

        return str(get_settings().academic_search_provider).strip().lower()
    except Exception:
        return "openalex"


def _build_provider_order(preferred: str) -> list[str]:
    """Build provider fallback order with preferred first."""
    ordered: list[str] = []
    if preferred in ACADEMIC_PROVIDERS:
        ordered.append(preferred)
    for name in ACADEMIC_PROVIDERS:
        if name not in ordered:
            ordered.append(name)
    return ordered


def _format_paper_result(paper) -> str:
    """Format a single PaperResult as markdown."""
    lines = [f"{paper.position}. **{paper.title}**"]

    meta_parts = []
    if paper.authors:
        author_str = ", ".join(paper.authors[:5])
        if len(paper.authors) > 5:
            author_str += f" et al. ({len(paper.authors)} authors)"
        meta_parts.append(author_str)
    if paper.year:
        meta_parts.append(str(paper.year))
    if paper.venue:
        meta_parts.append(paper.venue)
    if meta_parts:
        lines.append(f"   {' | '.join(meta_parts)}")

    detail_parts = []
    if paper.doi:
        detail_parts.append(f"DOI: {paper.doi}")
    if paper.citation_count is not None:
        detail_parts.append(f"Citations: {paper.citation_count}")
    if paper.open_access:
        detail_parts.append("Open Access")
    if detail_parts:
        lines.append(f"   {' | '.join(detail_parts)}")

    if paper.abstract:
        abstract = paper.abstract[:300]
        if len(paper.abstract) > 300:
            abstract += "..."
        lines.append(f"   {abstract}")

    if paper.open_access_url:
        lines.append(f"   PDF: {paper.open_access_url}")

    return "\n".join(lines)


def _format_paper_detail(paper) -> str:
    """Format a PaperDetail as markdown."""
    lines = [f"# {paper.title}", ""]

    # Authors with affiliations
    if paper.authors:
        lines.append("**Authors:**")
        for i, author in enumerate(paper.authors):
            aff = ""
            if paper.author_affiliations and i < len(paper.author_affiliations):
                aff = paper.author_affiliations[i]
            if aff:
                lines.append(f"- {author} ({aff})")
            else:
                lines.append(f"- {author}")
        lines.append("")

    # Metadata
    meta = []
    if paper.year:
        meta.append(f"**Year:** {paper.year}")
    if paper.venue:
        meta.append(f"**Venue:** {paper.venue}")
    if paper.doi:
        meta.append(f"**DOI:** {paper.doi}")
    if paper.citation_count is not None:
        meta.append(f"**Citations:** {paper.citation_count}")
    if paper.references_count is not None:
        meta.append(f"**References:** {paper.references_count}")
    if paper.open_access:
        meta.append("**Open Access:** Yes")
    if meta:
        lines.extend(meta)
        lines.append("")

    # TLDR
    if paper.tldr:
        lines.append(f"**TL;DR:** {paper.tldr}")
        lines.append("")

    # Abstract
    if paper.abstract:
        lines.append("**Abstract:**")
        lines.append(paper.abstract)
        lines.append("")

    # Topics
    if paper.topics:
        lines.append(f"**Topics:** {', '.join(paper.topics)}")
        lines.append("")

    # External IDs
    if paper.external_ids:
        ids = [f"{k}: {v}" for k, v in paper.external_ids.items()]
        lines.append(f"**IDs:** {' | '.join(ids)}")
        lines.append("")

    # PDF URLs
    if paper.pdf_urls:
        lines.append("**PDF URLs:**")
        for url in paper.pdf_urls:
            lines.append(f"- {url}")

    return "\n".join(lines)


class SearchPapersTool(BaseTool):
    """Search academic databases for papers."""

    name = "search_papers"
    description = (
        "Search academic databases (OpenAlex, Semantic Scholar) for research papers. "
        "Returns titles, authors, year, venue, DOI, abstract, citation count, and open access status."
    )
    category = "research"

    def get_schema(self, **context) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParameter(
                    name="query",
                    type="string",
                    description="The search query string.",
                    required=True,
                ),
                ToolParameter(
                    name="num_results",
                    type="integer",
                    description="Number of results to return (1-50, default 10).",
                    required=False,
                    default=10,
                ),
                ToolParameter(
                    name="year_range",
                    type="string",
                    description='Filter by publication year range (e.g., "2020-2024" or "2023").',
                    required=False,
                ),
                ToolParameter(
                    name="fields",
                    type="string",
                    description='Filter by field of study (e.g., "computer science", "medicine").',
                    required=False,
                ),
                ToolParameter(
                    name="sort_by",
                    type="string",
                    description="Sort results by: relevance, date, or citations.",
                    required=False,
                    enum=VALID_SORT_OPTIONS,
                ),
                ToolParameter(
                    name="provider",
                    type="string",
                    description=(
                        "Academic search provider override. Options: openalex, semantic_scholar. "
                        "If not specified, uses the default from settings."
                    ),
                    required=False,
                    enum=list(ACADEMIC_PROVIDERS.keys()),
                ),
            ],
        )

    def execute(self, args: dict[str, Any], agent_context: "AgentContext") -> str:
        query = args.get("query", "").strip()
        if not query:
            return "Error: search query is required."

        num_results = args.get("num_results", 10)
        if not isinstance(num_results, int):
            try:
                num_results = int(num_results)
            except (ValueError, TypeError):
                num_results = 10
        num_results = max(1, min(num_results, 50))

        year_range = _parse_year_range(args.get("year_range"))

        fields = args.get("fields")
        if isinstance(fields, str):
            fields = fields.strip() or None

        sort_by = args.get("sort_by", "relevance")
        if isinstance(sort_by, str):
            sort_by = sort_by.strip().lower()
        if sort_by not in VALID_SORT_OPTIONS:
            return f"Error: invalid sort_by '{sort_by}'. Use: {', '.join(VALID_SORT_OPTIONS)}"

        # Determine provider
        provider_name = args.get("provider")
        if isinstance(provider_name, str):
            provider_name = provider_name.strip().lower()
        if not provider_name:
            provider_name = _get_default_provider()
        if not provider_name:
            provider_name = "openalex"

        if provider_name not in ACADEMIC_PROVIDERS:
            return (
                f"Error: unknown academic search provider '{provider_name}'. "
                f"Available providers: {', '.join(ACADEMIC_PROVIDERS.keys())}"
            )

        provider_order = _build_provider_order(provider_name)
        logger.debug(
            "Academic search provider order query=%r preferred=%s order=%s",
            query[:80],
            provider_name,
            provider_order,
        )
        attempts: list[str] = []

        for current_name in provider_order:
            provider = get_academic_provider(current_name)
            if provider is None:
                attempts.append(f"`{current_name}`: provider is not available.")
                continue

            if not provider.is_configured():
                attempts.append(f"`{current_name}`: provider is not configured.")
                continue

            response = provider.search(
                query=query,
                num_results=num_results,
                year_range=year_range,
                fields=fields,
                sort_by=sort_by,
            )

            if response.error_message:
                logger.warning(
                    "Academic search provider failed: provider=%s query=%r reason=%r",
                    current_name,
                    query[:80],
                    response.error_message,
                )
                attempts.append(f"`{current_name}`: {response.error_message}")
                continue

            return self._format_response(response, attempts=attempts if attempts else None)

        return self._format_unavailable(query, attempts)

    def _format_response(self, response, attempts: Optional[list[str]] = None) -> str:
        if not response.results:
            if attempts:
                return "\n".join([
                    f"No results found for: {response.query}",
                    "",
                    "_Provider fallback used:_",
                    *[f"- {a}" for a in attempts],
                ])
            return f"No results found for: {response.query}"

        lines = [f"**Academic Search Results** ({response.provider})\n"]
        if attempts:
            lines.append("_Provider fallback used:_")
            for a in attempts:
                lines.append(f"- {a}")
            lines.append("")

        for paper in response.results:
            lines.append(_format_paper_result(paper))
            lines.append("")

        if response.total_results and response.total_results > len(response.results):
            lines.append(
                f"_Showing {len(response.results)} of ~{response.total_results:,} results_"
            )

        return "\n".join(lines)

    def _format_unavailable(self, query: str, attempts: list[str]) -> str:
        lines = [f"Error: academic search unavailable for query: {query}", ""]
        lines.append("Attempts:")
        for a in attempts:
            lines.append(f"- {a}")
        lines.extend([
            "",
            "How to fix:",
            "- OpenAlex requires no API key (should always work).",
            "- For Semantic Scholar: optionally set `SEMANTIC_SCHOLAR_API_KEY` in `.flavia/.env` for higher rate limits.",
            "- Set `OPENALEX_EMAIL` in `.flavia/.env` for polite pool access (higher rate limits).",
        ])
        return "\n".join(lines)


class GetPaperDetailsTool(BaseTool):
    """Get full metadata for a specific paper."""

    name = "get_paper_details"
    description = (
        "Get full metadata for a specific paper by DOI, OpenAlex ID, or Semantic Scholar ID. "
        "Returns full abstract, all authors with affiliations, citations, references, related works, and PDF URLs."
    )
    category = "research"

    def get_schema(self, **context) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParameter(
                    name="paper_id",
                    type="string",
                    description=(
                        "Paper identifier: DOI (e.g., '10.1234/example'), "
                        "OpenAlex ID (e.g., 'W1234567890'), "
                        "Semantic Scholar ID, or URL."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="provider",
                    type="string",
                    description=(
                        "Provider override. Options: openalex, semantic_scholar. "
                        "If not specified, auto-detects from paper_id format."
                    ),
                    required=False,
                    enum=list(ACADEMIC_PROVIDERS.keys()),
                ),
            ],
        )

    def execute(self, args: dict[str, Any], agent_context: "AgentContext") -> str:
        paper_id = args.get("paper_id", "").strip()
        if not paper_id:
            return "Error: paper_id is required."

        provider_name = args.get("provider")
        if isinstance(provider_name, str):
            provider_name = provider_name.strip().lower()

        if not provider_name:
            provider_name = self._detect_provider(paper_id)

        provider_order = _build_provider_order(provider_name)
        attempts: list[str] = []

        for current_name in provider_order:
            provider = get_academic_provider(current_name)
            if provider is None:
                attempts.append(f"`{current_name}`: provider is not available.")
                continue

            response = provider.get_details(paper_id)

            if response.error_message:
                attempts.append(f"`{current_name}`: {response.error_message}")
                continue

            if response.paper:
                result = _format_paper_detail(response.paper)
                if attempts:
                    result = "\n".join([
                        "_Provider fallback used:_",
                        *[f"- {a}" for a in attempts],
                        "",
                        result,
                    ])
                return result

            attempts.append(f"`{current_name}`: paper not found.")

        return "\n".join([
            f"Error: could not find paper: {paper_id}",
            "",
            "Attempts:",
            *[f"- {a}" for a in attempts],
        ])

    def _detect_provider(self, paper_id: str) -> str:
        """Detect the best provider for a given paper_id format."""
        pid = paper_id.strip()
        if pid.startswith("W") or pid.startswith("https://openalex.org/"):
            return "openalex"
        # Default to preferred provider from settings
        return _get_default_provider() or "openalex"


class GetCitationsTool(BaseTool):
    """Get papers that cite a given paper."""

    name = "get_citations"
    description = (
        "Get papers that cite a given paper. "
        "Returns a list of citing papers with titles, authors, year, venue, and citation counts."
    )
    category = "research"

    def get_schema(self, **context) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParameter(
                    name="paper_id",
                    type="string",
                    description="Paper identifier (DOI, OpenAlex ID, or Semantic Scholar ID).",
                    required=True,
                ),
                ToolParameter(
                    name="num_results",
                    type="integer",
                    description="Number of citing papers to return (1-100, default 10).",
                    required=False,
                    default=10,
                ),
                ToolParameter(
                    name="sort_by",
                    type="string",
                    description="Sort results by: relevance, date, or citations.",
                    required=False,
                    enum=VALID_SORT_OPTIONS,
                ),
                ToolParameter(
                    name="provider",
                    type="string",
                    description="Provider override. Options: openalex, semantic_scholar.",
                    required=False,
                    enum=list(ACADEMIC_PROVIDERS.keys()),
                ),
            ],
        )

    def execute(self, args: dict[str, Any], agent_context: "AgentContext") -> str:
        paper_id = args.get("paper_id", "").strip()
        if not paper_id:
            return "Error: paper_id is required."

        num_results = args.get("num_results", 10)
        if not isinstance(num_results, int):
            try:
                num_results = int(num_results)
            except (ValueError, TypeError):
                num_results = 10
        num_results = max(1, min(num_results, 100))

        sort_by = args.get("sort_by", "relevance")
        if isinstance(sort_by, str):
            sort_by = sort_by.strip().lower()
        if sort_by not in VALID_SORT_OPTIONS:
            sort_by = "relevance"

        provider_name = args.get("provider")
        if isinstance(provider_name, str):
            provider_name = provider_name.strip().lower()
        if not provider_name:
            provider_name = _get_default_provider() or "openalex"

        provider_order = _build_provider_order(provider_name)
        attempts: list[str] = []

        for current_name in provider_order:
            provider = get_academic_provider(current_name)
            if provider is None:
                attempts.append(f"`{current_name}`: provider is not available.")
                continue

            response = provider.get_citations(
                paper_id=paper_id,
                num_results=num_results,
                sort_by=sort_by,
            )

            if response.error_message:
                attempts.append(f"`{current_name}`: {response.error_message}")
                continue

            return self._format_response(paper_id, response, attempts)

        return "\n".join([
            f"Error: could not get citations for: {paper_id}",
            "",
            "Attempts:",
            *[f"- {a}" for a in attempts],
        ])

    def _format_response(self, paper_id: str, response, attempts: list[str]) -> str:
        lines = [f"**Citations of {paper_id}** ({response.provider})\n"]
        if attempts:
            lines.append("_Provider fallback used:_")
            for a in attempts:
                lines.append(f"- {a}")
            lines.append("")

        if not response.citations:
            lines.append("No citing papers found.")
            return "\n".join(lines)

        for paper in response.citations:
            lines.append(_format_paper_result(paper))
            lines.append("")

        if response.total_results and response.total_results > len(response.citations):
            lines.append(
                f"_Showing {len(response.citations)} of ~{response.total_results:,} citing papers_"
            )

        return "\n".join(lines)


class GetReferencesTool(BaseTool):
    """Get papers referenced by a given paper."""

    name = "get_references"
    description = (
        "Get papers referenced by a given paper. "
        "Returns a list of referenced papers with titles, authors, year, venue, and citation counts."
    )
    category = "research"

    def get_schema(self, **context) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParameter(
                    name="paper_id",
                    type="string",
                    description="Paper identifier (DOI, OpenAlex ID, or Semantic Scholar ID).",
                    required=True,
                ),
                ToolParameter(
                    name="num_results",
                    type="integer",
                    description="Number of referenced papers to return (1-100, default 10).",
                    required=False,
                    default=10,
                ),
                ToolParameter(
                    name="provider",
                    type="string",
                    description="Provider override. Options: openalex, semantic_scholar.",
                    required=False,
                    enum=list(ACADEMIC_PROVIDERS.keys()),
                ),
            ],
        )

    def execute(self, args: dict[str, Any], agent_context: "AgentContext") -> str:
        paper_id = args.get("paper_id", "").strip()
        if not paper_id:
            return "Error: paper_id is required."

        num_results = args.get("num_results", 10)
        if not isinstance(num_results, int):
            try:
                num_results = int(num_results)
            except (ValueError, TypeError):
                num_results = 10
        num_results = max(1, min(num_results, 100))

        provider_name = args.get("provider")
        if isinstance(provider_name, str):
            provider_name = provider_name.strip().lower()
        if not provider_name:
            provider_name = _get_default_provider() or "openalex"

        provider_order = _build_provider_order(provider_name)
        attempts: list[str] = []

        for current_name in provider_order:
            provider = get_academic_provider(current_name)
            if provider is None:
                attempts.append(f"`{current_name}`: provider is not available.")
                continue

            response = provider.get_references(
                paper_id=paper_id,
                num_results=num_results,
            )

            if response.error_message:
                attempts.append(f"`{current_name}`: {response.error_message}")
                continue

            return self._format_response(paper_id, response, attempts)

        return "\n".join([
            f"Error: could not get references for: {paper_id}",
            "",
            "Attempts:",
            *[f"- {a}" for a in attempts],
        ])

    def _format_response(self, paper_id: str, response, attempts: list[str]) -> str:
        lines = [f"**References of {paper_id}** ({response.provider})\n"]
        if attempts:
            lines.append("_Provider fallback used:_")
            for a in attempts:
                lines.append(f"- {a}")
            lines.append("")

        if not response.citations:
            lines.append("No referenced papers found.")
            return "\n".join(lines)

        for paper in response.citations:
            lines.append(_format_paper_result(paper))
            lines.append("")

        if response.total_results and response.total_results > len(response.citations):
            lines.append(
                f"_Showing {len(response.citations)} of ~{response.total_results:,} referenced papers_"
            )

        return "\n".join(lines)


class FindSimilarPapersTool(BaseTool):
    """Find papers similar to a given paper."""

    name = "find_similar_papers"
    description = (
        "Find papers similar to a given paper using recommendations and related works. "
        "Returns a list of similar papers with titles, authors, year, venue, and citation counts."
    )
    category = "research"

    def get_schema(self, **context) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParameter(
                    name="paper_id",
                    type="string",
                    description="Paper identifier (DOI, OpenAlex ID, or Semantic Scholar ID).",
                    required=True,
                ),
                ToolParameter(
                    name="num_results",
                    type="integer",
                    description="Number of similar papers to return (1-50, default 10).",
                    required=False,
                    default=10,
                ),
                ToolParameter(
                    name="provider",
                    type="string",
                    description="Provider override. Options: openalex, semantic_scholar.",
                    required=False,
                    enum=list(ACADEMIC_PROVIDERS.keys()),
                ),
            ],
        )

    def execute(self, args: dict[str, Any], agent_context: "AgentContext") -> str:
        paper_id = args.get("paper_id", "").strip()
        if not paper_id:
            return "Error: paper_id is required."

        num_results = args.get("num_results", 10)
        if not isinstance(num_results, int):
            try:
                num_results = int(num_results)
            except (ValueError, TypeError):
                num_results = 10
        num_results = max(1, min(num_results, 50))

        provider_name = args.get("provider")
        if isinstance(provider_name, str):
            provider_name = provider_name.strip().lower()
        if not provider_name:
            provider_name = _get_default_provider() or "openalex"

        provider_order = _build_provider_order(provider_name)
        attempts: list[str] = []

        for current_name in provider_order:
            provider = get_academic_provider(current_name)
            if provider is None:
                attempts.append(f"`{current_name}`: provider is not available.")
                continue

            response = provider.find_similar(
                paper_id=paper_id,
                num_results=num_results,
            )

            if response.error_message:
                attempts.append(f"`{current_name}`: {response.error_message}")
                continue

            return self._format_response(paper_id, response, attempts)

        return "\n".join([
            f"Error: could not find similar papers for: {paper_id}",
            "",
            "Attempts:",
            *[f"- {a}" for a in attempts],
        ])

    def _format_response(self, paper_id: str, response, attempts: list[str]) -> str:
        lines = [f"**Papers Similar to {paper_id}** ({response.provider})\n"]
        if attempts:
            lines.append("_Provider fallback used:_")
            for a in attempts:
                lines.append(f"- {a}")
            lines.append("")

        if not response.results:
            lines.append("No similar papers found.")
            return "\n".join(lines)

        for paper in response.results:
            lines.append(_format_paper_result(paper))
            lines.append("")

        if response.total_results and response.total_results > len(response.results):
            lines.append(
                f"_Showing {len(response.results)} of ~{response.total_results:,} similar papers_"
            )

        return "\n".join(lines)


# Register all tools
register_tool(SearchPapersTool())
register_tool(GetPaperDetailsTool())
register_tool(GetCitationsTool())
register_tool(GetReferencesTool())
register_tool(FindSimilarPapersTool())
