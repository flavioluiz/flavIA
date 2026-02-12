"""Tests for dry-run mode in write tools.

Verifies that when dry_run=True, tools report what they would do
without actually modifying the filesystem.
"""

import pytest
from pathlib import Path

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


def _make_dry_run_context(base_dir: Path) -> AgentContext:
    """Create a test AgentContext with dry_run=True and auto-approve."""
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
        permissions=AgentPermissions(),
        write_confirmation=wc,
        dry_run=True,
    )


class TestDryRunWriteFile:
    def test_create_file_dry_run(self, tmp_path):
        tool = WriteFileTool()
        ctx = _make_dry_run_context(tmp_path)
        result = tool.execute({"path": "new.txt", "content": "content"}, ctx)

        assert "[DRY-RUN]" in result
        assert "Would create" in result
        # File should not be created
        assert not (tmp_path / "new.txt").exists()

    def test_overwrite_file_dry_run(self, tmp_path):
        (tmp_path / "existing.txt").write_text("old content")
        tool = WriteFileTool()
        ctx = _make_dry_run_context(tmp_path)
        result = tool.execute({"path": "existing.txt", "content": "new content"}, ctx)

        assert "[DRY-RUN]" in result
        assert "Would overwrite" in result
        # File should still have old content
        assert (tmp_path / "existing.txt").read_text() == "old content"


class TestDryRunEditFile:
    def test_edit_file_dry_run(self, tmp_path):
        (tmp_path / "code.py").write_text("x = 1\ny = 2\nz = 3\n")
        tool = EditFileTool()
        ctx = _make_dry_run_context(tmp_path)
        result = tool.execute(
            {
                "path": "code.py",
                "old_text": "y = 2",
                "new_text": "y = 42",
            },
            ctx,
        )

        assert "[DRY-RUN]" in result
        assert "Would edit" in result
        # File should be unchanged
        assert (tmp_path / "code.py").read_text() == "x = 1\ny = 2\nz = 3\n"


class TestDryRunInsertText:
    def test_insert_text_dry_run(self, tmp_path):
        (tmp_path / "f.txt").write_text("line1\nline2\n")
        tool = InsertTextTool()
        ctx = _make_dry_run_context(tmp_path)
        result = tool.execute(
            {
                "path": "f.txt",
                "line_number": 2,
                "text": "inserted",
            },
            ctx,
        )

        assert "[DRY-RUN]" in result
        assert "Would insert" in result
        # File should be unchanged
        assert (tmp_path / "f.txt").read_text() == "line1\nline2\n"


class TestDryRunAppendFile:
    def test_append_file_dry_run(self, tmp_path):
        (tmp_path / "log.txt").write_text("entry1\n")
        tool = AppendFileTool()
        ctx = _make_dry_run_context(tmp_path)
        result = tool.execute({"path": "log.txt", "content": "entry2\n"}, ctx)

        assert "[DRY-RUN]" in result
        assert "Would append" in result
        # File should be unchanged
        assert (tmp_path / "log.txt").read_text() == "entry1\n"

    def test_create_file_via_append_dry_run(self, tmp_path):
        tool = AppendFileTool()
        ctx = _make_dry_run_context(tmp_path)
        result = tool.execute({"path": "new.txt", "content": "content"}, ctx)

        assert "[DRY-RUN]" in result
        assert "Would create" in result
        # File should not be created
        assert not (tmp_path / "new.txt").exists()


class TestDryRunDeleteFile:
    def test_delete_file_dry_run(self, tmp_path):
        target = tmp_path / "victim.txt"
        target.write_text("bye")
        tool = DeleteFileTool()
        ctx = _make_dry_run_context(tmp_path)
        result = tool.execute({"path": "victim.txt"}, ctx)

        assert "[DRY-RUN]" in result
        assert "Would delete" in result
        # File should still exist
        assert target.exists()
        assert target.read_text() == "bye"


