"""Tests for Task 8.2 -- Context Compaction with Confirmation.

Covers:
- AgentProfile.compact_threshold field and from_config parsing
- needs_compaction property on BaseAgent
- compact_conversation() method: summary generation, reset, and message injection
- _serialize_messages_for_compaction() helper
- CLI _prompt_compaction() output and flow
- Telegram _build_compaction_warning() output
"""

from io import StringIO
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from flavia.agent.context import AgentContext
from flavia.agent.profile import AgentProfile
from flavia.agent.recursive import RecursiveAgent
from flavia.config.providers import ProviderConfig, ModelConfig as ProviderModelConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_agent(
    max_tokens: int = 128_000,
    compact_threshold: float = 0.9,
    compact_threshold_source: str = "config",
    provider_id: str = "test",
    model_id: str = "test-model",
    provider_compact_threshold: float | None = None,
    model_compact_threshold: float | None = None,
    settings_compact_threshold: float = 0.9,
    settings_compact_threshold_configured: bool = False,
    *,
    with_provider: bool = True,
) -> RecursiveAgent:
    """Build a minimal RecursiveAgent with stubbed dependencies."""
    agent = RecursiveAgent.__new__(RecursiveAgent)

    # Token tracking attributes
    agent.last_prompt_tokens = 0
    agent.last_completion_tokens = 0
    agent.total_prompt_tokens = 0
    agent.total_completion_tokens = 0
    agent.max_context_tokens = max_tokens

    # Profile with compact_threshold
    agent.profile = MagicMock()
    agent.profile.compact_threshold = compact_threshold
    agent.profile.compact_threshold_source = compact_threshold_source

    if with_provider:
        model_cfg = ProviderModelConfig(
            id=model_id,
            name=model_id,
            max_tokens=max_tokens,
            compact_threshold=model_compact_threshold,
        )
        agent.provider = ProviderConfig(
            id=provider_id,
            name=provider_id,
            api_base_url="http://localhost",
            api_key="test-key",
            models=[model_cfg],
            compact_threshold=provider_compact_threshold,
        )
    else:
        agent.provider = None

    agent.model_id = model_id
    agent.messages = [{"role": "system", "content": "You are a test assistant."}]
    agent.settings = MagicMock()
    agent.settings.verbose = False
    agent.settings.compact_threshold = settings_compact_threshold
    agent.settings.compact_threshold_configured = settings_compact_threshold_configured
    agent.compaction_warning_pending = False
    agent.compaction_warning_prompt_tokens = 0
    agent.tool_schemas = []

    # Context for status notifications
    agent.context = AgentContext(agent_id="main", current_depth=0, max_depth=3)
    agent.status_callback = None

    return agent


def _make_usage(prompt_tokens: int = 100, completion_tokens: int = 50) -> SimpleNamespace:
    """Create a fake usage object matching OpenAI SDK shape."""
    return SimpleNamespace(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
    )


# ---------------------------------------------------------------------------
# AgentProfile compact_threshold tests
# ---------------------------------------------------------------------------


