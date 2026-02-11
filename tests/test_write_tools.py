"""Functional tests for write tools."""

import os
from pathlib import Path

import pytest

from flavia.agent.context import AgentContext
from flavia.agent.profile import AgentPermissions
from flavia.tools.write_confirmation import WriteConfirmation
from flavia.tools.write.write_file import WriteFileTool
from flavia.tools.write.edit_file import EditFileTool
from flavia.tools.write.insert_text import InsertTextTool
from flavia.tools.write.append_file import AppendFileTool
from flavia.tools.write.delete_file import DeleteFileTool
from flavia.tools.write.create_directory import CreateDirectoryTool
from flavia.tools.write.remove_directory import RemoveDirectoryTool


def _make_context(base_dir: Path, permissions: AgentPermissions | None = None) -> AgentContext:
    """Create a test AgentContext with auto-approve write confirmation."""
    wc = WriteConfirmation()
    wc.set_auto_approve(True)
    return AgentContext(
        agent_id="test",
        name="test",
        current_depth=0,
        max_depth=3,
        parent_id=None,
        base_dir=base_dir,
        available_tools=[],
        subagents={},
        model_id="test-model",
        messages=[],
        permissions=permissions or AgentPermissions(),
        write_confirmation=wc,
    )


# ──────────────────────────────────────────────
#  write_file
# ──────────────────────────────────────────────


class TestWriteFile:
    def test_create_new_file(self, tmp_path):
        tool = WriteFileTool()
        ctx = _make_context(tmp_path)
        result = tool.execute({"path": "hello.txt", "content": "Hello, world!"}, ctx)
        assert "created" in result.lower()
        assert (tmp_path / "hello.txt").read_text() == "Hello, world!"

    def test_overwrite_existing_file(self, tmp_path):
        (tmp_path / "existing.txt").write_text("old content")
        tool = WriteFileTool()
        ctx = _make_context(tmp_path)
        result = tool.execute({"path": "existing.txt", "content": "new content"}, ctx)
        assert "overwritten" in result.lower()
        assert (tmp_path / "existing.txt").read_text() == "new content"

    def test_creates_parent_directories(self, tmp_path):
        tool = WriteFileTool()
        ctx = _make_context(tmp_path)
        result = tool.execute({"path": "a/b/c/deep.txt", "content": "deep"}, ctx)
        assert "created" in result.lower()
        assert (tmp_path / "a" / "b" / "c" / "deep.txt").read_text() == "deep"

    def test_empty_path_error(self, tmp_path):
        tool = WriteFileTool()
        ctx = _make_context(tmp_path)
        result = tool.execute({"path": "", "content": "data"}, ctx)
        assert result.startswith("Error")

    def test_no_confirmation_handler(self, tmp_path):
        ctx = AgentContext(
            agent_id="test",
            name="test",
            base_dir=tmp_path,
            available_tools=[],
            subagents={},
            model_id="m",
            messages=[],
            permissions=AgentPermissions(),
            write_confirmation=None,
        )
        tool = WriteFileTool()
        result = tool.execute({"path": "f.txt", "content": "x"}, ctx)
        assert "confirmation" in result.lower()
        assert not (tmp_path / "f.txt").exists()

    def test_confirmation_denied(self, tmp_path):
        wc = WriteConfirmation()
        wc.set_callback(lambda op, path, det: False)
        ctx = AgentContext(
            agent_id="test",
            name="test",
            base_dir=tmp_path,
            available_tools=[],
            subagents={},
            model_id="m",
            messages=[],
            permissions=AgentPermissions(),
            write_confirmation=wc,
        )
        tool = WriteFileTool()
        result = tool.execute({"path": "f.txt", "content": "x"}, ctx)
        assert "cancelled" in result.lower()
        assert not (tmp_path / "f.txt").exists()

    def test_backup_created_on_overwrite(self, tmp_path):
        (tmp_path / "data.txt").write_text("original")
        tool = WriteFileTool()
        ctx = _make_context(tmp_path)
        tool.execute({"path": "data.txt", "content": "replaced"}, ctx)
        backup_dir = tmp_path / ".flavia" / "file_backups"
        assert backup_dir.exists()
        backups = list(backup_dir.rglob("*.bak"))
        assert len(backups) == 1
        assert backups[0].read_text() == "original"


# ──────────────────────────────────────────────
#  edit_file
# ──────────────────────────────────────────────


