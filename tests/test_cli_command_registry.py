"""Tests for CLI command registry and help system."""

import json
from unittest.mock import MagicMock

import pytest

from flavia.config.providers import ModelConfig, ProviderConfig, ProviderRegistry
from flavia.config.settings import Settings
from flavia.interfaces.commands import (
    COMMAND_REGISTRY,
    CommandContext,
    CommandMetadata,
    dispatch_command,
    get_command,
    get_command_help,
    get_help_listing,
    list_commands,
    register_command,
)


class _DummyConsole:
    """Fake console for capturing output."""

    def __init__(self):
        self.printed = []

    def print(self, *args, **kwargs):
        self.printed.append(" ".join(str(a) for a in args))


class _DummyAgent:
    """Fake agent for testing."""

    provider = None
    model_id = "test-model"


def _make_test_context(settings=None, agent=None, console=None):
    """Create a CommandContext for testing."""
    from pathlib import Path

    return CommandContext(
        settings=settings or Settings(base_dir=Path("/tmp")),
        agent=agent or _DummyAgent(),
        console=console or _DummyConsole(),
        history_file=Path("/tmp/.prompt_history"),
        chat_log_file=Path("/tmp/chat_history.jsonl"),
        history_enabled=False,
        create_agent=lambda s, m=None: _DummyAgent(),
    )


def _make_provider_settings(
    provider_id: str = "openai",
    api_key: str = "test-key",
    api_key_env_var: str | None = None,
    with_model: bool = True,
) -> Settings:
    models = [ModelConfig(id="gpt-4o", name="GPT-4o", default=True)] if with_model else []
    provider = ProviderConfig(
        id=provider_id,
        name=provider_id.title(),
        api_base_url=f"https://{provider_id}.example/v1",
        api_key=api_key,
        api_key_env_var=api_key_env_var,
        models=models,
    )
    return Settings(
        providers=ProviderRegistry(
            providers={provider_id: provider},
            default_provider_id=provider_id,
        )
    )


# =============================================================================
# Command Registry Tests
# =============================================================================


def test_command_registry_contains_expected_commands():
    """Verify all expected commands are registered."""
    expected = {
        "/quit",
        "/exit",
        "/q",
        "/reset",
        "/help",
        "/agent_setup",
        "/agent",
        "/model",
        "/providers",
        "/tools",
        "/citations",
        "/config",
        "/catalog",
        "/provider-setup",
        "/provider-manage",
        "/provider-test",
        "/compact",
        "/settings",
        "/rag-debug",
        "/index",
        "/index-build",
        "/index-update",
        "/index-stats",
        "/index-diagnose",
    }
    registered = set(COMMAND_REGISTRY.keys())
    assert expected.issubset(registered), f"Missing: {expected - registered}"


def test_command_aliases_point_to_same_handler():
    """Verify /quit, /exit, /q all point to the same handler."""
    quit_meta = COMMAND_REGISTRY.get("/quit")
    exit_meta = COMMAND_REGISTRY.get("/exit")
    q_meta = COMMAND_REGISTRY.get("/q")

    assert quit_meta is not None
    assert exit_meta is not None
    assert q_meta is not None

    # They should all be the same object (aliases)
    assert quit_meta is exit_meta
    assert exit_meta is q_meta


def test_get_command_finds_registered_command():
    """Test get_command returns metadata for registered commands."""
    metadata, cmd_name, args = get_command("/help")

    assert metadata is not None
    assert cmd_name == "/help"
    assert args == ""


def test_get_command_extracts_arguments():
    """Test get_command correctly extracts command arguments."""
    metadata, cmd_name, args = get_command("/model gpt-4o")

    assert metadata is not None
    assert cmd_name == "/model"
    assert args == "gpt-4o"


def test_get_command_returns_none_for_unknown():
    """Test get_command returns None for unknown commands."""
    metadata, cmd_name, args = get_command("/unknown_command")

    assert metadata is None
    assert cmd_name == "/unknown_command"


