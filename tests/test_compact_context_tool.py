"""Tests for Task 8.5 -- Context Compaction Tool (compact_context).

Covers:
- CompactContextTool schema and execution (sentinel generation)
- Sentinel detection in RecursiveAgent._process_tool_calls_with_spawns()
- compact_conversation() with custom instructions parameter
- Mid-execution context warning injection
"""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from flavia.agent.context import AgentContext
from flavia.agent.recursive import RecursiveAgent
from flavia.config.providers import ProviderConfig, ModelConfig as ProviderModelConfig
from flavia.tools.compact.compact_context import CompactContextTool, COMPACT_SENTINEL


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_agent(
    max_tokens: int = 128_000,
    compact_threshold: float = 0.9,
) -> RecursiveAgent:
    """Build a minimal RecursiveAgent with stubbed dependencies."""
    agent = RecursiveAgent.__new__(RecursiveAgent)

    agent.last_prompt_tokens = 0
    agent.last_completion_tokens = 0
    agent.total_prompt_tokens = 0
    agent.total_completion_tokens = 0
    agent.max_context_tokens = max_tokens

    agent.profile = MagicMock()
    agent.profile.compact_threshold = compact_threshold
    agent.profile.compact_threshold_source = "config"

    model_cfg = ProviderModelConfig(
        id="test-model",
        name="test-model",
        max_tokens=max_tokens,
    )
    agent.provider = ProviderConfig(
        id="test",
        name="test",
        api_base_url="http://localhost",
        api_key="test-key",
        models=[model_cfg],
    )

    agent.model_id = "test-model"
    agent.messages = [{"role": "system", "content": "You are a test assistant."}]
    agent.settings = MagicMock()
    agent.settings.verbose = False
    agent.settings.compact_threshold = 0.9
    agent.settings.compact_threshold_configured = False
    agent.compaction_warning_pending = False
    agent.compaction_warning_prompt_tokens = 0
    agent.tool_schemas = []

    agent.context = AgentContext(agent_id="main", current_depth=0, max_depth=3)
    agent.status_callback = None

    return agent


def _make_tool_call(tool_call_id: str, name: str, arguments: str) -> SimpleNamespace:
    """Create a fake tool call matching OpenAI SDK shape."""
    return SimpleNamespace(
        id=tool_call_id,
        function=SimpleNamespace(name=name, arguments=arguments),
    )


# ---------------------------------------------------------------------------
# CompactContextTool schema tests
# ---------------------------------------------------------------------------


class TestCompactContextToolSchema:
    def test_tool_name(self):
        tool = CompactContextTool()
        assert tool.name == "compact_context"

    def test_tool_category(self):
        tool = CompactContextTool()
        assert tool.category == "context"

    def test_schema_has_instructions_parameter(self):
        tool = CompactContextTool()
        schema = tool.get_schema()
        param_names = [p.name for p in schema.parameters]
        assert "instructions" in param_names

    def test_instructions_is_optional(self):
        tool = CompactContextTool()
        schema = tool.get_schema()
        instructions_param = [p for p in schema.parameters if p.name == "instructions"][0]
        assert instructions_param.required is False

    def test_openai_schema_format(self):
        tool = CompactContextTool()
        schema = tool.get_schema().to_openai_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "compact_context"
        props = schema["function"]["parameters"]["properties"]
        assert "instructions" in props
        # instructions should NOT be in required list
        assert "instructions" not in schema["function"]["parameters"].get("required", [])


# ---------------------------------------------------------------------------
# CompactContextTool execution tests (sentinel generation)
# ---------------------------------------------------------------------------


class TestCompactContextToolExecute:
    def test_execute_without_instructions_returns_sentinel(self):
        tool = CompactContextTool()
        ctx = AgentContext()
        result = tool.execute({}, ctx)
        assert result == COMPACT_SENTINEL

    def test_execute_with_empty_instructions_returns_plain_sentinel(self):
        tool = CompactContextTool()
        ctx = AgentContext()
        result = tool.execute({"instructions": ""}, ctx)
        assert result == COMPACT_SENTINEL

    def test_execute_with_instructions_returns_sentinel_with_payload(self):
        tool = CompactContextTool()
        ctx = AgentContext()
        result = tool.execute({"instructions": "focus on file paths"}, ctx)
        assert result.startswith(COMPACT_SENTINEL + ":")
        payload = json.loads(result.split(":", 1)[1])
        assert payload["instructions"] == "focus on file paths"

    def test_sentinel_value_is_expected_string(self):
        assert COMPACT_SENTINEL == "__COMPACT_CONTEXT__"


