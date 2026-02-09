"""List files tool for flavIA."""

from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..base import BaseTool, ToolSchema, ToolParameter
from ..permissions import can_read_path, check_read_permission, resolve_path
from ..registry import register_tool

if TYPE_CHECKING:
    from flavia.agent.context import AgentContext


class ListFilesTool(BaseTool):
    """Tool for listing files in a directory."""

    name = "list_files"
    description = "List all files and subdirectories in a directory"
    category = "read"

    def get_schema(self, **context) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParameter(
                    name="path",
                    type="string",
                    description="Path to directory (relative to base directory or absolute). Use '.' for root.",
                    required=False,
                    default=".",
                ),
                ToolParameter(
                    name="recursive",
                    type="boolean",
                    description="If true, list files recursively in subdirectories",
                    required=False,
                    default=False,
                ),
                ToolParameter(
                    name="pattern",
                    type="string",
                    description="Optional glob pattern to filter files (e.g., '*.md', '*.py')",
                    required=False,
                ),
            ]
        )

    def execute(self, args: dict[str, Any], agent_context: "AgentContext") -> str:
        path = args.get("path", ".")
        recursive = args.get("recursive", False)
        pattern = args.get("pattern", "*")

        target_dir = resolve_path(path, agent_context.base_dir)

        # Permission check
        allowed, error_msg = check_read_permission(target_dir, agent_context)
        if not allowed:
            return f"Error: {error_msg}"

        if not target_dir.exists():
            return f"Error: Directory not found: {path}"

        if not target_dir.is_dir():
            return f"Error: '{path}' is not a directory"

        try:
            if recursive:
                items = list(target_dir.rglob(pattern))
            else:
                items = list(target_dir.glob(pattern))

            result = []
            for item in sorted(items):
                # Check if we can read this item
                if not can_read_path(item, agent_context):
                    continue
                try:
                    rel_path = item.relative_to(agent_context.base_dir)
                except ValueError:
                    rel_path = item
                if item.is_dir():
                    result.append(f"[DIR]  {rel_path}/")
                else:
                    size = item.stat().st_size
                    result.append(f"[FILE] {rel_path} ({self._format_size(size)})")

            if not result:
                return f"No files found in '{path}'" + (f" matching '{pattern}'" if pattern != "*" else "")

            header = f"Contents of '{path}'"
            if recursive:
                header += " (recursive)"
            if pattern != "*":
                header += f" matching '{pattern}'"

            return f"{header}:\n\n" + "\n".join(result)

        except PermissionError:
            return f"Error: Permission denied accessing '{path}'"
        except Exception as e:
            return f"Error listing directory: {e}"

    def _format_size(self, size: int) -> str:
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}" if unit != "B" else f"{size} {unit}"
            size /= 1024
        return f"{size:.1f} TB"


register_tool(ListFilesTool())
