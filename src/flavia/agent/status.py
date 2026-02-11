"""Tool status types and formatting for flavIA."""

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Optional


class StatusPhase(Enum):
    """Phase of agent execution."""

    WAITING_LLM = "waiting_llm"
    EXECUTING_TOOL = "executing_tool"
    SPAWNING_AGENT = "spawning_agent"


@dataclass
class ToolStatus:
    """Status update for tool execution."""

    phase: StatusPhase
    tool_name: Optional[str] = None
    tool_display: Optional[str] = None
    args: Optional[dict[str, Any]] = None
    agent_id: str = "main"
    depth: int = 0

    @classmethod
    def waiting_llm(cls, agent_id: str = "main", depth: int = 0) -> "ToolStatus":
        """Create a waiting for LLM status."""
        return cls(
            phase=StatusPhase.WAITING_LLM,
            agent_id=agent_id,
            depth=depth,
        )

    @classmethod
    def executing_tool(
        cls,
        tool_name: str,
        args: Any,
        agent_id: str = "main",
        depth: int = 0,
    ) -> "ToolStatus":
        """Create an executing tool status."""
        normalized_args = _normalize_args(args)
        safe_tool_name = sanitize_terminal_text(tool_name) or "tool"
        return cls(
            phase=StatusPhase.EXECUTING_TOOL,
            tool_name=safe_tool_name,
            tool_display=format_tool_display(safe_tool_name, normalized_args),
            args=normalized_args,
            agent_id=agent_id,
            depth=depth,
        )

    @classmethod
    def spawning_agent(
        cls,
        agent_name: str,
        agent_id: str = "main",
        depth: int = 0,
    ) -> "ToolStatus":
        """Create a spawning agent status."""
        return cls(
            phase=StatusPhase.SPAWNING_AGENT,
            tool_name="spawn_agent",
            tool_display=f"Spawning {sanitize_terminal_text(agent_name)}",
            agent_id=agent_id,
            depth=depth,
        )


StatusCallback = Callable[[ToolStatus], None]


_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def sanitize_terminal_text(value: Any) -> str:
    """Convert text to a single safe line for terminal rendering."""
    if value is None:
        return ""

    text = value if isinstance(value, str) else str(value)
    text = text.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    return _CONTROL_CHARS_RE.sub("", text)


def _normalize_args(args: Any) -> dict[str, Any]:
    """Normalize tool arguments to a dictionary."""
    return args if isinstance(args, dict) else {}


def _truncate_path(path: Any, max_len: int = 40) -> str:
    """Truncate a path to show the most relevant part."""
    path_text = sanitize_terminal_text(path)
    if len(path_text) <= max_len:
        return path_text
    # Show filename with some parent context
    parts = path_text.replace("\\", "/").split("/")
    if len(parts) <= 2:
        return f"...{path_text[-(max_len - 3) :]}"
    # Try to show parent/filename
    filename = parts[-1]
    parent = parts[-2]
    result = f"{parent}/{filename}"
    if len(result) <= max_len:
        return result
    # Just show truncated filename
    return f"...{filename[-(max_len - 3) :]}" if len(filename) > max_len - 3 else filename


def _truncate_text(text: Any, max_len: int = 30) -> str:
    """Truncate text with ellipsis."""
    safe_text = sanitize_terminal_text(text)
    if len(safe_text) <= max_len:
        return safe_text
    return safe_text[: max_len - 3] + "..."


