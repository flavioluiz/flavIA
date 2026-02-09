"""Read file tool for flavIA."""

from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..base import BaseTool, ToolSchema, ToolParameter
from ..permissions import check_read_permission, resolve_path
from ..registry import register_tool

if TYPE_CHECKING:
    from flavia.agent.context import AgentContext


class ReadFileTool(BaseTool):
    """Tool for reading file contents."""

    name = "read_file"
    description = "Read the complete contents of a file"
    category = "read"

    def get_schema(self, **context) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParameter(
                    name="path",
                    type="string",
                    description="Path to the file to read (relative to base directory or absolute)",
                    required=True,
                )
            ]
        )

    def execute(self, args: dict[str, Any], agent_context: "AgentContext") -> str:
        path = args.get("path", "")

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
            content = full_path.read_text(encoding="utf-8")
            return content
        except UnicodeDecodeError:
            return f"Error: Cannot read '{path}' - file is not valid UTF-8 text"
        except PermissionError:
            return f"Error: Permission denied reading '{path}'"
        except Exception as e:
            return f"Error reading file: {e}"


register_tool(ReadFileTool())
