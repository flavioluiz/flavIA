"""Tool for converting Office documents (Word/Excel/PPT) to markdown."""

from typing import TYPE_CHECKING, Any

from ..base import BaseTool, ToolParameter, ToolSchema
from ._conversion_helpers import (
    load_catalog_with_permissions,
    resolve_and_find_entry,
    convert_and_update_catalog,
)

if TYPE_CHECKING:
    from flavia.agent.context import AgentContext

_SUPPORTED_EXTENSIONS = {
    ".docx", ".xlsx", ".pptx",
    ".doc", ".xls", ".ppt",
    ".odt", ".ods", ".odp",
}


class ConvertOfficeTool(BaseTool):
    """Convert a Microsoft Office or OpenDocument file to markdown."""

    name = "convert_office"
    description = (
        "Convert a Microsoft Office or OpenDocument file to markdown. "
        "Supports: .docx, .xlsx, .pptx, .doc, .xls, .ppt, .odt, .ods, .odp. "
        "The converted file is saved in .converted/ and the catalog is updated."
    )
    category = "content"

    def get_schema(self, **context) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParameter(
                    name="path",
                    type="string",
                    description=(
                        "Path to the Office document (relative to project root or absolute)"
                    ),
                    required=True,
                ),
            ],
        )

    def execute(self, args: dict[str, Any], agent_context: "AgentContext") -> str:
        from flavia.content.converters.office_converter import OfficeConverter

        path_str = (args.get("path") or "").strip()
        if not path_str:
            return "Error: path is required"

        catalog, config_dir, converted_dir, base_dir, err = load_catalog_with_permissions(
            agent_context
        )
        if err:
            return err

        full_path, entry, err = resolve_and_find_entry(path_str, agent_context, catalog)
        if err:
            return err

        ext = full_path.suffix.lower()
        if ext not in _SUPPORTED_EXTENSIONS:
            supported = ", ".join(sorted(_SUPPORTED_EXTENSIONS))
            return (
                f"Error: Unsupported file extension '{ext}'. "
                f"Supported: {supported}"
            )

        converter = OfficeConverter()
        deps_ok, missing = converter.check_dependencies()
        if not deps_ok:
            return (
                f"Error: Missing dependencies for Office conversion: "
                f"{', '.join(missing)}.\n"
                f"Install with: pip install 'flavia[office]'"
            )

        rel_converted, err = convert_and_update_catalog(
            converter, full_path, converted_dir, entry, base_dir, catalog, config_dir
        )
        if err:
            return err
        if rel_converted is None:
            return f"Error: Office document conversion failed for '{path_str}'."

        # Determine document type for user-friendly output
        doc_types = {
            ".docx": "Word document", ".doc": "Word document", ".odt": "Writer document",
            ".xlsx": "Excel spreadsheet", ".xls": "Excel spreadsheet", ".ods": "Calc spreadsheet",
            ".pptx": "PowerPoint presentation", ".ppt": "PowerPoint presentation",
            ".odp": "Impress presentation",
        }
        doc_type = doc_types.get(ext, "Office document")

        return (
            f"{doc_type} converted successfully:\n"
            f"  Source: {path_str}\n"
            f"  Type: {doc_type}\n"
            f"  Converted to: {rel_converted}\n"
            f"\nContent is now searchable via search_chunks and query_catalog."
        )

    def is_available(self, agent_context: "AgentContext") -> bool:
        config_dir = agent_context.base_dir / ".flavia"
        return (config_dir / "content_catalog.json").exists()
