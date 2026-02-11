"""Tests for tool status display functionality."""

import threading

from flavia.agent.status import (
    StatusPhase,
    ToolStatus,
    _truncate_path,
    _truncate_text,
    format_tool_display,
    sanitize_terminal_text,
)
from flavia.tools import list_available_tools


class TestFormatToolDisplay:
    """Tests for format_tool_display function."""

    def test_read_file(self):
        """Test read_file formatting."""
        display = format_tool_display("read_file", {"path": "config.yaml"})
        assert display == "Reading config.yaml"

    def test_read_file_with_file_path_key(self):
        """Test read_file with file_path key."""
        display = format_tool_display("read_file", {"file_path": "settings.json"})
        assert display == "Reading settings.json"

    def test_list_files(self):
        """Test list_files formatting."""
        display = format_tool_display("list_files", {"path": "src/"})
        assert display == "Listing src/"

    def test_list_files_default_path(self):
        """Test list_files with no path uses default."""
        display = format_tool_display("list_files", {})
        assert display == "Listing ."

    def test_search_files(self):
        """Test search_files formatting."""
        display = format_tool_display("search_files", {"pattern": "TODO"})
        assert display == "Searching 'TODO'"

    def test_query_catalog(self):
        """Test query_catalog formatting."""
        display = format_tool_display("query_catalog", {"text_search": "machine learning"})
        assert display == "Searching catalog: 'machine learning'"

    def test_query_catalog_empty(self):
        """Test query_catalog with no query."""
        display = format_tool_display("query_catalog", {})
        assert display == "Querying catalog"

    def test_write_file(self):
        """Test write_file formatting."""
        display = format_tool_display("write_file", {"path": "output.txt"})
        assert display == "Writing output.txt"

    def test_execute_command(self):
        """Test execute_command formatting."""
        display = format_tool_display("execute_command", {"command": "git status"})
        assert display == "Executing: git status"

    def test_spawn_agent(self):
        """Test spawn_agent formatting."""
        display = format_tool_display("spawn_agent", {"task": "analyze this file"})
        assert display == "Spawning agent: analyze this file"

    def test_spawn_predefined(self):
        """Test spawn_predefined_agent formatting."""
        display = format_tool_display("spawn_predefined_agent", {"agent_name": "researcher"})
        assert display == "Spawning researcher"

    def test_unknown_tool_with_path(self):
        """Test unknown tool with path argument."""
        display = format_tool_display("custom_tool", {"path": "data.csv"})
        assert "custom_tool" in display
        assert "data.csv" in display

    def test_unknown_tool_no_args(self):
        """Test unknown tool with no arguments."""
        display = format_tool_display("custom_tool", {})
        assert display == "custom_tool"

    def test_handles_non_dict_args_without_crashing(self):
        """Formatter should tolerate malformed tool arguments."""
        display = format_tool_display("read_file", ["not", "a", "dict"])
        assert display == "Reading "

    def test_sanitizes_terminal_control_chars(self):
        """Display text must not include terminal control characters."""
        display = format_tool_display("read_file", {"path": "bad\x1b[31mname\nfile.txt"})
        assert "\x1b" not in display
        assert "\n" not in display

    def test_registered_tools_always_produce_non_empty_display(self):
        """Every registered tool should have a safe status label."""
        for tool_name in list_available_tools():
            display = format_tool_display(tool_name, {})
            assert isinstance(display, str)
            assert display.strip()
            assert "\x1b" not in display


class TestTruncation:
    """Tests for truncation helpers."""

    def test_truncate_path_short(self):
        """Short paths are not truncated."""
        assert _truncate_path("config.yaml") == "config.yaml"

    def test_truncate_path_long(self):
        """Long paths show filename context."""
        long_path = "very/long/path/to/some/deeply/nested/file.py"
        result = _truncate_path(long_path, max_len=30)
        assert "file.py" in result
        assert len(result) <= 30

    def test_truncate_path_preserves_parent(self):
        """Truncation preserves parent/filename when possible."""
        path = "src/components/Button.tsx"
        result = _truncate_path(path, max_len=30)
        assert "Button.tsx" in result

    def test_truncate_text_short(self):
        """Short text is not truncated."""
        assert _truncate_text("hello", 10) == "hello"

    def test_truncate_text_long(self):
        """Long text is truncated with ellipsis."""
        result = _truncate_text("hello world this is long", 15)
        assert len(result) == 15
        assert result.endswith("...")

    def test_sanitize_terminal_text(self):
        """Terminal sanitizer removes control chars and newlines."""
        sanitized = sanitize_terminal_text("A\x1b[31m\nB\tC")
        assert sanitized == "A[31m B C"


class TestToolStatus:
    """Tests for ToolStatus dataclass and factory methods."""

    def test_waiting_llm(self):
        """Test waiting_llm factory method."""
        status = ToolStatus.waiting_llm("main", depth=0)
        assert status.phase == StatusPhase.WAITING_LLM
        assert status.agent_id == "main"
        assert status.depth == 0
        assert status.tool_name is None

    def test_waiting_llm_subagent(self):
        """Test waiting_llm for sub-agent."""
        status = ToolStatus.waiting_llm("main.sub.1", depth=1)
        assert status.agent_id == "main.sub.1"
        assert status.depth == 1

    def test_executing_tool(self):
        """Test executing_tool factory method."""
        status = ToolStatus.executing_tool(
            "read_file",
            {"path": "config.yaml"},
            "main",
            depth=0,
        )
        assert status.phase == StatusPhase.EXECUTING_TOOL
        assert status.tool_name == "read_file"
        assert status.tool_display == "Reading config.yaml"
        assert status.args == {"path": "config.yaml"}
        assert status.agent_id == "main"

    def test_executing_tool_with_malformed_args(self):
        """Malformed args should not break status generation."""
        status = ToolStatus.executing_tool("read_file", ["invalid"], "main", depth=0)
        assert status.phase == StatusPhase.EXECUTING_TOOL
        assert status.args == {}
        assert status.tool_display == "Reading "

    def test_spawning_agent(self):
        """Test spawning_agent factory method."""
        status = ToolStatus.spawning_agent("researcher", "main", depth=0)
        assert status.phase == StatusPhase.SPAWNING_AGENT
        assert "researcher" in status.tool_display

    def test_status_callback_thread_safety(self):
        """Test that status callback works across threads."""
        status_holder: list[ToolStatus | None] = [None]

        def callback(s: ToolStatus) -> None:
            status_holder[0] = s

        def update_from_thread() -> None:
            callback(ToolStatus.executing_tool("read_file", {"path": "x"}, "main", 0))

        thread = threading.Thread(target=update_from_thread)
        thread.start()
        thread.join()

        assert status_holder[0] is not None
        assert status_holder[0].tool_name == "read_file"


class TestStatusPhase:
    """Tests for StatusPhase enum."""

    def test_phases_exist(self):
        """Verify all expected phases exist."""
        assert StatusPhase.WAITING_LLM.value == "waiting_llm"
        assert StatusPhase.EXECUTING_TOOL.value == "executing_tool"
        assert StatusPhase.SPAWNING_AGENT.value == "spawning_agent"
