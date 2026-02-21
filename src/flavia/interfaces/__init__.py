"""Interfaces package for flavIA."""

from .cli_interface import run_cli
from .bot_runner import run_telegram_bots


# Keep backward compatible
def run_telegram_bot(settings):
    """Legacy: run single bot (first configured). Use run_telegram_bots for multi-bot."""
    return run_telegram_bots(settings, bot_name=None)


__all__ = ["run_cli", "run_telegram_bot", "run_telegram_bots"]