class TestAgentProfileCompactThreshold:
    def test_default_value(self):
        profile = AgentProfile(context="test")
        assert profile.compact_threshold == 0.9

    def test_custom_value(self):
        profile = AgentProfile(context="test", compact_threshold=0.75)
        assert profile.compact_threshold == 0.75

    def test_from_config_default(self):
        config = {"context": "test agent"}
        profile = AgentProfile.from_config(config)
        assert profile.compact_threshold == 0.9

    def test_from_config_custom(self):
        config = {"context": "test agent", "compact_threshold": 0.8}
        profile = AgentProfile.from_config(config)
        assert profile.compact_threshold == 0.8

    def test_from_config_inherits_from_parent(self):
        parent = AgentProfile(context="parent", compact_threshold=0.7)
        config = {"context": "child"}
        profile = AgentProfile.from_config(config, parent=parent)
        assert profile.compact_threshold == 0.7

    def test_from_config_overrides_parent(self):
        parent = AgentProfile(context="parent", compact_threshold=0.7)
        config = {"context": "child", "compact_threshold": 0.85}
        profile = AgentProfile.from_config(config, parent=parent)
        assert profile.compact_threshold == 0.85

    def test_to_dict_includes_compact_threshold(self):
        profile = AgentProfile(context="test", compact_threshold=0.75)
        d = profile.to_dict()
        assert d["compact_threshold"] == 0.75

    def test_from_config_string_value(self):
        """compact_threshold should accept string values (from YAML)."""
        config = {"context": "test", "compact_threshold": "0.85"}
        profile = AgentProfile.from_config(config)
        assert profile.compact_threshold == 0.85

    def test_from_config_rejects_out_of_range(self):
        with pytest.raises(ValueError, match="compact_threshold"):
            AgentProfile.from_config({"context": "test", "compact_threshold": 1.5})

    def test_from_config_rejects_invalid_type(self):
        with pytest.raises(ValueError, match="compact_threshold"):
            AgentProfile.from_config({"context": "test", "compact_threshold": "abc"})


# ---------------------------------------------------------------------------
# needs_compaction property tests
# ---------------------------------------------------------------------------


class TestNeedsCompaction:
    def test_false_when_below_threshold(self):
        agent = _make_agent(max_tokens=100_000, compact_threshold=0.9)
        agent._update_token_usage(_make_usage(prompt_tokens=50_000))
        assert agent.needs_compaction is False

    def test_true_when_at_threshold(self):
        agent = _make_agent(max_tokens=100_000, compact_threshold=0.9)
        agent._update_token_usage(_make_usage(prompt_tokens=90_000))
        assert agent.needs_compaction is True

    def test_true_when_above_threshold(self):
        agent = _make_agent(max_tokens=100_000, compact_threshold=0.9)
        agent._update_token_usage(_make_usage(prompt_tokens=95_000))
        assert agent.needs_compaction is True

    def test_false_when_no_usage(self):
        agent = _make_agent(max_tokens=100_000, compact_threshold=0.9)
        assert agent.needs_compaction is False

    def test_custom_threshold(self):
        agent = _make_agent(max_tokens=100_000, compact_threshold=0.5)
        agent._update_token_usage(_make_usage(prompt_tokens=50_000))
        assert agent.needs_compaction is True

    def test_threshold_zero_always_triggers(self):
        agent = _make_agent(max_tokens=100_000, compact_threshold=0.0)
        assert agent.needs_compaction is True

    def test_threshold_one_never_triggers_below(self):
        agent = _make_agent(max_tokens=100_000, compact_threshold=1.0)
        agent._update_token_usage(_make_usage(prompt_tokens=99_999))
        assert agent.needs_compaction is False


class TestCompactionSignalInRun:
    def test_warning_pending_when_any_llm_call_crosses_threshold(self):
        agent = _make_agent(max_tokens=100_000, compact_threshold=0.9)

        first_response = SimpleNamespace(content="", tool_calls=[object()])
        final_response = SimpleNamespace(content="final", tool_calls=None)

        calls = {"n": 0}

        def fake_call_llm(_messages):
            calls["n"] += 1
            if calls["n"] == 1:
                agent.last_prompt_tokens = 92_000
                return first_response
            agent.last_prompt_tokens = 10_000
            return final_response

        agent._call_llm = MagicMock(side_effect=fake_call_llm)
        agent._assistant_message_to_dict = MagicMock(
            return_value={"role": "assistant", "content": ""}
        )
        agent._process_tool_calls_with_spawns = MagicMock(return_value=([], []))

        result = agent.run("Hello")

        assert result == "final"
        assert agent.compaction_warning_pending is True
        assert agent.compaction_warning_prompt_tokens == 92_000


# ---------------------------------------------------------------------------
# _serialize_messages_for_compaction tests
# ---------------------------------------------------------------------------


