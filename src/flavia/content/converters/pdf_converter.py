"""PDF to text/markdown converter.

Migrated and refactored from tools/setup/convert_pdfs.py.
"""

import re
from pathlib import Path
from typing import Optional

from .base import BaseConverter


class PdfConverter(BaseConverter):
    """Converts PDF files to text or markdown format."""

    supported_extensions = {".pdf"}

    def convert(
        self,
        source_path: Path,
        output_dir: Path,
        output_format: str = "md",
    ) -> Optional[Path]:
        """Convert a PDF file to text or markdown."""
        text = self.extract_text(source_path)
        if not text or not text.strip():
            return None

        if output_format == "md":
            content = self._format_as_markdown(text, source_path.stem)
        else:
            content = text

        # Preserve directory structure when source lives under output_dir.parent.
        # Fallback to flat output if source is outside that tree.
        try:
            relative_source = source_path.resolve().relative_to(output_dir.resolve().parent)
            output_file = output_dir / relative_source.with_suffix(f".{output_format}")
        except ValueError:
            output_file = output_dir / (source_path.stem + f".{output_format}")
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(content, encoding="utf-8")
        return output_file

    def extract_text(self, source_path: Path) -> Optional[str]:
        """Extract text from a PDF using pdfplumber (with pypdf fallback)."""
        try:
            return self._extract_with_pdfplumber(source_path)
        except ImportError:
            pass

        try:
            return self._extract_with_pypdf(source_path)
        except ImportError:
            return None
        except Exception:
            return None

    @staticmethod
    def _extract_with_pdfplumber(pdf_path: Path) -> str:
        """Extract text using pdfplumber."""
        import pdfplumber

        text_parts = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    text_parts.append(text)

        return "\n\n".join(text_parts)

    @staticmethod
    def _extract_with_pypdf(pdf_path: Path) -> str:
        """Fallback: extract text using pypdf."""
        from pypdf import PdfReader

        reader = PdfReader(str(pdf_path))
        text_parts = []
        for page in reader.pages:
            text_parts.append(page.extract_text() or "")
        return "\n\n".join(text_parts)

    @staticmethod
    def _format_as_markdown(text: str, title: str) -> str:
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
                # Regular paragraph — clean up line breaks within
                cleaned = " ".join(para.split())
                lines.append(cleaned)
                lines.append("")

        return "\n".join(lines)