class TestEditFile:
    def test_single_match_replacement(self, tmp_path):
        (tmp_path / "code.py").write_text("x = 1\ny = 2\nz = 3\n")
        tool = EditFileTool()
        ctx = _make_context(tmp_path)
        result = tool.execute(
            {
                "path": "code.py",
                "old_text": "y = 2",
                "new_text": "y = 42",
            },
            ctx,
        )
        assert "edited" in result.lower()
        assert (tmp_path / "code.py").read_text() == "x = 1\ny = 42\nz = 3\n"

    def test_not_found(self, tmp_path):
        (tmp_path / "f.txt").write_text("abc")
        tool = EditFileTool()
        ctx = _make_context(tmp_path)
        result = tool.execute(
            {
                "path": "f.txt",
                "old_text": "xyz",
                "new_text": "q",
            },
            ctx,
        )
        assert "not found" in result.lower()

    def test_multiple_matches_rejected(self, tmp_path):
        (tmp_path / "f.txt").write_text("aa bb aa")
        tool = EditFileTool()
        ctx = _make_context(tmp_path)
        result = tool.execute(
            {
                "path": "f.txt",
                "old_text": "aa",
                "new_text": "cc",
            },
            ctx,
        )
        assert "2 times" in result

    def test_file_not_found(self, tmp_path):
        tool = EditFileTool()
        ctx = _make_context(tmp_path)
        result = tool.execute(
            {
                "path": "missing.txt",
                "old_text": "a",
                "new_text": "b",
            },
            ctx,
        )
        assert "not found" in result.lower()

    def test_empty_old_text_error(self, tmp_path):
        (tmp_path / "f.txt").write_text("data")
        tool = EditFileTool()
        ctx = _make_context(tmp_path)
        result = tool.execute(
            {
                "path": "f.txt",
                "old_text": "",
                "new_text": "b",
            },
            ctx,
        )
        assert result.startswith("Error")

    def test_backup_created(self, tmp_path):
        (tmp_path / "f.txt").write_text("hello world")
        tool = EditFileTool()
        ctx = _make_context(tmp_path)
        tool.execute(
            {
                "path": "f.txt",
                "old_text": "hello",
                "new_text": "goodbye",
            },
            ctx,
        )
        backups = list((tmp_path / ".flavia" / "file_backups").rglob("*.bak"))
        assert len(backups) == 1
        assert backups[0].read_text() == "hello world"


# ──────────────────────────────────────────────
#  insert_text
# ──────────────────────────────────────────────


class TestInsertText:
    def test_insert_at_beginning(self, tmp_path):
        (tmp_path / "f.txt").write_text("line2\nline3\n")
        tool = InsertTextTool()
        ctx = _make_context(tmp_path)
        result = tool.execute(
            {
                "path": "f.txt",
                "line_number": 1,
                "text": "line1",
            },
            ctx,
        )
        assert "inserted" in result.lower()
        assert (tmp_path / "f.txt").read_text() == "line1\nline2\nline3\n"

    def test_insert_at_end(self, tmp_path):
        (tmp_path / "f.txt").write_text("line1\nline2\n")
        tool = InsertTextTool()
        ctx = _make_context(tmp_path)
        result = tool.execute(
            {
                "path": "f.txt",
                "line_number": 3,
                "text": "line3",
            },
            ctx,
        )
        assert "inserted" in result.lower()
        content = (tmp_path / "f.txt").read_text()
        assert "line3" in content

    def test_invalid_line_number(self, tmp_path):
        (tmp_path / "f.txt").write_text("one\ntwo\n")
        tool = InsertTextTool()
        ctx = _make_context(tmp_path)
        result = tool.execute(
            {
                "path": "f.txt",
                "line_number": 100,
                "text": "bad",
            },
            ctx,
        )
        assert "out of range" in result.lower()

    def test_line_zero_rejected(self, tmp_path):
        (tmp_path / "f.txt").write_text("content\n")
        tool = InsertTextTool()
        ctx = _make_context(tmp_path)
        result = tool.execute(
            {
                "path": "f.txt",
                "line_number": 0,
                "text": "bad",
            },
            ctx,
        )
        assert "out of range" in result.lower()

    def test_file_not_found(self, tmp_path):
        tool = InsertTextTool()
        ctx = _make_context(tmp_path)
        result = tool.execute(
            {
                "path": "missing.txt",
                "line_number": 1,
                "text": "x",
            },
            ctx,
        )
        assert "not found" in result.lower()


# ──────────────────────────────────────────────
#  append_file
# ──────────────────────────────────────────────


class TestAppendFile:
    def test_append_to_existing(self, tmp_path):
        (tmp_path / "log.txt").write_text("entry1\n")
        tool = AppendFileTool()
        ctx = _make_context(tmp_path)
        result = tool.execute({"path": "log.txt", "content": "entry2\n"}, ctx)
        assert "appended" in result.lower()
        assert (tmp_path / "log.txt").read_text() == "entry1\nentry2\n"

    def test_create_new_file(self, tmp_path):
        tool = AppendFileTool()
        ctx = _make_context(tmp_path)
        result = tool.execute({"path": "new.txt", "content": "fresh"}, ctx)
        assert "created" in result.lower()
        assert (tmp_path / "new.txt").read_text() == "fresh"

    def test_adds_separator_when_no_trailing_newline(self, tmp_path):
        (tmp_path / "f.txt").write_text("no newline at end")
        tool = AppendFileTool()
        ctx = _make_context(tmp_path)
        tool.execute({"path": "f.txt", "content": "more"}, ctx)
        content = (tmp_path / "f.txt").read_text()
        assert content == "no newline at end\nmore"

    def test_backup_created_on_append(self, tmp_path):
        (tmp_path / "f.txt").write_text("original")
        tool = AppendFileTool()
        ctx = _make_context(tmp_path)
        tool.execute({"path": "f.txt", "content": " added"}, ctx)
        backups = list((tmp_path / ".flavia" / "file_backups").rglob("*.bak"))
        assert len(backups) == 1


