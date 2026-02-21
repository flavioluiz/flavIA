"""Tool for converting a PDF file to markdown."""

from typing import TYPE_CHECKING, Any

from ..base import BaseTool, ToolParameter, ToolSchema
from ._conversion_helpers import (
    load_catalog_with_permissions,
    resolve_and_find_entry,
    convert_and_update_catalog,
)

if TYPE_CHECKING:
    from flavia.agent.context import AgentContext


class ConvertPdfTool(BaseTool):
    """Convert a PDF file to markdown text."""

    name = "convert_pdf"
    description = (
        "Convert a PDF file to markdown text. "
        "Supports simple text extraction (fast) and optional OCR via Mistral API "
        "for scanned or image-heavy documents. "
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
                    description="Path to the PDF file (relative to project root or absolute)",
                    required=True,
                ),
                ToolParameter(
                    name="use_ocr",
                    type="boolean",
                    description=(
                        "Use Mistral OCR for scanned/image-heavy PDFs. "
                        "Requires MISTRAL_API_KEY. Default: false (simple text extraction)"
                    ),
                    required=False,
                ),
            ],
        )

    def execute(self, args: dict[str, Any], agent_context: "AgentContext") -> str:
        path_str = (args.get("path") or "").strip()
        if not path_str:
            return "Error: path is required"

        use_ocr = bool(args.get("use_ocr", False))

        catalog, config_dir, converted_dir, base_dir, err = load_catalog_with_permissions(
            agent_context
        )
        if err:
            return err

        full_path, entry, err = resolve_and_find_entry(path_str, agent_context, catalog)
        if err:
            return err

        if full_path.suffix.lower() != ".pdf":
            return f"Error: '{path_str}' is not a PDF file (extension: {full_path.suffix})"

        if use_ocr:
            from flavia.content.converters.mistral_ocr_converter import MistralOcrConverter
            from flavia.content.converters.mistral_key_manager import get_mistral_api_key

            api_key = get_mistral_api_key(interactive=False)
            if not api_key:
                return (
                    "Error: MISTRAL_API_KEY is required for OCR. "
                    "Set it in .flavia/.env or as an environment variable."
                )
            converter = MistralOcrConverter()
            method = "OCR (Mistral)"
        else:
            from flavia.content.converters.pdf_converter import PdfConverter

            converter = PdfConverter()
            method = "simple text extraction"

        deps_ok, missing = converter.check_dependencies()
        if not deps_ok:
            return (
                f"Error: Missing dependencies for PDF conversion: "
                f"{', '.join(missing)}.\n"
                f"Install with: pip install 'flavia[pdf]'"
            )

        rel_converted, err = convert_and_update_catalog(
            converter, full_path, converted_dir, entry, base_dir, catalog, config_dir
        )
        if err:
            return err
        if rel_converted is None:
            return (
                f"Error: PDF conversion failed using {method}. "
                f"The file may contain no extractable text. "
                + ("" if use_ocr else "Try use_ocr=true for scanned documents.")
            )

        return (
            f"PDF converted successfully:\n"
            f"  Source: {path_str}\n"
            f"  Method: {method}\n"
            f"  Converted to: {rel_converted}\n"
            f"\nContent is now searchable via search_chunks and query_catalog."
        )

    def is_available(self, agent_context: "AgentContext") -> bool:
        config_dir = agent_context.base_dir / ".flavia"
        return (config_dir / "content_catalog.json").exists()
