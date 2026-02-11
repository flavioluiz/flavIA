"""Security tests for write tools — path traversal, symlinks, permission denial."""

import os
import tempfile
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


def _auto_approve_ctx(base_dir: Path, permissions: AgentPermissions | None = None) -> AgentContext:
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


def _denied_ctx(base_dir: Path, callback) -> AgentContext:
    wc = WriteConfirmation()
    wc.set_callback(callback)
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
        permissions=AgentPermissions(),
        write_confirmation=wc,
    )


# ──────────────────────────────────────────────
#  Path traversal — all write tools must refuse
#  to write outside the allowed directories.
# ──────────────────────────────────────────────


class TestPathTraversal:
    """Every write tool must block paths that resolve outside base_dir."""

    def _outside_path(self, tmp_path: Path) -> str:
        """Return a relative path that escapes base_dir."""
        return "../outside.txt"

    def test_write_file_blocks_traversal(self, tmp_path):
        ctx = _auto_approve_ctx(tmp_path)
        result = WriteFileTool().execute(
            {"path": self._outside_path(tmp_path), "content": "hack"}, ctx
        )
        assert "denied" in result.lower()

    def test_edit_file_blocks_traversal(self, tmp_path):
        ctx = _auto_approve_ctx(tmp_path)
        result = EditFileTool().execute(
            {"path": self._outside_path(tmp_path), "old_text": "a", "new_text": "b"}, ctx
        )
        assert "denied" in result.lower()

    def test_insert_text_blocks_traversal(self, tmp_path):
        ctx = _auto_approve_ctx(tmp_path)
        result = InsertTextTool().execute(
            {"path": self._outside_path(tmp_path), "line_number": 1, "text": "x"}, ctx
        )
        assert "denied" in result.lower()

    def test_append_file_blocks_traversal(self, tmp_path):
        ctx = _auto_approve_ctx(tmp_path)
        result = AppendFileTool().execute(
            {"path": self._outside_path(tmp_path), "content": "leak"}, ctx
        )
        assert "denied" in result.lower()

    def test_delete_file_blocks_traversal(self, tmp_path):
        ctx = _auto_approve_ctx(tmp_path)
        result = DeleteFileTool().execute({"path": self._outside_path(tmp_path)}, ctx)
        assert "denied" in result.lower()

    def test_create_directory_blocks_traversal(self, tmp_path):
        ctx = _auto_approve_ctx(tmp_path)
        result = CreateDirectoryTool().execute({"path": "../evil_dir"}, ctx)
        assert "denied" in result.lower()

    def test_remove_directory_blocks_traversal(self, tmp_path):
        ctx = _auto_approve_ctx(tmp_path)
        result = RemoveDirectoryTool().execute({"path": "../some_dir"}, ctx)
        assert "denied" in result.lower()


class TestAbsolutePathTraversal:
    """Absolute paths pointing outside base_dir must be blocked."""

    def test_write_file_absolute_outside(self, tmp_path):
        outside = Path(tempfile.mkdtemp())
        ctx = _auto_approve_ctx(tmp_path)
        result = WriteFileTool().execute({"path": str(outside / "leak.txt"), "content": "bad"}, ctx)
        assert "denied" in result.lower()

    def test_delete_file_absolute_outside(self, tmp_path):
        outside = Path(tempfile.mkdtemp())
        target = outside / "target.txt"
        target.write_text("precious")
        ctx = _auto_approve_ctx(tmp_path)
        result = DeleteFileTool().execute({"path": str(target)}, ctx)
        assert "denied" in result.lower()
        assert target.read_text() == "precious"  # file untouched


class TestSymlinkProtection:
    """Write tools must not follow symlinks that escape base_dir."""

    def test_write_file_through_symlink_outside(self, tmp_path):
        outside = Path(tempfile.mkdtemp())
        link = tmp_path / "link"
        try:
            os.symlink(outside, link)
        except (OSError, NotImplementedError):
            pytest.skip("symlinks not available")

        ctx = _auto_approve_ctx(tmp_path)
        result = WriteFileTool().execute({"path": "link/escaped.txt", "content": "data"}, ctx)
        # The resolved path should be outside base_dir, so permission denied.
        assert "denied" in result.lower()
        assert not (outside / "escaped.txt").exists()