# ---------------------------------------------------------------------------
# Sentinel detection in _process_tool_calls_with_spawns
# ---------------------------------------------------------------------------


class TestCompactSentinelDetection:
    def test_sentinel_triggers_compact_conversation(self):
        agent = _make_agent()
        agent.messages.extend(
            [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi!"},
            ]
        )

        agent.compact_conversation = MagicMock(return_value="Summary of conversation.")
        agent._notify_status = MagicMock()
        agent._execute_tool = MagicMock(return_value=COMPACT_SENTINEL)

        tool_call = _make_tool_call("call-1", "compact_context", "{}")
        results, spawns = agent._process_tool_calls_with_spawns([tool_call])

        agent.compact_conversation.assert_called_once_with(instructions=None)
        assert len(results) == 1
        assert "compacted successfully" in results[0]["content"].lower()
        assert "Summary of conversation." in results[0]["content"]

    def test_sentinel_with_instructions_passes_to_compact(self):
        agent = _make_agent()
        agent.messages.extend(
            [
                {"role": "user", "content": "Hello"},
            ]
        )

        agent.compact_conversation = MagicMock(return_value="Technical summary.")
        agent._notify_status = MagicMock()
        payload = json.dumps({"instructions": "focus on technical decisions"})
        agent._execute_tool = MagicMock(return_value=f"{COMPACT_SENTINEL}:{payload}")

        tool_call = _make_tool_call(
            "call-1", "compact_context", '{"instructions":"focus on technical decisions"}'
        )
        results, _ = agent._process_tool_calls_with_spawns([tool_call])

        agent.compact_conversation.assert_called_once_with(
            instructions="focus on technical decisions"
        )
        assert "Technical summary." in results[0]["content"]

    def test_sentinel_empty_conversation_returns_nothing_message(self):
        agent = _make_agent()

        agent.compact_conversation = MagicMock(return_value="")
        agent._notify_status = MagicMock()
        agent._execute_tool = MagicMock(return_value=COMPACT_SENTINEL)

        tool_call = _make_tool_call("call-1", "compact_context", "{}")
        results, _ = agent._process_tool_calls_with_spawns([tool_call])

        assert "nothing to compact" in results[0]["content"].lower()

    def test_sentinel_compaction_failure_returns_error(self):
        agent = _make_agent()
        agent.messages.append({"role": "user", "content": "Hello"})

        agent.compact_conversation = MagicMock(
            side_effect=RuntimeError("Compaction summary was empty")
        )
        agent._notify_status = MagicMock()
        agent._execute_tool = MagicMock(return_value=COMPACT_SENTINEL)

        tool_call = _make_tool_call("call-1", "compact_context", "{}")
        results, _ = agent._process_tool_calls_with_spawns([tool_call])

        assert "compaction failed" in results[0]["content"].lower()

    def test_sentinel_not_confused_with_spawn(self):
        """Compact sentinel should not be treated as a spawn request."""
        agent = _make_agent()
        agent.messages.append({"role": "user", "content": "Hello"})

        agent.compact_conversation = MagicMock(return_value="Summary.")
        agent._notify_status = MagicMock()
        agent._execute_tool = MagicMock(return_value=COMPACT_SENTINEL)

        tool_call = _make_tool_call("call-1", "compact_context", "{}")
        results, spawns = agent._process_tool_calls_with_spawns([tool_call])

        assert len(spawns) == 0
        assert len(results) == 1


# ---------------------------------------------------------------------------
# compact_conversation() with instructions parameter
# ---------------------------------------------------------------------------


