"""Tests for Telegram help text and log helpers."""

from flavia.config.settings import Settings
from flavia.interfaces.telegram_interface import TelegramBot


def _make_bot() -> TelegramBot:
    bot = TelegramBot.__new__(TelegramBot)
    bot.settings = Settings()
    bot.bot_config = None
    bot.agents = {}
    bot._user_agents = {}
    return bot


def test_help_text_lists_all_commands():
    bot = _make_bot()
    text = bot._build_help_text()
    assert "Welcome to flavIA Telegram mode." in text
    assert "/start" in text
    assert "/help" in text
    assert "/whoami" in text
    assert "/reset" in text
    assert "/compact" in text
    assert "Capabilities:" in text
    assert "- Reading and analyzing files" in text


def test_message_preview_truncates_long_text():
    bot = _make_bot()
    preview = bot._message_preview("a" * 200, max_len=20)
    assert preview.endswith("...")
    assert len(preview) == 20


def test_agent_id_prefix_keeps_telegram_legacy_value():
    bot = _make_bot()
    assert bot._agent_id_prefix() == "tg"
