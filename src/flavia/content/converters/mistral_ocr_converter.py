"""OCR converter for scanned/image-based PDFs using the Mistral OCR API."""

import base64
import json
import os
import re
from pathlib import Path
from typing import Optional

from .base import BaseConverter


class MistralOcrConverter(BaseConverter):
    """Converts scanned/image-based PDFs to markdown using mistral-ocr-2512."""

    supported_extensions = {".pdf"}
    requires_dependencies = ["mistralai"]

    MIN_CHARS_PER_PAGE = 50

    def can_handle(self, file_path: Path) -> bool:
        # Not registered in the global registry; called explicitly by PdfConverter.
        return False

    def convert(
        self,
        source_path: Path,
        output_dir: Path,
        output_format: str = "md",
    ) -> Optional[Path]:
        """Run Mistral OCR on a PDF and write markdown (+ images) to output_dir."""
        md_text, images = self._run_mistral_ocr(source_path)
        if md_text is None:
            return None

        stem = source_path.stem

        # Save extracted images
        if images:
            images_dir = output_dir / f"{stem}_images"
            images_dir.mkdir(parents=True, exist_ok=True)
            img_name_map: dict[str, str] = {}
            for idx, (img_id, img_bytes) in enumerate(images, start=1):
                img_filename = f"img-{idx:04d}.png"
                (images_dir / img_filename).write_bytes(img_bytes)
                img_name_map[img_id] = f"{stem}_images/{img_filename}"

            # Replace image references in markdown
            def _replace_img(match: re.Match) -> str:
                alt = match.group(1)
                ref = match.group(2)
                new_ref = img_name_map.get(ref, ref)
                return f"![{alt}]({new_ref})"

            md_text = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", _replace_img, md_text)

        # Determine output path, preserving directory structure when possible
        try:
            relative_source = source_path.resolve().relative_to(output_dir.resolve().parent)
            output_file = output_dir / relative_source.with_suffix(f".{output_format}")
        except ValueError:
            output_file = output_dir / (stem + f".{output_format}")

        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(md_text, encoding="utf-8")
        return output_file

    def extract_text(self, source_path: Path) -> Optional[str]:
        """Return OCR'd markdown text without writing any files."""
        md_text, _ = self._run_mistral_ocr(source_path)
        return md_text

    def _run_mistral_ocr(
        self, pdf_path: Path
    ) -> tuple[Optional[str], list[tuple[str, bytes]]]:
        """Upload the PDF to Mistral and run OCR.

        Returns:
            (markdown_text, [(img_id, img_bytes), ...])
            On failure returns (None, []).
        """
        api_key = os.environ.get("MISTRAL_API_KEY")
        if not api_key:
            return None, []

        try:
            from mistralai import Mistral
            from mistralai.models import DocumentURLChunk
        except ImportError:
            return None, []

        try:
            client = Mistral(api_key=api_key)

            with open(pdf_path, "rb") as f:
                upload = client.files.upload(
                    file={"file_name": pdf_path.name, "content": f},
                    purpose="ocr",
                )

            signed = client.files.get_signed_url(file_id=upload.id, expiry=1)

            resp = client.ocr.process(
                model="mistral-ocr-2512",
                document=DocumentURLChunk(document_url=signed.url),
                include_image_base64=True,
            )

            data = json.loads(resp.model_dump_json())

            pages = data.get("pages", [])
            md_parts: list[str] = []
            images: list[tuple[str, bytes]] = []

            for page in pages:
                md_parts.append(page.get("markdown", ""))
                for img in page.get("images", []):
                    img_id = img.get("id", "")
                    b64_data = img.get("image_base64", "")
                    if b64_data:
                        # Strip data URI prefix if present
                        if "," in b64_data:
                            b64_data = b64_data.split(",", 1)[1]
                        img_bytes = base64.b64decode(b64_data)
                        images.append((img_id, img_bytes))

            return "\n\n".join(md_parts), images

        except Exception:
            return None, []
