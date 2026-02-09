"""Tests for the content management system."""

import json
import os
import time
import hashlib
from pathlib import Path

import pytest

from flavia.content.scanner import FileScanner, FileEntry, DirectoryNode
from flavia.content.catalog import ContentCatalog, CATALOG_FILENAME
from flavia.content.converters import PdfConverter, TextReader


# ---------------------------------------------------------------------------
# FileScanner tests
# ---------------------------------------------------------------------------


class TestFileScanner:
    """Tests for the FileScanner class."""

    def test_scan_basic_directory(self, tmp_path):
        """Scan a simple directory and verify file entries."""
        # Create test files
        (tmp_path / "readme.md").write_text("# Hello")
        (tmp_path / "script.py").write_text("print('hello')")
        (tmp_path / "data.csv").write_text("a,b,c\n1,2,3")

        scanner = FileScanner(tmp_path)
        files, tree = scanner.scan()

        assert len(files) == 3
        assert tree.file_count == 3

        # Check file types
        by_name = {f.name: f for f in files}
        assert by_name["readme.md"].file_type == "text"
        assert by_name["readme.md"].category == "markdown"
        assert by_name["script.py"].file_type == "text"
        assert by_name["script.py"].category == "python"
        assert by_name["data.csv"].file_type == "text"
        assert by_name["data.csv"].category == "csv"

    def test_scan_nested_directories(self, tmp_path):
        """Scan nested directories and verify tree structure."""
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "file.txt").write_text("content")
        (tmp_path / "root.txt").write_text("root")

        scanner = FileScanner(tmp_path)
        files, tree = scanner.scan()

        assert len(files) == 2
        assert tree.file_count == 2
        assert len(tree.children) == 1
        assert tree.children[0].name == "sub"
        assert tree.children[0].file_count == 1

    def test_scan_ignores_default_dirs(self, tmp_path):
        """Verify that .git, __pycache__, etc. are ignored."""
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "config").write_text("git config")
        (tmp_path / "__pycache__").mkdir()
        (tmp_path / "__pycache__" / "mod.pyc").write_bytes(b"\x00")
        (tmp_path / "real.py").write_text("code")

        scanner = FileScanner(tmp_path)
        files, tree = scanner.scan()

        assert len(files) == 1
        assert files[0].name == "real.py"

    def test_scan_custom_ignore_patterns(self, tmp_path):
        """Verify custom ignore patterns work."""
        (tmp_path / "keep.py").write_text("keep")
        (tmp_path / "ignore_me.tmp").write_text("ignore")

        scanner = FileScanner(tmp_path, ignore_patterns=["*.tmp"])
        files, _ = scanner.scan()

        assert len(files) == 1
        assert files[0].name == "keep.py"

    def test_scan_ignores_converted_directories(self, tmp_path):
        """Converted outputs should not be indexed as separate source files."""
        (tmp_path / "paper.pdf").write_bytes(b"%PDF-1.4")

        # Create .converted directory with converted markdown
        converted_dir = tmp_path / ".converted"
        converted_dir.mkdir()
        (converted_dir / "paper.md").write_text("# converted", encoding="utf-8")

        scanner = FileScanner(tmp_path)
        files, _ = scanner.scan()
        paths = {f.path for f in files}

        # Original PDF should be indexed, but not the converted file
        assert "paper.pdf" in paths
        assert ".converted/paper.md" not in paths

    def test_file_entry_metadata(self, tmp_path):
        """Verify file entry contains correct metadata."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello world")

        scanner = FileScanner(tmp_path)
        files, _ = scanner.scan()

        entry = files[0]
        assert entry.name == "test.txt"
        assert entry.path == "test.txt"
        assert entry.extension == ".txt"
        assert entry.file_type == "text"
        assert entry.size_bytes == 11
        assert entry.checksum_sha256  # Not empty
        assert entry.status == "current"
        assert entry.created_at  # Not empty
        assert entry.modified_at  # Not empty
        assert entry.indexed_at  # Not empty

    def test_file_classification(self):
        """Test file type classification for various extensions."""
        classify = FileScanner._classify_file

        assert classify(".py") == ("text", "python")
        assert classify(".md") == ("text", "markdown")
        assert classify(".tex") == ("text", "latex")
        assert classify(".pdf") == ("binary_document", "pdf")
        assert classify(".docx") == ("binary_document", "word")
        assert classify(".png") == ("image", "png")
        assert classify(".mp3") == ("audio", "mp3")
        assert classify(".mp4") == ("video", "mp4")
        assert classify(".zip") == ("archive", "zip")
        assert classify(".xyz") == ("other", "xyz")

    def test_checksum_consistency(self, tmp_path):
        """Same content produces same checksum."""
        f1 = tmp_path / "file1.txt"
        f2 = tmp_path / "file2.txt"
        f1.write_text("identical content")
        f2.write_text("identical content")

        scanner = FileScanner(tmp_path)
        files, _ = scanner.scan()
        by_name = {f.name: f for f in files}

        assert by_name["file1.txt"].checksum_sha256 == by_name["file2.txt"].checksum_sha256

    def test_checksum_differs_for_different_content(self, tmp_path):
        """Different content produces different checksum."""
        f1 = tmp_path / "file1.txt"
        f2 = tmp_path / "file2.txt"
        f1.write_text("content A")
        f2.write_text("content B")

        scanner = FileScanner(tmp_path)
        files, _ = scanner.scan()
        by_name = {f.name: f for f in files}

        assert by_name["file1.txt"].checksum_sha256 != by_name["file2.txt"].checksum_sha256


# ---------------------------------------------------------------------------
# FileEntry serialization tests
# ---------------------------------------------------------------------------


class TestFileEntrySerialization:
    """Tests for FileEntry to_dict / from_dict."""

    def test_roundtrip(self):
        """Serialize and deserialize a FileEntry."""
        entry = FileEntry(
            path="papers/smith.pdf",
            name="smith.pdf",
            extension=".pdf",
            file_type="binary_document",
            category="pdf",
            size_bytes=1024,
            created_at="2025-01-01T00:00:00+00:00",
            modified_at="2025-06-01T00:00:00+00:00",
            indexed_at="2026-02-09T10:00:00+00:00",
            checksum_sha256="abc123",
            status="current",
            converted_to="converted/papers/smith.md",
            summary="A paper about CFD",
            tags=["cfd", "navier-stokes"],
        )

        d = entry.to_dict()
        restored = FileEntry.from_dict(d)

        assert restored.path == entry.path
        assert restored.converted_to == entry.converted_to
        assert restored.summary == entry.summary
        assert restored.tags == entry.tags
        assert restored.status == entry.status

    def test_minimal_entry(self):
        """Entry without optional fields serializes cleanly."""
        entry = FileEntry(
            path="file.py",
            name="file.py",
            extension=".py",
            file_type="text",
            category="python",
            size_bytes=100,
            created_at="2025-01-01T00:00:00+00:00",
            modified_at="2025-01-01T00:00:00+00:00",
            indexed_at="2025-01-01T00:00:00+00:00",
            checksum_sha256="abc",
        )

        d = entry.to_dict()
        assert "converted_to" not in d
        assert "summary" not in d
        assert "tags" not in d

    def test_online_source_fields_roundtrip(self):
        """Online source fields serialize and deserialize correctly."""
        entry = FileEntry(
            path="_online/youtube/abc123",
            name="Test Video",
            extension="",
            file_type="online",
            category="youtube",
            size_bytes=0,
            created_at="2025-01-01T00:00:00+00:00",
            modified_at="2025-01-01T00:00:00+00:00",
            indexed_at="2025-01-01T00:00:00+00:00",
            checksum_sha256="",
            source_type="youtube",
            source_url="https://youtube.com/watch?v=abc123",
            source_metadata={"title": "Test Video", "duration": 300},
            fetch_status="not_implemented",
        )

        d = entry.to_dict()
        assert d["source_type"] == "youtube"
        assert d["source_url"] == "https://youtube.com/watch?v=abc123"
        assert d["source_metadata"] == {"title": "Test Video", "duration": 300}
        assert d["fetch_status"] == "not_implemented"

        restored = FileEntry.from_dict(d)
        assert restored.source_type == entry.source_type
        assert restored.source_url == entry.source_url
        assert restored.source_metadata == entry.source_metadata
        assert restored.fetch_status == entry.fetch_status

    def test_local_file_defaults_not_serialized(self):
        """Local files don't serialize online source fields with defaults."""
        entry = FileEntry(
            path="file.py",
            name="file.py",
            extension=".py",
            file_type="text",
            category="python",
            size_bytes=100,
            created_at="2025-01-01T00:00:00+00:00",
            modified_at="2025-01-01T00:00:00+00:00",
            indexed_at="2025-01-01T00:00:00+00:00",
            checksum_sha256="abc",
        )

        d = entry.to_dict()
        # Default values should not be serialized
        assert "source_type" not in d
        assert "source_url" not in d
        assert "source_metadata" not in d
        assert "fetch_status" not in d

    def test_backwards_compatibility_from_old_catalog(self):
        """Old catalog entries without online fields load correctly."""
        old_data = {
            "path": "file.py",
            "name": "file.py",
            "extension": ".py",
            "file_type": "text",
            "category": "python",
            "size_bytes": 100,
            "created_at": "2025-01-01T00:00:00+00:00",
            "modified_at": "2025-01-01T00:00:00+00:00",
            "indexed_at": "2025-01-01T00:00:00+00:00",
            "checksum_sha256": "abc",
        }

        entry = FileEntry.from_dict(old_data)

        # Should have defaults for online fields
        assert entry.source_type == "local"
        assert entry.source_url is None
        assert entry.source_metadata == {}
        assert entry.fetch_status == "completed"


