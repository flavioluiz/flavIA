"""Delete file tool for flavIA."""

from typing import TYPE_CHECKING, Any

from ..backup import FileBackup
from ..base import BaseTool, ToolParameter, ToolSchema
from ..permissions import check_write_permission, resolve_path
from ..registry import register_tool

if TYPE_CHECKING:
    from flavia.agent.context import AgentContext


class DeleteFileTool(BaseTool):
    """Tool for deleting a file."""

    name = "delete_file"
    description = "Delete a file from the filesystem"
    category = "write"

    def get_schema(self, **context) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParameter(
                    name="path",
                    type="string",
                    description="Path to the file to delete (relative to base directory or absolute)",
                    required=True,
                ),
            ],
        )

    def execute(self, args: dict[str, Any], agent_context: "AgentContext") -> str:
        path = args.get("path", "")

        if not path:
            return "Error: path is required"

        full_path = resolve_path(path, agent_context.base_dir)

        # Permission check
        allowed, error_msg = check_write_permission(full_path, agent_context)
        if not allowed:
            return f"Error: {error_msg}"

        if not full_path.exists():
            return f"Error: File not found: {path}"
        if not full_path.is_file():
            return f"Error: '{path}' is not a file (use remove_directory for directories)"

        # Build details
        try:
            size = full_path.stat().st_size
            details = f"{size} bytes"
        except OSError:
            details = ""

        # User confirmation
        wc = agent_context.write_confirmation
        if wc is None:
            return "Error: Write operations require confirmation but no confirmation handler is configured"
        if not wc.confirm("Delete file", str(full_path), details):
            return "Operation cancelled by user"

        # Backup before deletion
        FileBackup.backup(full_path, agent_context.base_dir)

        try:
            full_path.unlink()
        except PermissionError:
            return f"Error: OS permission denied deleting '{path}'"
        except OSError as e:
            return f"Error deleting file: {e}"

        try:
            rel_path = full_path.relative_to(agent_context.base_dir)
        except ValueError:
            rel_path = full_path

        return f"Deleted file: {rel_path}"


register_tool(DeleteFileTool())
