"""Centralized permission checking utilities for flavIA tools."""

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from flavia.agent.context import AgentContext


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
    # If no explicit permissions are configured, fall back to base_dir check
    # (backward compatibility)
    if not context.permissions.read_paths and not context.permissions.write_paths:
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
    if not context.permissions.read_paths and not context.permissions.write_paths:
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