# ---------------------------------------------------------------------------
# DirectoryNode serialization tests
# ---------------------------------------------------------------------------


class TestDirectoryNodeSerialization:
    """Tests for DirectoryNode to_dict / from_dict."""

    def test_roundtrip(self):
        """Serialize and deserialize a DirectoryNode tree."""
        tree = DirectoryNode(
            path=".",
            name="project",
            summary="A research project",
            file_count=10,
            children=[
                DirectoryNode(
                    path="papers",
                    name="papers",
                    summary="Academic papers",
                    file_count=5,
                ),
                DirectoryNode(
                    path="notes",
                    name="notes",
                    file_count=5,
                ),
            ],
        )

        d = tree.to_dict()
        restored = DirectoryNode.from_dict(d)

        assert restored.name == "project"
        assert restored.summary == "A research project"
        assert len(restored.children) == 2
        assert restored.children[0].summary == "Academic papers"
        assert restored.children[1].summary is None


# ---------------------------------------------------------------------------
# ContentCatalog tests
# ---------------------------------------------------------------------------


class TestContentCatalog:
    """Tests for the ContentCatalog class."""

    def test_build_and_save(self, tmp_path):
        """Build a catalog and save it to disk."""
        (tmp_path / "file.py").write_text("code")
        (tmp_path / "doc.md").write_text("# Doc")
        config_dir = tmp_path / ".flavia"
        config_dir.mkdir()

        catalog = ContentCatalog(tmp_path)
        catalog.build()

        assert len(catalog.files) == 2
        assert catalog.directory_tree is not None

        path = catalog.save(config_dir)
        assert path.exists()

        # Verify JSON structure
        with open(path) as f:
            data = json.load(f)
        assert data["version"] == "1.0"
        assert len(data["files"]) == 2
        assert data["stats"]["total_files"] == 2

    def test_load(self, tmp_path):
        """Load a saved catalog."""
        (tmp_path / "file.txt").write_text("hello")
        config_dir = tmp_path / ".flavia"
        config_dir.mkdir()

        catalog = ContentCatalog(tmp_path)
        catalog.build()
        catalog.save(config_dir)

        loaded = ContentCatalog.load(config_dir)
        assert loaded is not None
        assert len(loaded.files) == 1
        assert "file.txt" in loaded.files

    def test_load_nonexistent(self, tmp_path):
        """Loading from nonexistent directory returns None."""
        config_dir = tmp_path / ".flavia"
        config_dir.mkdir()

        result = ContentCatalog.load(config_dir)
        assert result is None

    def test_load_or_build_creates_new(self, tmp_path):
        """load_or_build creates new catalog when none exists."""
        (tmp_path / "file.txt").write_text("hello")
        config_dir = tmp_path / ".flavia"
        config_dir.mkdir()

        catalog = ContentCatalog.load_or_build(tmp_path, config_dir)
        assert len(catalog.files) == 1

    def test_load_or_build_loads_existing(self, tmp_path):
        """load_or_build loads existing catalog."""
        (tmp_path / "file.txt").write_text("hello")
        config_dir = tmp_path / ".flavia"
        config_dir.mkdir()

        # Build and save
        catalog = ContentCatalog(tmp_path)
        catalog.build()
        catalog.files["file.txt"].summary = "test summary"
        catalog.save(config_dir)

        # Load existing
        loaded = ContentCatalog.load_or_build(tmp_path, config_dir)
        assert loaded.files["file.txt"].summary == "test summary"

    def test_query_by_name(self, tmp_path):
        """Query by filename substring."""
        (tmp_path / "paper_smith.pdf").write_bytes(b"\x00")
        (tmp_path / "paper_jones.pdf").write_bytes(b"\x00")
        (tmp_path / "notes.md").write_text("notes")

        catalog = ContentCatalog(tmp_path)
        catalog.build()

        results = catalog.query(name="smith")
        assert len(results) == 1
        assert results[0].name == "paper_smith.pdf"

    def test_query_by_extension(self, tmp_path):
        """Query by file extension."""
        (tmp_path / "a.py").write_text("code")
        (tmp_path / "b.py").write_text("code")
        (tmp_path / "c.md").write_text("doc")

        catalog = ContentCatalog(tmp_path)
        catalog.build()

        results = catalog.query(extension=".py")
        assert len(results) == 2

    def test_query_by_file_type(self, tmp_path):
        """Query by file type."""
        (tmp_path / "code.py").write_text("code")
        (tmp_path / "doc.pdf").write_bytes(b"%PDF-1.4")

        catalog = ContentCatalog(tmp_path)
        catalog.build()

        results = catalog.query(file_type="text")
        assert len(results) == 1
        assert results[0].name == "code.py"

    def test_query_text_search_in_summary(self, tmp_path):
        """Query text search matches in summary."""
        (tmp_path / "paper.md").write_text("content")

        catalog = ContentCatalog(tmp_path)
        catalog.build()
        catalog.files["paper.md"].summary = "About navier-stokes equations"

        results = catalog.query(text_search="navier")
        assert len(results) == 1

    def test_query_limit(self, tmp_path):
        """Query respects limit parameter."""
        for i in range(10):
            (tmp_path / f"file{i}.txt").write_text(f"content {i}")

        catalog = ContentCatalog(tmp_path)
        catalog.build()

        results = catalog.query(limit=3)
        assert len(results) == 3

    def test_query_zero_limit_returns_no_results(self, tmp_path):
        """Non-positive limits return no results."""
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")

        catalog = ContentCatalog(tmp_path)
        catalog.build()

        assert catalog.query(limit=0) == []
        assert catalog.query(limit=-5) == []

    def test_get_stats(self, tmp_path):
        """Get catalog statistics."""
        (tmp_path / "a.py").write_text("code")
        (tmp_path / "b.md").write_text("doc")
        (tmp_path / "c.pdf").write_bytes(b"%PDF")

        catalog = ContentCatalog(tmp_path)
        catalog.build()

        stats = catalog.get_stats()
        assert stats["total_files"] == 3
        assert "text" in stats["by_type"]
        assert "binary_document" in stats["by_type"]

    def test_generate_context_summary(self, tmp_path):
        """Generate a context summary for the LLM."""
        (tmp_path / "a.py").write_text("code")
        (tmp_path / "b.md").write_text("doc")

        catalog = ContentCatalog(tmp_path)
        catalog.build()

        summary = catalog.generate_context_summary()
        assert "2 files" in summary
        assert "text" in summary.lower()

    def test_generate_context_summary_max_length(self, tmp_path):
        """Context summary respects max_length."""
        for i in range(50):
            (tmp_path / f"file_{i:03d}.txt").write_text(f"content {i}")

        catalog = ContentCatalog(tmp_path)
        catalog.build()

        summary = catalog.generate_context_summary(max_length=100)
        assert len(summary) <= 100


