"""Edit file tool for flavIA."""

from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..backup import FileBackup
from ..base import BaseTool, ToolParameter, ToolSchema
from ..permissions import check_write_permission, resolve_path
from ..registry import register_tool

if TYPE_CHECKING:
    from flavia.agent.context import AgentContext


class EditFileTool(BaseTool):
    """Tool for replacing a specific text fragment in a file."""

    name = "edit_file"
    description = (
        "Replace an exact text fragment in a file with new text. "
        "The old_text must match exactly once in the file."
    )
    category = "write"

    def get_schema(self, **context) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParameter(
                    name="path",
                    type="string",
                    description="Path to the file (relative to base directory or absolute)",
                    required=True,
                ),
                ToolParameter(
                    name="old_text",
                    type="string",
                    description="Exact text to find and replace (must appear exactly once)",
                    required=True,
                ),
                ToolParameter(
                    name="new_text",
                    type="string",
                    description="Replacement text",
                    required=True,
                ),
            ],
        )

    def execute(self, args: dict[str, Any], agent_context: "AgentContext") -> str:
        path = args.get("path", "")
        old_text = args.get("old_text", "")
        new_text = args.get("new_text", "")

        if not path:
            return "Error: path is required"
        if not old_text:
            return "Error: old_text is required"

        full_path = resolve_path(path, agent_context.base_dir)

        # Permission check
        allowed, error_msg = check_write_permission(full_path, agent_context)
        if not allowed:
            return f"Error: {error_msg}"

        if not full_path.exists():
            return f"Error: File not found: {path}"
        if not full_path.is_file():
            return f"Error: '{path}' is not a file"

        # Read current content
        try:
            content = full_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return f"Error: Cannot read '{path}' - file is not valid UTF-8 text"
        except PermissionError:
            return f"Error: OS permission denied reading '{path}'"

        # Verify exact match count
        count = content.count(old_text)
        if count == 0:
            return "Error: Text not found in file"
        if count > 1:
            return (
                f"Error: Text found {count} times - please provide more context for a unique match"
            )

        # Compute affected line numbers for reporting
        match_start = content.index(old_text)
        prefix = content[:match_start]
        start_line = prefix.count("\n") + 1
        old_line_count = old_text.count("\n") + 1
        new_line_count = new_text.count("\n") + 1

        # Build details for confirmation
        details = (
            f"Lines {start_line}-{start_line + old_line_count - 1}: "
            f"replacing {len(old_text)} chars with {len(new_text)} chars"
        )

        # User confirmation
        wc = agent_context.write_confirmation
        if wc is None:
            return "Error: Write operations require confirmation but no confirmation handler is configured"
        if not wc.confirm("Edit file", str(full_path), details):
            return "Operation cancelled by user"

        # Backup before edit
        FileBackup.backup(full_path, agent_context.base_dir)

        # Apply edit
        new_content = content.replace(old_text, new_text, 1)

        try:
            full_path.write_text(new_content, encoding="utf-8")
        except PermissionError:
            return f"Error: OS permission denied writing to '{path}'"
        except OSError as e:
            return f"Error writing file: {e}"

        try:
            rel_path = full_path.relative_to(agent_context.base_dir)
        except ValueError:
            rel_path = full_path

        return (
            f"File edited: {rel_path}\n"
            f"  Lines {start_line}-{start_line + old_line_count - 1} "
            f"({old_line_count} lines -> {new_line_count} lines)"
        )


register_tool(EditFileTool())
