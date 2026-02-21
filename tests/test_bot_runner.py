"""Tests for src/flavia/interfaces/bot_runner.py."""

import pytest

from flavia.config.bots import BotConfig, BotAccessConfig, BotRegistry
from flavia.interfaces.bot_runner import run_telegram_bots


def test_bot_selection_by_name():
    """Test that a specific bot can be selected by name."""
    registry = BotRegistry()
    registry.bots["bot1"] = BotConfig(
        id="bot1",
        platform="telegram",
        token="123:ABC",
        default_agent="main",
    )
    registry.bots["bot2"] = BotConfig(
        id="bot2",
        platform="telegram",
        token="456:DEF",
        default_agent="researcher",
    )

    # Test that selection logic works
    assert registry.get_bot("bot1").id == "bot1"
    assert registry.get_bot("bot2").id == "bot2"
    assert registry.get_bot("nonexistent") is None


def test_get_telegram_bots_filters_by_platform():
    """Test that get_telegram_bots only returns telegram bots."""
    registry = BotRegistry()
    registry.bots["tg1"] = BotConfig(
        id="tg1",
        platform="telegram",
        token="a",
    )
    registry.bots["tg2"] = BotConfig(
        id="tg2",
        platform="telegram",
        token="b",
    )
    registry.bots["wa1"] = BotConfig(
        id="wa1",
        platform="whatsapp",
        token="c",
    )

    tg_bots = registry.get_telegram_bots()
    assert len(tg_bots) == 2
    assert all(b.platform == "telegram" for b in tg_bots)


def test_bot_access_config_whitelist():
    """Test that bot access control works correctly."""
    registry = BotRegistry()
    registry.bots["public"] = BotConfig(
        id="public",
        platform="telegram",
        token="a",
        access=BotAccessConfig(allow_all=True, allowed_users=[]),
    )
    registry.bots["restricted"] = BotConfig(
        id="restricted",
        platform="telegram",
        token="b",
        access=BotAccessConfig(allow_all=False, allowed_users=[123, 456]),
    )

    assert registry.get_bot("public").access.allow_all is True
    assert registry.get_bot("restricted").access.allow_all is False
    assert registry.get_bot("restricted").access.allowed_users == [123, 456]


def test_bot_empty_registry():
    """Test empty registry behavior."""
    registry = BotRegistry()
    assert registry.get_bots_by_platform("telegram") == []
    assert registry.get_telegram_bots() == []
    assert registry.get_bot("any") is None


def test_bot_multiple_platforms():
    """Test registry with bots from multiple platforms."""
    registry = BotRegistry()
    registry.bots["tg1"] = BotConfig(id="tg1", platform="telegram", token="a")
    registry.bots["wa1"] = BotConfig(id="wa1", platform="whatsapp", token="b")
    registry.bots["web1"] = BotConfig(id="web1", platform="web", token="c")
    registry.bots["tg2"] = BotConfig(id="tg2", platform="telegram", token="d")

    assert len(registry.get_telegram_bots()) == 2
    assert len(registry.get_bots_by_platform("whatsapp")) == 1
    assert len(registry.get_bots_by_platform("web")) == 1
