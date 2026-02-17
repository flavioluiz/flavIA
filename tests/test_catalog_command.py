"""Tests for the catalog command interface."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from flavia.content.catalog import ContentCatalog
from flavia.content.scanner import FileEntry
from flavia.interfaces.catalog_command import (
    _extract_youtube_frames,
    _browse_files,
    _format_size,
    _manage_media_files,
    _manage_office_files,
    _manage_online_sources,
    _manage_pdf_files,
    _offer_resummarization_with_quality,
    _show_overview,
    run_catalog_command,
)


class TestFormatSize:
    """Tests for the _format_size helper."""

    def test_bytes(self):
        """Format bytes."""
        assert _format_size(0) == "0 B"
        assert _format_size(512) == "512 B"
        assert _format_size(1023) == "1023 B"

    def test_kilobytes(self):
        """Format kilobytes."""
        assert _format_size(1024) == "1.0 KB"
        assert _format_size(2048) == "2.0 KB"
        assert _format_size(1536) == "1.5 KB"

    def test_megabytes(self):
        """Format megabytes."""
        assert _format_size(1024 * 1024) == "1.0 MB"
        assert _format_size(5 * 1024 * 1024) == "5.0 MB"

    def test_gigabytes(self):
        """Format gigabytes."""
        assert _format_size(1024 * 1024 * 1024) == "1.0 GB"
        assert _format_size(2 * 1024 * 1024 * 1024) == "2.0 GB"


class TestCatalogCommandFunctions:
    """Tests for catalog command helper functions."""

    def test_show_overview_displays_stats(self, tmp_path, capsys):
        """Overview shows catalog statistics."""
        # Create a catalog with some files
        (tmp_path / "test.py").write_text("code")
        (tmp_path / "doc.md").write_text("# Doc")
        config_dir = tmp_path / ".flavia"
        config_dir.mkdir()

        catalog = ContentCatalog(tmp_path)
        catalog.build()

        # Patch console to capture output
        with patch("flavia.interfaces.catalog_command.console") as mock_console:
            _show_overview(catalog)
            # Should have been called multiple times
            assert mock_console.print.called

    def test_browse_files_handles_empty_tree(self, tmp_path):
        """Browse handles catalog with no tree."""
        catalog = ContentCatalog(tmp_path)
        catalog.directory_tree = None

        with patch("flavia.interfaces.catalog_command.console") as mock_console:
            _browse_files(catalog)
            # Should print a message about no structure
            mock_console.print.assert_called()

    def test_show_online_sources_empty(self, tmp_path):
        """Show online sources when none exist."""
        catalog = ContentCatalog(tmp_path)
        catalog.build()

        settings = MagicMock()

        with patch("flavia.interfaces.catalog_command.console") as mock_console:
            _manage_online_sources(catalog, tmp_path / ".flavia", settings)
            # Should print a message about no sources
            mock_console.print.assert_called()

    def test_extract_youtube_frames_updates_catalog_entry(self, tmp_path, monkeypatch):
        """YouTube frame extraction stores frame description paths in entry metadata."""
        config_dir = tmp_path / ".flavia"
        config_dir.mkdir()
        converted_dir = tmp_path / ".converted"
        converted_dir.mkdir()
        transcript_path = converted_dir / "_online" / "youtube" / "svd.md"
        transcript_path.parent.mkdir(parents=True, exist_ok=True)
        transcript_path.write_text(
            "# Transcript\n\n[00:00 - 00:02] Intro",
            encoding="utf-8",
        )
        frame_md = converted_dir / "_online" / "youtube" / "video_frames" / "frame_00m00s.md"
        frame_md.parent.mkdir(parents=True, exist_ok=True)
        frame_md.write_text("Frame description", encoding="utf-8")

        now = "2026-02-17T00:00:00+00:00"
        entry = FileEntry(
            path="_online/youtube/hash123",
            name="SVD Overview",
            extension="",
            file_type="online",
            category="youtube",
            size_bytes=0,
            created_at=now,
            modified_at=now,
            indexed_at=now,
            checksum_sha256="",
            source_type="youtube",
            source_url="https://www.youtube.com/watch?v=gXbThCXjZFM",
            converted_to=".converted/_online/youtube/svd.md",
            fetch_status="completed",
        )

        catalog = ContentCatalog(tmp_path)
        catalog.files[entry.path] = entry
        settings = MagicMock()

        class _FakeYouTubeConverter:
            def check_dependencies(self):
                return True, []

            def _has_yt_dlp(self):
                return True

            def extract_and_describe_frames(
                self,
                source_url,
                transcript,
                base_output_dir,
                settings,
            ):
                assert source_url == entry.source_url
                assert "[00:00 - 00:02]" in transcript
                assert base_output_dir == converted_dir / "_online" / "youtube"
                return [frame_md], [0.0]

        monkeypatch.setattr(
            "flavia.content.converters.online.youtube.YouTubeConverter",
            _FakeYouTubeConverter,
        )

        with (
            patch("flavia.interfaces.catalog_command.console") as mock_console,
            patch("flavia.interfaces.catalog_command._prompt_yes_no", return_value=False),
        ):
            _extract_youtube_frames(
                entry,
                catalog,
                config_dir,
                tmp_path,
                converted_dir,
                settings,
            )

        assert len(entry.frame_descriptions) == 1
        assert (
            entry.frame_descriptions[0]
            == ".converted/_online/youtube/video_frames/frame_00m00s.md"
        )
        printed = " ".join(
            " ".join(str(arg) for arg in call.args) for call in mock_console.print.call_args_list
        )
        assert "Generated 1 frame descriptions" in printed


class TestRunCatalogCommand:
    """Tests for the main run_catalog_command function."""

    def test_no_catalog_returns_false(self, tmp_path):
        """Returns False when no catalog exists."""
        config_dir = tmp_path / ".flavia"
        config_dir.mkdir()

        settings = MagicMock()
        settings.base_dir = tmp_path

        with patch("flavia.interfaces.catalog_command.console") as mock_console:
            result = run_catalog_command(settings)
            assert result is False

    def test_quit_immediately(self, tmp_path):
        """Quit option exits the menu."""
        (tmp_path / "test.txt").write_text("hello")
        config_dir = tmp_path / ".flavia"
        config_dir.mkdir()

        catalog = ContentCatalog(tmp_path)
        catalog.build()
        catalog.save(config_dir)

        settings = MagicMock()
        settings.base_dir = tmp_path

        with (
            patch("flavia.interfaces.catalog_command.console") as mock_console,
            patch("flavia.interfaces.catalog_command.q_select") as mock_q_select,
        ):
            # Mock q_select to return 'q' immediately
            mock_q_select.return_value = "q"

            result = run_catalog_command(settings)
            assert result is True

    def test_overview_option(self, tmp_path):
        """Option 1 shows overview."""
        (tmp_path / "test.txt").write_text("hello")
        config_dir = tmp_path / ".flavia"
        config_dir.mkdir()

        catalog = ContentCatalog(tmp_path)
        catalog.build()
        catalog.save(config_dir)

        settings = MagicMock()
        settings.base_dir = tmp_path

        with (
            patch("flavia.interfaces.catalog_command.console") as mock_console,
            patch("flavia.interfaces.catalog_command.q_select") as mock_q_select,
        ):
            # Return "1" first, then "q" to exit
            mock_q_select.side_effect = ["1", "q"]

            result = run_catalog_command(settings)
            assert result is True
            # Should have printed overview
            assert mock_console.print.call_count > 2


class TestCatalogCommandIntegration:
    """Integration tests for catalog command with real catalog."""

    def test_full_workflow(self, tmp_path):
        """Test a realistic workflow through the menu."""
        # Create some test files
        (tmp_path / "code.py").write_text("print('hello')")
        (tmp_path / "readme.md").write_text("# Project")
        sub = tmp_path / "docs"
        sub.mkdir()
        (sub / "guide.txt").write_text("User guide content")

        config_dir = tmp_path / ".flavia"
        config_dir.mkdir()

        catalog = ContentCatalog(tmp_path)
        catalog.build()
        catalog.files["readme.md"].summary = "Project documentation"
        catalog.save(config_dir)

        settings = MagicMock()
        settings.base_dir = tmp_path

        with (
            patch("flavia.interfaces.catalog_command.console") as mock_console,
            patch("flavia.interfaces.catalog_command.q_select") as mock_q_select,
        ):
            # Simulate: overview -> browse -> summaries -> quit
            mock_q_select.side_effect = ["1", "2", "4", "q"]

            result = run_catalog_command(settings)
            assert result is True


def test_manage_pdf_files_blocks_path_traversal(monkeypatch, tmp_path):
    config_dir = tmp_path / ".flavia"
    config_dir.mkdir()

    catalog = ContentCatalog(tmp_path)
    catalog.files["../secret.pdf"] = FileEntry(
        path="../secret.pdf",
        name="secret.pdf",
        extension=".pdf",
        file_type="binary_document",
        category="pdf",
        size_bytes=10,
        created_at="2026-01-01T00:00:00+00:00",
        modified_at="2026-01-01T00:00:00+00:00",
        indexed_at="2026-01-01T00:00:00+00:00",
        checksum_sha256="abc",
    )

    settings = MagicMock()
    settings.default_model = "openai:test"

    convert_calls = []

    def _fake_convert(self, source_path, output_dir, output_format="md"):
        convert_calls.append((source_path, output_dir, output_format))
        return None

    with (
        patch("flavia.interfaces.catalog_command.console") as mock_console,
        patch(
            "flavia.interfaces.catalog_command.q_select",
            side_effect=["../secret.pdf", "simple", "__back__"],
        ),
        patch("flavia.content.converters.PdfConverter.convert", _fake_convert),
    ):
        _manage_pdf_files(catalog, config_dir, settings)

    assert convert_calls == []
    printed = " ".join(
        " ".join(str(arg) for arg in call.args) for call in mock_console.print.call_args_list
    )
    assert "Blocked unsafe path outside project directory" in printed


def test_manage_office_files_blocks_path_traversal(monkeypatch, tmp_path):
    config_dir = tmp_path / ".flavia"
    config_dir.mkdir()

    catalog = ContentCatalog(tmp_path)
    catalog.files["../secret.docx"] = FileEntry(
        path="../secret.docx",
        name="secret.docx",
        extension=".docx",
        file_type="binary_document",
        category="word",
        size_bytes=10,
        created_at="2026-01-01T00:00:00+00:00",
        modified_at="2026-01-01T00:00:00+00:00",
        indexed_at="2026-01-01T00:00:00+00:00",
        checksum_sha256="abc",
    )

    settings = MagicMock()
    settings.default_model = "openai:test"

    convert_calls = []

    def _fake_convert(self, source_path, output_dir, output_format="md"):
        convert_calls.append((source_path, output_dir, output_format))
        return None

    with (
        patch("flavia.interfaces.catalog_command.console") as mock_console,
        patch(
            "flavia.interfaces.catalog_command.q_select",
            side_effect=["../secret.docx", "convert", "__back__"],
        ),
        patch("flavia.content.converters.OfficeConverter.convert", _fake_convert),
        patch(
            "flavia.content.converters.OfficeConverter.check_dependencies",
            return_value=(True, []),
        ),
    ):
        _manage_office_files(catalog, config_dir, settings)

    assert convert_calls == []
    printed = " ".join(
        " ".join(str(arg) for arg in call.args) for call in mock_console.print.call_args_list
    )
    assert "Blocked unsafe path outside project directory" in printed


def test_manage_media_files_blocks_path_traversal(monkeypatch, tmp_path):
    config_dir = tmp_path / ".flavia"
    config_dir.mkdir()

    catalog = ContentCatalog(tmp_path)
    catalog.files["../secret.mp3"] = FileEntry(
        path="../secret.mp3",
        name="secret.mp3",
        extension=".mp3",
        file_type="audio",
        category="mp3",
        size_bytes=10,
        created_at="2026-01-01T00:00:00+00:00",
        modified_at="2026-01-01T00:00:00+00:00",
        indexed_at="2026-01-01T00:00:00+00:00",
        checksum_sha256="abc",
    )

    settings = MagicMock()
    settings.default_model = "openai:test"

    convert_calls = []

    def _fake_convert(self, source_path, output_dir, output_format="md"):
        convert_calls.append((source_path, output_dir, output_format))
        return None

    with (
        patch("flavia.interfaces.catalog_command.console") as mock_console,
        patch(
            "flavia.interfaces.catalog_command.q_select",
            side_effect=["../secret.mp3", "transcribe", "__back__"],
        ),
        patch("flavia.content.converters.AudioConverter.convert", _fake_convert),
    ):
        _manage_media_files(catalog, config_dir, settings)

    assert convert_calls == []
    printed = " ".join(
        " ".join(str(arg) for arg in call.args) for call in mock_console.print.call_args_list
    )
    assert "Blocked unsafe path outside project directory" in printed


def test_manage_media_files_transcribe_can_resummarize_with_quality(monkeypatch, tmp_path):
    config_dir = tmp_path / ".flavia"
    config_dir.mkdir()
    (tmp_path / "lecture.mp3").write_bytes(b"\xff\xfb\x90\x00")
    (tmp_path / ".converted").mkdir()
    converted_path = tmp_path / ".converted" / "lecture.md"
    converted_path.write_text("transcript", encoding="utf-8")

    catalog = ContentCatalog(tmp_path)
    catalog.files["lecture.mp3"] = FileEntry(
        path="lecture.mp3",
        name="lecture.mp3",
        extension=".mp3",
        file_type="audio",
        category="mp3",
        size_bytes=10,
        created_at="2026-01-01T00:00:00+00:00",
        modified_at="2026-01-01T00:00:00+00:00",
        indexed_at="2026-01-01T00:00:00+00:00",
        checksum_sha256="abc",
    )

    settings = MagicMock()
    settings.default_model = "openai:test"
    settings.resolve_model_with_provider.return_value = (
        SimpleNamespace(
            id="openai",
            api_key="test-key",
            api_base_url="https://api.example.com/v1",
            headers={},
        ),
        "test-model",
    )

    with (
        patch("flavia.interfaces.catalog_command.console") as mock_console,
        patch(
            "flavia.interfaces.catalog_command.q_select",
            side_effect=["lecture.mp3", "transcribe", "Yes", "Yes", "__back__"],
        ),
        patch(
            "flavia.content.converters.AudioConverter.check_dependencies",
            return_value=(True, []),
        ),
        patch(
            "flavia.content.converters.AudioConverter.convert",
            lambda self, source_path, output_dir, output_format="md": converted_path,
        ),
        patch(
            "flavia.content.summarizer.summarize_file_with_quality",
            lambda *args, **kwargs: ("Resumo da transcrição", "good"),
        ),
    ):
        _manage_media_files(catalog, config_dir, settings)

    assert catalog.files["lecture.mp3"].converted_to == ".converted/lecture.md"
    assert catalog.files["lecture.mp3"].summary == "Resumo da transcrição"
    assert catalog.files["lecture.mp3"].extraction_quality == "good"
    printed = " ".join(
        " ".join(str(arg) for arg in call.args) for call in mock_console.print.call_args_list
    )
    assert "Transcription complete:" in printed
    assert "Re-summarized." in printed


def test_manage_pdf_files_simple_can_resummarize_with_quality(monkeypatch, tmp_path):
    config_dir = tmp_path / ".flavia"
    config_dir.mkdir()
    (tmp_path / "paper.pdf").write_bytes(b"%PDF")

    catalog = ContentCatalog(tmp_path)
    catalog.files["paper.pdf"] = FileEntry(
        path="paper.pdf",
        name="paper.pdf",
        extension=".pdf",
        file_type="binary_document",
        category="pdf",
        size_bytes=10,
        created_at="2026-01-01T00:00:00+00:00",
        modified_at="2026-01-01T00:00:00+00:00",
        indexed_at="2026-01-01T00:00:00+00:00",
        checksum_sha256="abc",
    )

    settings = MagicMock()
    settings.default_model = "openai:test"
    settings.resolve_model_with_provider.return_value = (
        SimpleNamespace(
            api_key="test-key",
            api_base_url="https://api.example.com/v1",
            headers={},
        ),
        "test-model",
    )

    converted_path = tmp_path / ".converted" / "paper.md"

    with (
        patch("flavia.interfaces.catalog_command.console") as mock_console,
        patch(
            "flavia.interfaces.catalog_command.q_select",
            side_effect=["paper.pdf", "simple", "yes", "__back__"],
        ),
        patch(
            "flavia.content.converters.PdfConverter.convert",
            lambda self, source_path, output_dir, output_format="md": converted_path,
        ),
        patch(
            "flavia.content.summarizer.summarize_file_with_quality",
            lambda *args, **kwargs: ("Resumo do documento", "good"),
        ),
    ):
        _manage_pdf_files(catalog, config_dir, settings)

    assert catalog.files["paper.pdf"].summary == "Resumo do documento"
    assert catalog.files["paper.pdf"].extraction_quality == "good"
    printed = " ".join(
        " ".join(str(arg) for arg in call.args) for call in mock_console.print.call_args_list
    )
    assert "Re-summarized." in printed


def test_manage_pdf_files_simple_warns_when_provider_key_missing(monkeypatch, tmp_path):
    config_dir = tmp_path / ".flavia"
    config_dir.mkdir()
    (tmp_path / "paper.pdf").write_bytes(b"%PDF")

    catalog = ContentCatalog(tmp_path)
    catalog.files["paper.pdf"] = FileEntry(
        path="paper.pdf",
        name="paper.pdf",
        extension=".pdf",
        file_type="binary_document",
        category="pdf",
        size_bytes=10,
        created_at="2026-01-01T00:00:00+00:00",
        modified_at="2026-01-01T00:00:00+00:00",
        indexed_at="2026-01-01T00:00:00+00:00",
        checksum_sha256="abc",
    )

    settings = MagicMock()
    settings.default_model = "openai:test"
    settings.resolve_model_with_provider.return_value = (
        SimpleNamespace(api_key=None, api_base_url="", headers={}),
        "test-model",
    )

    converted_path = tmp_path / ".converted" / "paper.md"

    with (
        patch("flavia.interfaces.catalog_command.console") as mock_console,
        patch(
            "flavia.interfaces.catalog_command.q_select",
            side_effect=["paper.pdf", "simple", "Yes", "No", "__back__"],
        ),
        patch(
            "flavia.content.converters.PdfConverter.convert",
            lambda self, source_path, output_dir, output_format="md": converted_path,
        ),
    ):
        _manage_pdf_files(catalog, config_dir, settings)

    printed = " ".join(
        " ".join(str(arg) for arg in call.args) for call in mock_console.print.call_args_list
    )
    assert (
        "Summary/quality skipped: no API key configured for the active model provider." in printed
    )


def test_manage_pdf_files_resummarize_does_not_reextract(monkeypatch, tmp_path):
    config_dir = tmp_path / ".flavia"
    config_dir.mkdir()
    (tmp_path / "paper.pdf").write_bytes(b"%PDF")
    (tmp_path / ".converted").mkdir()
    (tmp_path / ".converted" / "paper.md").write_text("converted", encoding="utf-8")

    catalog = ContentCatalog(tmp_path)
    catalog.files["paper.pdf"] = FileEntry(
        path="paper.pdf",
        name="paper.pdf",
        extension=".pdf",
        file_type="binary_document",
        category="pdf",
        size_bytes=10,
        created_at="2026-01-01T00:00:00+00:00",
        modified_at="2026-01-01T00:00:00+00:00",
        indexed_at="2026-01-01T00:00:00+00:00",
        checksum_sha256="abc",
        converted_to=".converted/paper.md",
    )

    settings = MagicMock()
    settings.default_model = "openai:test"
    settings.resolve_model_with_provider.return_value = (
        SimpleNamespace(
            id="openai",
            api_key="test-key",
            api_base_url="https://api.example.com/v1",
            headers={},
        ),
        "test-model",
    )

    with (
        patch("flavia.interfaces.catalog_command.console"),
        patch(
            "flavia.interfaces.catalog_command.q_select",
            side_effect=["paper.pdf", "resummarize", "__back__"],
        ),
        patch(
            "flavia.content.converters.PdfConverter.convert",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("Should not reconvert")),
        ),
        patch(
            "flavia.content.summarizer.summarize_file_with_quality",
            lambda *args, **kwargs: ("Resumo atualizado", "good"),
        ),
    ):
        _manage_pdf_files(catalog, config_dir, settings)

    assert catalog.files["paper.pdf"].summary == "Resumo atualizado"
    assert catalog.files["paper.pdf"].extraction_quality == "good"


def test_offer_resummarization_retries_after_model_switch(monkeypatch, tmp_path):
    (tmp_path / ".converted").mkdir()
    (tmp_path / ".converted" / "paper.md").write_text("converted", encoding="utf-8")
    entry = FileEntry(
        path="paper.pdf",
        name="paper.pdf",
        extension=".pdf",
        file_type="binary_document",
        category="pdf",
        size_bytes=10,
        created_at="2026-01-01T00:00:00+00:00",
        modified_at="2026-01-01T00:00:00+00:00",
        indexed_at="2026-01-01T00:00:00+00:00",
        checksum_sha256="abc",
        converted_to=".converted/paper.md",
    )

    settings = MagicMock()
    settings.default_model = "provider:model-a"
    settings.summary_model = None

    provider = SimpleNamespace(
        id="provider",
        api_key="key",
        api_base_url="https://api.example.com/v1",
        headers={},
    )
    settings.resolve_model_with_provider.side_effect = lambda model_ref: (
        provider,
        str(model_ref).split(":", 1)[-1],
    )

    summarize_results = iter([(None, None), ("Resumo final", "partial")])
    monkeypatch.setattr(
        "flavia.content.summarizer.summarize_file_with_quality",
        lambda *args, **kwargs: next(summarize_results),
    )
    monkeypatch.setattr(
        "flavia.content.summarizer.get_last_llm_call_info",
        lambda: {},
    )
    monkeypatch.setattr(
        "flavia.interfaces.catalog_command._prompt_yes_no",
        lambda *args, **kwargs: True,
    )

    def _switch_model(_settings):
        _settings.summary_model = "provider:model-b"
        return True

    monkeypatch.setattr(
        "flavia.interfaces.catalog_command._select_model_for_summary",
        _switch_model,
    )

    with patch("flavia.interfaces.catalog_command.console") as mock_console:
        _offer_resummarization_with_quality(entry, tmp_path, settings, ask_confirmation=False)

    assert entry.summary == "Resumo final"
    assert entry.extraction_quality == "partial"
    printed = " ".join(
        " ".join(str(arg) for arg in call.args) for call in mock_console.print.call_args_list
    )
    assert "Re-summarized." in printed


def test_offer_resummarization_auto_fallbacks_to_instruct(monkeypatch, tmp_path):
    (tmp_path / ".converted").mkdir()
    (tmp_path / ".converted" / "paper.md").write_text("converted", encoding="utf-8")
    entry = FileEntry(
        path="paper.pdf",
        name="paper.pdf",
        extension=".pdf",
        file_type="binary_document",
        category="pdf",
        size_bytes=10,
        created_at="2026-01-01T00:00:00+00:00",
        modified_at="2026-01-01T00:00:00+00:00",
        indexed_at="2026-01-01T00:00:00+00:00",
        checksum_sha256="abc",
        converted_to=".converted/paper.md",
    )

    provider = SimpleNamespace(
        id="synthetic",
        api_key="key",
        api_base_url="https://api.example.com/v1",
        headers={},
        models=[
            SimpleNamespace(
                id="hf:zai-org/GLM-4.7",
                name="GLM-4.7",
                description="With reasoning capability",
            ),
            SimpleNamespace(
                id="hf:moonshotai/Kimi-K2-Instruct-0905",
                name="Kimi-K2-Instruct-0905",
                description="Instruction model",
            ),
        ],
    )

    settings = MagicMock()
    settings.default_model = "synthetic:hf:zai-org/GLM-4.7"
    settings.summary_model = None
    settings.providers = SimpleNamespace(providers={"synthetic": provider})
    settings.resolve_model_with_provider.side_effect = lambda model_ref: (
        provider,
        str(model_ref).split(":", 1)[-1],
    )

    called_models = []

    def _fake_summarize(*args, **kwargs):
        called_models.append(kwargs["model"])
        if kwargs["model"] == "hf:zai-org/GLM-4.7":
            return None, None
        return "Resumo final", "good"

    monkeypatch.setattr(
        "flavia.content.summarizer.summarize_file_with_quality",
        _fake_summarize,
    )
    monkeypatch.setattr(
        "flavia.content.summarizer.get_last_llm_call_info",
        lambda: {
            "status": "empty_after_retry",
            "first_finish_reason": "length",
            "retry_finish_reason": "length",
        },
    )

    with patch("flavia.interfaces.catalog_command.console") as mock_console:
        _offer_resummarization_with_quality(entry, tmp_path, settings, ask_confirmation=False)

    assert called_models == [
        "hf:zai-org/GLM-4.7",
        "hf:moonshotai/Kimi-K2-Instruct-0905",
    ]
    assert settings.summary_model == "synthetic:hf:moonshotai/Kimi-K2-Instruct-0905"
    assert entry.summary == "Resumo final"
    assert entry.extraction_quality == "good"
    printed = " ".join(
        " ".join(str(arg) for arg in call.args) for call in mock_console.print.call_args_list
    )
    assert "Retrying automatically with instruct model" in printed


def test_run_catalog_command_media_option_dispatches(monkeypatch, tmp_path):
    (tmp_path / "note.txt").write_text("hello")
    config_dir = tmp_path / ".flavia"
    config_dir.mkdir()

    catalog = ContentCatalog(tmp_path)
    catalog.build()
    catalog.save(config_dir)

    settings = MagicMock()
    settings.base_dir = tmp_path

    called = {"media": 0}

    def _fake_manage_media(_catalog, _config_dir, _settings):
        called["media"] += 1

    with (
        patch(
            "flavia.interfaces.catalog_command.q_select",
            side_effect=["10", "q"],
        ),
        patch(
            "flavia.interfaces.catalog_command._manage_media_files",
            _fake_manage_media,
        ),
    ):
        assert run_catalog_command(settings) is True

    assert called["media"] == 1
