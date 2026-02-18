"""Theme system for flavIA display.

This module defines color palettes and themes for the console display.
"""

from dataclasses import dataclass
from typing import Optional

ThemeName = str


@dataclass
class ColorPalette:
    """Color palette for a UI theme."""

    # Semantic colors
    primary: str = "cyan"
    success: str = "green"
    error: str = "red"
    warning: str = "yellow"
    info: str = "blue"
    muted: str = "dim"

    # UI-specific colors
    model_ref: str = "cyan"
    file_path: str = "cyan"
    tool_name: str = "green"
    agent_label: str = "bold blue"
    token_low: str = "green"
    token_mid: str = "yellow"
    token_high: str = "red"


@dataclass
class Theme:
    """A complete theme with palette and behavior settings."""

    name: ThemeName
    palette: ColorPalette
    use_ansi_status: bool = True


THEMES: dict[str, Theme] = {
    "default": Theme(
        name="default",
        palette=ColorPalette(),
    ),
    "light": Theme(
        name="light",
        palette=ColorPalette(
            primary="blue",
            success="green",
            error="red",
            warning="bright_yellow",
            info="blue",
            muted="grey50",
        ),
    ),
    "minimal": Theme(
        name="minimal",
        palette=ColorPalette(
            primary="white",
            success="white",
            error="white",
            warning="white",
            info="white",
            muted="dim",
        ),
        use_ansi_status=False,
    ),
}


_current_theme_name: Optional[str] = None
_current_theme: Optional[Theme] = None


def set_theme(name: str) -> None:
    """Set the current theme by name."""
    global _current_theme_name, _current_theme
    _current_theme_name = name
    _current_theme = THEMES.get(name, THEMES["default"])
    if not _current_theme:
        _current_theme = THEMES["default"]
        _current_theme_name = "default"


def get_current_theme() -> Theme:
    """Get the current theme, loading from settings if needed."""
    global _current_theme_name, _current_theme

    if _current_theme is not None:
        return _current_theme

    if _current_theme_name is not None:
        set_theme(_current_theme_name)
        return _current_theme

    # Load from settings
    try:
        from flavia.config import get_settings

        settings = get_settings()
        theme_name = getattr(settings, "color_theme", "default")
        set_theme(theme_name)
    except Exception:
        set_theme("default")

    return _current_theme if _current_theme is not None else THEMES["default"]


def reset_theme() -> None:
    """Reset the current theme (call after changing settings)."""
    global _current_theme_name, _current_theme
    _current_theme_name = None
    _current_theme = None
    set_theme("default")