def test_get_command_rejects_args_for_no_arg_command():
    """Commands that do not accept args should reject trailing input."""
    metadata, cmd_name, args = get_command("/quit now")

    assert metadata is None
    assert cmd_name == "/quit"
    assert args == "now"


def test_list_commands_returns_primary_names_only():
    """Verify list_commands excludes aliases."""
    commands = list_commands()

    # Should include /quit but not /exit or /q (they're aliases)
    assert "/quit" in commands
    assert "/exit" not in commands
    assert "/q" not in commands

    # Should include other primary commands
    assert "/help" in commands
    assert "/model" in commands
    assert "/agent" in commands
    assert "/compact" in commands


# =============================================================================
# Dispatch Tests
# =============================================================================


def test_dispatch_command_calls_handler():
    """Test dispatch_command invokes the correct handler."""
    console = _DummyConsole()
    ctx = _make_test_context(console=console)

    # /help should print something and return True (continue)
    result = dispatch_command(ctx, "/help")

    assert result is True
    assert len(console.printed) > 0


def test_dispatch_command_handles_unknown_command():
    """Test dispatch_command handles unknown commands gracefully."""
    console = _DummyConsole()
    ctx = _make_test_context(console=console)

    result = dispatch_command(ctx, "/not_a_real_command")

    assert result is True  # Should continue loop
    assert any("Unknown command" in line for line in console.printed)


def test_dispatch_quit_returns_false():
    """Test /quit command returns False to exit loop."""
    console = _DummyConsole()
    ctx = _make_test_context(console=console)

    result = dispatch_command(ctx, "/quit")

    assert result is False
    assert any("Goodbye" in line for line in console.printed)


def test_dispatch_exit_returns_false():
    """Test /exit alias also returns False."""
    console = _DummyConsole()
    ctx = _make_test_context(console=console)

    result = dispatch_command(ctx, "/exit")

    assert result is False


def test_dispatch_no_arg_command_with_args_is_unknown():
    """No-arg commands should not execute when trailing args are provided."""
    console = _DummyConsole()
    ctx = _make_test_context(console=console)

    result = dispatch_command(ctx, "/quit now")

    assert result is True
    assert any("Unknown command" in line for line in console.printed)
    assert not any("Goodbye" in line for line in console.printed)


def test_dispatch_reset_refreshes_themed_console(monkeypatch, tmp_path):
    """Reset should refresh theme and console after loading updated settings."""
    from io import StringIO

    from rich.console import Console

    console = _DummyConsole()
    current_settings = Settings(base_dir=tmp_path, color_theme="default")
    reloaded_settings = Settings(base_dir=tmp_path, color_theme="minimal")
    ctx = _make_test_context(settings=current_settings, console=console)

    monkeypatch.setattr("flavia.config.reset_settings", lambda: None)
    monkeypatch.setattr("flavia.config.load_settings", lambda: reloaded_settings)
    monkeypatch.setattr(
        "flavia.interfaces.cli_interface._history_paths",
        lambda _base_dir: (tmp_path / ".prompt_history", tmp_path / "chat_history.jsonl"),
    )
    monkeypatch.setattr("flavia.interfaces.cli_interface._configure_prompt_history", lambda _f: False)
    monkeypatch.setattr("flavia.interfaces.cli_interface._print_active_model_hint", lambda *_a: None)

    set_theme_calls: list[str] = []
    themed_console = Console(file=StringIO())
    monkeypatch.setattr("flavia.display.set_theme", lambda name: set_theme_calls.append(name))
    monkeypatch.setattr("flavia.display.reset_console", lambda: None)
    monkeypatch.setattr("flavia.interfaces.cli_interface.refresh_console", lambda: themed_console)

    result = dispatch_command(ctx, "/reset")

    assert result is True
    assert set_theme_calls == ["minimal"]
    assert ctx.console is themed_console


