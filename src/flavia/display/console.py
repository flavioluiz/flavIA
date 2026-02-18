"""Console factory with theme support.

This module provides a singleton Console instance with the current theme applied.
"""

from typing import Optional

from rich.console import Console
from rich.theme import Theme as RichTheme

from flavia.display.theme import get_current_theme

_console_instance: Optional[Console] = None


def get_console() -> Console:
    """Get the singleton Console instance with current theme applied."""
    global _console_instance
    if _console_instance is None:
        _console_instance = _create_themed_console()
    return _console_instance


def _create_themed_console() -> Console:
    """Create a Console with Rich Theme based on current theme."""
    theme = get_current_theme()
    palette = theme.palette

    # Map palette to Rich Theme
    rich_theme = RichTheme(
        {
            "primary": palette.primary,
            "success": palette.success,
            "error": palette.error,
            "warning": palette.warning,
            "info": palette.info,
            "muted": palette.muted,
            "model": palette.model_ref,
            "path": palette.file_path,
            "tool": palette.tool_name,
            "agent": palette.agent_label,
        }
    )

    return Console(theme=rich_theme)


def reset_console() -> None:
    """Reset the console instance (call after theme change)."""
    global _console_instance
    _console_instance = None
