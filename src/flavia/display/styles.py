"""Semantic style helpers based on current theme.

This module provides convenient style helpers that use the current theme's colors.
"""

from flavia.display.theme import get_current_theme


class Styles:
    """Access styles based on the current theme."""

    @staticmethod
    def primary(text: str) -> str:
        theme = get_current_theme()
        return f"[{theme.palette.primary}]{text}[/{theme.palette.primary}]"

    @staticmethod
    def success(text: str) -> str:
        theme = get_current_theme()
        return f"[{theme.palette.success}]{text}[/{theme.palette.success}]"

    @staticmethod
    def error(text: str) -> str:
        theme = get_current_theme()
        return f"[{theme.palette.error}]{text}[/{theme.palette.error}]"

    @staticmethod
    def warning(text: str) -> str:
        theme = get_current_theme()
        return f"[{theme.palette.warning}]{text}[/{theme.palette.warning}]"

    @staticmethod
    def info(text: str) -> str:
        theme = get_current_theme()
        return f"[{theme.palette.info}]{text}[/{theme.palette.info}]"

    @staticmethod
    def muted(text: str) -> str:
        theme = get_current_theme()
        return f"[{theme.palette.muted}]{text}[/{theme.palette.muted}]"

    @staticmethod
    def model(text: str) -> str:
        theme = get_current_theme()
        return f"[{theme.palette.model_ref}]{text}[/{theme.palette.model_ref}]"

    @staticmethod
    def path(text: str) -> str:
        theme = get_current_theme()
        return f"[{theme.palette.file_path}]{text}[/{theme.palette.file_path}]"

    @staticmethod
    def tool(text: str) -> str:
        theme = get_current_theme()
        return f"[{theme.palette.tool_name}]{text}[/{theme.palette.tool_name}]"

    @staticmethod
    def agent(text: str) -> str:
        theme = get_current_theme()
        return f"[{theme.palette.agent_label}]{text}[/{theme.palette.agent_label}]"


# Global shortcut instance
S = Styles()
