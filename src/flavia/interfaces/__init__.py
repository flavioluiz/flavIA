"""Interfaces package for flavIA."""

from .cli_interface import run_cli


def run_telegram_bot(settings):
    """Lazy import to avoid Telegram/logging side effects in CLI mode."""
    from .telegram_interface import run_telegram_bot as _run_telegram_bot
    return _run_telegram_bot(settings)

__all__ = ["run_cli", "run_telegram_bot"]
