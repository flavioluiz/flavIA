"""Tests for project venv bootstrap behavior."""

from pathlib import Path

import pytest

from flavia import venv_bootstrap


def test_find_project_root_resolves_repository_root():
    root = venv_bootstrap.find_project_root()
    assert root is not None
    assert (root / "pyproject.toml").exists()
    assert (root / "src" / "flavia").exists()


def test_ensure_project_venv_skips_when_disabled(monkeypatch):
    monkeypatch.setenv(venv_bootstrap.DISABLE_AUTO_VENV_ENV, "1")
    called = {"execv": False}

    def fake_execv(path, argv):
        called["execv"] = True

    monkeypatch.setattr(venv_bootstrap.os, "execv", fake_execv)
    venv_bootstrap.ensure_project_venv_and_reexec(["--version"])
    assert called["execv"] is False


def test_ensure_project_venv_reexecs_when_ready(monkeypatch, tmp_path):
    project_root = tmp_path / "project"
    venv_dir = project_root / ".venv"
    python_path = venv_dir / "bin" / "python"
    marker = venv_dir / venv_bootstrap.BOOTSTRAP_MARKER

    python_path.parent.mkdir(parents=True)
    python_path.write_text("", encoding="utf-8")
    marker.write_text("ok\n", encoding="utf-8")

    current_python = tmp_path / "python-current"
    current_python.write_text("", encoding="utf-8")

    monkeypatch.delenv(venv_bootstrap.DISABLE_AUTO_VENV_ENV, raising=False)
    monkeypatch.setattr(venv_bootstrap, "find_project_root", lambda: project_root)
    monkeypatch.setattr(venv_bootstrap.sys, "executable", str(current_python))

    captured = {}

    def fake_execv(path, argv):
        captured["path"] = path
        captured["argv"] = argv
        raise RuntimeError("stop")

    monkeypatch.setattr(venv_bootstrap.os, "execv", fake_execv)

    with pytest.raises(RuntimeError, match="stop"):
        venv_bootstrap.ensure_project_venv_and_reexec(["--version"])

    assert captured["path"] == str(python_path)
    assert captured["argv"] == [str(python_path), "-m", "flavia", "--version"]


def test_ensure_project_venv_bootstraps_when_marker_missing(monkeypatch, tmp_path):
    project_root = tmp_path / "project"
    venv_dir = project_root / ".venv"
    python_path = venv_dir / "bin" / "python"
    marker = venv_dir / venv_bootstrap.BOOTSTRAP_MARKER

    python_path.parent.mkdir(parents=True)
    python_path.write_text("", encoding="utf-8")

    current_python = tmp_path / "python-current"
    current_python.write_text("", encoding="utf-8")

    monkeypatch.delenv(venv_bootstrap.DISABLE_AUTO_VENV_ENV, raising=False)
    monkeypatch.setattr(venv_bootstrap, "find_project_root", lambda: project_root)
    monkeypatch.setattr(venv_bootstrap.sys, "executable", str(current_python))

    calls = {"bootstrap": 0, "execv": 0}

    def fake_bootstrap(root: Path, venv: Path):
        calls["bootstrap"] += 1
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("ok\n", encoding="utf-8")

    def fake_execv(path, argv):
        calls["execv"] += 1
        raise RuntimeError("stop")

    monkeypatch.setattr(venv_bootstrap, "_bootstrap_project_venv", fake_bootstrap)
    monkeypatch.setattr(venv_bootstrap.os, "execv", fake_execv)

    with pytest.raises(RuntimeError, match="stop"):
        venv_bootstrap.ensure_project_venv_and_reexec(["--config"])

    assert calls["bootstrap"] == 1
    assert calls["execv"] == 1
