"""Write file tool for flavIA."""

from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..backup import FileBackup
from ..base import BaseTool, ToolParameter, ToolSchema
from ..permissions import check_write_permission, resolve_path
from ..registry import register_tool

if TYPE_CHECKING:
    from flavia.agent.context import AgentContext


class WriteFileTool(BaseTool):
    """Tool for creating a new file or overwriting an existing file."""

    name = "write_file"
    description = "Create a new file or overwrite an existing file with the given content"
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
                    description="Content to write to the file",
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

        # Determine operation type
        is_overwrite = full_path.exists() and full_path.is_file()
        operation = "Overwrite file" if is_overwrite else "Create file"

        # Build details for confirmation
        content_bytes = len(content.encode("utf-8"))
        details = f"{content_bytes} bytes"
        if is_overwrite:
            try:
                old_size = full_path.stat().st_size
                details += f" (replacing {old_size} bytes)"
            except OSError:
                pass

        # User confirmation
        wc = agent_context.write_confirmation
        if wc is None:
            return "Error: Write operations require confirmation but no confirmation handler is configured"
        if not wc.confirm(operation, str(full_path), details):
            return "Operation cancelled by user"

        # Backup existing file before overwrite
        if is_overwrite:
            FileBackup.backup(full_path, agent_context.base_dir)

        try:
            # Create parent directories if needed
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content, encoding="utf-8")

            try:
                rel_path = full_path.relative_to(agent_context.base_dir)
            except ValueError:
                rel_path = full_path

            action = "overwritten" if is_overwrite else "created"
            return f"File {action}: {rel_path} ({content_bytes} bytes)"
        except PermissionError:
            return f"Error: OS permission denied writing to '{path}'"
        except OSError as e:
            return f"Error writing file: {e}"


register_tool(WriteFileTool())
