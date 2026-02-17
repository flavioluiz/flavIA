"""Centralized permission checking utilities for flavIA tools."""

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from flavia.agent.context import AgentContext

_CONVERTED_ACCESS_MODES = {"strict", "hybrid", "open"}
_SEARCH_CHUNKS_LOOKBACK = 24


def resolve_path(path: str, base_dir: Path) -> Path:
    """
    Resolve a path string (relative or absolute) to an absolute Path.

    Args:
        path: Path string (can be relative or absolute)
        base_dir: Base directory for resolving relative paths

    Returns:
        Resolved absolute Path
    """
    p = Path(path)
    if p.is_absolute():
        return p.resolve()
    return (base_dir / p).resolve()


def _is_in_converted_dir(path: Path, base_dir: Path) -> bool:
    """Return True when path is inside base_dir/.converted."""
    converted_dir = (base_dir / ".converted").resolve()
    try:
        path.resolve().relative_to(converted_dir)
        return True
    except ValueError:
        return False


def _resolve_converted_access_mode(context: "AgentContext") -> str:
    """Resolve converted access mode with legacy compatibility."""
    mode = getattr(context, "converted_access_mode", None)
    allow = getattr(context, "allow_converted_read", None)

    if isinstance(mode, str):
        normalized = mode.strip().lower()
        if normalized in _CONVERTED_ACCESS_MODES:
            # Backward compatibility: contexts built with only
            # allow_converted_read=True should still behave as open.
            if normalized == "hybrid" and allow is True:
                return "open"
            return normalized

    if isinstance(allow, bool):
        return "open" if allow else "strict"

    return "strict"


def _extract_tool_name(tool_call: object) -> str | None:
    """Extract function/tool name from normalized or SDK-like tool calls."""
    if isinstance(tool_call, dict):
        function = tool_call.get("function")
        if isinstance(function, dict):
            name = function.get("name")
            if isinstance(name, str) and name.strip():
                return name.strip()
        return None

    function = getattr(tool_call, "function", None)
    name = getattr(function, "name", None)
    if isinstance(name, str) and name.strip():
        return name.strip()
    return None


def _has_recent_search_chunks_call(context: "AgentContext") -> bool:
    """Check if recent assistant tool calls include search_chunks."""
    messages = getattr(context, "messages", None)
    if not isinstance(messages, list) or not messages:
        return False

    for msg in reversed(messages[-_SEARCH_CHUNKS_LOOKBACK:]):
        if not isinstance(msg, dict):
            continue
        tool_calls = msg.get("tool_calls")
        if not isinstance(tool_calls, list):
            continue
        for call in tool_calls:
            if _extract_tool_name(call) == "search_chunks":
                return True
    return False


def _search_chunks_is_available(context: "AgentContext") -> bool:
    """Return True when search_chunks is usable in the current context."""
    tools = getattr(context, "available_tools", None)
    if isinstance(tools, list) and "search_chunks" not in tools:
        return False
    return (context.base_dir / ".index" / "index.db").exists()


def _check_converted_access_policy(path: Path, context: "AgentContext") -> tuple[bool, str]:
    """Apply converted-content read policy before general path permissions."""
    if not _is_in_converted_dir(path, context.base_dir):
        return True, ""

    mode = _resolve_converted_access_mode(context)
    if mode == "open":
        return True, ""

    if mode == "hybrid":
        if not _search_chunks_is_available(context):
            # No usable retrieval path in this context: allow direct fallback.
            return True, ""
        if _has_recent_search_chunks_call(context):
            return True, ""
        return (
            False,
            "Access denied - direct '.converted/' access in hybrid mode requires a prior "
            "'search_chunks' call. Run search_chunks first, then retry. "
            "For unrestricted direct access, set converted_access_mode: open.",
        )

    return (
        False,
        "Access denied - direct '.converted/' access is disabled "
        "(converted_access_mode: strict). Use 'search_chunks' for content retrieval, "
        "or set converted_access_mode: hybrid/open.",
    )


def check_read_permission(path: Path, context: "AgentContext") -> tuple[bool, str]:
    """
    Check if the agent has permission to read the given path.

    Args:
        path: Path to check (should be resolved/absolute)
        context: Agent context with permissions

    Returns:
        Tuple of (allowed: bool, error_message: str)
        If allowed is True, error_message is empty.
    """
    converted_allowed, converted_error = _check_converted_access_policy(path, context)
    if not converted_allowed:
        return False, converted_error

    # If no explicit permissions are configured, fall back to base_dir check
    # (backward compatibility)
    if (
        not context.permissions.explicit
        and not context.permissions.read_paths
        and not context.permissions.write_paths
    ):
        resolved = path.resolve()
        base_resolved = context.base_dir.resolve()
        try:
            resolved.relative_to(base_resolved)
            return True, ""
        except ValueError:
            return False, f"Access denied - path is outside allowed directory"

    if context.permissions.can_read(path):
        return True, ""

    # Build helpful error message
    allowed_paths = context.permissions.read_paths + context.permissions.write_paths
    if allowed_paths:
        paths_str = ", ".join(str(p) for p in allowed_paths[:3])
        if len(allowed_paths) > 3:
            paths_str += f" and {len(allowed_paths) - 3} more"
        return False, f"Access denied - path is outside allowed directories: {paths_str}"
    return False, "Access denied - no read permissions configured"


def check_write_permission(path: Path, context: "AgentContext") -> tuple[bool, str]:
    """
    Check if the agent has permission to write to the given path.

    Args:
        path: Path to check (should be resolved/absolute)
        context: Agent context with permissions

    Returns:
        Tuple of (allowed: bool, error_message: str)
        If allowed is True, error_message is empty.
    """
    # If no explicit permissions are configured, fall back to base_dir check
    # (backward compatibility)
    if (
        not context.permissions.explicit
        and not context.permissions.read_paths
        and not context.permissions.write_paths
    ):
        resolved = path.resolve()
        base_resolved = context.base_dir.resolve()
        try:
            resolved.relative_to(base_resolved)
            return True, ""
        except ValueError:
            return False, f"Write access denied - path is outside allowed directory"

    if context.permissions.can_write(path):
        return True, ""

    # Build helpful error message
    if context.permissions.write_paths:
        paths_str = ", ".join(str(p) for p in context.permissions.write_paths[:3])
        if len(context.permissions.write_paths) > 3:
            paths_str += f" and {len(context.permissions.write_paths) - 3} more"
        return False, f"Write access denied - allowed write directories: {paths_str}"
    return False, "Write access denied - no write permissions configured"


def can_read_path(path: Path, context: "AgentContext") -> bool:
    """
    Check if the agent can read the given path (simple boolean check).

    Args:
        path: Path to check (should be resolved/absolute)
        context: Agent context with permissions

    Returns:
        True if the path can be read, False otherwise.
    """
    allowed, _ = check_read_permission(path, context)
    return allowed


def can_write_path(path: Path, context: "AgentContext") -> bool:
    """
    Check if the agent can write to the given path (simple boolean check).

    Args:
        path: Path to check (should be resolved/absolute)
        context: Agent context with permissions

    Returns:
        True if the path can be written, False otherwise.
    """
    allowed, _ = check_write_permission(path, context)
    return allowed