class TestSerializeMessagesForCompaction:
    def test_user_message(self):
        messages = [{"role": "user", "content": "Hello"}]
        result = RecursiveAgent._serialize_messages_for_compaction(messages)
        assert result == "User: Hello"

    def test_assistant_message(self):
        messages = [{"role": "assistant", "content": "Hi there!"}]
        result = RecursiveAgent._serialize_messages_for_compaction(messages)
        assert result == "Assistant: Hi there!"

    def test_tool_call_message(self):
        messages = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_123",
                        "function": {"name": "read_file", "arguments": '{"path": "test.txt"}'},
                    }
                ],
            }
        ]
        result = RecursiveAgent._serialize_messages_for_compaction(messages)
        assert "read_file" in result
        assert "test.txt" in result

    def test_tool_result_message(self):
        messages = [{"role": "tool", "tool_call_id": "call_123", "content": "file contents here"}]
        result = RecursiveAgent._serialize_messages_for_compaction(messages)
        assert "Tool result (call_123):" in result
        assert "file contents here" in result

    def test_multi_message_conversation(self):
        messages = [
            {"role": "user", "content": "Read the file"},
            {"role": "assistant", "content": "I'll read the file for you."},
            {"role": "user", "content": "Thanks!"},
        ]
        result = RecursiveAgent._serialize_messages_for_compaction(messages)
        lines = result.split("\n")
        assert len(lines) == 3
        assert lines[0] == "User: Read the file"
        assert lines[1] == "Assistant: I'll read the file for you."
        assert lines[2] == "User: Thanks!"

    def test_empty_messages(self):
        result = RecursiveAgent._serialize_messages_for_compaction([])
        assert result == ""


# ---------------------------------------------------------------------------
# compact_conversation() tests
# ---------------------------------------------------------------------------


