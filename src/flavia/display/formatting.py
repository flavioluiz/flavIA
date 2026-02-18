"""Formatting helpers for display.

This module provides formatting utilities such as timestamp formatting.
"""

from datetime import datetime, timezone
from typing import Literal

TimestampStyle = Literal["iso", "relative", "local"]


def format_timestamp(dt: datetime, style: TimestampStyle | None = None) -> str:
    """Format a datetime timestamp according to the specified style.

    Args:
        dt: The datetime to format.
        style: The style to use. If None, uses current settings.

    Returns:
        The formatted timestamp string.
    """
    if style is None:
        try:
            from flavia.config import get_settings

            settings = get_settings()
            style = getattr(settings, "timestamp_format", "iso")
        except Exception:
            style = "iso"

    if style == "relative":
        return _relative_time(dt)
    elif style == "local":
        return dt.astimezone().strftime("%Y-%m-%d %H:%M:%S")
    else:  # iso
        return dt.isoformat()


def _relative_time(dt: datetime) -> str:
    """Format datetime as relative time (e.g., "2 min ago", "1h ago")."""
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    delta = now - dt
    seconds = abs(delta.total_seconds())

    if seconds < 60:
        return f"{int(seconds)}s ago"
    elif seconds < 3600:
        minutes = int(seconds / 60)
        return f"{minutes}m ago"
    elif seconds < 86400:
        hours = int(seconds / 3600)
        return f"{hours}h ago"
    elif seconds < 604800:
        days = int(seconds / 86400)
        return f"{days}d ago"
    else:
        weeks = int(seconds / 604800)
        return f"{weeks}w ago"
