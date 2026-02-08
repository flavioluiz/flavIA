"""Tests for spawn tool payload protocol."""

from pathlib import Path

from flavia.agent.context import AgentContext
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
