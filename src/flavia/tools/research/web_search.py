"""Web search tool for flavIA.

Provides web search capabilities through multiple search providers
(DuckDuckGo, Google, Brave, Bing) with a unified interface.
"""

import logging
from typing import TYPE_CHECKING, Any

from ..base import BaseTool, ToolParameter, ToolSchema
from ..registry import register_tool
from .search_providers import PROVIDERS, get_provider

if TYPE_CHECKING:
    from flavia.agent.context import AgentContext

logger = logging.getLogger(__name__)

VALID_TIME_RANGES = ["day", "week", "month", "year"]


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
        time_range = args.get("time_range")
        if time_range and time_range not in VALID_TIME_RANGES:
            return f"Error: invalid time_range '{time_range}'. Use: {', '.join(VALID_TIME_RANGES)}"

        # Determine provider
        provider_name = args.get("provider")
        if not provider_name:
            try:
                from flavia.config import get_settings

                provider_name = get_settings().web_search_provider
            except Exception:
                provider_name = "duckduckgo"

        provider = get_provider(provider_name)
        if provider is None:
            return (
                f"Error: unknown search provider '{provider_name}'. "
                f"Available providers: {', '.join(PROVIDERS.keys())}"
            )

        if not provider.is_configured():
            if provider_name == "duckduckgo":
                return (
                    "Error: DuckDuckGo search requires the duckduckgo-search library. "
                    "Install it with: pip install 'flavia[research]'"
                )
            return (
                f"Error: {provider_name} search provider is not configured. "
                f"Set the required API keys via environment variables or /settings."
            )

        # Execute search
        response = provider.search(
            query=query,
            num_results=num_results,
            region=region,
            time_range=time_range,
        )

        # Format results as markdown
        return self._format_response(response)

    def _format_response(self, response) -> str:
        """Format search response as markdown."""
        if not response.results:
            return f"No results found for: {response.query}"

        lines = [f"**Web Search Results** ({response.provider})\n"]

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