def test_dispatch_agent_cancelled_selection_shows_list_without_switch(monkeypatch, tmp_path):
    """Cancelling /agent selection should not switch to 'main' implicitly."""
    from flavia.setup.prompt_utils import SetupCancelled

    console = _DummyConsole()
    settings = Settings(
        base_dir=tmp_path,
        agents_config={
            "main": {"context": "Main", "tools": []},
            "subagents": {"reviewer": {"context": "Review", "tools": []}},
        },
    )
    ctx = _make_test_context(settings=settings, console=console)
    listed: list[tuple[Settings, bool]] = []

    monkeypatch.setattr(
        "flavia.interfaces.cli_interface._get_available_agents",
        lambda _settings: {"main": {}, "reviewer": {}},
    )
    monkeypatch.setattr("flavia.setup.prompt_utils.is_interactive", lambda: True)
    monkeypatch.setattr(
        "flavia.setup.prompt_utils.q_select",
        lambda *args, **kwargs: (_ for _ in ()).throw(SetupCancelled()),
    )
    monkeypatch.setattr(
        "flavia.display.display_agents",
        lambda configured_settings, console=None, use_rich=True: listed.append(
            (configured_settings, use_rich)
        ),
    )

    result = dispatch_command(ctx, "/agent")

    assert result is True
    assert settings.active_agent is None
    assert listed == [(settings, True)]


def test_dispatch_provider_setup_runs_wizard_with_base_dir(monkeypatch, tmp_path):
    """Provider setup command should run wizard for the active session base_dir."""
    console = _DummyConsole()
    settings = Settings(base_dir=tmp_path)
    ctx = _make_test_context(settings=settings, console=console)
    captured: dict[str, object] = {}

    def _fake_run_provider_wizard(target_dir=None):
        captured["target_dir"] = target_dir
        return True

    monkeypatch.setattr(
        "flavia.setup.provider_wizard.run_provider_wizard",
        _fake_run_provider_wizard,
    )

    result = dispatch_command(ctx, "/provider-setup")

    assert result is True
    assert captured["target_dir"] == tmp_path
    assert any("Use /reset to reload configuration." in line for line in console.printed)


def test_dispatch_provider_manage_passes_provider_id_and_base_dir(monkeypatch, tmp_path):
    """Provider manage command should forward provider_id and target_dir."""
    console = _DummyConsole()
    settings = Settings(base_dir=tmp_path)
    ctx = _make_test_context(settings=settings, console=console)
    captured: dict[str, object] = {}

    def _fake_manage_provider_models(_settings, provider_id, target_dir=None):
        captured["provider_id"] = provider_id
        captured["target_dir"] = target_dir
        return True

    monkeypatch.setattr(
        "flavia.setup.provider_wizard.manage_provider_models",
        _fake_manage_provider_models,
    )

    result = dispatch_command(ctx, "/provider-manage openai")

    assert result is True
    assert captured["provider_id"] == "openai"
    assert captured["target_dir"] == tmp_path
    assert any("Use /reset to reload configuration." in line for line in console.printed)


def test_dispatch_provider_test_reports_unknown_provider():
    """Unknown provider IDs should show available provider list."""
    console = _DummyConsole()
    settings = _make_provider_settings(provider_id="openai")
    ctx = _make_test_context(settings=settings, console=console)

    result = dispatch_command(ctx, "/provider-test missing")

    assert result is True
    assert any("Provider 'missing' not found." in line for line in console.printed)
    assert any("Available: openai" in line for line in console.printed)


def test_dispatch_provider_test_requires_default_provider():
    """Without args, /provider-test should require a default provider."""
    console = _DummyConsole()
    settings = Settings()
    ctx = _make_test_context(settings=settings, console=console)

    result = dispatch_command(ctx, "/provider-test")

    assert result is True
    assert any("No default provider configured." in line for line in console.printed)


def test_dispatch_provider_test_calls_connection_test(monkeypatch):
    """Provider test command should call provider_wizard.test_provider_connection."""
    console = _DummyConsole()
    settings = _make_provider_settings(provider_id="openai")
    ctx = _make_test_context(settings=settings, console=console)
    calls: list[tuple[str, str, str, dict | None]] = []

    def _fake_test_provider_connection(api_key, api_base_url, model_id, headers=None):
        calls.append((api_key, api_base_url, model_id, headers))
        return True, "ok"

    monkeypatch.setattr(
        "flavia.setup.provider_wizard.test_provider_connection",
        _fake_test_provider_connection,
    )

    result = dispatch_command(ctx, "/provider-test openai")

    assert result is True
    assert calls == [("test-key", "https://openai.example/v1", "gpt-4o", None)]
    assert any("SUCCESS" in line and "ok" in line for line in console.printed)


