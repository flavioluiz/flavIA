"""Tests for configuration loading behavior."""

import os
import subprocess
import sys
from pathlib import Path

from flavia.config.loader import get_config_paths, init_local_config
from flavia.config.settings import load_settings


def test_env_file_prefers_local_flavia_over_user(tmp_path, monkeypatch):
    """Local .flavia/.env should override user-level configuration."""
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    monkeypatch.chdir(project_dir)

    home_dir = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home_dir))
    monkeypatch.delenv("SYNTHETIC_API_KEY", raising=False)

    local_config = project_dir / ".flavia"
    local_config.mkdir()
    (local_config / ".env").write_text("SYNTHETIC_API_KEY=local_key\n", encoding="utf-8")

    user_config = home_dir / ".config" / "flavia"
    user_config.mkdir(parents=True)
    (user_config / ".env").write_text("SYNTHETIC_API_KEY=user_key\n", encoding="utf-8")

    paths = get_config_paths()
    assert paths.env_file == local_config / ".env"

    settings = load_settings()
    assert settings.api_key == "local_key"


def test_load_settings_ignores_invalid_telegram_user_ids(tmp_path, monkeypatch):
    """Invalid IDs should not crash settings loading."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "123, invalid, 456, , nope")

    settings = load_settings()
    assert settings.telegram_allowed_users == [123, 456]
    assert settings.telegram_whitelist_configured is True
    assert settings.telegram_allow_all_users is False


def test_load_settings_supports_explicit_public_telegram_mode(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("TELEGRAM_ALLOW_ALL_USERS", "true")
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "123")

    settings = load_settings()
    assert settings.telegram_allow_all_users is True


def test_load_settings_supports_wildcard_public_mode(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "*")

    settings = load_settings()
    assert settings.telegram_allow_all_users is True
    assert settings.telegram_whitelist_configured is False


def test_load_settings_reads_global_compact_threshold_from_env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("AGENT_COMPACT_THRESHOLD", "0.82")

    settings = load_settings()
    assert settings.compact_threshold == 0.82
    assert settings.compact_threshold_configured is True


def test_load_settings_ignores_invalid_compact_threshold_env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("AGENT_COMPACT_THRESHOLD", "9.99")

    settings = load_settings()
    assert settings.compact_threshold == 0.9
    assert settings.compact_threshold_configured is False


def test_load_settings_reads_status_task_limits_from_env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("STATUS_MAX_TASKS_MAIN", "8")
    monkeypatch.setenv("STATUS_MAX_TASKS_SUBAGENT", "2")

    settings = load_settings()
    assert settings.status_max_tasks_main == 8
    assert settings.status_max_tasks_subagent == 2


def test_load_settings_reads_summary_model_from_env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("SUMMARY_MODEL", "synthetic:hf:moonshotai/Kimi-K2-Instruct-0905")

    settings = load_settings()
    assert settings.summary_model == "synthetic:hf:moonshotai/Kimi-K2-Instruct-0905"


def test_python_m_flavia_propagates_exit_code(tmp_path):
    """python -m flavia should return the CLI exit code."""
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")
    env["HOME"] = str(tmp_path / "home")
    env["FLAVIA_DISABLE_AUTO_VENV"] = "1"
    env.pop("SYNTHETIC_API_KEY", None)

    result = subprocess.run(
        [sys.executable, "-m", "flavia"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "API key not configured" in result.stdout


def test_init_local_config_uses_broad_read_only_toolset(tmp_path):
    ok = init_local_config(tmp_path)
    assert ok is True

    agents_data = (tmp_path / ".flavia" / "agents.yaml").read_text(encoding="utf-8")
    assert "- analyze_image" in agents_data
    assert "- compact_context" in agents_data
    assert "- search_chunks" in agents_data
    assert "- refresh_catalog" not in agents_data
    assert "- compile_latex" not in agents_data