class TestCompactConversation:
    def test_empty_conversation_returns_empty(self):
        agent = _make_agent()
        # Only system prompt, no conversation
        result = agent.compact_conversation()
        assert result == ""

    def test_compaction_calls_llm_and_resets(self):
        agent = _make_agent()
        agent.messages.append({"role": "user", "content": "Hello"})
        agent.messages.append({"role": "assistant", "content": "Hi!"})

        # Mock _call_llm to return a summary
        mock_response = MagicMock()
        mock_response.content = "Summary: User greeted assistant."
        agent._call_llm = MagicMock(return_value=mock_response)

        # Mock _init_system_prompt for reset
        agent._init_system_prompt = MagicMock(
            side_effect=lambda: setattr(
                agent,
                "messages",
                [{"role": "system", "content": "You are a test assistant."}],
            )
        )

        summary = agent.compact_conversation()

        assert summary == "Summary: User greeted assistant."
        # Verify _call_llm was called with compaction messages
        agent._call_llm.assert_called_once()
        call_messages = agent._call_llm.call_args[0][0]
        assert call_messages[0]["role"] == "system"
        assert "summarizing a conversation" in call_messages[0]["content"].lower()
        assert call_messages[1]["role"] == "user"

    def test_compaction_injects_summary_messages(self):
        agent = _make_agent()
        agent.messages.append({"role": "user", "content": "Hello"})
        agent.messages.append({"role": "assistant", "content": "Hi!"})

        mock_response = MagicMock()
        mock_response.content = "Summary: User greeted assistant."
        agent._call_llm = MagicMock(return_value=mock_response)
        agent._init_system_prompt = MagicMock(
            side_effect=lambda: setattr(
                agent,
                "messages",
                [{"role": "system", "content": "You are a test assistant."}],
            )
        )

        agent.compact_conversation()

        # After compaction: system prompt + summary user msg + ack assistant msg
        assert len(agent.messages) == 3
        assert agent.messages[0]["role"] == "system"
        assert agent.messages[1]["role"] == "user"
        assert "[Conversation summary from compaction]" in agent.messages[1]["content"]
        assert "Summary: User greeted assistant." in agent.messages[1]["content"]
        assert agent.messages[2]["role"] == "assistant"
        assert "context from our previous conversation" in agent.messages[2]["content"]

    def test_compaction_estimates_non_zero_context_after_injection(self):
        agent = _make_agent()
        agent.messages.append({"role": "user", "content": "Hello"})
        agent.messages.append({"role": "assistant", "content": "Hi!"})

        mock_response = MagicMock()
        mock_response.content = "Summary: User greeted assistant."
        agent._call_llm = MagicMock(return_value=mock_response)
        agent._init_system_prompt = MagicMock(
            side_effect=lambda: setattr(
                agent,
                "messages",
                [{"role": "system", "content": "You are a test assistant."}],
            )
        )

        agent.compact_conversation()

        assert agent.last_prompt_tokens > 0
        assert agent.context_utilization > 0

    def test_compaction_resets_token_counters(self):
        agent = _make_agent()
        agent.messages.append({"role": "user", "content": "Hello"})
        agent._update_token_usage(_make_usage(50_000, 1000))

        mock_response = MagicMock()
        mock_response.content = "Summary."
        agent._call_llm = MagicMock(return_value=mock_response)
        agent._init_system_prompt = MagicMock(
            side_effect=lambda: setattr(
                agent,
                "messages",
                [{"role": "system", "content": "You are a test assistant."}],
            )
        )

        agent.compact_conversation()

        # Token counters from the compaction LLM call itself are the current state.
        # The reset() call zeros cumulative totals. The compaction _call_llm updates
        # last_* via _update_token_usage (called by the real _call_llm).
        # Since we mocked _call_llm, reset() zeros were set, and our mock doesn't
        # call _update_token_usage, so totals should be 0.
        assert agent.total_prompt_tokens == 0
        assert agent.total_completion_tokens == 0

    def test_compaction_disables_tools_during_call(self):
        agent = _make_agent()
        agent.tool_schemas = [{"type": "function", "function": {"name": "test_tool"}}]
        agent.messages.append({"role": "user", "content": "Hello"})

        captured_schemas = []

        def mock_call_llm(messages):
            captured_schemas.append(agent.tool_schemas.copy())
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

        agent.compact_conversation()

        # During the LLM call, tool_schemas should have been empty
        assert captured_schemas == [[]]
        # After compaction, tool_schemas should be restored
        assert len(agent.tool_schemas) == 1
        assert agent.tool_schemas[0]["function"]["name"] == "test_tool"

    def test_compaction_empty_summary_raises_without_resetting_messages(self):
        agent = _make_agent()
        original_messages = [
            {"role": "system", "content": "You are a test assistant."},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi!"},
        ]
        agent.messages = list(original_messages)

        mock_response = MagicMock()
        mock_response.content = "   "
        agent._call_llm = MagicMock(return_value=mock_response)

        with pytest.raises(RuntimeError, match="summary was empty"):
            agent.compact_conversation()

        # Conversation history is preserved when compaction fails.
        assert agent.messages == original_messages

    def test_compaction_falls_back_to_chunked_summary_on_context_error(self):
        agent = _make_agent()
        agent.messages.extend(
            [
                {"role": "user", "content": "u1"},
                {"role": "assistant", "content": "a1"},
                {"role": "user", "content": "u2"},
                {"role": "assistant", "content": "a2"},
            ]
        )

        call_count = {"n": 0}

        def mock_call_llm(_messages):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("API error (status 400): maximum context length exceeded")
            response = MagicMock()
            if call_count["n"] == 2:
                response.content = "Left summary"
            elif call_count["n"] == 3:
                response.content = "Right summary"
            else:
                response.content = "Merged summary"
            return response

        agent._call_llm = MagicMock(side_effect=mock_call_llm)
        agent._init_system_prompt = MagicMock(
            side_effect=lambda: setattr(
                agent,
                "messages",
                [{"role": "system", "content": "You are a test assistant."}],
            )
        )

        summary = agent.compact_conversation()

        assert summary == "Merged summary"
        assert call_count["n"] == 4
        assert len(agent.messages) == 3

    def test_compaction_does_not_retry_non_retryable_error(self):
        agent = _make_agent()
        agent.messages.append({"role": "user", "content": "hello"})
        agent._call_llm = MagicMock(side_effect=RuntimeError("Authentication failed"))

        with pytest.raises(RuntimeError, match="Authentication failed"):
            agent.compact_conversation()

        agent._call_llm.assert_called_once()