def test_dispatch_compact_cancelled(monkeypatch):
    """Declining /compact should not trigger compaction."""
    console = _DummyConsole()

    class _CompactAgent(_DummyAgent):
        def __init__(self):
            self.last_prompt_tokens = 45_000
            self.max_context_tokens = 128_000
            self.compact_conversation = MagicMock(return_value="summary")

        @property
        def context_utilization(self):
            return self.last_prompt_tokens / self.max_context_tokens

    agent = _CompactAgent()
    ctx = _make_test_context(console=console, agent=agent)
    monkeypatch.setattr("builtins.input", lambda: "n")

    result = dispatch_command(ctx, "/compact")

    assert result is True
    agent.compact_conversation.assert_not_called()
    output = " ".join(console.printed)
    assert "Context: 45,000/128,000 (35%). Compact conversation?" in output
    assert "Compaction cancelled." in output


def test_dispatch_compact_confirmed_shows_summary_and_new_usage(monkeypatch):
    """Confirming /compact should show summary and updated token usage."""
    console = _DummyConsole()

    class _CompactAgent(_DummyAgent):
        def __init__(self):
            self.last_prompt_tokens = 45_000
            self.max_context_tokens = 128_000
            self.compact_conversation = MagicMock(side_effect=self._compact)

        @property
        def context_utilization(self):
            return self.last_prompt_tokens / self.max_context_tokens

        def _compact(self):
            self.last_prompt_tokens = 3_200
            return "Compact summary"

    agent = _CompactAgent()
    ctx = _make_test_context(console=console, agent=agent)
    monkeypatch.setattr("builtins.input", lambda: "y")

    result = dispatch_command(ctx, "/compact")

    assert result is True
    agent.compact_conversation.assert_called_once()
    output = " ".join(console.printed)
    assert "Conversation compacted." in output
    assert "Summary:" in output
    assert "Compact summary" in output
    assert "New context: 3,200/128,000 (2.5%)" in output


def test_dispatch_compact_handles_empty_conversation(monkeypatch):
    """Compact command should explain when there's nothing to compact."""
    console = _DummyConsole()

    class _CompactAgent(_DummyAgent):
        def __init__(self):
            self.last_prompt_tokens = 0
            self.max_context_tokens = 128_000
            self.compact_conversation = MagicMock(return_value="")

        @property
        def context_utilization(self):
            return 0.0

    agent = _CompactAgent()
    ctx = _make_test_context(console=console, agent=agent)
    monkeypatch.setattr("builtins.input", lambda: "y")

    result = dispatch_command(ctx, "/compact")

    assert result is True
    agent.compact_conversation.assert_called_once()
    output = " ".join(console.printed)
    assert "Nothing to compact (conversation is empty)." in output


# =============================================================================
# Help System Tests
# =============================================================================


def test_get_help_listing_includes_all_categories():
    """Test /help listing includes expected category headers."""
    help_text = get_help_listing()

    assert "Session:" in help_text
    assert "Agents:" in help_text
    assert "Models & Providers:" in help_text
    assert "Information:" in help_text
    assert "Index:" in help_text


def test_get_help_listing_includes_commands():
    """Test /help listing includes key commands."""
    help_text = get_help_listing()

    assert "/quit" in help_text
    assert "/reset" in help_text
    assert "/compact" in help_text
    assert "/help" in help_text
    assert "/model" in help_text
    assert "/agent" in help_text
    assert "/providers" in help_text
    assert "/provider-setup" in help_text
    assert "/provider-manage" in help_text
    assert "/provider-test" in help_text
    assert "/index <build|update|stats|diagnose>" in help_text
    assert "/tools" in help_text
    assert "/config" in help_text


