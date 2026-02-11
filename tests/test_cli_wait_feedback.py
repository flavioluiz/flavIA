"""Tests for CLI wait feedback helpers."""

from flavia.agent.status import StatusPhase, ToolStatus
from flavia.interfaces.cli_interface import (
    LOADING_DOTS,
    LOADING_MESSAGES,
    _agent_label_from_id,
    _build_agent_activity_line,
    _build_agent_header_line,
    _build_agent_prefix,
    _build_loading_line,
    _build_tool_status_line,
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


def test_build_loading_line_sanitizes_control_chars():
    line = _build_loading_line("Work\nnow", 0, model_ref="openai\x1b[31m")
    assert "\x1b" not in line
    assert "\n" not in line


def test_build_tool_status_line_verbose_sanitizes_arguments_and_model():
    status = ToolStatus(
        phase=StatusPhase.EXECUTING_TOOL,
        tool_name="read_file",
        args={"path": "evil\x1b[31m\nname.txt"},
        depth=0,
    )
    line = _build_tool_status_line(status, step=0, model_ref="openai\x1b[31m", verbose=True)

    assert line.startswith("Agent [openai[31m]: ")
    assert "read_file(path='evil[31m name.txt')" in line
    assert "\x1b" not in line
    assert "\n" not in line


def test_build_tool_status_line_indents_for_subagents():
    status = ToolStatus(
        phase=StatusPhase.EXECUTING_TOOL,
        tool_name="read_file",
        tool_display="Reading config.yaml",
        depth=2,
    )
    line = _build_tool_status_line(status, step=0, model_ref="", verbose=False)
    assert line.startswith("    Agent: Reading config.yaml ")


def test_build_tool_status_line_can_disable_dots():
    status = ToolStatus(
        phase=StatusPhase.EXECUTING_TOOL,
        tool_name="read_file",
        tool_display="Reading config.yaml",
        depth=0,
    )
    line = _build_tool_status_line(status, step=0, model_ref="", verbose=False, show_dots=False)
    assert line == "Agent: Reading config.yaml"


def test_agent_label_from_id_for_main_and_subagents():
    assert _agent_label_from_id("main") == "main"
    assert _agent_label_from_id("main.summarizer.1") == "summarizer"
    assert _agent_label_from_id("main.sub.2") == "sub-2"


def test_build_agent_header_and_activity_lines():
    status = ToolStatus(
        phase=StatusPhase.EXECUTING_TOOL,
        tool_name="query_catalog",
        tool_display="Searching catalog: 'ITA'",
        agent_id="main.summarizer.1",
        depth=1,
    )
    header = _build_agent_header_line(status)
    activity = _build_agent_activity_line(status, step=0, model_ref="", verbose=False)
    assert header == "  summarizer:"
    assert activity == "    Searching catalog: 'ITA'"


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
