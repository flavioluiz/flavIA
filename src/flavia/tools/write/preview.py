"""Operation preview system for flavIA write tools.

Provides preview generation for write operations, allowing users to see
exactly what will change before confirming an operation.
"""

import difflib
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class OperationPreview:
    """Preview information for a write operation.

    Provides detailed information about what a write operation will do,
    allowing users to make informed decisions before confirming.
    """

    operation: str
    """Type of operation: write, edit, insert, append, delete, mkdir, rmdir."""

    path: str
    """Target path for the operation."""

    diff: Optional[str] = None
    """Unified diff for edit operations."""

    content_preview: Optional[str] = None
    """Content preview for write/append operations (may be truncated)."""

    content_lines: int = 0
    """Number of lines in the content being written."""

    content_bytes: int = 0
    """Size in bytes of the content being written."""

    context_before: Optional[str] = None
    """Lines before the insertion point (for insert operations)."""

    context_after: Optional[str] = None
    """Lines after the insertion point (for insert operations)."""

    file_preview: Optional[str] = None
    """Preview of file content being deleted (first lines)."""

    file_size: int = 0
    """Size of the file being deleted or modified."""

    dir_contents: list[str] = field(default_factory=list)
    """List of items in a directory (for directory operations)."""


def generate_diff(
    old_text: str,
    new_text: str,
    filename: str = "file",
    context_lines: int = 3,
) -> str:
    """Generate a unified diff between two texts.

    Args:
        old_text: Original file content.
        new_text: New file content after modification.
        filename: Name to use in diff header.
        context_lines: Number of context lines around changes.

    Returns:
        Unified diff string, or empty string if no differences.
    """
    old_lines = old_text.splitlines(keepends=True)
    new_lines = new_text.splitlines(keepends=True)

    # Ensure consistent line endings for diff
    if old_lines and not old_lines[-1].endswith("\n"):
        old_lines[-1] += "\n"
    if new_lines and not new_lines[-1].endswith("\n"):
        new_lines[-1] += "\n"

    diff_lines = list(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{filename}",
            tofile=f"b/{filename}",
            n=context_lines,
        )
    )

    return "".join(diff_lines)


def format_content_preview(
    content: str,
    max_lines: int = 20,
    max_line_length: int = 120,
) -> str:
    """Format content for preview, truncating if necessary.

    Args:
        content: Content to preview.
        max_lines: Maximum number of lines to show.
        max_line_length: Maximum length per line before truncation.

    Returns:
        Formatted preview string with truncation indicators if needed.
    """
    if not content:
        return "(empty)"

    lines = content.splitlines()
    total_lines = len(lines)
    truncated = False

    if total_lines > max_lines:
        lines = lines[:max_lines]
        truncated = True

    # Truncate long lines
    formatted_lines = []
    for line in lines:
        if len(line) > max_line_length:
            formatted_lines.append(line[: max_line_length - 3] + "...")
        else:
            formatted_lines.append(line)

    result = "\n".join(formatted_lines)

    if truncated:
        result += f"\n... ({total_lines - max_lines} more lines)"

    return result


def format_dir_contents(
    path: Path,
    max_items: int = 20,
) -> list[str]:
    """List directory contents for preview.

    Args:
        path: Directory path to list.
        max_items: Maximum number of items to return.

    Returns:
        List of directory entries with type indicators.
    """
    if not path.exists() or not path.is_dir():
        return []

    items = []
    try:
        entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        for entry in entries[:max_items]:
            if entry.is_dir():
                items.append(f"{entry.name}/")
            else:
                items.append(entry.name)

        total = len(list(path.iterdir()))
        if total > max_items:
            items.append(f"... ({total - max_items} more items)")

    except PermissionError:
        items.append("(permission denied)")
    except OSError as e:
        items.append(f"(error: {e})")

    return items


def format_insertion_context(
    lines: list[str],
    insert_line: int,
    context_lines: int = 3,
) -> tuple[Optional[str], Optional[str]]:
    """Get context around an insertion point.

    Args:
        lines: All lines in the file.
        insert_line: 1-based line number where text will be inserted.
        context_lines: Number of context lines to show.

    Returns:
        Tuple of (context_before, context_after) strings.
    """
    insert_index = insert_line - 1  # Convert to 0-based
    total_lines = len(lines)

    # Context before
    start_before = max(0, insert_index - context_lines)
    before_lines = lines[start_before:insert_index]
    context_before = None
    if before_lines:
        # Format with line numbers
        formatted = []
        for i, line in enumerate(before_lines, start=start_before + 1):
            line_content = line.rstrip("\n\r")
            formatted.append(f"{i:4d} | {line_content}")
        context_before = "\n".join(formatted)

    # Context after
    end_after = min(total_lines, insert_index + context_lines)
    after_lines = lines[insert_index:end_after]
    context_after = None
    if after_lines:
        # Format with line numbers (these will shift down after insert)
        formatted = []
        for i, line in enumerate(after_lines, start=insert_index + 1):
            line_content = line.rstrip("\n\r")
            formatted.append(f"{i:4d} | {line_content}")
        context_after = "\n".join(formatted)

    return context_before, context_after


def format_file_preview(path: Path, max_lines: int = 10) -> Optional[str]:
    """Get preview of file content (first lines).

    Args:
        path: Path to the file.
        max_lines: Maximum number of lines to preview.

    Returns:
        Preview string or None if file cannot be read.
    """
    if not path.exists() or not path.is_file():
        return None

    try:
        content = path.read_text(encoding="utf-8")
        return format_content_preview(content, max_lines=max_lines)
    except (UnicodeDecodeError, PermissionError, OSError):
        return None
