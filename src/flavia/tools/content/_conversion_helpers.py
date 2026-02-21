"""Shared helpers for content conversion tools.

Provides common patterns for:
- Loading catalog with permission checks
- Resolving file paths and finding catalog entries
- Running converters and updating catalog entries
"""

from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional, Tuple

if TYPE_CHECKING:
    from flavia.agent.context import AgentContext
    from flavia.content.catalog import ContentCatalog, FileEntry
    from flavia.content.converters.base import BaseConverter


def load_catalog_with_permissions(
    agent_context: "AgentContext",
    need_converted_dir: bool = True,
) -> "Tuple[Any, Optional[Path], Optional[Path], Optional[Path], Optional[str]]":
    """Load catalog and verify read/write permissions.

    Args:
        agent_context: Current agent context.
        need_converted_dir: Whether to also check write permission on .converted/.

    Returns:
        Tuple of (catalog, config_dir, converted_dir, base_dir, error_msg).
        If error_msg is not None, the other values may be None.
    """
    from flavia.content.catalog import ContentCatalog
    from ..permissions import check_read_permission, check_write_permission

    base_dir: Path = agent_context.base_dir
    config_dir = base_dir / ".flavia"
    converted_dir = base_dir / ".converted"

    can_read, err = check_read_permission(base_dir, agent_context)
    if not can_read:
        return None, None, None, None, f"Error: {err}"

    can_write_cfg, err = check_write_permission(config_dir, agent_context)
    if not can_write_cfg:
        return None, None, None, None, f"Error: {err}"

    if need_converted_dir:
        can_write_conv, err = check_write_permission(converted_dir, agent_context)
        if not can_write_conv:
            return None, None, None, None, f"Error: {err}"

    catalog = ContentCatalog.load(config_dir)
    if catalog is None:
        return None, None, None, None, (
            "Error: No content catalog found. "
            "Run 'flavia --init' or 'flavia --update' to build the catalog."
        )

    return catalog, config_dir, converted_dir, base_dir, None


def resolve_and_find_entry(
    path_str: str,
    agent_context: "AgentContext",
    catalog: "ContentCatalog",
) -> "Tuple[Optional[Path], Any, Optional[str]]":
    """Resolve a path string and find the matching catalog entry.

    Args:
        path_str: File path (relative to base_dir or absolute).
        agent_context: Current agent context.
        catalog: Loaded content catalog.

    Returns:
        Tuple of (full_path, entry_or_None, error_msg).
        If error_msg is set, full_path may be None.
    """
    from ..permissions import resolve_path, check_read_permission

    full_path = resolve_path(path_str, agent_context.base_dir)

    allowed, err = check_read_permission(full_path, agent_context)
    if not allowed:
        return None, None, f"Error: {err}"

    if not full_path.exists():
        return None, None, f"Error: File not found: {path_str}"
    if not full_path.is_file():
        return None, None, f"Error: '{path_str}' is not a file"

    # Find matching catalog entry by relative path
    try:
        rel = str(full_path.resolve().relative_to(agent_context.base_dir.resolve()))
    except ValueError:
        rel = None

    entry = catalog.files.get(rel) if rel else None
    return full_path, entry, None


def convert_and_update_catalog(
    converter: "BaseConverter",
    source_path: Path,
    converted_dir: Path,
    entry: "Optional[Any]",
    base_dir: Path,
    catalog: "ContentCatalog",
    config_dir: Path,
) -> "Tuple[Optional[str], Optional[str]]":
    """Run converter.convert(), update catalog entry, and save.

    Args:
        converter: Converter instance to use.
        source_path: Source file path.
        converted_dir: Output directory for converted files.
        entry: Catalog entry to update (can be None).
        base_dir: Project base directory.
        catalog: Loaded content catalog.
        config_dir: Config directory for saving catalog.

    Returns:
        Tuple of (rel_converted_path, error_msg).
        On success, error_msg is None. On failure, rel_converted_path is None.
    """
    try:
        result_path = converter.convert(source_path, converted_dir)
    except Exception as e:
        return None, f"Error: Conversion failed: {e}"

    if not result_path or not result_path.exists():
        return None, None  # Converter returned None — caller decides message

    try:
        rel_converted = str(result_path.relative_to(base_dir))
    except ValueError:
        rel_converted = str(result_path)

    if entry is not None:
        entry.converted_to = rel_converted
        catalog.save(config_dir)

    return rel_converted, None
