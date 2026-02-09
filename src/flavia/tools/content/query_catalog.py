"""Tool for querying the content catalog."""

from typing import TYPE_CHECKING, Any

from ..base import BaseTool, ToolSchema, ToolParameter

if TYPE_CHECKING:
    from flavia.agent.context import AgentContext


class QueryCatalogTool(BaseTool):
    """Query the project content catalog to find files by name, type, or content."""

    name = "query_catalog"
    description = (
        "Search the project content catalog to find files by name, type, category, "
        "or text search in summaries. Returns file metadata including paths, types, "
        "sizes, and summaries. Much faster than searching the filesystem directly."
    )
    category = "content"

    def get_schema(self, **context) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParameter(
                    name="name",
                    type="string",
                    description="Substring match on filename (e.g. 'smith', 'chapter1')",
                    required=False,
                ),
                ToolParameter(
                    name="extension",
                    type="string",
                    description="File extension filter (e.g. '.pdf', '.md', '.py')",
                    required=False,
                ),
                ToolParameter(
                    name="file_type",
                    type="string",
                    description="File type filter",
                    required=False,
                    enum=["text", "binary_document", "image", "audio", "video", "archive", "other"],
                ),
                ToolParameter(
                    name="category",
                    type="string",
                    description="Category filter (e.g. 'python', 'pdf', 'markdown', 'latex', 'csv')",
                    required=False,
                ),
                ToolParameter(
                    name="text_search",
                    type="string",
                    description="Free text search in file paths, summaries, and tags",
                    required=False,
                ),
                ToolParameter(
                    name="show_stats",
                    type="boolean",
                    description="Include catalog statistics in the response",
                    required=False,
                ),
                ToolParameter(
                    name="limit",
                    type="integer",
                    description="Maximum number of results (default: 30)",
                    required=False,
                ),
            ],
        )

    def execute(self, args: dict[str, Any], agent_context: "AgentContext") -> str:
        from flavia.content.catalog import ContentCatalog

        config_dir = agent_context.base_dir / ".flavia"
        catalog = ContentCatalog.load(config_dir)
        if catalog is None:
            return (
                "Error: No content catalog found. "
                "Run 'flavia --init' or 'flavia --update' to build the catalog."
            )

        show_stats = args.get("show_stats", False)
        limit = args.get("limit", 30)

        # Build query filters
        query_kwargs: dict[str, Any] = {"limit": limit}
        for key in ("name", "extension", "file_type", "category", "text_search"):
            if key in args and args[key]:
                query_kwargs[key] = args[key]

        results = catalog.query(**query_kwargs)

        # Build response
        parts: list[str] = []

        if show_stats:
            stats = catalog.get_stats()
            parts.append(
                f"Catalog: {stats['total_files']} files, "
                f"{stats['total_size_bytes'] / 1024 / 1024:.1f} MB total"
            )
            if stats["by_type"]:
                type_str = ", ".join(
                    f"{v} {k}" for k, v in sorted(stats["by_type"].items(), key=lambda x: -x[1])
                )
                parts.append(f"Types: {type_str}")
            parts.append("")

        if not results and not show_stats:
            return "No files found matching the query."

        if results:
            parts.append(f"Found {len(results)} file(s):\n")
            for entry in results:
                line = f"  {entry.path}"
                details = []
                details.append(f"{entry.file_type}/{entry.category}")
                if entry.size_bytes >= 1024 * 1024:
                    details.append(f"{entry.size_bytes / 1024 / 1024:.1f} MB")
                else:
                    details.append(f"{entry.size_bytes / 1024:.1f} KB")
                if entry.converted_to:
                    details.append(f"converted: {entry.converted_to}")
                if entry.status != "current":
                    details.append(f"status: {entry.status}")
                line += f"  [{', '.join(details)}]"
                if entry.summary:
                    line += f"\n    Summary: {entry.summary}"
                parts.append(line)

        return "\n".join(parts)

    def is_available(self, agent_context: "AgentContext") -> bool:
        """Available whenever a catalog exists."""
        config_dir = agent_context.base_dir / ".flavia"
        return (config_dir / "content_catalog.json").exists()
