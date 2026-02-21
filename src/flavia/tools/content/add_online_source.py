"""Tool for registering an online source URL in the catalog."""

from typing import TYPE_CHECKING, Any

from ..base import BaseTool, ToolParameter, ToolSchema
from ..permissions import check_read_permission, check_write_permission

if TYPE_CHECKING:
    from flavia.agent.context import AgentContext


class AddOnlineSourceTool(BaseTool):
    """Register a URL in the content catalog without downloading its content."""

    name = "add_online_source"
    description = (
        "Register a URL (YouTube video, webpage, etc.) in the content catalog "
        "without downloading its content. The source is catalogued with metadata "
        "and can be fetched later using fetch_online_source."
    )
    category = "content"

    def get_schema(self, **context) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParameter(
                    name="source_url",
                    type="string",
                    description="URL to register (YouTube URL, webpage URL, etc.)",
                    required=True,
                ),
                ToolParameter(
                    name="source_type",
                    type="string",
                    description=(
                        'Source type: "auto" detects from URL, "youtube", or "webpage". '
                        'Default: "auto"'
                    ),
                    required=False,
                    enum=["auto", "youtube", "webpage"],
                ),
                ToolParameter(
                    name="tags",
                    type="array",
                    description="Optional tags to associate with this source",
                    required=False,
                    items={"type": "string"},
                ),
            ],
        )

    def execute(self, args: dict[str, Any], agent_context: "AgentContext") -> str:
        from flavia.content.catalog import ContentCatalog

        source_url = (args.get("source_url") or "").strip()
        if not source_url:
            return "Error: source_url is required"

        source_type = (args.get("source_type") or "auto").strip().lower()
        tags = args.get("tags") or []

        base_dir = agent_context.base_dir
        config_dir = base_dir / ".flavia"

        can_read, err = check_read_permission(base_dir, agent_context)
        if not can_read:
            return f"Error: {err}"

        can_write, err = check_write_permission(config_dir, agent_context)
        if not can_write:
            return f"Error: {err}"

        catalog = ContentCatalog.load(config_dir)
        if catalog is None:
            return (
                "Error: No content catalog found. "
                "Run 'flavia --init' or 'flavia --update' to build the catalog."
            )

        # Check if URL already registered
        existing = next(
            (e for e in catalog.files.values() if e.source_url == source_url),
            None,
        )
        if existing:
            return (
                f"Source already registered:\n"
                f"  Path: {existing.path}\n"
                f"  Name: {existing.name}\n"
                f"  Type: {existing.source_type}\n"
                f"  Fetch status: {existing.fetch_status}\n"
                f"  Converted: {existing.converted_to or 'not yet fetched'}"
            )

        entry = catalog.add_online_source(source_url, source_type, tags if tags else None)
        if entry is None:
            return (
                f"Error: Could not register source. "
                f"URL may be unsupported or source_type is invalid. "
                f"Try specifying source_type explicitly ('youtube' or 'webpage')."
            )

        catalog.save(config_dir)

        parts = [
            f"Source registered successfully:",
            f"  Path: {entry.path}",
            f"  Name: {entry.name}",
            f"  Type: {entry.source_type}",
            f"  Fetch status: {entry.fetch_status}",
        ]
        if entry.source_metadata:
            meta = entry.source_metadata
            if meta.get("description"):
                parts.append(f"  Description: {meta['description'][:200]}")
            if meta.get("duration"):
                parts.append(f"  Duration: {meta['duration']}")
            if meta.get("author"):
                parts.append(f"  Author: {meta['author']}")
        if tags:
            parts.append(f"  Tags: {', '.join(tags)}")
        parts.append(
            f"\nUse fetch_online_source with source_url='{source_url}' to download content."
        )

        return "\n".join(parts)

    def is_available(self, agent_context: "AgentContext") -> bool:
        config_dir = agent_context.base_dir / ".flavia"
        return (config_dir / "content_catalog.json").exists()
