"""Bootstrap and enforce an isolated project virtual environment."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional


DISABLE_AUTO_VENV_ENV = "FLAVIA_DISABLE_AUTO_VENV"
BOOTSTRAP_MARKER = ".flavia_bootstrap_complete"


def find_project_root() -> Optional[Path]:
    """Find flavIA project root from the current module location."""
    module_path = Path(__file__).resolve()
    for parent in module_path.parents:
        if (parent / "pyproject.toml").exists() and (parent / "src" / "flavia").exists():
            return parent
    return None


def _venv_python_path(venv_dir: Path) -> Path:
    """Return Python executable path inside a venv."""
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _run(cmd: list[str], cwd: Path) -> None:
    """Run a command and fail fast on errors."""
    subprocess.run(cmd, cwd=cwd, check=True)


def _bootstrap_project_venv(project_root: Path, venv_dir: Path) -> None:
    """Create project venv and install locked dependencies + package."""
    venv_python = _venv_python_path(venv_dir)
    print(f"[flavia] Preparing isolated environment at {venv_dir}")

    _run([sys.executable, "-m", "venv", str(venv_dir)], cwd=project_root)
    _run([str(venv_python), "-m", "pip", "install", "--upgrade", "pip"], cwd=project_root)

    lock_file = project_root / "requirements.lock"
    if lock_file.exists():
        _run([str(venv_python), "-m", "pip", "install", "-r", str(lock_file)], cwd=project_root)

    _run(
        [str(venv_python), "-m", "pip", "install", "--no-deps", "-e", str(project_root)],
        cwd=project_root,
    )

    (venv_dir / BOOTSTRAP_MARKER).write_text("ok\n", encoding="utf-8")


def ensure_project_venv_and_reexec(argv: list[str]) -> None:
    """
    Ensure flavIA runs from dedicated project venv.

    If needed, creates `.venv/`, installs locked dependencies, and re-execs current
    command inside that interpreter.
    """
    if os.getenv(DISABLE_AUTO_VENV_ENV) == "1":
        return

    project_root = find_project_root()
    if not project_root:
        return

    venv_dir = project_root / ".venv"
    venv_python = _venv_python_path(venv_dir)
    marker = venv_dir / BOOTSTRAP_MARKER

    try:
        current_python = Path(sys.executable).resolve()
        target_python = venv_python.resolve()
    except FileNotFoundError:
        current_python = Path(sys.executable)
        target_python = venv_python

    if current_python == target_python:
        return

    if not venv_python.exists() or not marker.exists():
        try:
            _bootstrap_project_venv(project_root, venv_dir)
        except subprocess.CalledProcessError as exc:
            print(f"[flavia] Failed to bootstrap venv: {exc}", file=sys.stderr)
            raise SystemExit(1) from exc

    os.execv(str(venv_python), [str(venv_python), "-m", "flavia", *argv])