# ---------------------------------------------------------------------------
# Incremental Update tests
# ---------------------------------------------------------------------------


class TestCatalogUpdate:
    """Tests for incremental catalog updates."""

    def test_detect_new_file(self, tmp_path):
        """Detect a newly added file."""
        (tmp_path / "original.txt").write_text("original")
        config_dir = tmp_path / ".flavia"
        config_dir.mkdir()

        catalog = ContentCatalog(tmp_path)
        catalog.build()
        catalog.save(config_dir)

        # Add new file
        (tmp_path / "new_file.txt").write_text("new content")

        # Reload and update
        catalog = ContentCatalog.load(config_dir)
        result = catalog.update()

        assert result["counts"]["new"] == 1
        assert "new_file.txt" in result["new"]

    def test_detect_modified_file(self, tmp_path):
        """Detect a modified file."""
        test_file = tmp_path / "file.txt"
        test_file.write_text("original")
        config_dir = tmp_path / ".flavia"
        config_dir.mkdir()

        catalog = ContentCatalog(tmp_path)
        catalog.build()
        catalog.save(config_dir)

        # Modify the file (need to ensure mtime changes)
        time.sleep(0.05)
        test_file.write_text("modified content")

        # Reload and update
        catalog = ContentCatalog.load(config_dir)
        result = catalog.update()

        assert result["counts"]["modified"] == 1
        assert "file.txt" in result["modified"]

    def test_detect_missing_file(self, tmp_path):
        """Detect a deleted file."""
        test_file = tmp_path / "file.txt"
        test_file.write_text("content")
        config_dir = tmp_path / ".flavia"
        config_dir.mkdir()

        catalog = ContentCatalog(tmp_path)
        catalog.build()
        catalog.save(config_dir)

        # Delete the file
        test_file.unlink()

        # Reload and update
        catalog = ContentCatalog.load(config_dir)
        result = catalog.update()

        assert result["counts"]["missing"] == 1
        assert "file.txt" in result["missing"]

    def test_remove_missing(self, tmp_path):
        """Remove missing files from catalog."""
        (tmp_path / "file.txt").write_text("content")
        config_dir = tmp_path / ".flavia"
        config_dir.mkdir()

        catalog = ContentCatalog(tmp_path)
        catalog.build()
        catalog.save(config_dir)

        # Delete and update
        (tmp_path / "file.txt").unlink()
        catalog = ContentCatalog.load(config_dir)
        catalog.update()

        removed = catalog.remove_missing()
        assert len(removed) == 1
        assert "file.txt" not in catalog.files

    def test_mark_all_current(self, tmp_path):
        """Mark all files as current after processing."""
        (tmp_path / "file.txt").write_text("content")

        catalog = ContentCatalog(tmp_path)
        catalog.build()

        # Simulate adding a new file
        (tmp_path / "new.txt").write_text("new")
        catalog.update()

        catalog.mark_all_current()
        for entry in catalog.files.values():
            assert entry.status == "current" or entry.status == "missing"

    def test_unchanged_file_not_reprocessed(self, tmp_path):
        """Unchanged files keep their status."""
        (tmp_path / "stable.txt").write_text("stable content")
        config_dir = tmp_path / ".flavia"
        config_dir.mkdir()

        catalog = ContentCatalog(tmp_path)
        catalog.build()
        catalog.save(config_dir)

        # Reload and update without changes
        catalog = ContentCatalog.load(config_dir)
        result = catalog.update()

        assert result["counts"]["unchanged"] == 1
        assert result["counts"]["new"] == 0
        assert result["counts"]["modified"] == 0

    def test_get_files_needing_conversion(self, tmp_path):
        """Identify binary documents without conversions."""
        (tmp_path / "doc.pdf").write_bytes(b"%PDF")
        (tmp_path / "code.py").write_text("code")

        catalog = ContentCatalog(tmp_path)
        catalog.build()

        needs_conversion = catalog.get_files_needing_conversion()
        assert len(needs_conversion) == 1
        assert needs_conversion[0].name == "doc.pdf"

        # After setting converted_to, it should not be listed
        catalog.files["doc.pdf"].converted_to = "converted/doc.md"
        needs_conversion = catalog.get_files_needing_conversion()
        assert len(needs_conversion) == 0

    def test_modified_binary_with_existing_conversion_needs_reconversion(self, tmp_path):
        """Modified binaries are reconverted even when converted_to already exists."""
        pdf_path = tmp_path / "doc.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 original")
        config_dir = tmp_path / ".flavia"
        config_dir.mkdir()

        catalog = ContentCatalog(tmp_path)
        catalog.build()
        catalog.files["doc.pdf"].converted_to = "converted/doc.md"
        catalog.save(config_dir)

        time.sleep(0.05)
        pdf_path.write_bytes(b"%PDF-1.4 modified")

        catalog = ContentCatalog.load(config_dir)
        catalog.update()

        needs_conversion = catalog.get_files_needing_conversion()
        assert len(needs_conversion) == 1
        assert needs_conversion[0].name == "doc.pdf"