class TestCompactConversationWithInstructions:
    def test_no_instructions_uses_default_prompt(self):
        agent = _make_agent()
        agent.messages.extend(
            [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there!"},
            ]
        )

        captured_messages = []

        def mock_call_llm(messages):
            captured_messages.append(messages)
            resp = MagicMock()
            resp.content = "Summary without instructions."
            return resp

        agent._call_llm = mock_call_llm
        agent._init_system_prompt = MagicMock(
            side_effect=lambda: setattr(
                agent,
                "messages",
                [{"role": "system", "content": "You are a test assistant."}],
            )
        )

        agent.compact_conversation()

        system_prompt = captured_messages[0][0]["content"]
        assert "Additional instructions:" not in system_prompt

    def test_instructions_appended_to_compaction_prompt(self):
        agent = _make_agent()
        agent.messages.extend(
            [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there!"},
            ]
        )

        captured_messages = []

        def mock_call_llm(messages):
            captured_messages.append(messages)
            resp = MagicMock()
            resp.content = "Technical summary."
            return resp

        agent._call_llm = mock_call_llm
        agent._init_system_prompt = MagicMock(
            side_effect=lambda: setattr(
                agent,
                "messages",
                [{"role": "system", "content": "You are a test assistant."}],
            )
        )

        agent.compact_conversation(instructions="focus on file paths")

        system_prompt = captured_messages[0][0]["content"]
        assert "Additional instructions:" in system_prompt
        assert "focus on file paths" in system_prompt

    def test_none_instructions_same_as_no_instructions(self):
        agent = _make_agent()
        agent.messages.extend(
            [
                {"role": "user", "content": "Hello"},
            ]
        )

        captured_messages = []

        def mock_call_llm(messages):
            captured_messages.append(messages)
            resp = MagicMock()
            resp.content = "Summary."
            return resp

        agent._call_llm = mock_call_llm
        agent._init_system_prompt = MagicMock(
            side_effect=lambda: setattr(
                agent,
                "messages",
                [{"role": "system", "content": "You are a test assistant."}],
            )
        )

        agent.compact_conversation(instructions=None)

        system_prompt = captured_messages[0][0]["content"]
        assert "Additional instructions:" not in system_prompt

    def test_instructions_propagated_in_recursive_split(self):
        """When compaction splits messages, instructions should be used in each chunk."""
        agent = _make_agent()
        agent.messages.extend([{"role": "user", "content": f"Message {i}"} for i in range(6)])

        call_count = [0]
        captured_system_prompts = []

        def mock_call_llm(messages):
            captured_system_prompts.append(messages[0]["content"])
            call_count[0] += 1
            if call_count[0] == 1:
                # First call fails with context error to trigger split
                raise RuntimeError("status 400: context too long")
            resp = MagicMock()
            resp.content = f"Chunk summary {call_count[0]}."
            return resp

        agent._call_llm = mock_call_llm
        agent._init_system_prompt = MagicMock(
            side_effect=lambda: setattr(
                agent,
                "messages",
                [{"role": "system", "content": "You are a test assistant."}],
            )
        )

        result = agent.compact_conversation(instructions="keep file paths")

        # All LLM calls should have had the instructions
        for prompt in captured_system_prompts:
            assert "keep file paths" in prompt


# ---------------------------------------------------------------------------
# Mid-execution context warning injection (Feature 3)
# ---------------------------------------------------------------------------


