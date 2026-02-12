"""Tests for the preview module."""

import pytest
from pathlib import Path

from flavia.tools.write.preview import (
    OperationPreview,
    generate_diff,
    format_content_preview,
    format_dir_contents,
    format_insertion_context,
    format_file_preview,
)


class TestGenerateDiff:
    def test_basic_diff(self):
        old_text = "line1\nline2\nline3\n"
        new_text = "line1\nmodified\nline3\n"
        diff = generate_diff(old_text, new_text, "test.txt")

        assert "--- a/test.txt" in diff
        assert "+++ b/test.txt" in diff
        assert "-line2" in diff
        assert "+modified" in diff

    def test_no_changes_returns_empty(self):
        text = "same content\n"
        diff = generate_diff(text, text, "test.txt")
        assert diff == ""

    def test_addition_diff(self):
        old_text = "line1\nline2\n"
        new_text = "line1\nline2\nline3\n"
        diff = generate_diff(old_text, new_text, "test.txt")
        assert "+line3" in diff

    def test_deletion_diff(self):
        old_text = "line1\nline2\nline3\n"
        new_text = "line1\nline3\n"
        diff = generate_diff(old_text, new_text, "test.txt")
        assert "-line2" in diff

    def test_context_lines(self):
        old_text = "a\nb\nc\nd\ne\nf\ng\n"
        new_text = "a\nb\nc\nX\ne\nf\ng\n"
        diff = generate_diff(old_text, new_text, "test.txt", context_lines=1)
        # With context_lines=1, should show 1 line before and after
        assert "c" in diff
        assert "e" in diff


class TestFormatContentPreview:
    def test_short_content(self):
        content = "line1\nline2\nline3"
        preview = format_content_preview(content)
        assert "line1" in preview
        assert "line2" in preview
        assert "line3" in preview
        assert "more lines" not in preview

    def test_empty_content(self):
        preview = format_content_preview("")
        assert preview == "(empty)"

    def test_truncates_long_content(self):
        content = "\n".join(f"line{i}" for i in range(50))
        preview = format_content_preview(content, max_lines=10)
        assert "line0" in preview
        assert "line9" in preview
        assert "line10" not in preview or "more lines" in preview

    def test_truncates_long_lines(self):
        content = "a" * 200
        preview = format_content_preview(content, max_line_length=50)
        assert len(preview) < 200
        assert "..." in preview


class TestFormatDirContents:
    def test_empty_directory(self, tmp_path):
        contents = format_dir_contents(tmp_path)
        assert contents == []

    def test_lists_files(self, tmp_path):
        (tmp_path / "file1.txt").write_text("content")
        (tmp_path / "file2.txt").write_text("content")
        contents = format_dir_contents(tmp_path)
        assert "file1.txt" in contents
        assert "file2.txt" in contents

    def test_directories_have_slash(self, tmp_path):
        (tmp_path / "subdir").mkdir()
        (tmp_path / "file.txt").write_text("content")
        contents = format_dir_contents(tmp_path)
        assert "subdir/" in contents
        assert "file.txt" in contents

    def test_directories_listed_first(self, tmp_path):
        (tmp_path / "zfile.txt").write_text("content")
        (tmp_path / "adir").mkdir()
        contents = format_dir_contents(tmp_path)
        # Directory should come before file
        dir_idx = contents.index("adir/")
        file_idx = contents.index("zfile.txt")
        assert dir_idx < file_idx

    def test_truncates_large_directories(self, tmp_path):
        for i in range(30):
            (tmp_path / f"file{i:02d}.txt").write_text("content")
        contents = format_dir_contents(tmp_path, max_items=10)
        assert len([c for c in contents if not c.startswith("...")]) == 10
        assert any("more items" in c for c in contents)

    def test_nonexistent_directory(self, tmp_path):
        nonexistent = tmp_path / "does_not_exist"
        contents = format_dir_contents(nonexistent)
        assert contents == []


class TestFormatInsertionContext:
    def test_middle_insertion(self):
        lines = ["line1\n", "line2\n", "line3\n", "line4\n", "line5\n"]
        before, after = format_insertion_context(lines, 3, context_lines=2)

        assert before is not None
        assert "line1" in before
        assert "line2" in before

        assert after is not None
        assert "line3" in after
        assert "line4" in after

    def test_beginning_insertion(self):
        lines = ["line1\n", "line2\n", "line3\n"]
        before, after = format_insertion_context(lines, 1, context_lines=2)

        # No lines before position 1
        assert before is None

        assert after is not None
        assert "line1" in after

    def test_end_insertion(self):
        lines = ["line1\n", "line2\n", "line3\n"]
        before, after = format_insertion_context(lines, 4, context_lines=2)

        assert before is not None
        assert "line2" in before
        assert "line3" in before

        # No lines after end position
        assert after is None


class TestFormatFilePreview:
    def test_small_file(self, tmp_path):
        test_file = tmp_path / "test.txt"
        test_file.write_text("line1\nline2\nline3\n")
        preview = format_file_preview(test_file)

        assert preview is not None
        assert "line1" in preview
        assert "line2" in preview
        assert "line3" in preview

    def test_nonexistent_file(self, tmp_path):
        nonexistent = tmp_path / "does_not_exist.txt"
        preview = format_file_preview(nonexistent)
        assert preview is None

    def test_truncates_large_file(self, tmp_path):
        test_file = tmp_path / "large.txt"
        test_file.write_text("\n".join(f"line{i}" for i in range(100)))
        preview = format_file_preview(test_file, max_lines=5)

        assert preview is not None
        assert "line0" in preview
        assert "more lines" in preview


class TestOperationPreview:
    def test_dataclass_creation(self):
        preview = OperationPreview(
            operation="write",
            path="/tmp/test.txt",
            content_preview="hello world",
            content_lines=1,
            content_bytes=11,
        )

        assert preview.operation == "write"
        assert preview.path == "/tmp/test.txt"
        assert preview.content_preview == "hello world"
        assert preview.content_lines == 1
        assert preview.content_bytes == 11

    def test_defaults(self):
        preview = OperationPreview(
            operation="edit",
            path="/tmp/test.txt",
        )

        assert preview.diff is None
        assert preview.content_preview is None
        assert preview.content_lines == 0
        assert preview.content_bytes == 0
        assert preview.context_before is None
        assert preview.context_after is None
        assert preview.file_preview is None
        assert preview.file_size == 0
        assert preview.dir_contents == []
