"""Text reader for files that are already plain text."""

from pathlib import Path
from typing import Optional

from .base import BaseConverter
from ..scanner import TEXT_EXTENSIONS


class TextReader(BaseConverter):
    """
    Handles files that are already plain text.

    Doesn't need to 'convert' — just reads the content directly.
    """

    supported_extensions = TEXT_EXTENSIONS

    def convert(
        self,
        source_path: Path,
        output_dir: Path,
        output_format: str = "md",
    ) -> Optional[Path]:
        """
        Text files don't need conversion.

        Returns None to indicate no conversion was performed (the file
        is already readable as-is).
        """
        return None

    def extract_text(self, source_path: Path) -> Optional[str]:
        """Read text content from a text file."""
        try:
            return source_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                return source_path.read_text(encoding="latin-1")
            except Exception:
                return None
        except Exception:
            return None
