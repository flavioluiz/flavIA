"""Unit tests for src/flavia/config/bots.py."""

import textwrap
from pathlib import Path

import pytest

from flavia.config.bots import (
    BotAccessConfig,
    BotConfig,
    BotRegistry,
    create_fallback_telegram_bot,
    load_bot_config,
    load_bots_from_file,
    merge_bot_registries,
)


# ---------------------------------------------------------------------------
# BotAccessConfig
# ---------------------------------------------------------------------------


def test_bot_access_config_whitelist_configured_true():
    access = BotAccessConfig(allowed_users=[123, 456])
    assert access.whitelist_configured is True


def test_bot_access_config_whitelist_configured_false_when_empty():
    access = BotAccessConfig(allowed_users=[])
    assert access.whitelist_configured is False


def test_bot_access_config_whitelist_configured_true_when_explicit_empty():
    access = BotAccessConfig(allowed_users=[], allowed_users_configured=True)
    assert access.whitelist_configured is True


# ---------------------------------------------------------------------------
# BotConfig.is_agent_allowed
# ---------------------------------------------------------------------------


def test_is_agent_allowed_none_means_all():
    bot = BotConfig(id="b", platform="telegram", token="t", allowed_agents=None)
    assert bot.is_agent_allowed("anything") is True


def test_is_agent_allowed_restricted_list():
    bot = BotConfig(id="b", platform="telegram", token="t", allowed_agents=["main", "researcher"])
    assert bot.is_agent_allowed("main") is True
    assert bot.is_agent_allowed("researcher") is True
    assert bot.is_agent_allowed("summarizer") is False


# ---------------------------------------------------------------------------
# load_bot_config
# ---------------------------------------------------------------------------


def test_load_bot_config_basic():
    data = {
        "platform": "telegram",
        "token": "123:ABC",
        "default_agent": "main",
    }
    bot = load_bot_config(data, "my-bot")
    assert bot.id == "my-bot"
    assert bot.platform == "telegram"
    assert bot.token == "123:ABC"
    assert bot.default_agent == "main"
    assert bot.allowed_agents is None
    assert bot.access.allowed_users == []
    assert bot.access.allow_all is False


def test_load_bot_config_with_access():
    data = {
        "platform": "telegram",
        "token": "tok",
        "access": {
            "allowed_users": [111, 222],
            "allow_all": False,
        },
    }
    bot = load_bot_config(data, "restricted")
    assert bot.access.allowed_users == [111, 222]
    assert bot.access.allow_all is False
    assert bot.access.whitelist_configured is True


def test_load_bot_config_with_explicit_empty_allowed_users_marks_whitelist():
    data = {
        "platform": "telegram",
        "token": "tok",
        "access": {
            "allowed_users": [],
            "allow_all": False,
        },
    }
    bot = load_bot_config(data, "restricted")
    assert bot.access.allowed_users == []
    assert bot.access.allow_all is False
    assert bot.access.whitelist_configured is True


def test_load_bot_config_allowed_agents_list():
    data = {
        "platform": "telegram",
        "token": "tok",
        "allowed_agents": ["main", "researcher"],
    }
    bot = load_bot_config(data, "b")
    assert bot.allowed_agents == ["main", "researcher"]


def test_load_bot_config_allowed_agents_all_string():
    data = {"platform": "telegram", "token": "tok", "allowed_agents": "all"}
    bot = load_bot_config(data, "b")
    assert bot.allowed_agents is None


def test_load_bot_config_allowed_agents_omitted():
    data = {"platform": "telegram", "token": "tok"}
    bot = load_bot_config(data, "b")
    assert bot.allowed_agents is None


def test_load_bot_config_env_var_expansion(monkeypatch):
    monkeypatch.setenv("MY_BOT_TOKEN", "999:XYZ")
    data = {"platform": "telegram", "token": "${MY_BOT_TOKEN}"}
    bot = load_bot_config(data, "env-bot")
    assert bot.token == "999:XYZ"
    assert bot.token_env_var == "MY_BOT_TOKEN"


def test_load_bot_config_invalid_allowed_users_is_ignored():
    data = {
        "platform": "telegram",
        "token": "tok",
        "access": {
            "allowed_users": ["abc", None, 123],
            "allow_all": False,
        },
    }
    bot = load_bot_config(data, "b")
    assert bot.access.allowed_users == [123]
    assert bot.access.whitelist_configured is True


def test_load_bot_config_allow_all_parses_string_false():
    data = {
        "platform": "telegram",
        "token": "tok",
        "access": {
            "allow_all": "false",
        },
    }
    bot = load_bot_config(data, "b")
    assert bot.access.allow_all is False


def test_load_bot_config_allow_all_parses_string_true():
    data = {
        "platform": "telegram",
        "token": "tok",
        "access": {
            "allow_all": "true",
        },
    }
    bot = load_bot_config(data, "b")
    assert bot.access.allow_all is True


# ---------------------------------------------------------------------------
# load_bots_from_file
# ---------------------------------------------------------------------------


