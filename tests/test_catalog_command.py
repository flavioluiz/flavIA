"""Tests for the catalog command interface."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from flavia.content.catalog import ContentCatalog
from flavia.interfaces.catalog_command import (
    _format_size,
    _show_overview,
    _browse_files,
    _show_online_sources,
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

        with patch("flavia.interfaces.catalog_command.console") as mock_console:
            _show_online_sources(catalog)
            # Should print a message about no sources
            mock_console.print.assert_called()


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

        with patch("flavia.interfaces.catalog_command.console") as mock_console:
            # Mock input to return 'q' immediately
            mock_console.input.return_value = "q"

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

        with patch("flavia.interfaces.catalog_command.console") as mock_console:
            # Return "1" first, then "q" to exit
            mock_console.input.side_effect = ["1", "q"]

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

        with patch("flavia.interfaces.catalog_command.console") as mock_console:
            # Simulate: overview -> browse -> summaries -> quit
            mock_console.input.side_effect = ["1", "2", "4", "q"]

            result = run_catalog_command(settings)
            assert result is True
