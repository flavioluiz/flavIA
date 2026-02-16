"""Regression tests for content catalog CLI update flows."""

import time
from pathlib import Path
from types import SimpleNamespace

from flavia.cli import main, run_catalog_update
from flavia.content.catalog import ContentCatalog


def test_run_catalog_update_reconverts_modified_pdf(monkeypatch, tmp_path):
    pdf_path = tmp_path / "doc.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 original")

    config_dir = tmp_path / ".flavia"
    config_dir.mkdir()

    catalog = ContentCatalog(tmp_path)
    catalog.build()
    catalog.files["doc.pdf"].converted_to = ".converted/doc.md"
    catalog.save(config_dir)

    time.sleep(0.05)
    pdf_path.write_bytes(b"%PDF-1.4 modified")

    converted_calls: list[Path] = []

    def _fake_convert(source_path: Path, output_dir: Path, output_format: str = "md"):
        converted_calls.append(source_path)
        output_file = output_dir / source_path.with_suffix(f".{output_format}").name
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text("converted", encoding="utf-8")
        return output_file

    class _FakeConverter:
        @staticmethod
        def check_dependencies():
            return True, []

        @staticmethod
        def convert(source_path: Path, output_dir: Path, output_format: str = "md"):
            return _fake_convert(source_path, output_dir, output_format)

    monkeypatch.setattr(
        "flavia.content.converters.converter_registry.get_for_file",
        lambda _path: _FakeConverter(),
    )
    monkeypatch.chdir(tmp_path)

    assert run_catalog_update(convert=True) == 0
    assert converted_calls == [pdf_path]


def test_run_catalog_update_reconverts_modified_audio(monkeypatch, tmp_path):
    audio_path = tmp_path / "meeting.mp3"
    audio_path.write_bytes(b"audio-original")

    config_dir = tmp_path / ".flavia"
    config_dir.mkdir()

    catalog = ContentCatalog(tmp_path)
    catalog.build()
    catalog.files["meeting.mp3"].converted_to = ".converted/meeting.md"
    catalog.save(config_dir)

    time.sleep(0.05)
    audio_path.write_bytes(b"audio-modified")

    converted_calls: list[Path] = []

    def _fake_convert(source_path: Path, output_dir: Path, output_format: str = "md"):
        converted_calls.append(source_path)
        output_file = output_dir / source_path.with_suffix(f".{output_format}").name
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text("converted", encoding="utf-8")
        return output_file

    class _FakeConverter:
        @staticmethod
        def check_dependencies():
            return True, []

        @staticmethod
        def convert(source_path: Path, output_dir: Path, output_format: str = "md"):
            return _fake_convert(source_path, output_dir, output_format)

    monkeypatch.setattr(
        "flavia.content.converters.converter_registry.get_for_file",
        lambda _path: _FakeConverter(),
    )
    monkeypatch.chdir(tmp_path)

    assert run_catalog_update(convert=True) == 0
    assert converted_calls == [audio_path]


def test_main_passes_path_to_run_catalog_update(monkeypatch, tmp_path):
    args = SimpleNamespace(
        version=False,
        init=False,
        update=True,
        update_convert=False,
        update_summarize=False,
        update_full=False,
        path=str(tmp_path),
    )
    called = {}

    monkeypatch.setattr("flavia.cli.ensure_project_venv_and_reexec", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("flavia.cli.parse_args", lambda: args)
    monkeypatch.setattr(
        "flavia.cli.run_catalog_update",
        lambda **kwargs: called.update(kwargs) or 0,
    )

    assert main() == 0
    assert called["base_dir"] == tmp_path.resolve()


def test_run_catalog_update_uses_summary_model_override(monkeypatch, tmp_path):
    doc_path = tmp_path / "doc.md"
    doc_path.write_text("Some text content", encoding="utf-8")

    config_dir = tmp_path / ".flavia"
    config_dir.mkdir()
    catalog = ContentCatalog(tmp_path)
    catalog.build()
    catalog.save(config_dir)

    calls = []
    provider = SimpleNamespace(
        id="synthetic",
        api_key="test-key",
        api_base_url="https://api.example.com/v1",
        headers={},
    )

    class _FakeSettings:
        default_model = "synthetic:hf:zai-org/GLM-4.7"
        summary_model = "synthetic:hf:moonshotai/Kimi-K2-Instruct-0905"

        @staticmethod
        def resolve_model_with_provider(model_ref):
            calls.append(model_ref)
            return provider, str(model_ref).split(":", 1)[-1]

    monkeypatch.setattr("flavia.cli.load_settings", lambda: _FakeSettings())
    monkeypatch.setattr(
        "flavia.content.summarizer.summarize_file_with_quality",
        lambda *args, **kwargs: ("Resumo", "good"),
    )

    assert run_catalog_update(summarize=True, base_dir=tmp_path) == 0
    assert calls == ["synthetic:hf:moonshotai/Kimi-K2-Instruct-0905"]