class TestExplicitPermissions:
    """When explicit write_paths are configured, only those are allowed."""

    def test_write_denied_outside_allowed(self, tmp_path):
        allowed = tmp_path / "allowed"
        allowed.mkdir()
        denied = tmp_path / "denied"
        denied.mkdir()

        permissions = AgentPermissions(
            read_paths=[tmp_path.resolve()],
            write_paths=[allowed.resolve()],
        )
        ctx = _auto_approve_ctx(tmp_path, permissions)

        result = WriteFileTool().execute({"path": "denied/secret.txt", "content": "x"}, ctx)
        assert "denied" in result.lower()

    def test_write_allowed_inside_allowed(self, tmp_path):
        allowed = tmp_path / "allowed"
        allowed.mkdir()

        permissions = AgentPermissions(
            read_paths=[tmp_path.resolve()],
            write_paths=[allowed.resolve()],
        )
        ctx = _auto_approve_ctx(tmp_path, permissions)

        result = WriteFileTool().execute({"path": "allowed/ok.txt", "content": "fine"}, ctx)
        assert "created" in result.lower()
        assert (allowed / "ok.txt").read_text() == "fine"

    def test_delete_denied_outside_allowed(self, tmp_path):
        allowed = tmp_path / "allowed"
        allowed.mkdir()
        target = tmp_path / "outside.txt"
        target.write_text("safe")

        permissions = AgentPermissions(
            read_paths=[tmp_path.resolve()],
            write_paths=[allowed.resolve()],
        )
        ctx = _auto_approve_ctx(tmp_path, permissions)

        result = DeleteFileTool().execute({"path": "outside.txt"}, ctx)
        assert "denied" in result.lower()
        assert target.read_text() == "safe"

    def test_create_directory_denied_outside_allowed(self, tmp_path):
        allowed = tmp_path / "allowed"
        allowed.mkdir()

        permissions = AgentPermissions(
            read_paths=[tmp_path.resolve()],
            write_paths=[allowed.resolve()],
        )
        ctx = _auto_approve_ctx(tmp_path, permissions)

        result = CreateDirectoryTool().execute({"path": "forbidden_dir"}, ctx)
        assert "denied" in result.lower()

    def test_edit_denied_outside_allowed(self, tmp_path):
        allowed = tmp_path / "allowed"
        denied = tmp_path / "denied"
        allowed.mkdir()
        denied.mkdir()
        target = denied / "file.txt"
        target.write_text("abc")

        permissions = AgentPermissions(
            read_paths=[tmp_path.resolve()],
            write_paths=[allowed.resolve()],
        )
        ctx = _auto_approve_ctx(tmp_path, permissions)
        result = EditFileTool().execute(
            {"path": "denied/file.txt", "old_text": "a", "new_text": "z"}, ctx
        )
        assert "denied" in result.lower()
        assert target.read_text() == "abc"

    def test_insert_denied_outside_allowed(self, tmp_path):
        allowed = tmp_path / "allowed"
        denied = tmp_path / "denied"
        allowed.mkdir()
        denied.mkdir()
        target = denied / "file.txt"
        target.write_text("line1\n")

        permissions = AgentPermissions(
            read_paths=[tmp_path.resolve()],
            write_paths=[allowed.resolve()],
        )
        ctx = _auto_approve_ctx(tmp_path, permissions)
        result = InsertTextTool().execute(
            {"path": "denied/file.txt", "line_number": 1, "text": "x"}, ctx
        )
        assert "denied" in result.lower()
        assert target.read_text() == "line1\n"

    def test_append_denied_outside_allowed(self, tmp_path):
        allowed = tmp_path / "allowed"
        denied = tmp_path / "denied"
        allowed.mkdir()
        denied.mkdir()
        target = denied / "file.txt"
        target.write_text("base")

        permissions = AgentPermissions(
            read_paths=[tmp_path.resolve()],
            write_paths=[allowed.resolve()],
        )
        ctx = _auto_approve_ctx(tmp_path, permissions)
        result = AppendFileTool().execute({"path": "denied/file.txt", "content": "x"}, ctx)
        assert "denied" in result.lower()
        assert target.read_text() == "base"

    def test_remove_directory_denied_outside_allowed(self, tmp_path):
        allowed = tmp_path / "allowed"
        denied = tmp_path / "denied"
        allowed.mkdir()
        denied.mkdir()

        permissions = AgentPermissions(
            read_paths=[tmp_path.resolve()],
            write_paths=[allowed.resolve()],
        )
        ctx = _auto_approve_ctx(tmp_path, permissions)
        result = RemoveDirectoryTool().execute({"path": "denied"}, ctx)
        assert "denied" in result.lower()
        assert denied.exists()

    def test_explicit_empty_permissions_deny_write_in_base_dir(self, tmp_path):
        permissions = AgentPermissions.from_config({}, tmp_path)
        ctx = _auto_approve_ctx(tmp_path, permissions)

        result = WriteFileTool().execute({"path": "file.txt", "content": "x"}, ctx)
        assert "denied" in result.lower()
        assert not (tmp_path / "file.txt").exists()


