"""Automatic file backup before write operations.

Creates timestamped backups in ``.flavia/file_backups/`` so that
destructive edits can be audited or rolled back manually.
"""

import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Optional


class FileBackup:
    """Create and manage file backups before modifications."""

    BACKUP_DIR_NAME = "file_backups"

    @staticmethod
    def _backup_dir(base_dir: Path) -> Path:
        """Return the backup directory path under ``.flavia/``."""
        return base_dir / ".flavia" / FileBackup.BACKUP_DIR_NAME

    @staticmethod
    def backup(file_path: Path, base_dir: Path) -> Optional[Path]:
        """Create a backup of *file_path* before it is modified.

        Args:
            file_path: Absolute, resolved path of the file to back up.
            base_dir: Project base directory (used to compute relative
                      backup paths and to locate the backup folder).

        Returns:
            The ``Path`` of the backup file, or ``None`` if the source
            file does not exist (nothing to back up).
        """
        if not file_path.exists() or not file_path.is_file():
            return None

        backup_root = FileBackup._backup_dir(base_dir)

        # Mirror the original directory structure inside the backup dir.
        try:
            relative = file_path.relative_to(base_dir.resolve())
        except ValueError:
            # File is outside base_dir — use the full path as structure.
            relative = Path(*file_path.parts[1:])

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        backup_name = f"{relative.name}.{timestamp}.bak"
        backup_path = backup_root / relative.parent / backup_name
        suffix = 1
        while backup_path.exists():
            backup_name = f"{relative.name}.{timestamp}.{suffix}.bak"
            backup_path = backup_root / relative.parent / backup_name
            suffix += 1

        try:
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(file_path), str(backup_path))
            return backup_path
        except Exception:
            # Backup failure should not block the operation, but callers
            # may choose to log or warn.
            return None

    @staticmethod
    def cleanup_old_backups(base_dir: Path, max_age_days: int = 7) -> int:
        """Remove backup files older than *max_age_days*.

        Args:
            base_dir: Project base directory.
            max_age_days: Maximum age in days. Files older than this are
                          removed.

        Returns:
            Number of backup files deleted.
        """
        backup_root = FileBackup._backup_dir(base_dir)
        if not backup_root.exists():
            return 0

        cutoff = time.time() - (max_age_days * 86400)
        deleted = 0

        for backup_file in backup_root.rglob("*.bak"):
            try:
                if backup_file.stat().st_mtime < cutoff:
                    backup_file.unlink()
                    deleted += 1
            except Exception:
                continue

        # Clean up empty directories left behind.
        for dirpath in sorted(backup_root.rglob("*"), reverse=True):
            try:
                if dirpath.is_dir() and not any(dirpath.iterdir()):
                    dirpath.rmdir()
            except Exception:
                continue

        return deleted
