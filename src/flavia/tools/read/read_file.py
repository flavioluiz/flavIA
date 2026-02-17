"""Read file tool for flavIA with context-window size protection."""

from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..base import BaseTool, ToolSchema, ToolParameter
from ..permissions import check_read_permission, resolve_path
from ..registry import register_tool

if TYPE_CHECKING:
    from flavia.agent.context import AgentContext

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CHARS_PER_TOKEN = 4  # conservative estimate (1 token ~ 4 chars)
MAX_CONTEXT_FRACTION = 0.25  # never use more than 25% of context window
REMAINING_FRACTION = 0.50  # never use more than 50% of *remaining* context
PREVIEW_LINES = 50  # lines to show in the preview when blocking


def _estimate_tokens(num_chars: int) -> int:
    """Estimate token count from character count."""
    return max(1, num_chars // CHARS_PER_TOKEN)


def _compute_max_result_tokens(agent_context: "AgentContext") -> int:
    """Compute the dynamic budget for a single tool result.

    Budget = min(25% of total context, 50% of remaining context).
    This implements Camada 4: as context fills up the budget shrinks.
    """
    max_ctx = getattr(agent_context, "max_context_tokens", 128_000)
    current = getattr(agent_context, "current_context_tokens", 0)
    remaining = max(0, max_ctx - current)

    absolute_cap = int(max_ctx * MAX_CONTEXT_FRACTION)
    dynamic_cap = int(remaining * REMAINING_FRACTION)
    return max(1, min(absolute_cap, dynamic_cap))


def _count_lines(full_path: Path) -> int:
    """Count lines in a file efficiently without reading the whole file into memory."""
    count = 0
    with open(full_path, "r", encoding="utf-8") as f:
        for _ in f:
            count += 1
    return count


def _read_line_range(full_path: Path, start: int, end: int) -> tuple[str, int, int]:
    """Read a specific line range from a file.

    Args:
        full_path: Path to the file.
        start: 1-based start line (inclusive).
        end: 1-based end line (inclusive).

    Returns:
        Tuple of (content, actual_start, actual_end) where actual values
        reflect clamping to file boundaries.
    """
    lines_out: list[str] = []
    actual_start = start
    actual_end = start  # will be updated
    with open(full_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            if line_num < start:
                continue
            if line_num > end:
                break
            lines_out.append(line)
            actual_end = line_num
    return "".join(lines_out), actual_start, actual_end


def _build_blocked_message(
    path: str,
    full_path: Path,
    file_size: int,
    estimated_tokens: int,
    max_result_tokens: int,
    agent_context: "AgentContext",
) -> str:
    """Build the informative message returned when a file is too large."""
    max_ctx = getattr(agent_context, "max_context_tokens", 128_000)
    current = getattr(agent_context, "current_context_tokens", 0)
    pct_of_context = (estimated_tokens / max_ctx * 100) if max_ctx > 0 else 0
    context_usage_pct = (current / max_ctx * 100) if max_ctx > 0 else 0

    # Count lines
    try:
        total_lines = _count_lines(full_path)
    except Exception:
        total_lines = "unknown"

    # Read preview
    try:
        preview, _, preview_end = _read_line_range(full_path, 1, PREVIEW_LINES)
    except Exception:
        preview = "(could not read preview)"
        preview_end = 0

    # Format file size
    if file_size >= 1_048_576:
        size_str = f"{file_size / 1_048_576:.1f} MB"
    elif file_size >= 1024:
        size_str = f"{file_size / 1024:.1f} KB"
    else:
        size_str = f"{file_size} bytes"

    # Suggest chunk size (in lines) that would fit the budget
    if total_lines != "unknown" and total_lines > 0:
        chars_per_line = file_size / total_lines
        tokens_per_line = chars_per_line / CHARS_PER_TOKEN
        safe_lines = int(max_result_tokens / tokens_per_line) if tokens_per_line > 0 else 500
        safe_lines = max(50, min(safe_lines, total_lines))
    else:
        safe_lines = 500

    return (
        f"⚠ FILE TOO LARGE FOR FULL READ\n"
        f"\n"
        f"File: {path}\n"
        f"Size: {size_str} (~{estimated_tokens:,} tokens)\n"
        f"Total lines: {total_lines}\n"
        f"Would occupy: {pct_of_context:.1f}% of context window\n"
        f"Current context usage: {context_usage_pct:.1f}%\n"
        f"Budget for this read: ~{max_result_tokens:,} tokens\n"
        f"\n"
        f"--- Preview (lines 1-{preview_end}) ---\n"
        f"{preview}"
        f"--- End of preview ---\n"
        f"\n"
        f"To read this file, use partial reads:\n"
        f'  - read_file(path="{path}", start_line=1, end_line={safe_lines})\n'
        f'  - read_file(path="{path}", start_line={safe_lines + 1}, end_line={safe_lines * 2})\n'
        f"  - ...and so on in chunks of ~{safe_lines} lines\n"
        f"\n"
        f"Or delegate to a sub-agent that can process the file in its own context window."
    )


class ReadFileTool(BaseTool):
    """Tool for reading file contents with context-window protection.

    For large files that would exceed the context-window budget, returns
    a preview with metadata and instructions for partial reads instead
    of the full content.  Supports ``start_line`` / ``end_line``
    parameters for reading specific sections.
    """

    name = "read_file"
    description = (
        "Read file contents. For large files returns a preview with metadata. "
        "Use start_line/end_line for partial reads."
    )
    category = "read"

    def get_schema(self, **context) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParameter(
                    name="path",
                    type="string",
                    description=(
                        "Path to the file to read (relative to base directory or absolute)"
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="start_line",
                    type="integer",
                    description=(
                        "First line to read (1-based, inclusive). "
                        "Use together with end_line for partial reads of large files."
                    ),
                    required=False,
                ),
                ToolParameter(
                    name="end_line",
                    type="integer",
                    description=(
                        "Last line to read (1-based, inclusive). "
                        "Use together with start_line for partial reads of large files."
                    ),
                    required=False,
                ),
            ],
        )

    def execute(self, args: dict[str, Any], agent_context: "AgentContext") -> str:
        path = args.get("path", "")
        try:
            start_line = self._parse_line_arg(args.get("start_line"), "start_line")
            end_line = self._parse_line_arg(args.get("end_line"), "end_line")
        except ValueError as e:
            return f"Error: {e}"

        if not path:
            return "Error: path is required"

        full_path = resolve_path(path, agent_context.base_dir)

        # Permission check
        allowed, error_msg = check_read_permission(full_path, agent_context)
        if not allowed:
            return f"Error: {error_msg}"

        if not full_path.exists():
            return f"Error: File not found: {path}"

        if not full_path.is_file():
            return f"Error: '{path}' is not a file"

        try:
            file_size = full_path.stat().st_size
        except OSError as e:
            return f"Error: Cannot stat '{path}': {e}"

        max_result_tokens = _compute_max_result_tokens(agent_context)

        # --- Partial read (start_line / end_line) ---
        if start_line is not None or end_line is not None:
            return self._read_partial(path, full_path, start_line, end_line, max_result_tokens)

        # --- Full read with size guard ---
        estimated_tokens = _estimate_tokens(file_size)

        if estimated_tokens > max_result_tokens:
            return _build_blocked_message(
                path,
                full_path,
                file_size,
                estimated_tokens,
                max_result_tokens,
                agent_context,
            )

        # File fits within budget — read normally
        try:
            content = full_path.read_text(encoding="utf-8")
            return content
        except UnicodeDecodeError:
            return f"Error: Cannot read '{path}' - file is not valid UTF-8 text"
        except PermissionError:
            return f"Error: Permission denied reading '{path}'"
        except Exception as e:
            return f"Error reading file: {e}"

    @staticmethod
    def _parse_line_arg(value: Any, param_name: str) -> int | None:
        """Parse optional line-number args and reject invalid types."""
        if value is None:
            return None
        if isinstance(value, bool):
            raise ValueError(f"{param_name} must be an integer")
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            stripped = value.strip()
            if stripped and (stripped.isdigit() or (stripped.startswith("-") and stripped[1:].isdigit())):
                return int(stripped)
        raise ValueError(f"{param_name} must be an integer")

    def _read_partial(
        self,
        path: str,
        full_path: Path,
        start_line: int | None,
        end_line: int | None,
        max_result_tokens: int,
    ) -> str:
        """Read a specific line range, with size guard on the result."""
        try:
            total_lines = _count_lines(full_path)
        except UnicodeDecodeError:
            return f"Error: Cannot read '{path}' - file is not valid UTF-8 text"
        except Exception as e:
            return f"Error counting lines in '{path}': {e}"

        start = max(1, start_line if start_line is not None else 1)
        end = min(total_lines, end_line if end_line is not None else total_lines)

        if start > total_lines:
            return f"Error: start_line ({start}) exceeds total lines ({total_lines}) in '{path}'"
        if start > end:
            return f"Error: start_line ({start}) is greater than end_line ({end})"

        try:
            content, actual_start, actual_end = _read_line_range(full_path, start, end)
        except UnicodeDecodeError:
            return f"Error: Cannot read '{path}' - file is not valid UTF-8 text"
        except Exception as e:
            return f"Error reading '{path}': {e}"

        # Check if partial result itself exceeds budget
        result_tokens = _estimate_tokens(len(content))
        if result_tokens > max_result_tokens:
            # Truncate to fit budget
            max_chars = max_result_tokens * CHARS_PER_TOKEN
            content = content[:max_chars]
            return (
                f"[Partial read of '{path}' lines {actual_start}-{actual_end} "
                f"(total: {total_lines} lines) — TRUNCATED to ~{max_result_tokens:,} tokens "
                f"to fit context budget. Request a smaller range.]\n\n"
                f"{content}"
            )

        header = f"['{path}' lines {actual_start}-{actual_end} of {total_lines} total]\n\n"
        return header + content


register_tool(ReadFileTool())
