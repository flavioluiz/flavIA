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
MIN_PUBLICATION_YEAR = 1000
MAX_PUBLICATION_YEAR = 2100


def _normalize_text_arg(value: Any) -> str:
    """Normalize a tool arg into a stripped string."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _parse_bool_arg(value: Any, default: bool = False) -> bool:
    """Coerce common boolean-like values from tool args safely."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y", "on"}:
            return True
        if normalized in {"false", "0", "no", "n", "off", ""}:
            return False
    return bool(value)


def _normalize_provider_name(value: Any) -> str:
    """Normalize provider arg to lowercase token."""
    return _normalize_text_arg(value).lower()


def _parse_year_range(value: Any) -> Optional[tuple[int, int]]:
    """Parse a year range string like '2020-2024' into a tuple."""
    normalized_value = _normalize_text_arg(value)
    if not normalized_value:
        return None
    if "-" not in normalized_value:
        try:
            year = int(normalized_value)
            if year < MIN_PUBLICATION_YEAR or year > MAX_PUBLICATION_YEAR:
                return None
            return (year, year)
        except ValueError:
            return None
    parts = normalized_value.split("-", 1)
    try:
        start_year = int(parts[0].strip())
        end_year = int(parts[1].strip())
    except ValueError:
        return None
    if start_year > end_year:
        start_year, end_year = end_year, start_year
    if (
        start_year < MIN_PUBLICATION_YEAR
        or end_year > MAX_PUBLICATION_YEAR
    ):
        return None
    return (start_year, end_year)


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


def _provider_not_configured_reason(provider_name: str) -> str:
    """Get configuration hint for an unavailable provider."""
    if provider_name == "openalex":
        return "OpenAlex provider is not configured in this runtime."
    if provider_name == "semantic_scholar":
        return (
            "Semantic Scholar provider is not configured in this runtime "
            "(API key is optional; set `SEMANTIC_SCHOLAR_API_KEY` for higher limits)."
        )
    return "provider is not configured."


def _validate_provider_name(provider_name: str) -> Optional[str]:
    """Validate provider name and return an actionable error when invalid."""
    if provider_name in ACADEMIC_PROVIDERS:
        return None
    return (
        f"Error: unknown academic search provider '{provider_name}'. "
        f"Available providers: {', '.join(ACADEMIC_PROVIDERS.keys())}"
    )


def _resolve_provider_name(
    raw_provider: Any,
    fallback_provider: str,
) -> tuple[str, Optional[str]]:
    """Resolve provider from args/defaults with safe fallback."""
    requested_provider = _normalize_provider_name(raw_provider)
    if requested_provider:
        return requested_provider, _validate_provider_name(requested_provider)

    resolved_fallback = _normalize_provider_name(fallback_provider) or "openalex"
    if resolved_fallback not in ACADEMIC_PROVIDERS:
        logger.warning(
            "Invalid academic provider fallback=%r. Falling back to openalex.",
            resolved_fallback,
        )
        return "openalex", None
    return resolved_fallback, None


