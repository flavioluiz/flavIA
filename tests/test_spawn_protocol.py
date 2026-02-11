"""Tests for spawn tool payload protocol."""

from pathlib import Path

import flavia.agent.recursive as recursive_module
from flavia.agent.context import AgentContext
from flavia.agent.profile import AgentPermissions, AgentProfile
from flavia.agent.recursive import RecursiveAgent
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
