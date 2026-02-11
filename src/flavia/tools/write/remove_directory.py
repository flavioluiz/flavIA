"""Remove directory tool for flavIA."""

import shutil
from typing import TYPE_CHECKING, Any

from ..base import BaseTool, ToolParameter, ToolSchema
from ..permissions import check_write_permission, resolve_path
from ..registry import register_tool

if TYPE_CHECKING:
    from flavia.agent.context import AgentContext


class RemoveDirectoryTool(BaseTool):
    """Tool for removing a directory."""

    name = "remove_directory"
    description = (
        "Remove a directory. Use recursive=true to remove a non-empty "
        "directory with all its contents."
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
                    description="Path of the directory to remove (relative to base directory or absolute)",
                    required=True,
                ),
                ToolParameter(
                    name="recursive",
                    type="boolean",
                    description="If true, remove directory and all contents recursively. Default is false.",
                    required=False,
                    default=False,
                ),
            ],
        )

    def execute(self, args: dict[str, Any], agent_context: "AgentContext") -> str:
        path = args.get("path", "")
        recursive = args.get("recursive", False)

        if not path:
            return "Error: path is required"

        full_path = resolve_path(path, agent_context.base_dir)

        # Permission check on the directory itself
        allowed, error_msg = check_write_permission(full_path, agent_context)
        if not allowed:
            return f"Error: {error_msg}"

        if not full_path.exists():
            return f"Error: Directory not found: {path}"
        if not full_path.is_dir():
            return f"Error: '{path}' is not a directory (use delete_file for files)"

        # Check if directory is empty
        try:
            contents = list(full_path.iterdir())
        except PermissionError:
            return f"Error: OS permission denied reading directory '{path}'"

        if contents and not recursive:
            return (
                f"Error: Directory not empty ({len(contents)} items). "
                "Use recursive=true to remove with all contents."
            )

        # Build details
        if recursive and contents:
            file_count = 0
            dir_count = 0
            for item in full_path.rglob("*"):
                if item.is_file():
                    file_count += 1
                elif item.is_dir():
                    dir_count += 1
            details = f"{file_count} file(s), {dir_count} subdirectory(ies)"
        else:
            details = "empty directory"

        # User confirmation
        wc = agent_context.write_confirmation
        if wc is None:
            return "Error: Write operations require confirmation but no confirmation handler is configured"
        if not wc.confirm("Remove directory", str(full_path), details):
            return "Operation cancelled by user"

        try:
            if recursive:
                shutil.rmtree(str(full_path))
            else:
                full_path.rmdir()
        except PermissionError:
            return f"Error: OS permission denied removing directory '{path}'"
        except OSError as e:
            return f"Error removing directory: {e}"

        try:
            rel_path = full_path.relative_to(agent_context.base_dir)
        except ValueError:
            rel_path = full_path

        if recursive and contents:
            return f"Directory removed: {rel_path} ({details})"
        return f"Directory removed: {rel_path}"


register_tool(RemoveDirectoryTool())
