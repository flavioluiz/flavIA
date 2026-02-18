"""Display module for flavIA.

This module provides themed console output and styling.
"""

from flavia.display.console import get_console, reset_console
from flavia.display.styles import S, Styles
from flavia.display.theme import (
    THEMES,
    ColorPalette,
    Theme,
    get_current_theme,
    reset_theme,
    set_theme,
)

__all__ = [
    "get_console",
    "reset_console",
    "S",
    "Styles",
    "ColorPalette",
    "Theme",
    "THEMES",
    "get_current_theme",
    "reset_theme",
    "set_theme",
]
