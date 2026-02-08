"""Tool for converting PDFs to text/markdown."""

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..base import BaseTool, ToolSchema, ToolParameter
from ..registry import register_tool

if TYPE_CHECKING:
    from flavia.agent.context import AgentContext


class ConvertPdfsTool(BaseTool):
    """Tool for converting PDF files to text/markdown."""

    name = "convert_pdfs"
    description = "Convert PDF files to text or markdown format for easier analysis"
    category = "setup"

    def get_schema(self, **context) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParameter(
                    name="pdf_files",
                    type="array",
                    description="List of PDF file paths to convert (relative to base directory)",
                    required=True,
                    items={"type": "string"},
                ),
                ToolParameter(
                    name="output_format",
                    type="string",
                    description="Output format: 'txt' for plain text, 'md' for markdown",
                    required=False,
                    enum=["txt", "md"],
                ),
                ToolParameter(
                    name="output_dir",
                    type="string",
                    description="Output directory for converted files (default: same as PDF, or 'converted/' subdirectory)",
                    required=False,
                ),
                ToolParameter(
                    name="preserve_structure",
                    type="boolean",
                    description="Try to preserve document structure (headings, paragraphs) in markdown output",
                    required=False,
                ),
            ]
        )

    def execute(self, args: dict[str, Any], agent_context: "AgentContext") -> str:
        pdf_files = args.get("pdf_files", [])
        output_format = args.get("output_format", "md")
        output_dir = args.get("output_dir", "")
        preserve_structure = args.get("preserve_structure", True)

        if not pdf_files:
            return "Error: pdf_files is required"

        base_dir = agent_context.base_dir.resolve()
        converted = []
        errors = []

        # Determine output directory
        if output_dir:
            out_path = (base_dir / output_dir).resolve()
        else:
            out_path = (base_dir / "converted").resolve()

        try:
            out_path.relative_to(base_dir)
        except ValueError:
            return f"Error: Access denied - output_dir '{output_dir}' is outside allowed directory"

        out_path.mkdir(parents=True, exist_ok=True)

        for pdf_file in pdf_files:
            pdf_path = (base_dir / pdf_file).resolve()

            try:
                pdf_path.relative_to(base_dir)
            except ValueError:
                errors.append(f"{pdf_file}: Access denied - file is outside allowed directory")
                continue

            if not pdf_path.exists():
                errors.append(f"{pdf_file}: File not found")
                continue

            if not pdf_path.is_file():
                errors.append(f"{pdf_file}: Not a file")
                continue

            if not pdf_path.suffix.lower() == ".pdf":
                errors.append(f"{pdf_file}: Not a PDF file")
                continue

            try:
                # Convert the PDF
                text = self._extract_text(pdf_path)

                if not text.strip():
                    errors.append(f"{pdf_file}: No text extracted (may need OCR)")
                    continue

                # Format output
                if output_format == "md" and preserve_structure:
                    content = self._format_as_markdown(text, pdf_path.stem)
                else:
                    content = text

                # Write output file
                output_name = pdf_path.stem + f".{output_format}"
                output_file = out_path / output_name
                output_file.write_text(content, encoding="utf-8")

                converted.append(f"{pdf_file} -> {output_file.relative_to(base_dir)}")

            except ImportError as e:
                return f"Error: PDF library not installed. Run: pip install pdfplumber\n{e}"
            except Exception as e:
                errors.append(f"{pdf_file}: {str(e)}")

        # Build result message
        result_parts = []

        if converted:
            result_parts.append(f"Successfully converted {len(converted)} file(s):")
            for c in converted:
                result_parts.append(f"  - {c}")

        if errors:
            result_parts.append(f"\nErrors ({len(errors)}):")
            for e in errors:
                result_parts.append(f"  - {e}")

        if not converted and not errors:
            return "No files to convert"

        return "\n".join(result_parts)

    def _extract_text(self, pdf_path: Path) -> str:
        """Extract text from PDF using pdfplumber."""
        try:
            import pdfplumber
        except ImportError:
            # Fallback to pypdf
            try:
                from pypdf import PdfReader
                reader = PdfReader(str(pdf_path))
                text_parts = []
                for page in reader.pages:
                    text_parts.append(page.extract_text() or "")
                return "\n\n".join(text_parts)
            except ImportError:
                raise ImportError("Neither pdfplumber nor pypdf is installed")

        text_parts = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    text_parts.append(text)

        return "\n\n".join(text_parts)

    def _format_as_markdown(self, text: str, title: str) -> str:
        """Format extracted text as markdown with basic structure."""
        lines = []

        # Add title
        clean_title = title.replace("_", " ").replace("-", " ")
        lines.append(f"# {clean_title}")
        lines.append("")

        # Process text
        paragraphs = text.split("\n\n")

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            # Detect potential headings (all caps, short lines)
            if para.isupper() and len(para) < 100 and "\n" not in para:
                lines.append(f"\n## {para.title()}\n")
            # Detect numbered sections
            elif re.match(r"^\d+\.\s+[A-Z]", para):
                lines.append(f"\n### {para}\n")
            else:
                # Regular paragraph - clean up line breaks within
                cleaned = " ".join(para.split())
                lines.append(cleaned)
                lines.append("")

        return "\n".join(lines)

    def is_available(self, agent_context: "AgentContext") -> bool:
        """Only available in setup mode."""
        return getattr(agent_context, 'setup_mode', False)


# Don't auto-register - registered manually during setup
