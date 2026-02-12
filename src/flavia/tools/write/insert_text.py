"""Insert text tool for flavIA."""

from typing import TYPE_CHECKING, Any

from ..backup import FileBackup
from ..base import BaseTool, ToolParameter, ToolSchema
from ..permissions import check_write_permission, resolve_path
from ..registry import register_tool
from .preview import OperationPreview, format_content_preview, format_insertion_context

if TYPE_CHECKING:
    from flavia.agent.context import AgentContext


class InsertTextTool(BaseTool):
    """Tool for inserting text at a specific line in a file."""

    name = "insert_text"
    description = "Insert text at a specific line number in a file (1-based)"
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
                    name="line_number",
                    type="integer",
                    description="Line number where text will be inserted (1-based). "
                    "Existing content at that line and below is shifted down.",
                    required=True,
                ),
                ToolParameter(
                    name="text",
                    type="string",
                    description="Text to insert",
                    required=True,
                ),
            ],
        )

    def execute(self, args: dict[str, Any], agent_context: "AgentContext") -> str:
        path = args.get("path", "")
        line_number = args.get("line_number")
        text = args.get("text", "")

        if not path:
            return "Error: path is required"
        if line_number is None:
            return "Error: line_number is required"
        if not isinstance(line_number, int):
            try:
                line_number = int(line_number)
            except (TypeError, ValueError):
                return "Error: line_number must be an integer"

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

        lines = content.splitlines(keepends=True)
        total_lines = len(lines)

        # Validate line number (1-based, can be total_lines + 1 to append)
        if line_number < 1 or line_number > total_lines + 1:
            return (
                f"Error: line_number {line_number} is out of range "
                f"(file has {total_lines} lines, valid range: 1-{total_lines + 1})"
            )

        # Count lines being inserted
        insert_lines = text.splitlines(keepends=True)
        if text and not text.endswith("\n"):
            # Ensure inserted text ends with newline for clean insertion
            insert_lines = (text + "\n").splitlines(keepends=True)
        num_inserted = len(insert_lines)

        # Build details for confirmation
        details = f"{num_inserted} line(s) at line {line_number}"

        try:
            rel_path = full_path.relative_to(agent_context.base_dir)
        except ValueError:
            rel_path = full_path

        # Generate preview with insertion context
        context_before, context_after = format_insertion_context(lines, line_number)
        preview = OperationPreview(
            operation="insert",
            path=str(full_path),
            content_preview=format_content_preview(text),
            content_lines=num_inserted,
            content_bytes=len(text.encode("utf-8")),
            context_before=context_before,
            context_after=context_after,
            file_size=len(content.encode("utf-8")),
        )

        # User confirmation
        wc = agent_context.write_confirmation
        if wc is None:
            return "Error: Write operations require confirmation but no confirmation handler is configured"
        if not wc.confirm("Insert text", str(full_path), details, preview=preview):
            return "Operation cancelled by user"

        # Dry-run check (after confirmation, before actual write)
        if agent_context.dry_run:
            return f"[DRY-RUN] Would insert {num_inserted} line(s) at line {line_number} in {rel_path}"

        # Backup before insert
        FileBackup.backup(full_path, agent_context.base_dir)

        # Insert at the specified position (0-based index = line_number - 1)
        insert_index = line_number - 1
        new_lines = lines[:insert_index] + insert_lines + lines[insert_index:]
        new_content = "".join(new_lines)

        try:
            full_path.write_text(new_content, encoding="utf-8")
        except PermissionError:
            return f"Error: OS permission denied writing to '{path}'"
        except OSError as e:
            return f"Error writing file: {e}"

        return f"Inserted {num_inserted} line(s) at line {line_number} in {rel_path}"


register_tool(InsertTextTool())