# ---------------------------------------------------------------------------
# Online Sources tests
# ---------------------------------------------------------------------------


class TestOnlineSources:
    """Tests for online source methods in ContentCatalog."""

    def test_add_youtube_source(self, tmp_path):
        """Add a YouTube video to the catalog."""
        catalog = ContentCatalog(tmp_path)
        catalog.build()

        entry = catalog.add_online_source(
            "https://www.youtube.com/watch?v=abc123",
            source_type="youtube",
        )

        assert entry is not None
        assert entry.source_type == "youtube"
        assert entry.source_url == "https://www.youtube.com/watch?v=abc123"
        assert entry.fetch_status == "not_implemented"
        assert entry.file_type == "online"
        assert entry.category == "youtube"
        assert entry.path.startswith("_online/youtube/")

    def test_add_webpage_source(self, tmp_path):
        """Add a web page to the catalog."""
        catalog = ContentCatalog(tmp_path)
        catalog.build()

        entry = catalog.add_online_source(
            "https://docs.python.org/3/",
            source_type="webpage",
        )

        assert entry is not None
        assert entry.source_type == "webpage"
        assert entry.source_url == "https://docs.python.org/3/"
        assert entry.fetch_status == "not_implemented"

    def test_add_source_normalizes_source_type(self, tmp_path):
        """Source type is normalized to lowercase."""
        catalog = ContentCatalog(tmp_path)
        catalog.build()

        entry = catalog.add_online_source(
            "https://youtube.com/watch?v=abc123",
            source_type="YouTube",
        )

        assert entry is not None
        assert entry.source_type == "youtube"
        assert entry.category == "youtube"
        assert entry.path.startswith("_online/youtube/")

    def test_add_source_does_not_overwrite_existing_local_path(self, tmp_path):
        """Online source path collisions must not overwrite local file entries."""
        url = "https://youtube.com/watch?v=abc123"
        url_hash = hashlib.sha256(url.encode()).hexdigest()[:12]

        collision_file = tmp_path / "_online" / "youtube" / url_hash
        collision_file.parent.mkdir(parents=True)
        collision_file.write_text("local file")

        catalog = ContentCatalog(tmp_path)
        catalog.build()
        local_entry = catalog.files[f"_online/youtube/{url_hash}"]
        assert local_entry.source_type == "local"

        online_entry = catalog.add_online_source(url, source_type="youtube")
        assert online_entry is not None
        assert online_entry.path != local_entry.path
        assert catalog.files[local_entry.path].source_type == "local"
        assert catalog.files[online_entry.path].source_type == "youtube"

    def test_add_source_auto_detect_youtube(self, tmp_path):
        """Auto-detect YouTube URLs."""
        catalog = ContentCatalog(tmp_path)
        catalog.build()

        entry = catalog.add_online_source(
            "https://youtu.be/abc123",
            source_type="auto",
        )

        assert entry is not None
        assert entry.source_type == "youtube"

    def test_add_source_auto_detect_webpage(self, tmp_path):
        """Auto-detect web page URLs."""
        catalog = ContentCatalog(tmp_path)
        catalog.build()

        entry = catalog.add_online_source(
            "https://example.com/page",
            source_type="auto",
        )

        assert entry is not None
        assert entry.source_type == "webpage"

    def test_add_source_with_tags(self, tmp_path):
        """Add source with tags."""
        catalog = ContentCatalog(tmp_path)
        catalog.build()

        entry = catalog.add_online_source(
            "https://example.com",
            tags=["reference", "docs"],
        )

        assert entry is not None
        assert entry.tags == ["reference", "docs"]

    def test_add_source_updates_catalog_timestamp(self, tmp_path):
        """Adding a source updates the catalog timestamp."""
        catalog = ContentCatalog(tmp_path)
        catalog.build()
        original_timestamp = catalog.catalog_updated_at

        # Small delay to ensure timestamp changes
        import time
        time.sleep(0.01)

        catalog.add_online_source("https://example.com")

        assert catalog.catalog_updated_at != original_timestamp

    def test_get_online_sources_empty(self, tmp_path):
        """Get online sources when none exist."""
        catalog = ContentCatalog(tmp_path)
        catalog.build()

        sources = catalog.get_online_sources()
        assert sources == []

    def test_get_online_sources_all(self, tmp_path):
        """Get all online sources."""
        catalog = ContentCatalog(tmp_path)
        catalog.build()

        catalog.add_online_source("https://youtube.com/watch?v=1", source_type="youtube")
        catalog.add_online_source("https://youtube.com/watch?v=2", source_type="youtube")
        catalog.add_online_source("https://example.com", source_type="webpage")

        sources = catalog.get_online_sources()
        assert len(sources) == 3

    def test_get_online_sources_filter_by_type(self, tmp_path):
        """Filter online sources by type."""
        catalog = ContentCatalog(tmp_path)
        catalog.build()

        catalog.add_online_source("https://youtube.com/watch?v=1", source_type="youtube")
        catalog.add_online_source("https://youtube.com/watch?v=2", source_type="youtube")
        catalog.add_online_source("https://example.com", source_type="webpage")

        youtube_sources = catalog.get_online_sources(source_type="youtube")
        assert len(youtube_sources) == 2

        webpage_sources = catalog.get_online_sources(source_type="webpage")
        assert len(webpage_sources) == 1

    def test_get_online_sources_filter_by_status(self, tmp_path):
        """Filter online sources by fetch status."""
        catalog = ContentCatalog(tmp_path)
        catalog.build()

        entry1 = catalog.add_online_source("https://youtube.com/watch?v=1")
        entry2 = catalog.add_online_source("https://example.com")

        # Manually change one status to test filtering
        entry2.fetch_status = "completed"

        not_impl = catalog.get_online_sources(fetch_status="not_implemented")
        completed = catalog.get_online_sources(fetch_status="completed")

        assert len(not_impl) == 1
        assert len(completed) == 1

    def test_get_pending_fetches(self, tmp_path):
        """Get sources pending fetch."""
        catalog = ContentCatalog(tmp_path)
        catalog.build()

        entry = catalog.add_online_source("https://example.com")

        # Change status to pending
        entry.fetch_status = "pending"

        pending = catalog.get_pending_fetches()
        assert len(pending) == 1
        assert pending[0] is entry

    def test_stats_include_online_sources(self, tmp_path):
        """Stats include online source counts."""
        (tmp_path / "file.txt").write_text("content")

        catalog = ContentCatalog(tmp_path)
        catalog.build()

        catalog.add_online_source("https://youtube.com/watch?v=1", source_type="youtube")
        catalog.add_online_source("https://example.com", source_type="webpage")

        stats = catalog.get_stats()

        assert stats["online_sources"] == 2
        assert "youtube" in stats["by_source_type"]
        assert "webpage" in stats["by_source_type"]
        assert stats["by_source_type"]["youtube"] == 1
        assert stats["by_source_type"]["webpage"] == 1

    def test_online_sources_persist_to_disk(self, tmp_path):
        """Online sources are saved and loaded correctly."""
        config_dir = tmp_path / ".flavia"
        config_dir.mkdir()

        catalog = ContentCatalog(tmp_path)
        catalog.build()

        catalog.add_online_source(
            "https://youtube.com/watch?v=abc",
            source_type="youtube",
            tags=["video"],
        )
        catalog.save(config_dir)

        # Load and verify
        loaded = ContentCatalog.load(config_dir)
        sources = loaded.get_online_sources()

        assert len(sources) == 1
        assert sources[0].source_type == "youtube"
        assert sources[0].source_url == "https://youtube.com/watch?v=abc"
        assert sources[0].tags == ["video"]

    def test_update_keeps_online_sources_active(self, tmp_path):
        """Incremental update should not mark online sources as missing."""
        (tmp_path / "file.txt").write_text("content")
        config_dir = tmp_path / ".flavia"
        config_dir.mkdir()

        catalog = ContentCatalog(tmp_path)
        catalog.build()
        online_entry = catalog.add_online_source("https://example.com")
        catalog.save(config_dir)

        loaded = ContentCatalog.load(config_dir)
        result = loaded.update()

        assert result["counts"]["missing"] == 0
        assert loaded.files[online_entry.path].status == "new"
        assert loaded.get_stats()["online_sources"] == 1