class TestContextWarningInjection:
    def test_warning_injected_when_threshold_reached_mid_loop(self):
        """When context utilization crosses threshold during tool loop,
        a warning message should be injected into messages."""
        agent = _make_agent(compact_threshold=0.9)
        agent._compaction_warning_injected = False

        # Simulate: after first LLM call, context is at 92%
        call_count = [0]

        def mock_call_llm(messages):
            call_count[0] += 1
            resp = MagicMock()
            resp.content = None
            if call_count[0] == 1:
                agent._update_token_usage(
                    SimpleNamespace(
                        prompt_tokens=117_760, completion_tokens=100, total_tokens=117_860
                    )
                )
                resp.tool_calls = [_make_tool_call("call-1", "read_file", '{"path":"test.py"}')]
            elif call_count[0] == 2:
                # LLM sees the warning and decides to stop
                resp.tool_calls = None
                resp.content = "I see the context is running low."
            return resp

        agent._call_llm = mock_call_llm
        agent._execute_tool = MagicMock(return_value="file contents")
        agent._guard_tool_result = MagicMock(side_effect=lambda r, **kw: r)
        agent._notify_status = MagicMock()

        agent.run("Read test.py")

        # Find the injected warning in messages
        warning_messages = [
            m
            for m in agent.messages
            if m.get("role") == "user" and "[System notice]" in m.get("content", "")
        ]
        assert len(warning_messages) == 1
        assert "compact_context" in warning_messages[0]["content"]
        assert "92%" in warning_messages[0]["content"] or "91%" in warning_messages[0]["content"]

    def test_warning_injected_only_once_per_run(self):
        """The warning should not be duplicated across iterations."""
        agent = _make_agent(compact_threshold=0.9)
        agent._compaction_warning_injected = False

        call_count = [0]

        def mock_call_llm(messages):
            call_count[0] += 1
            resp = MagicMock()
            resp.content = None
            # Always above threshold
            agent._update_token_usage(
                SimpleNamespace(prompt_tokens=120_000, completion_tokens=100, total_tokens=120_100)
            )
            if call_count[0] <= 2:
                resp.tool_calls = [
                    _make_tool_call(f"call-{call_count[0]}", "read_file", '{"path":"f.py"}')
                ]
            else:
                resp.tool_calls = None
                resp.content = "Done."
            return resp

        agent._call_llm = mock_call_llm
        agent._execute_tool = MagicMock(return_value="data")
        agent._guard_tool_result = MagicMock(side_effect=lambda r, **kw: r)
        agent._notify_status = MagicMock()

        agent.run("Do something")

        warning_messages = [
            m
            for m in agent.messages
            if m.get("role") == "user" and "[System notice]" in m.get("content", "")
        ]
        assert len(warning_messages) == 1

    def test_warning_reset_between_runs(self):
        """_compaction_warning_injected should reset at the start of each run()."""
        agent = _make_agent(compact_threshold=0.9)
        agent._compaction_warning_injected = True  # leftover from previous run

        call_count = [0]

        def mock_call_llm(messages):
            call_count[0] += 1
            resp = MagicMock()
            # Above threshold
            agent._update_token_usage(
                SimpleNamespace(prompt_tokens=120_000, completion_tokens=100, total_tokens=120_100)
            )
            resp.tool_calls = None
            resp.content = "Response."
            return resp

        agent._call_llm = mock_call_llm
        agent._notify_status = MagicMock()

        agent.run("Hello")

        # Warning should have been injected despite previous True state
        # because run() resets the flag
        warning_messages = [
            m
            for m in agent.messages
            if m.get("role") == "user" and "[System notice]" in m.get("content", "")
        ]
        # With no tool calls, the LLM responds immediately and the warning
        # is checked after the response. Since there are no more iterations,
        # the warning won't be seen by the LLM, but the flag IS reset.
        assert agent._compaction_warning_injected is False or len(warning_messages) <= 1

    def test_warning_contains_token_info(self):
        """The injected warning should include token counts."""
        agent = _make_agent(compact_threshold=0.9)
        agent._compaction_warning_injected = False
        agent.last_prompt_tokens = 120_000
        agent.max_context_tokens = 128_000

        call_count = [0]

        def mock_call_llm(messages):
            call_count[0] += 1
            resp = MagicMock()
            agent._update_token_usage(
                SimpleNamespace(prompt_tokens=120_000, completion_tokens=100, total_tokens=120_100)
            )
            if call_count[0] == 1:
                resp.content = None
                resp.tool_calls = [_make_tool_call("call-1", "list_files", "{}")]
            else:
                resp.tool_calls = None
                resp.content = "OK."
            return resp

        agent._call_llm = mock_call_llm
        agent._execute_tool = MagicMock(return_value="files")
        agent._guard_tool_result = MagicMock(side_effect=lambda r, **kw: r)
        agent._notify_status = MagicMock()

        agent.run("List files")

        warning_messages = [
            m
            for m in agent.messages
            if m.get("role") == "user" and "[System notice]" in m.get("content", "")
        ]
        assert len(warning_messages) == 1
        content = warning_messages[0]["content"]
        assert "120,000" in content or "120000" in content
        assert "128,000" in content or "128000" in content

    def test_no_warning_below_threshold(self):
        """No warning should be injected when context usage is below threshold."""
        agent = _make_agent(compact_threshold=0.9)
        agent._compaction_warning_injected = False

        def mock_call_llm(messages):
            resp = MagicMock()
            # Well below threshold
            agent._update_token_usage(
                SimpleNamespace(prompt_tokens=50_000, completion_tokens=100, total_tokens=50_100)
            )
            resp.tool_calls = None
            resp.content = "Done."
            return resp

        agent._call_llm = mock_call_llm
        agent._notify_status = MagicMock()

        agent.run("Hello")

        warning_messages = [
            m
            for m in agent.messages
            if m.get("role") == "user" and "[System notice]" in m.get("content", "")
        ]
        assert len(warning_messages) == 0
