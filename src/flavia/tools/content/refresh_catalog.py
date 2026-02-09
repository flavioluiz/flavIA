"""Tool for refreshing the content catalog during a conversation."""

from typing import TYPE_CHECKING, Any

from ..base import BaseTool, ToolSchema, ToolParameter

if TYPE_CHECKING:
    from flavia.agent.context import AgentContext


class RefreshCatalogTool(BaseTool):
    """Refresh the content catalog to detect new or modified files."""

    name = "refresh_catalog"
    description = (
        "Update the content catalog by scanning for new, modified, or deleted files. "
        "Optionally convert new binary documents (PDFs) to text and generate summaries. "
        "Use this when you suspect the catalog is out of date."
    )
    category = "content"

    def get_schema(self, **context) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParameter(
                    name="convert",
                    type="boolean",
                    description="Convert new/modified binary documents (PDFs) to text (default: false)",
                    required=False,
                ),
                ToolParameter(
                    name="remove_missing",
                    type="boolean",
                    description="Remove entries for files that no longer exist on disk (default: true)",
                    required=False,
                ),
            ],
        )

    def execute(self, args: dict[str, Any], agent_context: "AgentContext") -> str:
        from flavia.content.catalog import ContentCatalog
        from flavia.content.converters import PdfConverter

        convert = args.get("convert", False)
        remove_missing = args.get("remove_missing", True)

        config_dir = agent_context.base_dir / ".flavia"
        catalog = ContentCatalog.load(config_dir)
        if catalog is None:
            return "Error: No content catalog found. Run 'flavia --init' to create one first."

        # Run incremental update
        update_result = catalog.update()
        counts = update_result["counts"]

        parts: list[str] = [
            f"Catalog updated:",
            f"  New files: {counts['new']}",
            f"  Modified files: {counts['modified']}",
            f"  Missing files: {counts['missing']}",
            f"  Unchanged: {counts['unchanged']}",
        ]

        # Convert new/modified binary documents if requested
        if convert:
            needs_conversion = catalog.get_files_needing_conversion()
            # Filter to only new/modified files
            to_convert = [
                e for e in needs_conversion if e.status in ("new", "modified") or not e.converted_to
            ]
            if to_convert:
                converter = PdfConverter()
                converted_dir = agent_context.base_dir / "converted"
                converted_count = 0
                for entry in to_convert:
                    source = agent_context.base_dir / entry.path
                    if not converter.can_handle(source):
                        continue
                    result = converter.convert(source, converted_dir)
                    if result:
                        try:
                            entry.converted_to = str(result.relative_to(agent_context.base_dir))
                        except ValueError:
                            entry.converted_to = str(result)
                        converted_count += 1

                parts.append(f"\n  Converted {converted_count} file(s) to text")

        # Remove missing entries
        if remove_missing and counts["missing"] > 0:
            removed = catalog.remove_missing()
            parts.append(f"  Removed {len(removed)} missing file(s) from catalog")

        # Mark all as current
        catalog.mark_all_current()

        # Save
        catalog.save(config_dir)

        # Show new/modified file details
        if update_result["new"]:
            parts.append(f"\nNew files:")
            for p in update_result["new"][:20]:
                parts.append(f"  + {p}")
            if len(update_result["new"]) > 20:
                parts.append(f"  ... and {len(update_result['new']) - 20} more")

        if update_result["modified"]:
            parts.append(f"\nModified files:")
            for p in update_result["modified"][:20]:
                parts.append(f"  ~ {p}")
            if len(update_result["modified"]) > 20:
                parts.append(f"  ... and {len(update_result['modified']) - 20} more")

        return "\n".join(parts)

    def is_available(self, agent_context: "AgentContext") -> bool:
        """Available whenever a catalog exists."""
        config_dir = agent_context.base_dir / ".flavia"
        return (config_dir / "content_catalog.json").exists()