# ---------------------------------------------------------------------------
# TextReader tests
# ---------------------------------------------------------------------------


class TestTextReader:
    """Tests for the TextReader converter."""

    def test_extract_text(self, tmp_path):
        """Read text from a file."""
        f = tmp_path / "test.txt"
        f.write_text("Hello, world!")

        reader = TextReader()
        text = reader.extract_text(f)
        assert text == "Hello, world!"

    def test_can_handle(self, tmp_path):
        """Check supported extensions."""
        reader = TextReader()
        assert reader.can_handle(Path("file.py"))
        assert reader.can_handle(Path("file.md"))
        assert reader.can_handle(Path("file.txt"))
        assert not reader.can_handle(Path("file.pdf"))
        assert not reader.can_handle(Path("file.mp3"))

    def test_convert_returns_none(self, tmp_path):
        """Text files don't need conversion."""
        f = tmp_path / "test.txt"
        f.write_text("content")

        reader = TextReader()
        result = reader.convert(f, tmp_path / "output")
        assert result is None


# ---------------------------------------------------------------------------
# PdfConverter tests (without actual PDFs)
# ---------------------------------------------------------------------------


class TestPdfConverter:
    """Tests for PdfConverter (structural tests without real PDFs)."""

    def test_can_handle(self):
        """Check supported extensions."""
        converter = PdfConverter()
        assert converter.can_handle(Path("file.pdf"))
        assert not converter.can_handle(Path("file.txt"))
        assert not converter.can_handle(Path("file.docx"))

    def test_format_as_markdown(self):
        """Test markdown formatting."""
        text = "INTRODUCTION\n\nSome text about the topic.\n\n1. First Section\n\nMore content."
        result = PdfConverter._format_as_markdown(text, "test_paper")

        assert "# test paper" in result
        assert "## Introduction" in result
        assert "### 1. First Section" in result

    def test_convert_preserves_relative_structure(self, tmp_path, monkeypatch):
        """Converted outputs preserve source subdirectories to avoid filename collisions."""
        source_a = tmp_path / "papers" / "v1" / "report.pdf"
        source_b = tmp_path / "notes" / "v2" / "report.pdf"
        source_a.parent.mkdir(parents=True)
        source_b.parent.mkdir(parents=True)
        source_a.write_bytes(b"%PDF-a")
        source_b.write_bytes(b"%PDF-b")

        converter = PdfConverter()
        monkeypatch.setattr(converter, "extract_text", lambda _path: "PDF CONTENT")

        output_dir = tmp_path / "converted"
        out_a = converter.convert(source_a, output_dir)
        out_b = converter.convert(source_b, output_dir)

        assert out_a == output_dir / "papers" / "v1" / "report.md"
        assert out_b == output_dir / "notes" / "v2" / "report.md"
        assert out_a != out_b
        assert out_a.exists()
        assert out_b.exists()
