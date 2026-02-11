"""Tests for the FileBackup mechanism."""

import time
from pathlib import Path

import pytest

from flavia.tools.backup import FileBackup


class TestFileBackup:
    def test_backup_creates_copy(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("important data")
        backup_path = FileBackup.backup(f, tmp_path)
        assert backup_path is not None
        assert backup_path.exists()
        assert backup_path.read_text() == "important data"
        assert backup_path.suffix == ".bak"

    def test_backup_preserves_directory_structure(self, tmp_path):
        sub = tmp_path / "a" / "b"
        sub.mkdir(parents=True)
        f = sub / "deep.txt"
        f.write_text("deep content")
        backup_path = FileBackup.backup(f, tmp_path)
        assert backup_path is not None
        # Should be under .flavia/file_backups/a/b/
        assert ".flavia" in str(backup_path)
        assert "file_backups" in str(backup_path)
        assert backup_path.read_text() == "deep content"

    def test_backup_nonexistent_file_returns_none(self, tmp_path):
        missing = tmp_path / "ghost.txt"
        result = FileBackup.backup(missing, tmp_path)
        assert result is None

    def test_backup_directory_returns_none(self, tmp_path):
        d = tmp_path / "adir"
        d.mkdir()
        result = FileBackup.backup(d, tmp_path)
        assert result is None

    def test_backup_has_timestamp_in_name(self, tmp_path):
        f = tmp_path / "ts.txt"
        f.write_text("data")
        backup_path = FileBackup.backup(f, tmp_path)
        assert backup_path is not None
        # Name format: ts.txt.YYYYMMDD_HHMMSS.bak
        name = backup_path.name
        assert name.startswith("ts.txt.")
        assert name.endswith(".bak")
        # Middle part should be a timestamp
        middle = name[len("ts.txt.") : -len(".bak")]
        assert len(middle) == 15  # YYYYMMDD_HHMMSS

    def test_multiple_backups_coexist(self, tmp_path):
        f = tmp_path / "multi.txt"
        f.write_text("v1")
        b1 = FileBackup.backup(f, tmp_path)
        # Modify and backup again (may need a short sleep for unique timestamp)
        time.sleep(1.1)
        f.write_text("v2")
        b2 = FileBackup.backup(f, tmp_path)
        assert b1 is not None and b2 is not None
        assert b1 != b2
        assert b1.read_text() == "v1"
        assert b2.read_text() == "v2"

    def test_backup_file_outside_base_dir(self, tmp_path):
        """Files outside base_dir are still backed up using full path structure."""
        import tempfile

        outside = Path(tempfile.mkdtemp())
        f = outside / "ext.txt"
        f.write_text("external")
        backup_path = FileBackup.backup(f, tmp_path)
        assert backup_path is not None
        assert backup_path.read_text() == "external"


class TestBackupCleanup:
    def test_cleanup_old_backups(self, tmp_path):
        backup_dir = tmp_path / ".flavia" / "file_backups"
        backup_dir.mkdir(parents=True)

        # Create a "old" backup by setting mtime in the past
        old_backup = backup_dir / "old.txt.20200101_000000.bak"
        old_backup.write_text("old")
        import os

        old_time = time.time() - (30 * 86400)  # 30 days ago
        os.utime(old_backup, (old_time, old_time))

        # Create a recent backup
        new_backup = backup_dir / "new.txt.20991231_235959.bak"
        new_backup.write_text("new")

        deleted = FileBackup.cleanup_old_backups(tmp_path, max_age_days=7)
        assert deleted == 1
        assert not old_backup.exists()
        assert new_backup.exists()

    def test_cleanup_no_backup_dir(self, tmp_path):
        """Cleanup on a project with no backups returns 0."""
        deleted = FileBackup.cleanup_old_backups(tmp_path)
        assert deleted == 0

    def test_cleanup_removes_empty_dirs(self, tmp_path):
        backup_dir = tmp_path / ".flavia" / "file_backups" / "sub"
        backup_dir.mkdir(parents=True)

        old_file = backup_dir / "file.txt.20200101_000000.bak"
        old_file.write_text("data")
        import os

        old_time = time.time() - (30 * 86400)
        os.utime(old_file, (old_time, old_time))

        FileBackup.cleanup_old_backups(tmp_path, max_age_days=7)
        # The "sub" directory should be removed since it's now empty
        assert not backup_dir.exists()