def format_tool_display(tool_name: str, args: Any) -> str:
    """Format tool call for user-friendly display.

    Args:
        tool_name: Name of the tool being executed.
        args: Arguments passed to the tool.

    Returns:
        Human-readable description of the tool call.
    """
    formatters = {
        "read_file": _format_read_file,
        "list_files": _format_list_files,
        "search_files": _format_search_files,
        "get_file_info": _format_get_file_info,
        "query_catalog": _format_query_catalog,
        "write_file": _format_write_file,
        "edit_file": _format_edit_file,
        "insert_text": _format_insert_text,
        "append_file": _format_append_file,
        "delete_file": _format_delete_file,
        "create_directory": _format_create_directory,
        "remove_directory": _format_remove_directory,
        "execute_command": _format_execute_command,
        "spawn_agent": _format_spawn_agent,
        "spawn_predefined_agent": _format_spawn_predefined,
    }

    safe_tool_name = sanitize_terminal_text(tool_name) or "tool"
    safe_args = _normalize_args(args)

    formatter = formatters.get(safe_tool_name)
    if formatter:
        try:
            return formatter(safe_args)
        except Exception:
            return safe_tool_name

    # Default: show tool name with first argument
    return _format_default(safe_tool_name, safe_args)


def _format_read_file(args: dict[str, Any]) -> str:
    path = args.get("path", args.get("file_path", ""))
    return f"Reading {_truncate_path(path)}"


def _format_list_files(args: dict[str, Any]) -> str:
    path = args.get("path", args.get("directory", "."))
    return f"Listing {_truncate_path(path)}"


def _format_search_files(args: dict[str, Any]) -> str:
    pattern = args.get("pattern", args.get("query", ""))
    return f"Searching '{_truncate_text(pattern)}'"


def _format_get_file_info(args: dict[str, Any]) -> str:
    path = args.get("path", args.get("file_path", ""))
    return f"Getting info: {_truncate_path(path)}"


def _format_query_catalog(args: dict[str, Any]) -> str:
    text = args.get("text_search", args.get("query", ""))
    if text:
        return f"Searching catalog: '{_truncate_text(text)}'"
    return "Querying catalog"


def _format_write_file(args: dict[str, Any]) -> str:
    path = args.get("path", args.get("file_path", ""))
    return f"Writing {_truncate_path(path)}"


def _format_edit_file(args: dict[str, Any]) -> str:
    path = args.get("path", args.get("file_path", ""))
    return f"Editing {_truncate_path(path)}"


def _format_insert_text(args: dict[str, Any]) -> str:
    path = args.get("path", args.get("file_path", ""))
    line = args.get("line_number", "")
    suffix = f" at line {line}" if line else ""
    return f"Inserting text in {_truncate_path(path)}{suffix}"


def _format_append_file(args: dict[str, Any]) -> str:
    path = args.get("path", args.get("file_path", ""))
    return f"Appending to {_truncate_path(path)}"


def _format_delete_file(args: dict[str, Any]) -> str:
    path = args.get("path", args.get("file_path", ""))
    return f"Deleting {_truncate_path(path)}"


def _format_create_directory(args: dict[str, Any]) -> str:
    path = args.get("path", "")
    return f"Creating directory {_truncate_path(path)}"


def _format_remove_directory(args: dict[str, Any]) -> str:
    path = args.get("path", "")
    return f"Removing directory {_truncate_path(path)}"


def _format_execute_command(args: dict[str, Any]) -> str:
    command = args.get("command", "")
    return f"Executing: {_truncate_text(command, 35)}"


def _format_spawn_agent(args: dict[str, Any]) -> str:
    task = args.get("task", "")
    return f"Spawning agent: {_truncate_text(task, 30)}"


def _format_spawn_predefined(args: dict[str, Any]) -> str:
    agent_name = args.get("agent_name", "agent")
    return f"Spawning {sanitize_terminal_text(agent_name)}"


def _format_default(tool_name: str, args: dict[str, Any]) -> str:
    """Default formatter for unknown tools."""
    if not args:
        return tool_name

    # Get first meaningful argument value
    first_value = None
    for key in ("path", "file_path", "query", "pattern", "text", "name"):
        if key in args:
            first_value = args[key]
            break

    if first_value is None:
        # Just use the first argument's value
        first_value = next(iter(args.values()), "")

    value_text = sanitize_terminal_text(first_value)
    if value_text:
        return f"{tool_name}({_truncate_text(value_text, 25)})"

    return tool_name
