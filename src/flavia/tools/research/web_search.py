"""Web search tool for flavIA.

Provides web search capabilities through multiple search providers
(DuckDuckGo, Google, Brave, Bing) with a unified interface.
"""

import logging
from typing import TYPE_CHECKING, Any, Optional

from ..base import BaseTool, ToolParameter, ToolSchema
from ..registry import register_tool
from .search_providers import PROVIDERS, get_provider

if TYPE_CHECKING:
    from flavia.agent.context import AgentContext

logger = logging.getLogger(__name__)

VALID_TIME_RANGES = ["day", "week", "month", "year"]
ERROR_RESULT_TITLES = {"Error", "Search Error", "Configuration Error"}


class WebSearchTool(BaseTool):
    """Search the web using configurable search providers."""

    name = "web_search"
    description = (
        "Search the web for information. Returns titles, URLs, and snippets "
        "from web search results. Useful for finding current information, "
        "research papers, documentation, and general knowledge."
    )
    category = "research"

    def get_schema(self, **context) -> ToolSchema:
        """Get the tool schema."""
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
                    description="Number of results to return (1-20, default 10).",
                    required=False,
                    default=10,
                ),
                ToolParameter(
                    name="region",
                    type="string",
                    description=(
                        "Region/locale code for localized results (e.g., 'us', 'br', 'de')."
                    ),
                    required=False,
                ),
                ToolParameter(
                    name="time_range",
                    type="string",
                    description="Filter results by time: day, week, month, or year.",
                    required=False,
                    enum=VALID_TIME_RANGES,
                ),
                ToolParameter(
                    name="provider",
                    type="string",
                    description=(
                        "Search provider override. Options: duckduckgo, google, brave, bing. "
                        "If not specified, uses the default from settings."
                    ),
                    required=False,
                    enum=list(PROVIDERS.keys()),
                ),
            ],
        )

    def execute(self, args: dict[str, Any], agent_context: "AgentContext") -> str:
        """Execute a web search."""
        query = args.get("query", "").strip()
        if not query:
            return "Error: search query is required."

        num_results = args.get("num_results", 10)
        if not isinstance(num_results, int):
            try:
                num_results = int(num_results)
            except (ValueError, TypeError):
                num_results = 10
        num_results = max(1, min(num_results, 20))

        region = args.get("region")
        if isinstance(region, str):
            region = region.strip()
            if len(region) == 2:
                region = region.lower()
            if not region:
                region = None

        time_range = args.get("time_range")
        if isinstance(time_range, str):
            time_range = time_range.strip().lower()
        if time_range and time_range not in VALID_TIME_RANGES:
            return f"Error: invalid time_range '{time_range}'. Use: {', '.join(VALID_TIME_RANGES)}"

        # Determine provider
        provider_name = args.get("provider")
        if isinstance(provider_name, str):
            provider_name = provider_name.strip().lower()
        if not provider_name:
            try:
                from flavia.config import get_settings

                provider_name = str(get_settings().web_search_provider).strip().lower()
            except Exception:
                provider_name = "duckduckgo"
        if not provider_name:
            provider_name = "duckduckgo"

        if provider_name not in PROVIDERS:
            return (
                f"Error: unknown search provider '{provider_name}'. "
                f"Available providers: {', '.join(PROVIDERS.keys())}"
            )

        provider_order = self._build_provider_order(provider_name)
        attempts: list[str] = []

        for current_provider_name in provider_order:
            provider = get_provider(current_provider_name)
            if provider is None:
                attempts.append(
                    f"`{current_provider_name}`: provider is not available in this build."
                )
                continue

            if not provider.is_configured():
                attempts.append(
                    f"`{current_provider_name}`: "
                    f"{self._provider_not_configured_reason(current_provider_name)}"
                )
                continue

            response = provider.search(
                query=query,
                num_results=num_results,
                region=region,
                time_range=time_range,
            )

            error_message = self._extract_response_error(response)
            if error_message:
                attempts.append(f"`{current_provider_name}`: {error_message}")
                continue

            return self._format_response(response, attempts=attempts if attempts else None)

        return self._format_unavailable(query, attempts)

    def _build_provider_order(self, preferred_provider: str) -> list[str]:
        """Build provider order with preferred provider first, then fallbacks."""
        ordered: list[str] = []
        if preferred_provider in PROVIDERS:
            ordered.append(preferred_provider)
        for name in PROVIDERS:
            if name not in ordered:
                ordered.append(name)
        return ordered

    def _provider_not_configured_reason(self, provider_name: str) -> str:
        """Get configuration hint for an unconfigured provider."""
        if provider_name == "duckduckgo":
            return (
                "duckduckgo-search is not installed in the current Python environment. "
                "Install with: pip install -e '.[research]' (project repo) "
                "or pip install 'duckduckgo-search>=6.0'"
            )
        if provider_name == "google":
            return "missing GOOGLE_SEARCH_API_KEY or GOOGLE_SEARCH_CX."
        if provider_name == "brave":
            return "missing BRAVE_SEARCH_API_KEY."
        if provider_name == "bing":
            return "missing BING_SEARCH_API_KEY."
        return "provider is not configured."

    def _extract_response_error(self, response) -> Optional[str]:
        """Extract an error message from provider response, if present."""
        explicit_error = getattr(response, "error_message", None)
        if explicit_error:
            return str(explicit_error).strip()

        if not response.results:
            return None

        first = response.results[0]
        if first.title in ERROR_RESULT_TITLES:
            return first.snippet.strip() or "provider returned an error."
        return None

    def _format_unavailable(self, query: str, attempts: list[str]) -> str:
        """Format an actionable error when all providers fail."""
        lines = [f"Error: web search unavailable for query: {query}", ""]
        lines.append("Attempts:")
        for attempt in attempts:
            lines.append(f"- {attempt}")
        lines.extend(
            [
                "",
                "How to fix:",
                "- For DuckDuckGo: install dependency with "
                "`pip install -e '.[research]'` (from project root) or "
                "`pip install 'duckduckgo-search>=6.0'`.",
                "- Or configure API providers in `.flavia/.env`: "
                "`GOOGLE_SEARCH_API_KEY` + `GOOGLE_SEARCH_CX`, "
                "`BRAVE_SEARCH_API_KEY`, `BING_SEARCH_API_KEY`.",
                "- You can also configure these values interactively with `/settings web_search`.",
            ]
        )
        return "\n".join(lines)

    def _format_response(self, response, attempts: Optional[list[str]] = None) -> str:
        """Format search response as markdown."""
        if not response.results:
            if attempts:
                return "\n".join(
                    [
                        f"No results found for: {response.query}",
                        "",
                        "_Provider fallback used:_",
                        *[f"- {attempt}" for attempt in attempts],
                    ]
                )
            return f"No results found for: {response.query}"

        lines = [f"**Web Search Results** ({response.provider})\n"]
        if attempts:
            lines.append("_Provider fallback used:_")
            for attempt in attempts:
                lines.append(f"- {attempt}")
            lines.append("")

        for result in response.results:
            lines.append(f"{result.position}. **{result.title}**")
            if result.url:
                lines.append(f"   {result.url}")
            if result.snippet:
                lines.append(f"   {result.snippet}")
            lines.append("")

        if response.total_results and response.total_results > len(response.results):
            lines.append(
                f"_Showing {len(response.results)} of ~{response.total_results:,} results_"
            )

        return "\n".join(lines)


# Register the tool
register_tool(WebSearchTool())
