"""Append file tool for flavIA."""

from typing import TYPE_CHECKING, Any

from ..backup import FileBackup
from ..base import BaseTool, ToolParameter, ToolSchema
from ..permissions import check_write_permission, resolve_path
from ..registry import register_tool

if TYPE_CHECKING:
    from flavia.agent.context import AgentContext


class AppendFileTool(BaseTool):
    """Tool for appending content to the end of a file."""

    name = "append_file"
    description = "Append content to the end of a file (creates the file if it does not exist)"
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
                    name="content",
                    type="string",
                    description="Content to append to the file",
                    required=True,
                ),
            ],
        )

    def execute(self, args: dict[str, Any], agent_context: "AgentContext") -> str:
        path = args.get("path", "")
        content = args.get("content", "")

        if not path:
            return "Error: path is required"

        full_path = resolve_path(path, agent_context.base_dir)

        # Permission check
        allowed, error_msg = check_write_permission(full_path, agent_context)
        if not allowed:
            return f"Error: {error_msg}"

        file_exists = full_path.exists() and full_path.is_file()
        operation = "Append to file" if file_exists else "Create file"
        content_bytes = len(content.encode("utf-8"))
        details = f"{content_bytes} bytes"

        # User confirmation
        wc = agent_context.write_confirmation
        if wc is None:
            return "Error: Write operations require confirmation but no confirmation handler is configured"
        if not wc.confirm(operation, str(full_path), details):
            return "Operation cancelled by user"

        # Backup existing file before append
        if file_exists:
            FileBackup.backup(full_path, agent_context.base_dir)

        try:
            # Create parent directories if needed
            full_path.parent.mkdir(parents=True, exist_ok=True)

            # Read existing content to add separator if needed
            if file_exists:
                existing = full_path.read_text(encoding="utf-8")
                separator = "" if not existing or existing.endswith("\n") else "\n"
                full_path.write_text(existing + separator + content, encoding="utf-8")
            else:
                full_path.write_text(content, encoding="utf-8")
        except UnicodeDecodeError:
            return f"Error: Cannot read existing '{path}' - file is not valid UTF-8 text"
        except PermissionError:
            return f"Error: OS permission denied writing to '{path}'"
        except OSError as e:
            return f"Error writing file: {e}"

        try:
            rel_path = full_path.relative_to(agent_context.base_dir)
        except ValueError:
            rel_path = full_path

        if file_exists:
            return f"Appended {content_bytes} bytes to {rel_path}"
        return f"File created: {rel_path} ({content_bytes} bytes)"


register_tool(AppendFileTool())