def test_load_bots_from_file_valid(tmp_path):
    yaml_content = textwrap.dedent("""\
        bots:
          research-bot:
            platform: telegram
            token: "123:ABC"
            default_agent: researcher
            allowed_agents:
              - researcher
              - summarizer
            access:
              allowed_users: [100, 200]
              allow_all: false
    """)
    bots_file = tmp_path / "bots.yaml"
    bots_file.write_text(yaml_content, encoding="utf-8")

    registry = load_bots_from_file(bots_file)
    assert "research-bot" in registry.bots
    bot = registry.bots["research-bot"]
    assert bot.platform == "telegram"
    assert bot.token == "123:ABC"
    assert bot.default_agent == "researcher"
    assert bot.allowed_agents == ["researcher", "summarizer"]
    assert bot.access.allowed_users == [100, 200]


def test_load_bots_from_file_empty_bots_section(tmp_path):
    bots_file = tmp_path / "bots.yaml"
    bots_file.write_text("bots: {}\n", encoding="utf-8")
    registry = load_bots_from_file(bots_file)
    assert registry.bots == {}


def test_load_bots_from_file_missing_file(tmp_path):
    registry = load_bots_from_file(tmp_path / "nonexistent.yaml")
    assert registry.bots == {}


def test_load_bots_from_file_invalid_yaml(tmp_path):
    bots_file = tmp_path / "bots.yaml"
    bots_file.write_text("{ invalid yaml: [\n", encoding="utf-8")
    registry = load_bots_from_file(bots_file)
    assert registry.bots == {}


def test_load_bots_from_file_non_mapping_root(tmp_path):
    bots_file = tmp_path / "bots.yaml"
    bots_file.write_text("- not-a-dict\n", encoding="utf-8")
    registry = load_bots_from_file(bots_file)
    assert registry.bots == {}


def test_load_bots_from_file_non_mapping_bots_section(tmp_path):
    bots_file = tmp_path / "bots.yaml"
    bots_file.write_text("bots: []\n", encoding="utf-8")
    registry = load_bots_from_file(bots_file)
    assert registry.bots == {}


def test_load_bots_from_file_skips_invalid_bot_entries(tmp_path):
    yaml_content = textwrap.dedent("""\
        bots:
          valid:
            platform: telegram
            token: "123:ABC"
            access:
              allowed_users: [100]
              allow_all: false
          broken:
            platform: telegram
            token: "123:ABC"
            access:
              allowed_users: "x,y,z"
              allow_all: false
          not-a-dict: "hello"
    """)
    bots_file = tmp_path / "bots.yaml"
    bots_file.write_text(yaml_content, encoding="utf-8")
    registry = load_bots_from_file(bots_file)
    assert "valid" in registry.bots
    assert "broken" in registry.bots
    assert "not-a-dict" not in registry.bots
    assert registry.bots["broken"].access.allowed_users == []


# ---------------------------------------------------------------------------
# create_fallback_telegram_bot
# ---------------------------------------------------------------------------


def test_create_fallback_telegram_bot_with_users():
    bot = create_fallback_telegram_bot("tok", [111, 222], False)
    assert bot.id == "default"
    assert bot.platform == "telegram"
    assert bot.token == "tok"
    assert bot.token_env_var == "TELEGRAM_BOT_TOKEN"
    assert bot.default_agent == "main"
    assert bot.allowed_agents is None
    assert bot.access.allowed_users == [111, 222]
    assert bot.access.allow_all is False


def test_create_fallback_telegram_bot_allow_all():
    bot = create_fallback_telegram_bot("tok", [], True)
    assert bot.access.allow_all is True
    assert bot.access.allowed_users == []


def test_create_fallback_telegram_bot_whitelist_flag():
    bot = create_fallback_telegram_bot("tok", [], False, whitelist_configured=True)
    assert bot.access.whitelist_configured is True


# ---------------------------------------------------------------------------
# merge_bot_registries
# ---------------------------------------------------------------------------


def test_merge_bot_registries_later_wins():
    reg1 = BotRegistry(
        bots={"bot-a": BotConfig(id="bot-a", platform="telegram", token="old")}
    )
    reg2 = BotRegistry(
        bots={"bot-a": BotConfig(id="bot-a", platform="telegram", token="new")}
    )
    merged = merge_bot_registries(reg1, reg2)
    assert merged.bots["bot-a"].token == "new"


def test_merge_bot_registries_combines_different_ids():
    reg1 = BotRegistry(bots={"a": BotConfig(id="a", platform="telegram", token="t1")})
    reg2 = BotRegistry(bots={"b": BotConfig(id="b", platform="telegram", token="t2")})
    merged = merge_bot_registries(reg1, reg2)
    assert "a" in merged.bots
    assert "b" in merged.bots


def test_merge_bot_registries_empty():
    merged = merge_bot_registries(BotRegistry(), BotRegistry())
    assert merged.bots == {}


# ---------------------------------------------------------------------------
# BotRegistry helpers
# ---------------------------------------------------------------------------


def test_bot_registry_get_bots_by_platform():
    reg = BotRegistry(
        bots={
            "tg1": BotConfig(id="tg1", platform="telegram", token="a"),
            "tg2": BotConfig(id="tg2", platform="telegram", token="b"),
            "wa1": BotConfig(id="wa1", platform="whatsapp", token="c"),
        }
    )
    tg_bots = reg.get_telegram_bots()
    assert len(tg_bots) == 2
    assert all(b.platform == "telegram" for b in tg_bots)


def test_bot_registry_get_first_telegram_bot_none_when_empty():
    reg = BotRegistry()
    assert reg.get_first_telegram_bot() is None
