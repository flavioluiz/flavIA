"""Create directory tool for flavIA."""

from typing import TYPE_CHECKING, Any

from ..base import BaseTool, ToolParameter, ToolSchema
from ..permissions import check_write_permission, resolve_path
from ..registry import register_tool
from .preview import OperationPreview

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

        try:
            rel_path = full_path.relative_to(agent_context.base_dir)
        except ValueError:
            rel_path = full_path

        if full_path.exists():
            if full_path.is_dir():
                return f"Directory already exists: {rel_path}"
            return f"Error: '{path}' exists but is not a directory"

        # Build path hierarchy for preview
        path_parts = []
        current = full_path
        while current != agent_context.base_dir and current.parent != current:
            try:
                part_rel = current.relative_to(agent_context.base_dir)
                path_parts.insert(0, str(part_rel) + "/")
            except ValueError:
                path_parts.insert(0, str(current) + "/")
            current = current.parent

        # Generate preview
        preview = OperationPreview(
            operation="mkdir",
            path=str(full_path),
            dir_contents=path_parts if len(path_parts) > 1 else [],
        )

        # User confirmation
        wc = agent_context.write_confirmation
        if wc is None:
            return "Error: Write operations require confirmation but no confirmation handler is configured"
        if not wc.confirm("Create directory", str(full_path), "", preview=preview):
            return "Operation cancelled by user"

        # Dry-run check (after confirmation, before actual creation)
        if agent_context.dry_run:
            return f"[DRY-RUN] Would create directory: {rel_path}"

        try:
            full_path.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            return f"Error: OS permission denied creating directory '{path}'"
        except OSError as e:
            return f"Error creating directory: {e}"

        return f"Directory created: {rel_path}"


register_tool(CreateDirectoryTool())