class TestResolveCompactThreshold:
    def test_profile_config_threshold_has_highest_priority(self):
        agent = _make_agent(
            compact_threshold=0.77,
            compact_threshold_source="config",
            provider_compact_threshold=0.55,
            model_compact_threshold=0.44,
            settings_compact_threshold=0.33,
            settings_compact_threshold_configured=True,
        )

        threshold, source = agent._resolve_compact_threshold()
        assert threshold == pytest.approx(0.77)
        assert source == "config"

    def test_model_threshold_overrides_provider_and_settings_when_profile_default(self):
        agent = _make_agent(
            compact_threshold=0.9,
            compact_threshold_source="default",
            provider_compact_threshold=0.6,
            model_compact_threshold=0.5,
            settings_compact_threshold=0.4,
            settings_compact_threshold_configured=True,
        )

        threshold, source = agent._resolve_compact_threshold()
        assert threshold == pytest.approx(0.5)
        assert source == "provider-model"

    def test_provider_threshold_overrides_settings_when_profile_default(self):
        agent = _make_agent(
            compact_threshold=0.9,
            compact_threshold_source="default",
            provider_compact_threshold=0.65,
            model_compact_threshold=None,
            settings_compact_threshold=0.4,
            settings_compact_threshold_configured=True,
        )

        threshold, source = agent._resolve_compact_threshold()
        assert threshold == pytest.approx(0.65)
        assert source == "provider"

    def test_settings_threshold_used_when_no_provider_defaults(self):
        agent = _make_agent(
            compact_threshold=0.9,
            compact_threshold_source="default",
            provider_compact_threshold=None,
            model_compact_threshold=None,
            settings_compact_threshold=0.42,
            settings_compact_threshold_configured=True,
        )

        threshold, source = agent._resolve_compact_threshold()
        assert threshold == pytest.approx(0.42)
        assert source == "settings"


# ---------------------------------------------------------------------------
# CLI _prompt_compaction tests
# ---------------------------------------------------------------------------


