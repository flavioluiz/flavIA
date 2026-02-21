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


def test_load_settings_reads_rag_debug_and_tuning_env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("RAG_DEBUG", "true")
    monkeypatch.setenv("RAG_VECTOR_K", "24")
    monkeypatch.setenv("RAG_FTS_K", "31")
    monkeypatch.setenv("RAG_CHUNK_MIN_TOKENS", "220")
    monkeypatch.setenv("RAG_CHUNK_MAX_TOKENS", "900")
    monkeypatch.setenv("RAG_VIDEO_WINDOW_SECONDS", "75")

    settings = load_settings()

    assert settings.rag_debug is True
    assert settings.rag_vector_k == 24
    assert settings.rag_fts_k == 31
    assert settings.rag_chunk_min_tokens == 220
    assert settings.rag_chunk_max_tokens == 900
    assert settings.rag_video_window_seconds == 75


def test_load_settings_ignores_invalid_rag_tuning_env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("RAG_VECTOR_K", "-1")
    monkeypatch.setenv("RAG_FTS_K", "abc")
    monkeypatch.setenv("RAG_CHUNK_MIN_TOKENS", "5000")
    monkeypatch.setenv("RAG_CHUNK_MAX_TOKENS", "20")

    settings = load_settings()

    assert settings.rag_vector_k == 15
    assert settings.rag_fts_k == 15
    assert settings.rag_chunk_min_tokens == 300
    assert settings.rag_chunk_max_tokens == 800


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
    assert "- web_search" in agents_data
    assert "- compact_context" in agents_data
    assert "- search_chunks" in agents_data
    assert "- refresh_catalog" not in agents_data
    assert "- compile_latex" not in agents_data


def test_init_local_config_creates_bots_yaml(tmp_path):
    """init_local_config should create a bots.yaml template."""
    ok = init_local_config(tmp_path)
    assert ok is True

    bots_yaml = tmp_path / ".flavia" / "bots.yaml"
    assert bots_yaml.exists()
    content = bots_yaml.read_text(encoding="utf-8")
    assert "bots:" in content
    assert "${TELEGRAM_BOT_TOKEN}" in content


# ---------------------------------------------------------------------------
# Bot registry integration tests
# ---------------------------------------------------------------------------


def test_load_bots_from_yaml(tmp_path, monkeypatch):
    """bots.yaml loads and syncs to legacy telegram fields."""
    import textwrap

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "legacy:token")
    monkeypatch.delenv("TELEGRAM_ALLOWED_USER_IDS", raising=False)
    monkeypatch.delenv("TELEGRAM_ALLOW_ALL_USERS", raising=False)

    local_dir = tmp_path / ".flavia"
    local_dir.mkdir()
    bots_yaml = local_dir / "bots.yaml"
    bots_yaml.write_text(
        textwrap.dedent("""\
            bots:
              my-bot:
                platform: telegram
                token: "${TELEGRAM_BOT_TOKEN}"
                default_agent: main
                access:
                  allowed_users: [999]
                  allow_all: false
        """),
        encoding="utf-8",
    )

    settings = load_settings()

    assert "my-bot" in settings.bot_registry.bots
    bot = settings.bot_registry.bots["my-bot"]
    assert bot.token == "legacy:token"
    assert bot.access.allowed_users == [999]
    # Legacy fields should be synced
    assert 999 in settings.telegram_allowed_users
    assert settings.telegram_token == "legacy:token"


def test_bots_yaml_missing_falls_back_to_env(tmp_path, monkeypatch):
    """When no bots.yaml exists, env vars create a fallback bot config."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "env:fallback")
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "777")
    monkeypatch.delenv("TELEGRAM_ALLOW_ALL_USERS", raising=False)

    settings = load_settings()

    # Fallback bot should be created from env vars
    first_tg = settings.bot_registry.get_first_telegram_bot()
    assert first_tg is not None
    assert first_tg.token == "env:fallback"
    assert 777 in first_tg.access.allowed_users
    assert settings.telegram_token == "env:fallback"


def test_bots_yaml_overrides_env_vars(tmp_path, monkeypatch):
    """bots.yaml token takes precedence over TELEGRAM_BOT_TOKEN for bot_config."""
    import textwrap

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("YAML_BOT_TOKEN", "yaml:secret")
    monkeypatch.delenv("TELEGRAM_ALLOWED_USER_IDS", raising=False)
    monkeypatch.delenv("TELEGRAM_ALLOW_ALL_USERS", raising=False)

    local_dir = tmp_path / ".flavia"
    local_dir.mkdir()
    bots_yaml = local_dir / "bots.yaml"
    bots_yaml.write_text(
        textwrap.dedent("""\
            bots:
              primary:
                platform: telegram
                token: "${YAML_BOT_TOKEN}"
                default_agent: main
                access:
                  allow_all: true
        """),
        encoding="utf-8",
    )

    settings = load_settings()

    first_tg = settings.bot_registry.get_first_telegram_bot()
    assert first_tg is not None
    assert first_tg.token == "yaml:secret"
    assert first_tg.access.allow_all is True


def test_empty_bots_yaml_falls_back_to_env(tmp_path, monkeypatch):
    """bots: {} in YAML should trigger env-var fallback."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "env:tok")
    monkeypatch.delenv("TELEGRAM_ALLOWED_USER_IDS", raising=False)
    monkeypatch.delenv("TELEGRAM_ALLOW_ALL_USERS", raising=False)

    local_dir = tmp_path / ".flavia"
    local_dir.mkdir()
    (local_dir / "bots.yaml").write_text("bots: {}\n", encoding="utf-8")

    settings = load_settings()

    first_tg = settings.bot_registry.get_first_telegram_bot()
    assert first_tg is not None
    assert first_tg.token == "env:tok"


def test_bots_yaml_explicit_empty_whitelist_denies_all(tmp_path, monkeypatch):
    """Explicit allowed_users: [] should be treated as configured deny-all."""
    import textwrap

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("TELEGRAM_ALLOWED_USER_IDS", raising=False)
    monkeypatch.delenv("TELEGRAM_ALLOW_ALL_USERS", raising=False)

    local_dir = tmp_path / ".flavia"
    local_dir.mkdir()
    (local_dir / "bots.yaml").write_text(
        textwrap.dedent("""\
            bots:
              secure:
                platform: telegram
                token: "mytoken"
                access:
                  allowed_users: []
                  allow_all: false
        """),
        encoding="utf-8",
    )

    settings = load_settings()

    first_tg = settings.bot_registry.get_first_telegram_bot()
    assert first_tg is not None
    assert first_tg.access.allowed_users == []
    assert first_tg.access.whitelist_configured is True
    assert settings.telegram_allowed_users == []
    assert settings.telegram_allow_all_users is False
    assert settings.telegram_whitelist_configured is True
