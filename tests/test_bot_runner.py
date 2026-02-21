"""Tests for Telegram multi-bot runner behavior."""

import asyncio
from types import SimpleNamespace

import pytest

import flavia.interfaces as interfaces
import flavia.interfaces.bot_runner as bot_runner
from flavia.config.bots import BotAccessConfig, BotConfig, BotRegistry


def _settings_with_registry(registry: BotRegistry) -> SimpleNamespace:
    return SimpleNamespace(bot_registry=registry)


def test_bot_selection_by_name():
    """Specific bot IDs resolve correctly from the registry."""
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

    assert registry.get_bot("bot1").id == "bot1"
    assert registry.get_bot("bot2").id == "bot2"
    assert registry.get_bot("nonexistent") is None


def test_get_telegram_bots_filters_by_platform():
    """Registry helper returns only Telegram bots."""
    registry = BotRegistry()
    registry.bots["tg1"] = BotConfig(id="tg1", platform="telegram", token="a")
    registry.bots["tg2"] = BotConfig(id="tg2", platform="telegram", token="b")
    registry.bots["wa1"] = BotConfig(id="wa1", platform="whatsapp", token="c")

    tg_bots = registry.get_telegram_bots()
    assert len(tg_bots) == 2
    assert all(b.platform == "telegram" for b in tg_bots)


def test_bot_access_config_whitelist():
    """Access control fields are preserved per bot."""
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


def test_run_telegram_bots_runs_only_selected_bot(monkeypatch):
    """When bot_name is provided, only that bot is dispatched."""
    registry = BotRegistry(
        bots={
            "bot1": BotConfig(id="bot1", platform="telegram", token="a"),
            "bot2": BotConfig(id="bot2", platform="telegram", token="b"),
        }
    )
    settings = _settings_with_registry(registry)
    captured: dict[str, list[str]] = {}

    async def _fake_run_multiple(_settings, bot_configs):
        captured["ids"] = [bot.id for bot in bot_configs]

    monkeypatch.setattr(bot_runner, "_run_multiple_bots_async", _fake_run_multiple)

    assert bot_runner.run_telegram_bots(settings, bot_name="bot2") is True
    assert captured["ids"] == ["bot2"]


def test_run_telegram_bots_returns_false_for_unknown_bot(monkeypatch):
    """Unknown bot names fail fast and do not invoke async runtime."""
    registry = BotRegistry(
        bots={
            "bot1": BotConfig(id="bot1", platform="telegram", token="a"),
        }
    )
    settings = _settings_with_registry(registry)
    called = {"runtime": False}

    async def _fake_run_multiple(_settings, _bot_configs):
        called["runtime"] = True

    monkeypatch.setattr(bot_runner, "_run_multiple_bots_async", _fake_run_multiple)

    assert bot_runner.run_telegram_bots(settings, bot_name="missing") is False
    assert called["runtime"] is False


def test_run_telegram_bots_returns_false_for_non_telegram_bot(monkeypatch):
    """Selecting a bot from another platform returns a startup error."""
    registry = BotRegistry(
        bots={
            "web1": BotConfig(id="web1", platform="web", token="a"),
        }
    )
    settings = _settings_with_registry(registry)
    called = {"runtime": False}

    async def _fake_run_multiple(_settings, _bot_configs):
        called["runtime"] = True

    monkeypatch.setattr(bot_runner, "_run_multiple_bots_async", _fake_run_multiple)

    assert bot_runner.run_telegram_bots(settings, bot_name="web1") is False
    assert called["runtime"] is False


def test_run_multiple_bots_async_propagates_exceptions(monkeypatch):
    """Bot task errors must not be silently swallowed."""
    bots = [BotConfig(id="bad", platform="telegram", token="bad-token")]

    async def _fake_single(_settings, _bot_config):
        raise RuntimeError("boom")

    monkeypatch.setattr(bot_runner, "_run_single_telegram_bot_async", _fake_single)

    with pytest.raises(RuntimeError, match="boom"):
        asyncio.run(bot_runner._run_multiple_bots_async(SimpleNamespace(), bots))


def test_legacy_run_telegram_bot_keeps_single_bot_entrypoint(monkeypatch):
    """Legacy helper should still delegate to telegram_interface.run_telegram_bot."""
    called: dict[str, object] = {}

    def _fake_run_telegram_bot(settings, bot_config=None):
        called["settings"] = settings
        called["bot_config"] = bot_config

    monkeypatch.setattr(
        "flavia.interfaces.telegram_interface.run_telegram_bot",
        _fake_run_telegram_bot,
    )
    settings = object()

    interfaces.run_telegram_bot(settings)

    assert called["settings"] is settings
    assert called["bot_config"] is None
