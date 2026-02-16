"""Tests for PDF conversion flows with optional OCR."""

from pathlib import Path

from flavia.content.converters.mistral_ocr_converter import MistralOcrConverter
from flavia.content.converters.pdf_converter import PdfConverter


def test_pdf_converter_convert_does_not_use_ocr_without_opt_in(monkeypatch, tmp_path):
    source = tmp_path / "slides.pdf"
    source.write_bytes(b"%PDF-1.4")
    output_dir = tmp_path / ".converted"

    monkeypatch.setattr(PdfConverter, "_is_scanned_pdf", staticmethod(lambda _p: True))
    monkeypatch.setattr(PdfConverter, "_extract_with_pdfplumber", staticmethod(lambda _p: "Plain text"))
    monkeypatch.setattr(
        MistralOcrConverter,
        "convert",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("OCR should not be used")),
    )

    result = PdfConverter().convert(source, output_dir, allow_ocr=False)

    assert result is not None
    assert result.exists()
    assert result.read_text(encoding="utf-8").startswith("# slides")


def test_pdf_converter_convert_routes_to_ocr_when_opted_in(monkeypatch, tmp_path):
    source = tmp_path / "scan.pdf"
    source.write_bytes(b"%PDF-1.4")
    output_dir = tmp_path / ".converted"
    expected = output_dir / "scan.md"

    monkeypatch.setattr(PdfConverter, "_is_scanned_pdf", staticmethod(lambda _p: True))
    monkeypatch.setattr(
        PdfConverter,
        "_extract_with_pdfplumber",
        staticmethod(lambda _p: (_ for _ in ()).throw(AssertionError("Local extractor should not run"))),
    )
    monkeypatch.setattr(MistralOcrConverter, "convert", lambda *_args, **_kwargs: expected)

    result = PdfConverter().convert(source, output_dir, allow_ocr=True)

    assert result == expected


def test_mistral_ocr_converter_stores_images_next_to_nested_output(monkeypatch, tmp_path):
    source = tmp_path / "papers" / "doc.pdf"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"%PDF-1.4")
    output_dir = tmp_path / ".converted"

    monkeypatch.setattr(
        MistralOcrConverter,
        "_run_mistral_ocr",
        lambda _self, _pdf: ("![figure](img_ref_1)", [("img_ref_1", b"\x89PNG\r\n\x1a\n")]),
    )

    result = MistralOcrConverter().convert(source, output_dir)

    assert result == output_dir / "papers" / "doc.md"
    assert result is not None
    assert result.exists()
    image_file = output_dir / "papers" / "doc_images" / "img-0001.png"
    assert image_file.exists()
    assert "doc_images/img-0001.png" in result.read_text(encoding="utf-8")
