"""Tests for read_file context-window size guard (Camadas 1-4)."""

from pathlib import Path
from dataclasses import dataclass

import pytest

from flavia.agent.context import AgentContext
from flavia.tools.read.read_file import (
    CHARS_PER_TOKEN,
    MAX_CONTEXT_FRACTION,
    PREVIEW_LINES,
    REMAINING_FRACTION,
    ReadFileTool,
    _compute_max_result_tokens,
    _estimate_tokens,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_context(
    base_dir: Path,
    max_context_tokens: int = 128_000,
    current_context_tokens: int = 0,
) -> AgentContext:
    """Create a minimal AgentContext for testing."""
    return AgentContext(
        base_dir=base_dir,
        max_context_tokens=max_context_tokens,
        current_context_tokens=current_context_tokens,
    )


def _write_file(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


@dataclass
class _FakeFunctionCall:
    name: str
    arguments: str = "{}"


@dataclass
class _FakeToolCall:
    id: str
    function: _FakeFunctionCall


# ---------------------------------------------------------------------------
# Unit tests for helpers
# ---------------------------------------------------------------------------


class TestEstimateTokens:
    def test_basic(self):
        assert _estimate_tokens(400) == 100

    def test_minimum(self):
        assert _estimate_tokens(0) == 1

    def test_chars_per_token(self):
        assert _estimate_tokens(CHARS_PER_TOKEN) == 1


class TestComputeMaxResultTokens:
    def test_empty_context(self, tmp_path):
        ctx = _make_context(tmp_path, max_context_tokens=100_000, current_context_tokens=0)
        budget = _compute_max_result_tokens(ctx)
        # min(100_000 * 0.25, 100_000 * 0.50) = min(25_000, 50_000) = 25_000
        assert budget == 25_000

    def test_half_full_context(self, tmp_path):
        ctx = _make_context(tmp_path, max_context_tokens=100_000, current_context_tokens=50_000)
        budget = _compute_max_result_tokens(ctx)
        # remaining = 50_000; min(25_000, 25_000) = 25_000
        assert budget == 25_000

    def test_almost_full_context(self, tmp_path):
        """When context is 90% full, dynamic cap dominates."""
        ctx = _make_context(tmp_path, max_context_tokens=100_000, current_context_tokens=90_000)
        budget = _compute_max_result_tokens(ctx)
        # remaining = 10_000; min(25_000, 5_000) = 5_000
        assert budget == 5_000

    def test_context_completely_full(self, tmp_path):
        ctx = _make_context(tmp_path, max_context_tokens=100_000, current_context_tokens=100_000)
        budget = _compute_max_result_tokens(ctx)
        # remaining = 0; min(25_000, 0) = 0 -> max(1, 0) = 1
        assert budget == 1


# ---------------------------------------------------------------------------
# ReadFileTool integration tests
# ---------------------------------------------------------------------------


class TestReadFileSmallFiles:
    """Small files should be read normally without any blocking."""

    def test_read_small_file(self, tmp_path):
        _write_file(tmp_path, "small.txt", "Hello, world!\n")
        tool = ReadFileTool()
        ctx = _make_context(tmp_path)
        result = tool.execute({"path": "small.txt"}, ctx)
        assert result == "Hello, world!\n"

    def test_read_empty_file(self, tmp_path):
        _write_file(tmp_path, "empty.txt", "")
        tool = ReadFileTool()
        ctx = _make_context(tmp_path)
        result = tool.execute({"path": "empty.txt"}, ctx)
        assert result == ""

    def test_read_file_not_found(self, tmp_path):
        tool = ReadFileTool()
        ctx = _make_context(tmp_path)
        result = tool.execute({"path": "nonexistent.txt"}, ctx)
        assert "Error" in result
        assert "not found" in result.lower()


class TestReadFileLargeFileBlocked:
    """Large files should return a preview + instructions instead of full content."""

    def test_large_file_blocked(self, tmp_path):
        # Create a file that exceeds 25% of a small context window
        # Context: 1000 tokens -> budget: 250 tokens -> 1000 chars
        line = "A" * 99 + "\n"  # 100 chars per line
        content = line * 200  # 20_000 chars -> 5_000 tokens
        _write_file(tmp_path, "big.txt", content)

        tool = ReadFileTool()
        ctx = _make_context(tmp_path, max_context_tokens=1_000)
        result = tool.execute({"path": "big.txt"}, ctx)

        assert "FILE TOO LARGE" in result
        assert "Preview" in result
        assert "start_line" in result
        assert "end_line" in result
        assert "big.txt" in result

    def test_large_file_shows_preview_lines(self, tmp_path):
        # 100 lines of "Line NNN\n"
        lines = [f"Line {i:03d}\n" for i in range(1, 101)]
        content = "".join(lines)
        _write_file(tmp_path, "hundred.txt", content)

        tool = ReadFileTool()
        # Make the budget very small so the file is blocked
        ctx = _make_context(tmp_path, max_context_tokens=100)
        result = tool.execute({"path": "hundred.txt"}, ctx)

        assert "FILE TOO LARGE" in result
        # First 50 lines should be in preview
        assert "Line 001" in result
        assert "Line 050" in result

    def test_file_just_under_budget_passes(self, tmp_path):
        # File that just fits within 25% of context
        # Context: 100_000 tokens -> budget: 25_000 tokens -> 100_000 chars
        content = "x" * 90_000  # 22_500 tokens < 25_000
        _write_file(tmp_path, "fits.txt", content)

        tool = ReadFileTool()
        ctx = _make_context(tmp_path, max_context_tokens=100_000)
        result = tool.execute({"path": "fits.txt"}, ctx)

        assert "FILE TOO LARGE" not in result
        assert result == content


class TestReadFilePartialRead:
    """Partial reads via start_line / end_line."""

    def test_partial_read_basic(self, tmp_path):
        lines = [f"Line {i}\n" for i in range(1, 21)]
        _write_file(tmp_path, "lines.txt", "".join(lines))

        tool = ReadFileTool()
        ctx = _make_context(tmp_path)
        result = tool.execute({"path": "lines.txt", "start_line": 5, "end_line": 10}, ctx)

        assert "Line 5" in result
        assert "Line 10" in result
        assert "Line 4" not in result
        assert "Line 11" not in result
        assert "lines 5-10" in result
        assert "of 20 total" in result

    def test_partial_read_only_start(self, tmp_path):
        lines = [f"Line {i}\n" for i in range(1, 11)]
        _write_file(tmp_path, "ten.txt", "".join(lines))

        tool = ReadFileTool()
        ctx = _make_context(tmp_path)
        result = tool.execute({"path": "ten.txt", "start_line": 8}, ctx)

        assert "Line 8" in result
        assert "Line 9" in result
        assert "Line 10" in result
        assert "Line 7" not in result

    def test_partial_read_only_end(self, tmp_path):
        lines = [f"Line {i}\n" for i in range(1, 11)]
        _write_file(tmp_path, "ten.txt", "".join(lines))

        tool = ReadFileTool()
        ctx = _make_context(tmp_path)
        result = tool.execute({"path": "ten.txt", "end_line": 3}, ctx)

        assert "Line 1" in result
        assert "Line 3" in result
        assert "Line 4" not in result

    def test_partial_read_start_exceeds_total(self, tmp_path):
        _write_file(tmp_path, "short.txt", "one\ntwo\nthree\n")

        tool = ReadFileTool()
        ctx = _make_context(tmp_path)
        result = tool.execute({"path": "short.txt", "start_line": 100}, ctx)

        assert "Error" in result
        assert "exceeds total lines" in result

    def test_partial_read_start_greater_than_end(self, tmp_path):
        _write_file(tmp_path, "short.txt", "one\ntwo\nthree\n")

        tool = ReadFileTool()
        ctx = _make_context(tmp_path)
        result = tool.execute({"path": "short.txt", "start_line": 5, "end_line": 2}, ctx)

        assert "Error" in result

    def test_partial_read_truncated_if_still_too_large(self, tmp_path):
        # Big lines, tiny budget
        lines = [("X" * 1000 + "\n") for _ in range(100)]
        _write_file(tmp_path, "biglines.txt", "".join(lines))

        tool = ReadFileTool()
        ctx = _make_context(tmp_path, max_context_tokens=200)
        result = tool.execute({"path": "biglines.txt", "start_line": 1, "end_line": 100}, ctx)

        assert "TRUNCATED" in result

    def test_partial_read_rejects_invalid_start_type(self, tmp_path):
        _write_file(tmp_path, "short.txt", "one\ntwo\nthree\n")

        tool = ReadFileTool()
        ctx = _make_context(tmp_path)
        result = tool.execute({"path": "short.txt", "start_line": "abc"}, ctx)

        assert result == "Error: start_line must be an integer"

    def test_partial_read_rejects_bool_line_type(self, tmp_path):
        _write_file(tmp_path, "short.txt", "one\ntwo\nthree\n")

        tool = ReadFileTool()
        ctx = _make_context(tmp_path)
        result = tool.execute({"path": "short.txt", "end_line": True}, ctx)

        assert result == "Error: end_line must be an integer"


class TestDynamicBudget:
    """Camada 4: budget shrinks as context fills up."""

    def test_budget_shrinks_with_context_usage(self, tmp_path):
        # File is 4000 chars = 1000 tokens
        content = "A" * 4000
        _write_file(tmp_path, "medium.txt", content)
        tool = ReadFileTool()

        # With empty context (10_000 tokens), budget = min(2500, 5000) = 2500
        # File is 1000 tokens -> should pass
        ctx1 = _make_context(tmp_path, max_context_tokens=10_000, current_context_tokens=0)
        result1 = tool.execute({"path": "medium.txt"}, ctx1)
        assert "FILE TOO LARGE" not in result1

        # With 95% full context (10_000 tokens), budget = min(2500, 250) = 250
        # File is 1000 tokens -> should be blocked
        ctx2 = _make_context(tmp_path, max_context_tokens=10_000, current_context_tokens=9_500)
        result2 = tool.execute({"path": "medium.txt"}, ctx2)
        assert "FILE TOO LARGE" in result2


class TestToolResultGuard:
    """Camada 3: generic tool result guard in BaseAgent."""

    def test_guard_available_in_base_agent(self):
        """Verify _guard_tool_result is defined on BaseAgent."""
        from flavia.agent.base import BaseAgent

        assert hasattr(BaseAgent, "_guard_tool_result")

    def test_guard_constants(self):
        from flavia.agent.base import BaseAgent

        assert BaseAgent._GUARD_MAX_CONTEXT_FRACTION == 0.25
        assert BaseAgent._GUARD_REMAINING_FRACTION == 0.50
        assert BaseAgent._GUARD_KEEP_EDGE_CHARS == 500

    def test_guard_uses_consumed_tokens(self):
        from flavia.agent.base import BaseAgent

        class _DummyAgent(BaseAgent):
            def run(self, user_message: str) -> str:
                return user_message

        agent = object.__new__(_DummyAgent)
        agent.max_context_tokens = 100
        agent.last_prompt_tokens = 60

        result = "X" * 60  # ~15 tokens
        not_truncated = agent._guard_tool_result(result, consumed_tokens=0)
        truncated = agent._guard_tool_result(result, consumed_tokens=15)

        assert "TOOL RESULT TRUNCATED" not in not_truncated
        assert "TOOL RESULT TRUNCATED" in truncated

    def test_process_tool_calls_accounts_for_previous_results(self):
        from flavia.agent.base import BaseAgent

        class _DummyAgent(BaseAgent):
            def run(self, user_message: str) -> str:
                return user_message

        agent = object.__new__(_DummyAgent)
        agent.max_context_tokens = 100
        agent.last_prompt_tokens = 60
        agent.settings = type("SettingsStub", (), {"verbose": False})()
        agent.context = type("ContextStub", (), {"agent_id": "test"})()
        agent._execute_tool = lambda name, args: "A" * 60 if name == "first" else "B" * 60
        agent._handle_spawn_result = lambda result, tool_name, args: result

        tool_calls = [
            _FakeToolCall(id="call-1", function=_FakeFunctionCall(name="first")),
            _FakeToolCall(id="call-2", function=_FakeFunctionCall(name="second")),
        ]
        results = agent._process_tool_calls(tool_calls)

        assert "TOOL RESULT TRUNCATED" not in results[0]["content"]
        assert "TOOL RESULT TRUNCATED" in results[1]["content"]


class TestContextFieldsPropagated:
    """Verify that AgentContext has the new fields."""

    def test_default_values(self):
        ctx = AgentContext()
        assert ctx.max_context_tokens == 128_000
        assert ctx.current_context_tokens == 0

    def test_custom_values(self, tmp_path):
        ctx = _make_context(tmp_path, max_context_tokens=50_000, current_context_tokens=10_000)
        assert ctx.max_context_tokens == 50_000
        assert ctx.current_context_tokens == 10_000


class TestSchemaParameters:
    """Verify the tool schema exposes start_line and end_line."""

    def test_schema_has_partial_read_params(self):
        tool = ReadFileTool()
        schema = tool.get_schema()
        param_names = [p.name for p in schema.parameters]
        assert "path" in param_names
        assert "start_line" in param_names
        assert "end_line" in param_names

    def test_start_line_not_required(self):
        tool = ReadFileTool()
        schema = tool.get_schema()
        for p in schema.parameters:
            if p.name == "start_line":
                assert p.required is False
            if p.name == "end_line":
                assert p.required is False

    def test_description_mentions_partial_reads(self):
        tool = ReadFileTool()
        assert "start_line" in tool.description or "partial" in tool.description.lower()