def test_dispatch_index_subcommands(monkeypatch):
    """Test /index routes to the expected subcommand handlers."""
    console = _DummyConsole()
    ctx = _make_test_context(console=console)
    calls: list[str] = []

    monkeypatch.setattr(
        "flavia.interfaces.commands.cmd_index_build",
        lambda _ctx, _args: calls.append("build") or True,
    )
    monkeypatch.setattr(
        "flavia.interfaces.commands.cmd_index_update",
        lambda _ctx, _args: calls.append("update") or True,
    )
    monkeypatch.setattr(
        "flavia.interfaces.commands.cmd_index_stats",
        lambda _ctx, _args: calls.append("stats") or True,
    )
    monkeypatch.setattr(
        "flavia.interfaces.commands.cmd_index_diagnose",
        lambda _ctx, _args: calls.append("diagnose") or True,
    )

    assert dispatch_command(ctx, "/index build") is True
    assert dispatch_command(ctx, "/index update") is True
    assert dispatch_command(ctx, "/index stats") is True
    assert dispatch_command(ctx, "/index diagnose") is True
    assert calls == ["build", "update", "stats", "diagnose"]


def test_dispatch_index_invalid_subcommand_shows_usage():
    """Invalid /index subcommand should display usage guidance."""
    console = _DummyConsole()
    ctx = _make_test_context(console=console)

    assert dispatch_command(ctx, "/index nope") is True
    assert any("Usage: /index <build|update|stats|diagnose>" in line for line in console.printed)


def test_dispatch_rag_debug_toggles_runtime_flag():
    """RAG debug command should toggle settings and agent context flag."""
    console = _DummyConsole()
    settings = Settings()
    agent = _DummyAgent()
    agent.context = MagicMock()
    agent.context.rag_debug = False
    ctx = _make_test_context(console=console, settings=settings, agent=agent)

    assert dispatch_command(ctx, "/rag-debug on") is True
    assert settings.rag_debug is True
    assert agent.context.rag_debug is True

    assert dispatch_command(ctx, "/rag-debug off") is True
    assert settings.rag_debug is False
    assert agent.context.rag_debug is False


