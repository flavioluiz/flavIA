"""Tests for CLI wait feedback helpers."""

import threading
from io import StringIO

from rich.console import Console

from flavia.agent.recursive import RecursiveAgent
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
    _continue_after_max_iterations,
    _get_agent_model_ref,
    _run_status_animation,
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


def test_continue_after_max_iterations_runs_extra_iterations(monkeypatch):
    calls = []

    def fake_run(agent, user_input, verbose=False, run_kwargs=None):
        calls.append((agent, user_input, verbose, run_kwargs))
        return "Done"

    monkeypatch.setattr("flavia.interfaces.cli_interface._run_agent_with_feedback", fake_run)
    monkeypatch.setattr("builtins.input", lambda: "y")

    initial = RecursiveAgent.format_max_iterations_message(3)
    agent = object()

    result = _continue_after_max_iterations(agent, initial, verbose=True)

    assert result == "Done"
    assert len(calls) == 1
    assert calls[0][1] == ""
    assert calls[0][2] is True
    assert calls[0][3] == {"continue_from_current": True, "max_iterations": 3}


def test_continue_after_max_iterations_returns_original_when_user_declines(monkeypatch):
    called = []

    def fake_run(*_args, **_kwargs):
        called.append(True)
        return "should not run"

    monkeypatch.setattr("flavia.interfaces.cli_interface._run_agent_with_feedback", fake_run)
    monkeypatch.setattr("builtins.input", lambda: "n")

    initial = RecursiveAgent.format_max_iterations_message(5)

    result = _continue_after_max_iterations(object(), initial, verbose=False)

    assert result == initial
    assert called == []


def test_run_status_animation_shows_interleaved_agents_with_same_activity():
    class _StopAfterFirstWait:
        def __init__(self):
            self._stopped = False

        def is_set(self):
            return self._stopped

        def wait(self, _timeout):
            self._stopped = True
            return True

    event_a = ToolStatus(
        phase=StatusPhase.EXECUTING_TOOL,
        tool_name="list_files",
        tool_display="Listing /tmp/docs",
        agent_id="main.sub.1",
        depth=1,
    )
    event_b = ToolStatus(
        phase=StatusPhase.EXECUTING_TOOL,
        tool_name="list_files",
        tool_display="Listing /tmp/docs",
        agent_id="main.sub.2",
        depth=1,
    )

    status_holder = [event_b]
    status_events = [event_a, event_b]
    status_lock = threading.Lock()
    stop_event = _StopAfterFirstWait()

    buf = StringIO()
    test_console = Console(file=buf, no_color=True, width=200)

    import flavia.interfaces.cli_interface as cli_mod

    original_console = cli_mod.console
    cli_mod.console = test_console
    try:
        _run_status_animation(
            stop_event=stop_event,
            model_ref="",
            status_holder=status_holder,
            status_events=status_events,
            status_lock=status_lock,
            verbose=False,
        )
    finally:
        cli_mod.console = original_console

    output = buf.getvalue()
    assert "sub-1:" in output
    assert "sub-2:" in output
    assert output.count("Listing /tmp/docs") == 2


def test_run_status_animation_shows_ellipsis_when_agent_history_is_truncated():
    class _StopAfterFirstWait:
        def __init__(self):
            self._stopped = False

        def is_set(self):
            return self._stopped

        def wait(self, _timeout):
            self._stopped = True
            return True

    events = [
        ToolStatus(
            phase=StatusPhase.EXECUTING_TOOL,
            tool_name="list_files",
            tool_display=f"Task {index}",
            agent_id="main.sub.1",
            depth=1,
        )
        for index in range(10)
    ]

    status_holder = [events[-1]]
    status_events = events
    status_lock = threading.Lock()
    stop_event = _StopAfterFirstWait()

    buf = StringIO()
    test_console = Console(file=buf, no_color=True, width=200)

    import flavia.interfaces.cli_interface as cli_mod

    original_console = cli_mod.console
    cli_mod.console = test_console
    try:
        _run_status_animation(
            stop_event=stop_event,
            model_ref="",
            status_holder=status_holder,
            status_events=status_events,
            status_lock=status_lock,
            verbose=False,
        )
    finally:
        cli_mod.console = original_console

    output = buf.getvalue()
    assert "sub-1:" in output
    # With base_max_tasks=5 and 1 agent, 10 events => 5 omitted
    assert "  ... (5 previous)" in output
    assert "Task 0" not in output
    assert "Task 4" not in output
    assert "Task 5" in output
    assert "Task 9" in output


