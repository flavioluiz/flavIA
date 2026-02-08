"""Interfaces package for flavIA."""

from .cli_interface import run_cli
from .telegram_interface import run_telegram_bot

__all__ = ["run_cli", "run_telegram_bot"]
