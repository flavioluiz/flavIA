"""Tests for Task 8.1 -- Token Usage Tracking & Display.

Covers:
- Token counter initialization and accumulation in BaseAgent
- _update_token_usage() with valid, None, and partial usage objects
- reset() clearing all token counters
- context_utilization property
- max_context_tokens resolution from provider model config and fallback
- CLI _display_token_usage() output format and color coding
- Telegram _build_token_footer() output format
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from flavia.agent.recursive import RecursiveAgent
from flavia.config.providers import ProviderConfig, ModelConfig as ProviderModelConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_agent(
    max_tokens: int = 128_000,
    provider_id: str = "test",
    model_id: str = "test-model",
    *,
    with_provider: bool = True,
) -> RecursiveAgent:
    """Build a minimal RecursiveAgent with stubbed dependencies."""
    agent = RecursiveAgent.__new__(RecursiveAgent)

    # Token tracking attributes (mimicking __init__)
    agent.last_prompt_tokens = 0
    agent.last_completion_tokens = 0
    agent.total_prompt_tokens = 0
    agent.total_completion_tokens = 0
    agent.max_context_tokens = max_tokens

    if with_provider:
        model_cfg = ProviderModelConfig(id=model_id, name=model_id, max_tokens=max_tokens)
        agent.provider = ProviderConfig(
            id=provider_id,
            name=provider_id,
            api_base_url="http://localhost",
            api_key="test-key",
            models=[model_cfg],
        )
    else:
        agent.provider = None

    agent.model_id = model_id
    agent.messages = []
    agent.settings = MagicMock()
    agent.settings.verbose = False
    return agent


def _make_usage(prompt_tokens: int = 100, completion_tokens: int = 50) -> SimpleNamespace:
    """Create a fake usage object matching OpenAI SDK shape."""
    return SimpleNamespace(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
    )


# ---------------------------------------------------------------------------
# BaseAgent token counter tests
# ---------------------------------------------------------------------------


class TestTokenCounterInitialization:
    def test_counters_start_at_zero(self):
        agent = _make_agent()
        assert agent.last_prompt_tokens == 0
        assert agent.last_completion_tokens == 0
        assert agent.total_prompt_tokens == 0
        assert agent.total_completion_tokens == 0

    def test_max_context_tokens_set(self):
        agent = _make_agent(max_tokens=200_000)
        assert agent.max_context_tokens == 200_000


class TestUpdateTokenUsage:
    def test_updates_last_and_cumulative(self):
        agent = _make_agent()
        usage = _make_usage(prompt_tokens=1000, completion_tokens=200)
        agent._update_token_usage(usage)

        assert agent.last_prompt_tokens == 1000
        assert agent.last_completion_tokens == 200
        assert agent.total_prompt_tokens == 1000
        assert agent.total_completion_tokens == 200

    def test_cumulative_across_multiple_calls(self):
        agent = _make_agent()
        agent._update_token_usage(_make_usage(1000, 200))
        agent._update_token_usage(_make_usage(1500, 300))

        assert agent.last_prompt_tokens == 1500
        assert agent.last_completion_tokens == 300
        assert agent.total_prompt_tokens == 2500
        assert agent.total_completion_tokens == 500

    def test_none_usage_is_safe(self):
        agent = _make_agent()
        agent._update_token_usage(None)

        assert agent.last_prompt_tokens == 0
        assert agent.last_completion_tokens == 0
        assert agent.total_prompt_tokens == 0
        assert agent.total_completion_tokens == 0

    def test_none_usage_resets_last_but_keeps_totals(self):
        agent = _make_agent()
        agent._update_token_usage(_make_usage(400, 80))
        agent._update_token_usage(None)

        assert agent.last_prompt_tokens == 0
        assert agent.last_completion_tokens == 0
        assert agent.total_prompt_tokens == 400
        assert agent.total_completion_tokens == 80

    def test_dict_usage_object_is_supported(self):
        agent = _make_agent()
        usage = {"prompt_tokens": 700, "completion_tokens": 150}
        agent._update_token_usage(usage)

        assert agent.last_prompt_tokens == 700
        assert agent.last_completion_tokens == 150
        assert agent.total_prompt_tokens == 700
        assert agent.total_completion_tokens == 150

    def test_partial_usage_missing_fields(self):
        """Provider returns usage without some fields."""
        agent = _make_agent()
        usage = SimpleNamespace(prompt_tokens=500)  # no completion_tokens
        agent._update_token_usage(usage)

        assert agent.last_prompt_tokens == 500
        assert agent.last_completion_tokens == 0

    def test_none_field_values_treated_as_zero(self):
        """Some providers return None instead of 0."""
        agent = _make_agent()
        usage = SimpleNamespace(prompt_tokens=None, completion_tokens=None)
        agent._update_token_usage(usage)

        assert agent.last_prompt_tokens == 0
        assert agent.last_completion_tokens == 0


class TestReset:
    def test_reset_clears_token_counters(self):
        agent = _make_agent()
        agent._update_token_usage(_make_usage(5000, 1000))

        # Stub _init_system_prompt to avoid needing full context
        agent._init_system_prompt = MagicMock()
        agent.reset()

        assert agent.last_prompt_tokens == 0
        assert agent.last_completion_tokens == 0
        assert agent.total_prompt_tokens == 0
        assert agent.total_completion_tokens == 0


class TestContextUtilization:
    def test_zero_when_no_calls_made(self):
        agent = _make_agent(max_tokens=128_000)
        assert agent.context_utilization == 0.0

    def test_correct_ratio(self):
        agent = _make_agent(max_tokens=100_000)
        agent._update_token_usage(_make_usage(prompt_tokens=50_000, completion_tokens=100))
        assert agent.context_utilization == pytest.approx(0.5)

    def test_high_utilization(self):
        agent = _make_agent(max_tokens=100_000)
        agent._update_token_usage(_make_usage(prompt_tokens=95_000, completion_tokens=100))
        assert agent.context_utilization == pytest.approx(0.95)

    def test_zero_max_context_tokens(self):
        agent = _make_agent(max_tokens=0)
        agent._update_token_usage(_make_usage(prompt_tokens=1000, completion_tokens=100))
        assert agent.context_utilization == 0.0


class TestResolveMaxContextTokens:
    def test_from_provider_model_config(self):
        agent = _make_agent(max_tokens=200_000)
        # Directly test the resolver
        result = agent._resolve_max_context_tokens()
        assert result == 200_000

    def test_fallback_when_no_provider(self):
        agent = _make_agent(with_provider=False)
        result = agent._resolve_max_context_tokens()
        assert result == 128_000

    def test_fallback_when_model_not_found(self):
        agent = _make_agent()
        agent.model_id = "nonexistent-model"
        result = agent._resolve_max_context_tokens()
        assert result == 128_000


# ---------------------------------------------------------------------------
# CLI display tests
# ---------------------------------------------------------------------------


class TestCliTokenDisplay:
    def test_green_color_under_70_percent(self):
        from flavia.interfaces.cli_interface import _display_token_usage
        from io import StringIO
        from rich.console import Console

        agent = _make_agent(max_tokens=128_000)
        agent._update_token_usage(_make_usage(prompt_tokens=12_450, completion_tokens=850))

        buf = StringIO()
        test_console = Console(file=buf, no_color=True, width=200)

        # Temporarily replace module-level console
        import flavia.interfaces.cli_interface as cli_mod

        original_console = cli_mod.console
        cli_mod.console = test_console
        try:
            _display_token_usage(agent)
        finally:
            cli_mod.console = original_console

        output = buf.getvalue()
        assert "12,450" in output
        assert "128,000" in output
        assert "9.7%" in output
        assert "850" in output

    def test_yellow_color_at_75_percent(self):
        from flavia.interfaces.cli_interface import _display_token_usage
        from io import StringIO
        from rich.console import Console

        agent = _make_agent(max_tokens=100_000)
        agent._update_token_usage(_make_usage(prompt_tokens=75_000, completion_tokens=500))

        buf = StringIO()
        test_console = Console(file=buf, no_color=True, width=200)

        import flavia.interfaces.cli_interface as cli_mod

        original_console = cli_mod.console
        cli_mod.console = test_console
        try:
            _display_token_usage(agent)
        finally:
            cli_mod.console = original_console

        output = buf.getvalue()
        assert "75,000" in output
        assert "75.0%" in output

    def test_red_color_at_90_percent(self):
        from flavia.interfaces.cli_interface import _display_token_usage
        from io import StringIO
        from rich.console import Console

        agent = _make_agent(max_tokens=100_000)
        agent._update_token_usage(_make_usage(prompt_tokens=95_000, completion_tokens=500))

        buf = StringIO()
        test_console = Console(file=buf, no_color=True, width=200)

        import flavia.interfaces.cli_interface as cli_mod

        original_console = cli_mod.console
        cli_mod.console = test_console
        try:
            _display_token_usage(agent)
        finally:
            cli_mod.console = original_console

        output = buf.getvalue()
        assert "95,000" in output
        assert "95.0%" in output

    def test_respects_show_token_usage_setting(self):
        from flavia.interfaces.cli_interface import _display_token_usage
        from io import StringIO
        from rich.console import Console

        agent = _make_agent(max_tokens=100_000)
        agent.settings.show_token_usage = False
        agent._update_token_usage(_make_usage(prompt_tokens=20_000, completion_tokens=300))

        buf = StringIO()
        test_console = Console(file=buf, no_color=True, width=200)

        import flavia.interfaces.cli_interface as cli_mod

        original_console = cli_mod.console
        cli_mod.console = test_console
        try:
            _display_token_usage(agent)
        finally:
            cli_mod.console = original_console

        assert buf.getvalue() == ""


# ---------------------------------------------------------------------------
# Telegram footer tests
# ---------------------------------------------------------------------------


class TestTelegramTokenFooter:
    def test_footer_format(self):
        from flavia.interfaces.telegram_interface import _build_token_footer

        agent = _make_agent(max_tokens=128_000)
        agent._update_token_usage(_make_usage(prompt_tokens=12_450, completion_tokens=850))

        footer = _build_token_footer(agent)
        assert "\U0001f4ca" in footer  # 📊 emoji
        assert "12,450" in footer
        assert "128,000" in footer
        assert "9.7%" in footer

    def test_footer_starts_with_newlines(self):
        from flavia.interfaces.telegram_interface import _build_token_footer

        agent = _make_agent(max_tokens=100_000)
        agent._update_token_usage(_make_usage(prompt_tokens=1000, completion_tokens=100))

        footer = _build_token_footer(agent)
        assert footer.startswith("\n\n")

    def test_footer_zero_usage(self):
        from flavia.interfaces.telegram_interface import _build_token_footer

        agent = _make_agent(max_tokens=128_000)
        footer = _build_token_footer(agent)
        assert "0/128,000" in footer
        assert "0.0%" in footer
