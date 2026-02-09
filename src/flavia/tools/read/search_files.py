"""Search files tool for flavIA."""

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..base import BaseTool, ToolSchema, ToolParameter
from ..permissions import can_read_path, check_read_permission, resolve_path
from ..registry import register_tool

if TYPE_CHECKING:
    from flavia.agent.context import AgentContext


class SearchFilesTool(BaseTool):
    """Tool for searching content within files."""

    name = "search_files"
    description = "Search for a pattern (text or regex) within files"
    category = "read"

    MAX_RESULTS = 50
    CONTEXT_LINES = 2

    def get_schema(self, **context) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParameter(
                    name="pattern",
                    type="string",
                    description="Text or regex pattern to search for",
                    required=True,
                ),
                ToolParameter(
                    name="path",
                    type="string",
                    description="Directory to search in (relative to base directory or absolute)",
                    required=False,
                    default=".",
                ),
                ToolParameter(
                    name="file_pattern",
                    type="string",
                    description="Glob pattern to filter files (e.g., '*.py', '*.md')",
                    required=False,
                    default="*",
                ),
                ToolParameter(
                    name="case_sensitive",
                    type="boolean",
                    description="Whether search is case-sensitive",
                    required=False,
                    default=False,
                ),
                ToolParameter(
                    name="regex",
                    type="boolean",
                    description="Treat pattern as regex (default: plain text)",
                    required=False,
                    default=False,
                ),
            ]
        )

    def execute(self, args: dict[str, Any], agent_context: "AgentContext") -> str:
        pattern = args.get("pattern", "")
        path = args.get("path", ".")
        file_pattern = args.get("file_pattern", "*")
        case_sensitive = args.get("case_sensitive", False)
        use_regex = args.get("regex", False)

        if not pattern:
            return "Error: pattern is required"

        search_dir = resolve_path(path, agent_context.base_dir)

        # Permission check
        allowed, error_msg = check_read_permission(search_dir, agent_context)
        if not allowed:
            return f"Error: {error_msg}"

        if not search_dir.exists():
            return f"Error: Directory not found: {path}"
        if not search_dir.is_dir():
            return f"Error: '{path}' is not a directory"

        # Compile regex
        try:
            flags = 0 if case_sensitive else re.IGNORECASE
            if use_regex:
                regex = re.compile(pattern, flags)
            else:
                regex = re.compile(re.escape(pattern), flags)
        except re.error as e:
            return f"Error: Invalid regex pattern: {e}"

        results = []
        files_searched = 0
        files_with_matches = 0

        try:
            for file_path in search_dir.rglob(file_pattern):
                if not file_path.is_file():
                    continue

                resolved_file = file_path.resolve()
                # Check if we can read this file
                if not can_read_path(resolved_file, agent_context):
                    continue

                files_searched += 1
                file_results = self._search_file(resolved_file, regex, agent_context.base_dir)

                if file_results:
                    files_with_matches += 1
                    results.extend(file_results)

                    if len(results) >= self.MAX_RESULTS:
                        break

        except PermissionError:
            return f"Error: Permission denied accessing '{path}'"

        if not results:
            return f"No matches found for '{pattern}' in {files_searched} files"

        output = [f"Found {len(results)} matches in {files_with_matches} files (searched {files_searched} files):\n"]

        current_file = None
        for match in results[:self.MAX_RESULTS]:
            if match["file"] != current_file:
                current_file = match["file"]
                output.append(f"\n=== {current_file} ===")

            output.append(f"Line {match['line']}: {match['text'].strip()}")

        if len(results) > self.MAX_RESULTS:
            output.append(f"\n... and {len(results) - self.MAX_RESULTS} more matches (truncated)")

        return "\n".join(output)

    def _search_file(self, file_path: Path, regex: re.Pattern, base_dir: Path) -> list[dict[str, Any]]:
        results = []

        try:
            content = file_path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, PermissionError):
            return []

        lines = content.split("\n")
        try:
            rel_path = str(file_path.relative_to(base_dir))
        except ValueError:
            rel_path = str(file_path)

        for i, line in enumerate(lines, 1):
            if regex.search(line):
                results.append({
                    "file": rel_path,
                    "line": i,
                    "text": line,
                })

        return results


register_tool(SearchFilesTool())
