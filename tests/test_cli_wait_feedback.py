"""Tests for CLI wait feedback helpers."""

from flavia.interfaces.cli_interface import (
    LOADING_DOTS,
    LOADING_MESSAGES,
    _build_agent_prefix,
    _build_loading_line,
    _choose_loading_message,
    _get_agent_model_ref,
)


def test_build_loading_line_cycles_dot_frames():
    message = "Mensagem de teste"
    for i, dots in enumerate(LOADING_DOTS):
        assert _build_loading_line(message, i).endswith(f"{message} {dots}")


def test_build_loading_line_includes_model_when_available():
    line = _build_loading_line("Working", 0, model_ref="openai:gpt-4o")
    assert line.startswith("Agent [openai:gpt-4o]: ")


def test_choose_loading_message_avoids_immediate_repeat(monkeypatch):
    if len(LOADING_MESSAGES) < 2:
        return

    current = LOADING_MESSAGES[0]
    monkeypatch.setattr(
        "flavia.interfaces.cli_interface.random.choice",
        lambda candidates: candidates[0],
    )

    selected = _choose_loading_message(current)
    assert selected != current


def test_agent_model_ref_uses_provider_prefix():
    class Provider:
        id = "openai"

    class Agent:
        provider = Provider()
        model_id = "gpt-4o"

    assert _get_agent_model_ref(Agent()) == "openai:gpt-4o"
    assert _build_agent_prefix(Agent()) == "Agent [openai:gpt-4o]:"
