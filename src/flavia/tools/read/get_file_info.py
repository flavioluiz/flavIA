"""Get file info tool for flavIA."""

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..base import BaseTool, ToolSchema, ToolParameter
from ..registry import register_tool

if TYPE_CHECKING:
    from flavia.agent.context import AgentContext


class GetFileInfoTool(BaseTool):
    """Tool for getting file metadata."""

    name = "get_file_info"
    description = "Get metadata about a file or directory (size, dates, permissions)"
    category = "read"

    def get_schema(self, **context) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParameter(
                    name="path",
                    type="string",
                    description="Path to file or directory (relative to base directory)",
                    required=True,
                )
            ]
        )

    def execute(self, args: dict[str, Any], agent_context: "AgentContext") -> str:
        path = args.get("path", "")

        if not path:
            return "Error: path is required"

        base_dir = agent_context.base_dir
        full_path = (base_dir / path).resolve()

        # Security check
        try:
            full_path.relative_to(base_dir.resolve())
        except ValueError:
            return f"Error: Access denied - path '{path}' is outside allowed directory"

        if not full_path.exists():
            return f"Error: Path not found: {path}"

        try:
            stat = full_path.stat()

            info = {
                "name": full_path.name,
                "path": str(full_path.relative_to(base_dir)),
                "type": "directory" if full_path.is_dir() else "file",
                "size": self._format_size(stat.st_size),
                "size_bytes": stat.st_size,
                "created": self._format_time(stat.st_ctime),
                "modified": self._format_time(stat.st_mtime),
                "accessed": self._format_time(stat.st_atime),
                "permissions": oct(stat.st_mode)[-3:],
            }

            if full_path.is_file():
                info["extension"] = full_path.suffix or "(none)"
                try:
                    content = full_path.read_text(encoding="utf-8")
                    info["lines"] = content.count("\n") + 1
                    info["characters"] = len(content)
                except (UnicodeDecodeError, PermissionError):
                    info["lines"] = "(binary file)"

            if full_path.is_dir():
                try:
                    items = list(full_path.iterdir())
                    info["items"] = len(items)
                    info["files"] = sum(1 for i in items if i.is_file())
                    info["directories"] = sum(1 for i in items if i.is_dir())
                except PermissionError:
                    info["items"] = "(access denied)"

            output = [f"Information for: {path}\n"]
            for key, value in info.items():
                output.append(f"  {key}: {value}")

            return "\n".join(output)

        except PermissionError:
            return f"Error: Permission denied accessing '{path}'"
        except Exception as e:
            return f"Error getting file info: {e}"

    def _format_size(self, size: int) -> str:
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}" if unit != "B" else f"{size} {unit}"
            size /= 1024
        return f"{size:.1f} TB"

    def _format_time(self, timestamp: float) -> str:
        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


register_tool(GetFileInfoTool())