def _diagnostics_lines(
    provider_order: list[str],
    attempts: list[str],
    selected_provider: Optional[str] = None,
) -> list[str]:
    """Build a diagnostics block for provider attempts/order."""
    lines = ["_Diagnostics:_", f"- Provider order: {', '.join(provider_order)}"]
    if selected_provider:
        lines.append(f"- Provider selected: {selected_provider}")
    if attempts:
        for attempt in attempts:
            lines.append(f"- Failed attempt: {attempt}")
    else:
        lines.append("- No provider failures recorded.")
    return lines


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
                ToolParameter(
                    name="diagnostics",
                    type="boolean",
                    description=(
                        "When true, include provider-order diagnostics and detailed "
                        "fallback attempts in the tool output."
                    ),
                    required=False,
                    default=False,
                ),
            ],
        )

    def execute(self, args: dict[str, Any], agent_context: "AgentContext") -> str:
        query = _normalize_text_arg(args.get("query"))
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

        fields = _normalize_text_arg(args.get("fields")) or None

        sort_by = args.get("sort_by", "relevance")
        if isinstance(sort_by, str):
            sort_by = sort_by.strip().lower()
        if sort_by not in VALID_SORT_OPTIONS:
            return f"Error: invalid sort_by '{sort_by}'. Use: {', '.join(VALID_SORT_OPTIONS)}"

        # Determine provider
        diagnostics = _parse_bool_arg(args.get("diagnostics"), default=False)

        provider_name, provider_error = _resolve_provider_name(
            args.get("provider"),
            _get_default_provider() or "openalex",
        )
        if provider_error:
            return provider_error

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
                attempts.append(
                    f"`{current_name}`: {_provider_not_configured_reason(current_name)}"
                )
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

            return self._format_response(
                response,
                attempts=attempts if attempts else None,
                diagnostics=diagnostics,
                provider_order=provider_order,
            )

        return self._format_unavailable(
            query,
            attempts,
            diagnostics=diagnostics,
            provider_order=provider_order,
        )

    def _format_response(
        self,
        response,
        attempts: Optional[list[str]] = None,
        diagnostics: bool = False,
        provider_order: Optional[list[str]] = None,
    ) -> str:
        all_attempts = attempts or []
        resolved_provider_order = provider_order or [response.provider]
        if not response.results:
            if attempts:
                lines = [
                    f"No results found for: {response.query}",
                    "",
                    "_Provider fallback used:_",
                    *[f"- {a}" for a in all_attempts],
                ]
                if diagnostics:
                    lines.extend([""] + _diagnostics_lines(
                        resolved_provider_order,
                        all_attempts,
                        selected_provider=response.provider,
                    ))
                return "\n".join(lines)
            if diagnostics:
                return "\n".join([
                    f"No results found for: {response.query}",
                    "",
                    *_diagnostics_lines(
                        resolved_provider_order,
                        [],
                        selected_provider=response.provider,
                    ),
                ])
            return f"No results found for: {response.query}"

        lines = [f"**Academic Search Results** ({response.provider})\n"]
        if all_attempts:
            lines.append("_Provider fallback used:_")
            for a in all_attempts:
                lines.append(f"- {a}")
            lines.append("")
        if diagnostics:
            lines.extend(
                _diagnostics_lines(
                    resolved_provider_order,
                    all_attempts,
                    selected_provider=response.provider,
                )
            )
            lines.append("")

        for paper in response.results:
            lines.append(_format_paper_result(paper))
            lines.append("")

        if response.total_results and response.total_results > len(response.results):
            lines.append(
                f"_Showing {len(response.results)} of ~{response.total_results:,} results_"
            )

        return "\n".join(lines)

    def _format_unavailable(
        self,
        query: str,
        attempts: list[str],
        diagnostics: bool = False,
        provider_order: Optional[list[str]] = None,
    ) -> str:
        lines = [f"Error: academic search unavailable for query: {query}", ""]
        lines.append("Attempts:")
        for a in attempts:
            lines.append(f"- {a}")
        if diagnostics:
            lines.extend([""] + _diagnostics_lines(provider_order or [], attempts))
        else:
            lines.extend([
                "",
                "Tip: pass `diagnostics=true` to include provider-order diagnostics.",
            ])
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
                ToolParameter(
                    name="diagnostics",
                    type="boolean",
                    description=(
                        "When true, include provider-order diagnostics and detailed "
                        "fallback attempts in the tool output."
                    ),
                    required=False,
                    default=False,
                ),
            ],
        )

    def execute(self, args: dict[str, Any], agent_context: "AgentContext") -> str:
        paper_id = _normalize_text_arg(args.get("paper_id"))
        if not paper_id:
            return "Error: paper_id is required."

        diagnostics = _parse_bool_arg(args.get("diagnostics"), default=False)
        provider_name, provider_error = _resolve_provider_name(
            args.get("provider"),
            self._detect_provider(paper_id),
        )
        if provider_error:
            return provider_error

        provider_order = _build_provider_order(provider_name)
        attempts: list[str] = []

        for current_name in provider_order:
            provider = get_academic_provider(current_name)
            if provider is None:
                attempts.append(f"`{current_name}`: provider is not available.")
                continue

            if not provider.is_configured():
                attempts.append(
                    f"`{current_name}`: {_provider_not_configured_reason(current_name)}"
                )
                continue

            response = provider.get_details(paper_id)

            if response.error_message:
                attempts.append(f"`{current_name}`: {response.error_message}")
                continue

            if response.paper:
                result = _format_paper_detail(response.paper)
                metadata_lines: list[str] = []
                if attempts:
                    metadata_lines.extend([
                        "_Provider fallback used:_",
                        *[f"- {a}" for a in attempts],
                    ])
                if diagnostics:
                    if metadata_lines:
                        metadata_lines.append("")
                    metadata_lines.extend(
                        _diagnostics_lines(
                            provider_order,
                            attempts,
                            selected_provider=response.provider,
                        )
                    )
                if metadata_lines:
                    result = "\n".join([*metadata_lines, "", result])
                return result

            attempts.append(f"`{current_name}`: paper not found.")

        lines = [
            f"Error: could not find paper: {paper_id}",
            "",
            "Attempts:",
            *[f"- {a}" for a in attempts],
        ]
        if diagnostics:
            lines.extend([""] + _diagnostics_lines(provider_order, attempts))
        else:
            lines.extend([
                "",
                "Tip: pass `diagnostics=true` to include provider-order diagnostics.",
            ])
        return "\n".join(lines)

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
                ToolParameter(
                    name="diagnostics",
                    type="boolean",
                    description=(
                        "When true, include provider-order diagnostics and detailed "
                        "fallback attempts in the tool output."
                    ),
                    required=False,
                    default=False,
                ),
            ],
        )

    def execute(self, args: dict[str, Any], agent_context: "AgentContext") -> str:
        paper_id = _normalize_text_arg(args.get("paper_id"))
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

        diagnostics = _parse_bool_arg(args.get("diagnostics"), default=False)
        provider_name, provider_error = _resolve_provider_name(
            args.get("provider"),
            _get_default_provider() or "openalex",
        )
        if provider_error:
            return provider_error

        provider_order = _build_provider_order(provider_name)
        attempts: list[str] = []

        for current_name in provider_order:
            provider = get_academic_provider(current_name)
            if provider is None:
                attempts.append(f"`{current_name}`: provider is not available.")
                continue

            if not provider.is_configured():
                attempts.append(
                    f"`{current_name}`: {_provider_not_configured_reason(current_name)}"
                )
                continue

            response = provider.get_citations(
                paper_id=paper_id,
                num_results=num_results,
                sort_by=sort_by,
            )

            if response.error_message:
                attempts.append(f"`{current_name}`: {response.error_message}")
                continue

            return self._format_response(
                paper_id,
                response,
                attempts,
                diagnostics=diagnostics,
                provider_order=provider_order,
            )

        lines = [
            f"Error: could not get citations for: {paper_id}",
            "",
            "Attempts:",
            *[f"- {a}" for a in attempts],
        ]
        if diagnostics:
            lines.extend([""] + _diagnostics_lines(provider_order, attempts))
        else:
            lines.extend([
                "",
                "Tip: pass `diagnostics=true` to include provider-order diagnostics.",
            ])
        return "\n".join(lines)

    def _format_response(
        self,
        paper_id: str,
        response,
        attempts: list[str],
        diagnostics: bool = False,
        provider_order: Optional[list[str]] = None,
    ) -> str:
        lines = [f"**Citations of {paper_id}** ({response.provider})\n"]
        if attempts:
            lines.append("_Provider fallback used:_")
            for a in attempts:
                lines.append(f"- {a}")
            lines.append("")
        if diagnostics:
            lines.extend(
                _diagnostics_lines(
                    provider_order or [response.provider],
                    attempts,
                    selected_provider=response.provider,
                )
            )
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
                ToolParameter(
                    name="diagnostics",
                    type="boolean",
                    description=(
                        "When true, include provider-order diagnostics and detailed "
                        "fallback attempts in the tool output."
                    ),
                    required=False,
                    default=False,
                ),
            ],
        )

    def execute(self, args: dict[str, Any], agent_context: "AgentContext") -> str:
        paper_id = _normalize_text_arg(args.get("paper_id"))
        if not paper_id:
            return "Error: paper_id is required."

        num_results = args.get("num_results", 10)
        if not isinstance(num_results, int):
            try:
                num_results = int(num_results)
            except (ValueError, TypeError):
                num_results = 10
        num_results = max(1, min(num_results, 100))

        diagnostics = _parse_bool_arg(args.get("diagnostics"), default=False)
        provider_name, provider_error = _resolve_provider_name(
            args.get("provider"),
            _get_default_provider() or "openalex",
        )
        if provider_error:
            return provider_error

        provider_order = _build_provider_order(provider_name)
        attempts: list[str] = []

        for current_name in provider_order:
            provider = get_academic_provider(current_name)
            if provider is None:
                attempts.append(f"`{current_name}`: provider is not available.")
                continue

            if not provider.is_configured():
                attempts.append(
                    f"`{current_name}`: {_provider_not_configured_reason(current_name)}"
                )
                continue

            response = provider.get_references(
                paper_id=paper_id,
                num_results=num_results,
            )

            if response.error_message:
                attempts.append(f"`{current_name}`: {response.error_message}")
                continue

            return self._format_response(
                paper_id,
                response,
                attempts,
                diagnostics=diagnostics,
                provider_order=provider_order,
            )

        lines = [
            f"Error: could not get references for: {paper_id}",
            "",
            "Attempts:",
            *[f"- {a}" for a in attempts],
        ]
        if diagnostics:
            lines.extend([""] + _diagnostics_lines(provider_order, attempts))
        else:
            lines.extend([
                "",
                "Tip: pass `diagnostics=true` to include provider-order diagnostics.",
            ])
        return "\n".join(lines)

    def _format_response(
        self,
        paper_id: str,
        response,
        attempts: list[str],
        diagnostics: bool = False,
        provider_order: Optional[list[str]] = None,
    ) -> str:
        lines = [f"**References of {paper_id}** ({response.provider})\n"]
        if attempts:
            lines.append("_Provider fallback used:_")
            for a in attempts:
                lines.append(f"- {a}")
            lines.append("")
        if diagnostics:
            lines.extend(
                _diagnostics_lines(
                    provider_order or [response.provider],
                    attempts,
                    selected_provider=response.provider,
                )
            )
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
                ToolParameter(
                    name="diagnostics",
                    type="boolean",
                    description=(
                        "When true, include provider-order diagnostics and detailed "
                        "fallback attempts in the tool output."
                    ),
                    required=False,
                    default=False,
                ),
            ],
        )

    def execute(self, args: dict[str, Any], agent_context: "AgentContext") -> str:
        paper_id = _normalize_text_arg(args.get("paper_id"))
        if not paper_id:
            return "Error: paper_id is required."

        num_results = args.get("num_results", 10)
        if not isinstance(num_results, int):
            try:
                num_results = int(num_results)
            except (ValueError, TypeError):
                num_results = 10
        num_results = max(1, min(num_results, 50))

        diagnostics = _parse_bool_arg(args.get("diagnostics"), default=False)
        provider_name, provider_error = _resolve_provider_name(
            args.get("provider"),
            _get_default_provider() or "openalex",
        )
        if provider_error:
            return provider_error

        provider_order = _build_provider_order(provider_name)
        attempts: list[str] = []

        for current_name in provider_order:
            provider = get_academic_provider(current_name)
            if provider is None:
                attempts.append(f"`{current_name}`: provider is not available.")
                continue

            if not provider.is_configured():
                attempts.append(
                    f"`{current_name}`: {_provider_not_configured_reason(current_name)}"
                )
                continue

            response = provider.find_similar(
                paper_id=paper_id,
                num_results=num_results,
            )

            if response.error_message:
                attempts.append(f"`{current_name}`: {response.error_message}")
                continue

            return self._format_response(
                paper_id,
                response,
                attempts,
                diagnostics=diagnostics,
                provider_order=provider_order,
            )

        lines = [
            f"Error: could not find similar papers for: {paper_id}",
            "",
            "Attempts:",
            *[f"- {a}" for a in attempts],
        ]
        if diagnostics:
            lines.extend([""] + _diagnostics_lines(provider_order, attempts))
        else:
            lines.extend([
                "",
                "Tip: pass `diagnostics=true` to include provider-order diagnostics.",
            ])
        return "\n".join(lines)

    def _format_response(
        self,
        paper_id: str,
        response,
        attempts: list[str],
        diagnostics: bool = False,
        provider_order: Optional[list[str]] = None,
    ) -> str:
        lines = [f"**Papers Similar to {paper_id}** ({response.provider})\n"]
        if attempts:
            lines.append("_Provider fallback used:_")
            for a in attempts:
                lines.append(f"- {a}")
            lines.append("")
        if diagnostics:
            lines.extend(
                _diagnostics_lines(
                    provider_order or [response.provider],
                    attempts,
                    selected_provider=response.provider,
                )
            )
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