class TestConfirmationGate:
    """Write operations must be gated by confirmation."""

    def test_no_confirmation_handler_denies(self, tmp_path):
        """Without WriteConfirmation, all writes are denied."""
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
        result = WriteFileTool().execute({"path": "f.txt", "content": "x"}, ctx)
        assert "confirmation" in result.lower()

    def test_callback_denial_prevents_write(self, tmp_path):
        """When callback returns False, write is prevented."""
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
        result = DeleteFileTool().execute({"path": "f.txt"}, ctx)
        # Either "not found" (if checked before confirm) or "cancelled"
        # In this case, file doesn't exist, so "not found" is expected.
        # Let's test with an existing file.
        target = tmp_path / "real.txt"
        target.write_text("keep me")
        result = DeleteFileTool().execute({"path": "real.txt"}, ctx)
        assert "cancelled" in result.lower()
        assert target.read_text() == "keep me"

    def test_write_file_denied_by_callback(self, tmp_path):
        calls: list[tuple[str, str, str]] = []

        def _deny(op, path, details):
            calls.append((op, path, details))
            return False

        ctx = _denied_ctx(tmp_path, _deny)
        result = WriteFileTool().execute({"path": "new.txt", "content": "x"}, ctx)
        assert "cancelled" in result.lower()
        assert not (tmp_path / "new.txt").exists()
        assert len(calls) == 1
        assert calls[0][0] == "Create file"

    def test_edit_file_denied_by_callback(self, tmp_path):
        target = tmp_path / "file.txt"
        target.write_text("before")
        calls: list[tuple[str, str, str]] = []

        def _deny(op, path, details):
            calls.append((op, path, details))
            return False

        ctx = _denied_ctx(tmp_path, _deny)
        result = EditFileTool().execute(
            {"path": "file.txt", "old_text": "before", "new_text": "after"}, ctx
        )
        assert "cancelled" in result.lower()
        assert target.read_text() == "before"
        assert len(calls) == 1
        assert calls[0][0] == "Edit file"

    def test_insert_text_denied_by_callback(self, tmp_path):
        target = tmp_path / "file.txt"
        target.write_text("line1\n")
        calls: list[tuple[str, str, str]] = []

        def _deny(op, path, details):
            calls.append((op, path, details))
            return False

        ctx = _denied_ctx(tmp_path, _deny)
        result = InsertTextTool().execute(
            {"path": "file.txt", "line_number": 1, "text": "line0"}, ctx
        )
        assert "cancelled" in result.lower()
        assert target.read_text() == "line1\n"
        assert len(calls) == 1
        assert calls[0][0] == "Insert text"

    def test_append_file_denied_by_callback(self, tmp_path):
        target = tmp_path / "file.txt"
        target.write_text("line1\n")
        calls: list[tuple[str, str, str]] = []

        def _deny(op, path, details):
            calls.append((op, path, details))
            return False

        ctx = _denied_ctx(tmp_path, _deny)
        result = AppendFileTool().execute({"path": "file.txt", "content": "line2"}, ctx)
        assert "cancelled" in result.lower()
        assert target.read_text() == "line1\n"
        assert len(calls) == 1
        assert calls[0][0] == "Append to file"

    def test_delete_file_denied_by_callback(self, tmp_path):
        target = tmp_path / "file.txt"
        target.write_text("keep")
        calls: list[tuple[str, str, str]] = []

        def _deny(op, path, details):
            calls.append((op, path, details))
            return False

        ctx = _denied_ctx(tmp_path, _deny)
        result = DeleteFileTool().execute({"path": "file.txt"}, ctx)
        assert "cancelled" in result.lower()
        assert target.read_text() == "keep"
        assert len(calls) == 1
        assert calls[0][0] == "Delete file"

    def test_create_directory_denied_by_callback(self, tmp_path):
        calls: list[tuple[str, str, str]] = []

        def _deny(op, path, details):
            calls.append((op, path, details))
            return False

        ctx = _denied_ctx(tmp_path, _deny)
        result = CreateDirectoryTool().execute({"path": "newdir"}, ctx)
        assert "cancelled" in result.lower()
        assert not (tmp_path / "newdir").exists()
        assert len(calls) == 1
        assert calls[0][0] == "Create directory"

    def test_remove_directory_denied_by_callback(self, tmp_path):
        target = tmp_path / "newdir"
        target.mkdir()
        calls: list[tuple[str, str, str]] = []

        def _deny(op, path, details):
            calls.append((op, path, details))
            return False

        ctx = _denied_ctx(tmp_path, _deny)
        result = RemoveDirectoryTool().execute({"path": "newdir"}, ctx)
        assert "cancelled" in result.lower()
        assert target.exists()
        assert len(calls) == 1
        assert calls[0][0] == "Remove directory"
