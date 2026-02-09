"""Tool for getting the catalog context summary."""

from typing import TYPE_CHECKING, Any

from ..base import BaseTool, ToolSchema, ToolParameter
from ..permissions import check_read_permission

if TYPE_CHECKING:
    from flavia.agent.context import AgentContext


class GetSummaryTool(BaseTool):
    """Get an overview summary of the project content catalog."""

    name = "get_catalog_summary"
    description = (
        "Get a high-level overview of the project content: directory structure, "
        "file type breakdown, and file summaries. Useful for understanding "
        "what's available in the project before diving into specific files."
    )
    category = "content"

    def get_schema(self, **context) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParameter(
                    name="max_length",
                    type="integer",
                    description="Maximum character length of the summary (default: 3000)",
                    required=False,
                ),
                ToolParameter(
                    name="include_tree",
                    type="boolean",
                    description="Include directory tree structure (default: true)",
                    required=False,
                ),
            ],
        )

    def execute(self, args: dict[str, Any], agent_context: "AgentContext") -> str:
        from flavia.content.catalog import ContentCatalog

        config_dir = agent_context.base_dir / ".flavia"
        allowed, error_msg = check_read_permission(config_dir, agent_context)
        if not allowed:
            return f"Error: {error_msg}"

        catalog = ContentCatalog.load(config_dir)
        if catalog is None:
            return (
                "Error: No content catalog found. "
                "Run 'flavia --init' or 'flavia --update' to build the catalog."
            )

        max_length = args.get("max_length", 3000)
        include_tree = args.get("include_tree", True)

        # Generate the context summary
        summary = catalog.generate_context_summary(max_length=max_length)

        if not include_tree:
            # Strip tree section
            lines = summary.split("\n")
            filtered = []
            in_tree = False
            for line in lines:
                if line.strip().startswith("Directory structure:"):
                    in_tree = True
                    continue
                if in_tree and (line.strip().startswith("File summaries:") or not line.strip()):
                    if line.strip().startswith("File summaries:"):
                        in_tree = False
                        filtered.append(line)
                    continue
                if not in_tree:
                    filtered.append(line)
            summary = "\n".join(filtered)

        return summary

    def is_available(self, agent_context: "AgentContext") -> bool:
        """Available whenever a catalog exists."""
        config_dir = agent_context.base_dir / ".flavia"
        return (config_dir / "content_catalog.json").exists()