def test_dispatch_rag_debug_last_prints_recent_trace(tmp_path):
    """`/rag-debug last` should print persisted diagnostics traces."""
    console = _DummyConsole()
    settings = Settings(base_dir=tmp_path)
    ctx = _make_test_context(console=console, settings=settings)

    flavia_dir = tmp_path / ".flavia"
    flavia_dir.mkdir(parents=True, exist_ok=True)
    trace_path = flavia_dir / "rag_debug.jsonl"
    trace_path.write_text(
        json.dumps(
            {
                "trace_id": "abc123",
                "timestamp": "2026-02-17T12:00:00+00:00",
                "query_raw": "laplace",
                "query_effective": "laplace",
                "mentions": ["@video.mp4"],
                "trace": {
                    "params": {"top_k": 10},
                    "filters": {"input_doc_ids_filter_count": 1, "effective_doc_ids_filter_count": 1},
                    "counts": {"vector_hits": 2, "fts_hits": 3, "unique_candidates": 4, "final_results": 2},
                    "timings_ms": {"total": 5.0},
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    assert dispatch_command(ctx, "/rag-debug last") is True
    printed = "\n".join(console.printed)
    assert "Trace 1/1" in printed
    assert "abc123" in printed
    assert "query: laplace" in printed
    assert "mentions: @video.mp4" in printed
    assert "[RAG DEBUG]" in printed


def test_dispatch_rag_debug_last_rejects_invalid_limit():
    """`/rag-debug last` should validate optional limit argument."""
    console = _DummyConsole()
    ctx = _make_test_context(console=console)

    assert dispatch_command(ctx, "/rag-debug last nope") is True
    assert any("Usage: /rag-debug last [N]" in line for line in console.printed)


def test_dispatch_rag_debug_turn_filters_current_turn(tmp_path):
    """`/rag-debug turn` should show only traces for current turn id."""
    console = _DummyConsole()
    settings = Settings(base_dir=tmp_path)
    agent = _DummyAgent()
    agent.context = MagicMock()
    agent.context.rag_turn_id = "turn-000007-abc123"
    ctx = _make_test_context(console=console, settings=settings, agent=agent)

    flavia_dir = tmp_path / ".flavia"
    flavia_dir.mkdir(parents=True, exist_ok=True)
    trace_path = flavia_dir / "rag_debug.jsonl"
    trace_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "trace_id": "old1",
                        "timestamp": "2026-02-17T12:00:00+00:00",
                        "turn_id": "turn-000006-zzz999",
                        "query_effective": "old query",
                        "trace": {"params": {}, "filters": {}, "counts": {}, "timings_ms": {}},
                    }
                ),
                json.dumps(
                    {
                        "trace_id": "new1",
                        "timestamp": "2026-02-17T12:01:00+00:00",
                        "turn_id": "turn-000007-abc123",
                        "query_effective": "current query",
                        "trace": {"params": {}, "filters": {}, "counts": {}, "timings_ms": {}},
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    assert dispatch_command(ctx, "/rag-debug turn") is True
    printed = "\n".join(console.printed)
    assert "new1" in printed
    assert "current query" in printed
    assert "turn_id: turn-000007-abc123" in printed
    assert "old1" not in printed


def test_dispatch_rag_debug_turn_without_active_turn():
    """`/rag-debug turn` should explain when no active turn id exists."""
    console = _DummyConsole()
    agent = _DummyAgent()
    agent.context = MagicMock()
    agent.context.rag_turn_id = None
    ctx = _make_test_context(console=console, agent=agent)

    assert dispatch_command(ctx, "/rag-debug turn") is True
    assert any("No active turn id found" in line for line in console.printed)


def test_dispatch_rag_debug_turn_without_traces_and_debug_off_shows_hint(tmp_path):
    """`/rag-debug turn` should explain debug-off state when no traces exist."""
    console = _DummyConsole()
    settings = Settings(base_dir=tmp_path, rag_debug=False)
    agent = _DummyAgent()
    agent.context = MagicMock()
    agent.context.rag_turn_id = "turn-000123-aaaaaa"
    ctx = _make_test_context(console=console, settings=settings, agent=agent)

    assert dispatch_command(ctx, "/rag-debug turn") is True
    assert any("No RAG diagnostics traces found for current turn" in line for line in console.printed)
    assert any("RAG debug mode is currently OFF" in line for line in console.printed)


def test_dispatch_citations_turn_prints_current_turn_entries(tmp_path):
    """`/citations turn` should print citation entries filtered by active turn."""
    console = _DummyConsole()
    settings = Settings(base_dir=tmp_path)
    agent = _DummyAgent()
    agent.context = MagicMock()
    agent.context.rag_turn_id = "turn-000010-abc123"
    ctx = _make_test_context(console=console, settings=settings, agent=agent)

    flavia_dir = tmp_path / ".flavia"
    flavia_dir.mkdir(parents=True, exist_ok=True)
    citation_path = flavia_dir / "rag_citations.jsonl"
    citation_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "citation_id": "C-main-0001",
                        "turn_id": "turn-000009-zzzzzz",
                        "doc_name": "old.pdf",
                        "locator": {"line_start": 1, "line_end": 2},
                        "excerpt": "old",
                    }
                ),
                json.dumps(
                    {
                        "citation_id": "C-main-0002",
                        "turn_id": "turn-000010-abc123",
                        "doc_name": "current.pdf",
                        "locator": {"line_start": 10, "line_end": 20},
                        "excerpt": "current evidence",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    assert dispatch_command(ctx, "/citations turn") is True
    printed = "\n".join(console.printed)
    assert "C-main-0002" in printed
    assert "current.pdf" in printed
    assert "old.pdf" not in printed


def test_dispatch_citations_id_prints_single_entry(tmp_path):
    """`/citations id` should return exactly the requested citation."""
    console = _DummyConsole()
    settings = Settings(base_dir=tmp_path)
    ctx = _make_test_context(console=console, settings=settings)

    flavia_dir = tmp_path / ".flavia"
    flavia_dir.mkdir(parents=True, exist_ok=True)
    citation_path = flavia_dir / "rag_citations.jsonl"
    citation_path.write_text(
        json.dumps(
            {
                "citation_id": "C-main-0042",
                "turn_id": "turn-000111-abc111",
                "doc_name": "evidence.pdf",
                "locator": {"line_start": 7, "line_end": 9},
                "excerpt": "important excerpt",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    assert dispatch_command(ctx, "/citations id C-main-0042") is True
    printed = "\n".join(console.printed)
    assert "C-main-0042" in printed
    assert "evidence.pdf" in printed


def test_get_help_listing_shows_short_descriptions():
    """Test /help listing shows command descriptions."""
    help_text = get_help_listing()

    # Check some expected descriptions are present
    assert "Exit" in help_text  # /quit description
    assert "Reset" in help_text  # /reset description


def test_get_command_help_returns_detailed_help():
    """Test /help <command> returns detailed information."""
    help_text = get_command_help("/model")

    assert help_text is not None
    assert "/model" in help_text
    assert "Usage:" in help_text


def test_get_command_help_includes_examples():
    """Test detailed help includes examples when available."""
    help_text = get_command_help("/model")

    assert help_text is not None
    # /model has examples defined
    assert "Examples:" in help_text


def test_get_command_help_includes_aliases():
    """Test detailed help shows aliases for commands that have them."""
    help_text = get_command_help("/quit")

    assert help_text is not None
    assert "Aliases:" in help_text
    assert "/exit" in help_text
    assert "/q" in help_text


def test_get_command_help_includes_related():
    """Test detailed help shows related commands."""
    help_text = get_command_help("/model")

    assert help_text is not None
    assert "Related:" in help_text
    assert "/providers" in help_text


def test_get_command_help_returns_none_for_unknown():
    """Test /help for unknown command returns None."""
    help_text = get_command_help("/not_real")

    assert help_text is None


def test_get_command_help_normalizes_command_name():
    """Test help lookup works with or without leading slash."""
    with_slash = get_command_help("/model")
    without_slash = get_command_help("model")

    assert with_slash is not None
    assert without_slash is not None
    assert with_slash == without_slash


def test_help_command_shows_listing_without_args():
    """Test /help without args shows the command listing."""
    console = _DummyConsole()
    ctx = _make_test_context(console=console)

    dispatch_command(ctx, "/help")

    output = " ".join(console.printed)
    assert "Commands:" in output
    assert "Session:" in output


def test_help_command_shows_details_with_args():
    """Test /help <command> shows detailed help."""
    console = _DummyConsole()
    ctx = _make_test_context(console=console)

    dispatch_command(ctx, "/help model")

    output = " ".join(console.printed)
    assert "/model" in output
    assert "Usage:" in output


def test_help_command_handles_unknown_command_arg():
    """Test /help <unknown> shows error message."""
    console = _DummyConsole()
    ctx = _make_test_context(console=console)

    dispatch_command(ctx, "/help nonexistent")

    output = " ".join(console.printed)
    assert "Unknown command" in output


# =============================================================================
# Command Metadata Tests
# =============================================================================


def test_all_commands_have_required_metadata():
    """Verify all registered commands have required fields."""
    for cmd_name, metadata in COMMAND_REGISTRY.items():
        assert metadata.category, f"{cmd_name} missing category"
        assert metadata.short_desc, f"{cmd_name} missing short_desc"
        assert callable(metadata.handler), f"{cmd_name} handler not callable"


def test_commands_have_consistent_usage_format():
    """Verify usage strings start with the command name."""
    seen_handlers = set()

    for cmd_name, metadata in COMMAND_REGISTRY.items():
        # Skip aliases
        handler_id = id(metadata.handler)
        if handler_id in seen_handlers:
            continue
        seen_handlers.add(handler_id)

        if metadata.usage:
            # Find primary name
            primary = cmd_name
            for name, meta in COMMAND_REGISTRY.items():
                if meta is metadata and name not in metadata.aliases:
                    primary = name
                    break

            assert metadata.usage.startswith(primary), (
                f"{primary} usage '{metadata.usage}' doesn't start with command name"
            )
