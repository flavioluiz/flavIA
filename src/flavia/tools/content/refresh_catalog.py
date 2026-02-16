"""Tool for refreshing the content catalog during a conversation."""

from typing import TYPE_CHECKING, Any

from ..base import BaseTool, ToolSchema, ToolParameter
from ..permissions import check_read_permission, check_write_permission

if TYPE_CHECKING:
    from flavia.agent.context import AgentContext


class RefreshCatalogTool(BaseTool):
    """Refresh the content catalog to detect new or modified files."""

    name = "refresh_catalog"
    description = (
        "Update the content catalog by scanning for new, modified, or deleted files. "
        "Optionally convert new/modified docs, audio, and video to text and generate summaries. "
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
                    description="Convert new/modified docs, audio, and video to text (default: false)",
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
        from flavia.content.converters import converter_registry

        convert = args.get("convert", False)
        remove_missing = args.get("remove_missing", True)

        config_dir = agent_context.base_dir / ".flavia"

        can_read_base, read_base_error = check_read_permission(agent_context.base_dir, agent_context)
        if not can_read_base:
            return f"Error: {read_base_error}"

        can_write_catalog, write_catalog_error = check_write_permission(config_dir, agent_context)
        if not can_write_catalog:
            return f"Error: {write_catalog_error}"

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

        # Convert new/modified supported files if requested
        if convert:
            converted_dir = agent_context.base_dir / ".converted"
            can_write_converted, write_converted_error = check_write_permission(
                converted_dir,
                agent_context,
            )
            if not can_write_converted:
                return f"Error: {write_converted_error}"

            needs_conversion = catalog.get_files_needing_conversion()
            if needs_conversion:
                converted_count = 0
                skipped_count = 0
                failed_count = 0
                for entry in needs_conversion:
                    source = agent_context.base_dir / entry.path
                    converter = converter_registry.get_for_file(source)
                    if not converter:
                        skipped_count += 1
                        continue

                    deps_ok, _missing = converter.check_dependencies()
                    if not deps_ok:
                        skipped_count += 1
                        continue

                    try:
                        result = converter.convert(source, converted_dir)
                    except Exception:
                        failed_count += 1
                        continue

                    if result:
                        try:
                            entry.converted_to = str(result.relative_to(agent_context.base_dir))
                        except ValueError:
                            entry.converted_to = str(result)
                        converted_count += 1
                    else:
                        failed_count += 1

                parts.append(f"\n  Converted {converted_count} file(s) to text")
                if failed_count:
                    parts.append(f"  Failed conversions: {failed_count}")
                if skipped_count:
                    parts.append(f"  Skipped conversions: {skipped_count}")

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
