"""Tests for Telegram authorization behavior."""

from flavia.config.settings import Settings
from flavia.interfaces.telegram_interface import TelegramBot


def _make_bot(settings: Settings) -> TelegramBot:
    bot = TelegramBot.__new__(TelegramBot)
    bot.settings = settings
    bot.bot_config = None
    bot.agents = {}
    bot._user_agents = {}
    return bot


def test_is_authorized_allows_any_user_in_public_mode():
    settings = Settings(telegram_allow_all_users=True, telegram_allowed_users=[123])
    bot = _make_bot(settings)
    assert bot._is_authorized(999) is True


def test_is_authorized_uses_whitelist_when_present():
    settings = Settings(telegram_allow_all_users=False, telegram_allowed_users=[123])
    bot = _make_bot(settings)
    assert bot._is_authorized(123) is True
    assert bot._is_authorized(999) is False


def test_is_authorized_denies_all_if_whitelist_configured_but_invalid():
    settings = Settings(
        telegram_allow_all_users=False,
        telegram_allowed_users=[],
        telegram_whitelist_configured=True,
    )
    bot = _make_bot(settings)
    assert bot._is_authorized(123) is False


def test_is_authorized_back_compat_public_when_no_whitelist():
    settings = Settings(
        telegram_allow_all_users=False,
        telegram_allowed_users=[],
        telegram_whitelist_configured=False,
    )
    bot = _make_bot(settings)
    assert bot._is_authorized(123) is True
