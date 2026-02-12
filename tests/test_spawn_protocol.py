"""Tests for spawn tool payload protocol."""

import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import flavia.agent.recursive as recursive_module
from flavia.agent.context import AgentContext
from flavia.agent.profile import AgentPermissions, AgentProfile
from flavia.agent.recursive import RecursiveAgent
from flavia.agent.status import StatusPhase
from flavia.tools.spawn.spawn_agent import SpawnAgentTool
from flavia.tools.spawn.spawn_predefined_agent import SpawnPredefinedAgentTool


def test_spawn_agent_json_payload_handles_pipe_characters():
    ctx = AgentContext(base_dir=Path.cwd())
    tool = SpawnAgentTool()

    task = "Comparar A|B com C|D"
    context = "Especialista em tabelas | gráficos"

    result = tool.execute(
        {
            "task": task,
            "context": context,
            "model": "0",
            "tools": ["read_file", "search_files"],
        },
        ctx,
    )

    parser = RecursiveAgent.__new__(RecursiveAgent)
    parsed = parser._parse_spawn_agent(result, {})

    assert parsed["task"] == task
    assert parsed["context"] == context
    assert parsed["model"] == "0"
    assert parsed["tools"] == ["read_file", "search_files"]


def test_spawn_predefined_json_payload_handles_pipe_characters():
    ctx = AgentContext(
        base_dir=Path.cwd(),
        subagents={"summarizer": {"context": "x", "tools": ["read_file"]}},
    )
    tool = SpawnPredefinedAgentTool()

    task = "Resumir seção 2 | seção 3"
    result = tool.execute({"agent_name": "summarizer", "task": task}, ctx)

    parser = RecursiveAgent.__new__(RecursiveAgent)
    parsed = parser._parse_spawn_predefined(result, {})

    assert parsed["agent_name"] == "summarizer"
    assert parsed["task"] == task


def test_recursive_parser_keeps_backward_compatibility_for_old_payloads():
    parser = RecursiveAgent.__new__(RecursiveAgent)

    old_dynamic = "__SPAWN_AGENT__:task antigo|contexto antigo|model-x|read_file,search_files"
    parsed_dynamic = parser._parse_spawn_agent(old_dynamic, {})
    assert parsed_dynamic["task"] == "task antigo"
    assert parsed_dynamic["context"] == "contexto antigo"
    assert parsed_dynamic["model"] == "model-x"
    assert parsed_dynamic["tools"] == ["read_file", "search_files"]

    old_predefined = "__SPAWN_PREDEFINED__:summarizer|tarefa antiga"
    parsed_predefined = parser._parse_spawn_predefined(old_predefined, {})
    assert parsed_predefined["agent_name"] == "summarizer"
    assert parsed_predefined["task"] == "tarefa antiga"


def test_spawn_dynamic_inherits_parent_permissions(monkeypatch, tmp_path):
    captured: dict[str, AgentProfile] = {}

    class FakeChildAgent:
        def __init__(self, settings, profile, agent_id, depth, parent_id):
            captured["profile"] = profile

        def run(self, user_message: str) -> str:
            return "ok"

    monkeypatch.setattr(recursive_module, "RecursiveAgent", FakeChildAgent)

    parent_permissions = AgentPermissions(
        read_paths=[(tmp_path / "docs").resolve()],
        write_paths=[(tmp_path / "output").resolve()],
    )
    parent_profile = AgentProfile(
        context="parent",
        base_dir=tmp_path,
        tools=["read_file"],
        subagents={},
        permissions=parent_permissions,
    )

    agent = RecursiveAgent.__new__(RecursiveAgent)
    agent._child_counter = 0
    agent._child_counter_lock = threading.Lock()
    agent.profile = parent_profile
    agent.context = AgentContext(agent_id="main", current_depth=0, max_depth=3, base_dir=tmp_path)
    agent.settings = object()
    agent.log = lambda _msg: None
    agent.status_callback = None

    result = RecursiveAgent._spawn_dynamic(agent, task="tarefa", context="contexto")

    assert result == "[sub-agent]: ok"
    spawned_permissions = captured["profile"].permissions
    assert spawned_permissions.read_paths == parent_permissions.read_paths
    assert spawned_permissions.write_paths == parent_permissions.write_paths
    assert spawned_permissions is not parent_permissions


