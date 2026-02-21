"""Tool for fetching an online source and converting it to markdown."""

from typing import TYPE_CHECKING, Any

from ..base import BaseTool, ToolParameter, ToolSchema
from ._conversion_helpers import load_catalog_with_permissions

if TYPE_CHECKING:
    from flavia.agent.context import AgentContext


class FetchOnlineSourceTool(BaseTool):
    """Download an online source and convert its content to markdown."""

    name = "fetch_online_source"
    description = (
        "Download an online source (YouTube video, webpage) and convert its content "
        "to markdown. The converted file is saved in .converted/ and the catalog is "
        "updated. If the URL is not yet in the catalog, it is registered first."
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
                    description="URL to fetch and convert (YouTube URL, webpage URL, etc.)",
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
        from flavia.content.converters import converter_registry

        source_url = (args.get("source_url") or "").strip()
        if not source_url:
            return "Error: source_url is required"

        source_type = (args.get("source_type") or "auto").strip().lower()
        tags = args.get("tags") or []

        catalog, config_dir, converted_dir, base_dir, err = load_catalog_with_permissions(
            agent_context
        )
        if err:
            return err

        # Find existing entry or register new one
        entry = next(
            (e for e in catalog.files.values() if e.source_url == source_url),
            None,
        )
        if entry is None:
            entry = catalog.add_online_source(source_url, source_type, tags if tags else None)
            if entry is None:
                return (
                    f"Error: Could not register source. "
                    f"URL may be unsupported or source_type is invalid. "
                    f"Try specifying source_type explicitly ('youtube' or 'webpage')."
                )
            # Persist registration even if fetch exits early (e.g., missing deps).
            catalog.save(config_dir)

        converter = converter_registry.get_for_source(entry.source_type)
        if converter is None:
            return f"Error: No converter found for source type: {entry.source_type}"

        if not converter.is_implemented:
            return (
                f"Error: Converter for '{entry.source_type}' is not yet implemented."
            )

        deps_ok, missing = converter.check_dependencies()
        if not deps_ok:
            return (
                f"Error: Missing dependencies for '{entry.source_type}': "
                f"{', '.join(missing)}.\n"
                f"Install with: pip install 'flavia[online]'"
            )

        output_dir = converted_dir / "_online" / entry.source_type

        try:
            result_path = converter.fetch_and_convert(source_url, output_dir)
        except Exception as e:
            entry.fetch_status = "failed"
            catalog.save(config_dir)
            return f"Error: Fetch failed: {e}"

        if result_path and result_path.exists():
            try:
                rel_converted = str(result_path.relative_to(base_dir))
            except ValueError:
                rel_converted = str(result_path)

            entry.converted_to = rel_converted
            entry.fetch_status = "completed"
            catalog.save(config_dir)

            return (
                f"Content fetched successfully:\n"
                f"  Source: {source_url}\n"
                f"  Type: {entry.source_type}\n"
                f"  Name: {entry.name}\n"
                f"  Converted to: {rel_converted}\n"
                f"  Catalog path: {entry.path}\n"
                f"\nContent is now searchable via search_chunks and query_catalog."
            )
        else:
            entry.fetch_status = "failed"
            catalog.save(config_dir)
            return f"Error: Fetch failed. No content was retrieved from {source_url}"

    def is_available(self, agent_context: "AgentContext") -> bool:
        config_dir = agent_context.base_dir / ".flavia"
        return (config_dir / "content_catalog.json").exists()