class TestDryRunCreateDirectory:
    def test_create_directory_dry_run(self, tmp_path):
        tool = CreateDirectoryTool()
        ctx = _make_dry_run_context(tmp_path)
        result = tool.execute({"path": "newdir"}, ctx)

        assert "[DRY-RUN]" in result
        assert "Would create directory" in result
        # Directory should not be created
        assert not (tmp_path / "newdir").exists()

    def test_create_nested_directory_dry_run(self, tmp_path):
        tool = CreateDirectoryTool()
        ctx = _make_dry_run_context(tmp_path)
        result = tool.execute({"path": "a/b/c"}, ctx)

        assert "[DRY-RUN]" in result
        # No directories should be created
        assert not (tmp_path / "a").exists()


class TestDryRunRemoveDirectory:
    def test_remove_empty_directory_dry_run(self, tmp_path):
        (tmp_path / "empty").mkdir()
        tool = RemoveDirectoryTool()
        ctx = _make_dry_run_context(tmp_path)
        result = tool.execute({"path": "empty"}, ctx)

        assert "[DRY-RUN]" in result
        assert "Would remove directory" in result
        # Directory should still exist
        assert (tmp_path / "empty").exists()

    def test_remove_directory_recursive_dry_run(self, tmp_path):
        d = tmp_path / "tree"
        d.mkdir()
        (d / "sub").mkdir()
        (d / "sub" / "file.txt").write_text("nested")
        tool = RemoveDirectoryTool()
        ctx = _make_dry_run_context(tmp_path)
        result = tool.execute({"path": "tree", "recursive": True}, ctx)

        assert "[DRY-RUN]" in result
        assert "Would remove directory" in result
        # Directory and contents should still exist
        assert d.exists()
        assert (d / "sub" / "file.txt").exists()


class TestDryRunPropagation:
    def test_dry_run_propagates_to_child_context(self, tmp_path):
        """Verify dry_run is passed to child contexts."""
        from flavia.agent.profile import AgentProfile

        ctx = _make_dry_run_context(tmp_path)
        profile = AgentProfile(
            name="child",
            context="test child",
            model="test-model",
            tools=[],
            subagents={},
        )
        profile.base_dir = tmp_path

        child_ctx = ctx.create_child_context("child-1", profile)
        assert child_ctx.dry_run is True


class TestNoBackupInDryRun:
    def test_no_backup_created_on_dry_run_overwrite(self, tmp_path):
        """Verify backup is not created when dry-run prevents actual write."""
        (tmp_path / "data.txt").write_text("original")
        tool = WriteFileTool()
        ctx = _make_dry_run_context(tmp_path)
        tool.execute({"path": "data.txt", "content": "replaced"}, ctx)

        backup_dir = tmp_path / ".flavia" / "file_backups"
        # No backup should be created since write didn't happen
        assert not backup_dir.exists() or len(list(backup_dir.rglob("*.bak"))) == 0

    def test_no_backup_created_on_dry_run_edit(self, tmp_path):
        (tmp_path / "f.txt").write_text("hello world")
        tool = EditFileTool()
        ctx = _make_dry_run_context(tmp_path)
        tool.execute(
            {
                "path": "f.txt",
                "old_text": "hello",
                "new_text": "goodbye",
            },
            ctx,
        )

        backup_dir = tmp_path / ".flavia" / "file_backups"
        assert not backup_dir.exists() or len(list(backup_dir.rglob("*.bak"))) == 0

    def test_no_backup_created_on_dry_run_delete(self, tmp_path):
        (tmp_path / "victim.txt").write_text("content")
        tool = DeleteFileTool()
        ctx = _make_dry_run_context(tmp_path)
        tool.execute({"path": "victim.txt"}, ctx)

        backup_dir = tmp_path / ".flavia" / "file_backups"
        assert not backup_dir.exists() or len(list(backup_dir.rglob("*.bak"))) == 0