def test_spawn_dynamic_assigns_consistent_id_and_profile_name_under_concurrency(
    monkeypatch, tmp_path
):
    captured: list[tuple[str, str]] = []
    captured_lock = threading.Lock()

    class FakeChildAgent:
        def __init__(self, settings, profile, agent_id, depth, parent_id):
            with captured_lock:
                captured.append((agent_id, profile.name or ""))

        def run(self, user_message: str) -> str:
            return "ok"

    monkeypatch.setattr(recursive_module, "RecursiveAgent", FakeChildAgent)

    parent_profile = AgentProfile(
        context="parent",
        base_dir=tmp_path,
        tools=["read_file"],
        subagents={},
    )

    agent = RecursiveAgent.__new__(RecursiveAgent)
    agent._child_counter = 0
    agent._child_counter_lock = threading.Lock()
    agent.profile = parent_profile
    agent.context = AgentContext(agent_id="main", current_depth=0, max_depth=3, base_dir=tmp_path)
    agent.settings = object()
    agent.log = lambda _msg: None
    agent.status_callback = None

    total_spawns = 20
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [
            executor.submit(RecursiveAgent._spawn_dynamic, agent, f"task-{i}", "context")
            for i in range(total_spawns)
        ]
    results = [future.result() for future in futures]

    assert results == ["[sub-agent]: ok"] * total_spawns
    assert agent._child_counter == total_spawns
    assert len(captured) == total_spawns

    captured_ids = [agent_id for agent_id, _ in captured]
    assert len(set(captured_ids)) == total_spawns

    for child_id, profile_name in captured:
        counter = int(child_id.rsplit(".", 1)[-1])
        assert profile_name == f"sub-{counter}"


def test_process_tool_calls_normalizes_non_object_json_arguments():
    agent = RecursiveAgent.__new__(RecursiveAgent)
    agent.context = AgentContext(agent_id="main", current_depth=0, max_depth=3)
    agent.log = lambda _msg: None

    captured: dict[str, object] = {}

    def fake_execute(name: str, args: dict) -> str:
        captured["name"] = name
        captured["args"] = args
        return "ok"

    statuses = []
    agent._execute_tool = fake_execute
    agent._notify_status = statuses.append

    tool_call = SimpleNamespace(
        id="call-1",
        function=SimpleNamespace(name="read_file", arguments='["unexpected"]'),
    )

    results, spawns = RecursiveAgent._process_tool_calls_with_spawns(agent, [tool_call])

    assert captured["name"] == "read_file"
    assert captured["args"] == {}
    assert results[0]["content"] == "ok"
    assert spawns == []
    assert statuses[0].phase == StatusPhase.EXECUTING_TOOL


def test_process_tool_calls_emits_spawning_status_for_predefined_agents():
    agent = RecursiveAgent.__new__(RecursiveAgent)
    agent.context = AgentContext(agent_id="main", current_depth=0, max_depth=3)
    agent.log = lambda _msg: None
    agent._execute_tool = (
        lambda _name, _args: '__SPAWN_PREDEFINED__:{"agent_name":"summarizer","task":"resumir"}'
    )

    statuses = []
    agent._notify_status = statuses.append

    tool_call = SimpleNamespace(
        id="call-2",
        function=SimpleNamespace(
            name="spawn_predefined_agent",
            arguments='{"agent_name":"summarizer","task":"resumir"}',
        ),
    )

    results, spawns = RecursiveAgent._process_tool_calls_with_spawns(agent, [tool_call])

    assert results[0]["content"] == "[Spawning predefined agent...]"
    assert spawns[0]["agent_name"] == "summarizer"
    assert [s.phase for s in statuses] == [StatusPhase.EXECUTING_TOOL, StatusPhase.SPAWNING_AGENT]