def test_run_status_animation_reduces_tasks_with_many_agents():
    """When many sub-agents run in parallel, the per-agent task limit decreases."""

    class _StopAfterFirstWait:
        def __init__(self):
            self._stopped = False

        def is_set(self):
            return self._stopped

        def wait(self, _timeout):
            self._stopped = True
            return True

    # 6 sub-agents, each with 5 tasks => limit drops to 2 per agent
    events = []
    for agent_idx in range(1, 7):
        for task_idx in range(5):
            events.append(
                ToolStatus(
                    phase=StatusPhase.EXECUTING_TOOL,
                    tool_name="list_files",
                    tool_display=f"Agent{agent_idx}-Task{task_idx}",
                    agent_id=f"main.sub.{agent_idx}",
                    depth=1,
                )
            )

    status_holder = [events[-1]]
    status_events = events
    status_lock = threading.Lock()
    stop_event = _StopAfterFirstWait()

    buf = StringIO()
    test_console = Console(file=buf, no_color=True, width=200)

    import flavia.interfaces.cli_interface as cli_mod

    original_console = cli_mod.console
    cli_mod.console = test_console
    try:
        _run_status_animation(
            stop_event=stop_event,
            model_ref="",
            status_holder=status_holder,
            status_events=status_events,
            status_lock=status_lock,
            verbose=False,
        )
    finally:
        cli_mod.console = original_console

    output = buf.getvalue()
    # All 6 agents should appear
    for i in range(1, 7):
        assert f"sub-{i}:" in output
    # With 6 agents (>5), max_tasks_per_agent=2; 5 tasks - 2 kept = 3 omitted
    assert "  ... (3 previous)" in output
    # Only the last 2 tasks per agent should remain
    assert "Agent1-Task0" not in output
    assert "Agent1-Task3" in output
    assert "Agent1-Task4" in output


def test_run_status_animation_uses_previous_frame_height_after_shrink():
    """Regression: keep cursor rewind height after rendering a shorter frame."""

    class _StopAfterThreeFrames:
        def __init__(self, status_events, second_frame_events):
            self._stopped = False
            self._wait_count = 0
            self._status_events = status_events
            self._second_frame_events = second_frame_events

        def is_set(self):
            return self._stopped

        def wait(self, _timeout):
            self._wait_count += 1
            if self._wait_count == 1:
                # Feed frame 2 with one extra agent so max_tasks_per_agent drops
                # and the rendered block becomes shorter than frame 1.
                self._status_events.extend(self._second_frame_events)
                return False
            if self._wait_count == 2:
                # Frame 3 re-renders without new events.
                return False
            self._stopped = True
            return True

    # Frame 1: 3 agents with many tasks => each agent has ellipsis + 5 tasks.
    first_frame_events = []
    for agent_idx in range(1, 4):
        for task_idx in range(10):
            first_frame_events.append(
                ToolStatus(
                    phase=StatusPhase.EXECUTING_TOOL,
                    tool_name="list_files",
                    tool_display=f"A{agent_idx}-T{task_idx}",
                    agent_id=f"main.sub.{agent_idx}",
                    depth=1,
                )
            )

    # Frame 2: add one new agent; limit drops from 5 to 3 and frame shrinks.
    second_frame_events = [
        ToolStatus(
            phase=StatusPhase.EXECUTING_TOOL,
            tool_name="list_files",
            tool_display="A4-T0",
            agent_id="main.sub.4",
            depth=1,
        )
    ]

    status_holder = [first_frame_events[-1]]
    status_events = list(first_frame_events)
    status_lock = threading.Lock()
    stop_event = _StopAfterThreeFrames(status_events, second_frame_events)

    buf = StringIO()
    test_console = Console(file=buf, no_color=True, width=200)

    import flavia.interfaces.cli_interface as cli_mod

    original_console = cli_mod.console
    cli_mod.console = test_console
    try:
        _run_status_animation(
            stop_event=stop_event,
            model_ref="",
            status_holder=status_holder,
            status_events=status_events,
            status_lock=status_lock,
            verbose=False,
        )
    finally:
        cli_mod.console = original_console

    output = buf.getvalue()
    # Frame 2/3 must rewind to the first line of the 27-line painted area.
    # Cursor sits on the last line, so rewind distance is 26 (not 27).
    assert output.count("\x1b[26F") >= 2
    assert "\x1b[27F" not in output
