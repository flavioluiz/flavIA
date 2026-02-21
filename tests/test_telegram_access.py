"""Tests for Telegram authorization behavior."""

from flavia.config.settings import Settings
from flavia.config.bots import BotAccessConfig, BotConfig
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


def test_is_authorized_bot_config_explicit_empty_whitelist_denies_all():
    settings = Settings(
        telegram_allow_all_users=True,  # should be ignored by explicit bot access config
        telegram_allowed_users=[],
        telegram_whitelist_configured=False,
    )
    bot = _make_bot(settings)
    bot.bot_config = BotConfig(
        id="test",
        platform="telegram",
        token="tok",
        access=BotAccessConfig(
            allowed_users=[],
            allow_all=False,
            allowed_users_configured=True,
        ),
    )
    assert bot._is_authorized(123) is False


def test_is_authorized_bot_config_without_whitelist_falls_back_to_legacy():
    settings = Settings(
        telegram_allow_all_users=False,
        telegram_allowed_users=[42],
        telegram_whitelist_configured=True,
    )
    bot = _make_bot(settings)
    bot.bot_config = BotConfig(
        id="test",
        platform="telegram",
        token="tok",
        access=BotAccessConfig(
            allowed_users=[],
            allow_all=False,
            allowed_users_configured=False,
        ),
    )
    assert bot._is_authorized(42) is True
    assert bot._is_authorized(99) is False