# ──────────────────────────────────────────────
#  delete_file
# ──────────────────────────────────────────────


class TestDeleteFile:
    def test_delete_existing_file(self, tmp_path):
        target = tmp_path / "victim.txt"
        target.write_text("bye")
        tool = DeleteFileTool()
        ctx = _make_context(tmp_path)
        result = tool.execute({"path": "victim.txt"}, ctx)
        assert "deleted" in result.lower()
        assert not target.exists()

    def test_file_not_found(self, tmp_path):
        tool = DeleteFileTool()
        ctx = _make_context(tmp_path)
        result = tool.execute({"path": "ghost.txt"}, ctx)
        assert "not found" in result.lower()

    def test_cannot_delete_directory(self, tmp_path):
        (tmp_path / "adir").mkdir()
        tool = DeleteFileTool()
        ctx = _make_context(tmp_path)
        result = tool.execute({"path": "adir"}, ctx)
        assert "not a file" in result.lower()

    def test_backup_created_before_delete(self, tmp_path):
        (tmp_path / "data.txt").write_text("saved content")
        tool = DeleteFileTool()
        ctx = _make_context(tmp_path)
        tool.execute({"path": "data.txt"}, ctx)
        backups = list((tmp_path / ".flavia" / "file_backups").rglob("*.bak"))
        assert len(backups) == 1
        assert backups[0].read_text() == "saved content"


# ──────────────────────────────────────────────
#  create_directory
# ──────────────────────────────────────────────


class TestCreateDirectory:
    def test_create_single_directory(self, tmp_path):
        tool = CreateDirectoryTool()
        ctx = _make_context(tmp_path)
        result = tool.execute({"path": "newdir"}, ctx)
        assert "created" in result.lower()
        assert (tmp_path / "newdir").is_dir()

    def test_create_nested_directories(self, tmp_path):
        tool = CreateDirectoryTool()
        ctx = _make_context(tmp_path)
        result = tool.execute({"path": "a/b/c"}, ctx)
        assert "created" in result.lower()
        assert (tmp_path / "a" / "b" / "c").is_dir()

    def test_already_exists(self, tmp_path):
        (tmp_path / "existing").mkdir()
        tool = CreateDirectoryTool()
        ctx = _make_context(tmp_path)
        result = tool.execute({"path": "existing"}, ctx)
        assert "already exists" in result.lower()

    def test_path_is_file_error(self, tmp_path):
        (tmp_path / "afile").write_text("content")
        tool = CreateDirectoryTool()
        ctx = _make_context(tmp_path)
        result = tool.execute({"path": "afile"}, ctx)
        assert "not a directory" in result.lower()


# ──────────────────────────────────────────────
#  remove_directory
# ──────────────────────────────────────────────


class TestRemoveDirectory:
    def test_remove_empty_directory(self, tmp_path):
        (tmp_path / "empty").mkdir()
        tool = RemoveDirectoryTool()
        ctx = _make_context(tmp_path)
        result = tool.execute({"path": "empty"}, ctx)
        assert "removed" in result.lower()
        assert not (tmp_path / "empty").exists()

    def test_non_empty_without_recursive_fails(self, tmp_path):
        d = tmp_path / "notempty"
        d.mkdir()
        (d / "file.txt").write_text("data")
        tool = RemoveDirectoryTool()
        ctx = _make_context(tmp_path)
        result = tool.execute({"path": "notempty"}, ctx)
        assert "not empty" in result.lower()
        assert d.exists()

    def test_recursive_removal(self, tmp_path):
        d = tmp_path / "tree"
        d.mkdir()
        (d / "sub").mkdir()
        (d / "sub" / "file.txt").write_text("nested")
        (d / "top.txt").write_text("top")
        tool = RemoveDirectoryTool()
        ctx = _make_context(tmp_path)
        result = tool.execute({"path": "tree", "recursive": True}, ctx)
        assert "removed" in result.lower()
        assert not d.exists()

    def test_directory_not_found(self, tmp_path):
        tool = RemoveDirectoryTool()
        ctx = _make_context(tmp_path)
        result = tool.execute({"path": "ghost"}, ctx)
        assert "not found" in result.lower()

    def test_path_is_file_error(self, tmp_path):
        (tmp_path / "afile").write_text("content")
        tool = RemoveDirectoryTool()
        ctx = _make_context(tmp_path)
        result = tool.execute({"path": "afile"}, ctx)
        assert "not a directory" in result.lower()
