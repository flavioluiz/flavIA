"""Interfaces package for flavIA."""

from .base_bot import BaseMessagingBot, BotCommand, BotResponse, SendFileAction
from .cli_interface import run_cli
from .bot_runner import run_telegram_bots


# Keep backward compatible
def run_telegram_bot(settings):
    """Legacy single-bot entrypoint for compatibility with older imports."""
    from .telegram_interface import run_telegram_bot as _run_telegram_bot

    return _run_telegram_bot(settings)


__all__ = [
    "run_cli",
    "run_telegram_bot",
    "run_telegram_bots",
    "BaseMessagingBot",
    "BotCommand",
    "BotResponse",
    "SendFileAction",
]
