"""Create directory tool for flavIA."""

from typing import TYPE_CHECKING, Any

from ..base import BaseTool, ToolParameter, ToolSchema
from ..permissions import check_write_permission, resolve_path
from ..registry import register_tool

if TYPE_CHECKING:
    from flavia.agent.context import AgentContext


class CreateDirectoryTool(BaseTool):
    """Tool for creating a directory (including parent directories)."""

    name = "create_directory"
    description = "Create a directory, including any necessary parent directories"
    category = "write"

    def get_schema(self, **context) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParameter(
                    name="path",
                    type="string",
                    description="Path of the directory to create (relative to base directory or absolute)",
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

        if full_path.exists():
            if full_path.is_dir():
                try:
                    rel_path = full_path.relative_to(agent_context.base_dir)
                except ValueError:
                    rel_path = full_path
                return f"Directory already exists: {rel_path}"
            return f"Error: '{path}' exists but is not a directory"

        # User confirmation
        wc = agent_context.write_confirmation
        if wc is None:
            return "Error: Write operations require confirmation but no confirmation handler is configured"
        if not wc.confirm("Create directory", str(full_path), ""):
            return "Operation cancelled by user"

        try:
            full_path.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            return f"Error: OS permission denied creating directory '{path}'"
        except OSError as e:
            return f"Error creating directory: {e}"

        try:
            rel_path = full_path.relative_to(agent_context.base_dir)
        except ValueError:
            rel_path = full_path

        return f"Directory created: {rel_path}"


register_tool(CreateDirectoryTool())