class TestCliPromptCompaction:
    def test_no_prompt_when_below_threshold(self):
        from flavia.interfaces.cli_interface import _prompt_compaction

        agent = _make_agent(max_tokens=100_000, compact_threshold=0.9)
        agent._update_token_usage(_make_usage(prompt_tokens=50_000))

        result = _prompt_compaction(agent)
        assert result is False

    def test_prompt_shown_when_above_threshold(self):
        from flavia.interfaces.cli_interface import _prompt_compaction
        from rich.console import Console

        agent = _make_agent(max_tokens=100_000, compact_threshold=0.9)
        agent._update_token_usage(_make_usage(prompt_tokens=92_000))

        buf = StringIO()
        test_console = Console(file=buf, no_color=True, width=200)

        import flavia.interfaces.cli_interface as cli_mod

        original_console = cli_mod.console
        cli_mod.console = test_console
        try:
            # User declines compaction
            with patch("builtins.input", return_value="n"):
                result = _prompt_compaction(agent)
        finally:
            cli_mod.console = original_console

        output = buf.getvalue()
        assert "92%" in output
        assert "Compact conversation?" in output
        assert result is False

    def test_compaction_triggered_on_yes(self):
        from flavia.interfaces.cli_interface import _prompt_compaction
        from rich.console import Console

        agent = _make_agent(max_tokens=100_000, compact_threshold=0.9)
        agent._update_token_usage(_make_usage(prompt_tokens=92_000))

        # Mock compact_conversation
        agent.compact_conversation = MagicMock(return_value="Summary text")

        buf = StringIO()
        test_console = Console(file=buf, no_color=True, width=200)

        import flavia.interfaces.cli_interface as cli_mod

        original_console = cli_mod.console
        cli_mod.console = test_console
        try:
            with patch("builtins.input", return_value="y"):
                result = _prompt_compaction(agent)
        finally:
            cli_mod.console = original_console

        assert result is True
        agent.compact_conversation.assert_called_once()
        output = buf.getvalue()
        assert "Compacting conversation" in output
        assert "compacted" in output.lower()
        assert "Summary:" in output
        assert "Summary text" in output

    def test_compaction_not_triggered_on_empty_input(self):
        from flavia.interfaces.cli_interface import _prompt_compaction
        from rich.console import Console

        agent = _make_agent(max_tokens=100_000, compact_threshold=0.9)
        agent._update_token_usage(_make_usage(prompt_tokens=92_000))

        buf = StringIO()
        test_console = Console(file=buf, no_color=True, width=200)

        import flavia.interfaces.cli_interface as cli_mod

        original_console = cli_mod.console
        cli_mod.console = test_console
        try:
            with patch("builtins.input", return_value=""):
                result = _prompt_compaction(agent)
        finally:
            cli_mod.console = original_console

        assert result is False

    def test_prompt_shown_when_warning_pending_even_if_last_usage_is_low(self):
        from flavia.interfaces.cli_interface import _prompt_compaction
        from rich.console import Console

        agent = _make_agent(max_tokens=100_000, compact_threshold=0.9)
        agent._update_token_usage(_make_usage(prompt_tokens=10_000))
        agent.compaction_warning_pending = True
        agent.compaction_warning_prompt_tokens = 92_000

        buf = StringIO()
        test_console = Console(file=buf, no_color=True, width=200)

        import flavia.interfaces.cli_interface as cli_mod

        original_console = cli_mod.console
        cli_mod.console = test_console
        try:
            with patch("builtins.input", return_value="n"):
                result = _prompt_compaction(agent)
        finally:
            cli_mod.console = original_console

        assert result is False
        output = buf.getvalue()
        assert "92%" in output


# ---------------------------------------------------------------------------
# Telegram _build_compaction_warning tests
# ---------------------------------------------------------------------------


class TestTelegramCompactionWarning:
    def test_no_warning_below_threshold(self):
        from flavia.interfaces.telegram_interface import _build_compaction_warning

        agent = _make_agent(max_tokens=100_000, compact_threshold=0.9)
        agent._update_token_usage(_make_usage(prompt_tokens=50_000))

        warning = _build_compaction_warning(agent)
        assert warning == ""

    def test_warning_above_threshold(self):
        from flavia.interfaces.telegram_interface import _build_compaction_warning

        agent = _make_agent(max_tokens=100_000, compact_threshold=0.9)
        agent._update_token_usage(_make_usage(prompt_tokens=92_000))

        warning = _build_compaction_warning(agent)
        assert "\u26a0" in warning  # ⚠ emoji
        assert "92%" in warning
        assert "/compact" in warning

    def test_warning_at_exact_threshold(self):
        from flavia.interfaces.telegram_interface import _build_compaction_warning

        agent = _make_agent(max_tokens=100_000, compact_threshold=0.9)
        agent._update_token_usage(_make_usage(prompt_tokens=90_000))

        warning = _build_compaction_warning(agent)
        assert warning != ""
        assert "90%" in warning

    def test_warning_when_pending_even_if_current_usage_is_low(self):
        from flavia.interfaces.telegram_interface import _build_compaction_warning

        agent = _make_agent(max_tokens=100_000, compact_threshold=0.9)
        agent._update_token_usage(_make_usage(prompt_tokens=5_000))
        agent.compaction_warning_pending = True
        agent.compaction_warning_prompt_tokens = 92_000

        warning = _build_compaction_warning(agent)
        assert warning != ""
        assert "92%" in warning
