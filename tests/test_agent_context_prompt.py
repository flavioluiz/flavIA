"""Tests for system prompt construction and catalog-first guidance."""

from pathlib import Path

from flavia.agent.context import AgentContext, build_system_prompt
from flavia.agent.profile import AgentProfile


def test_build_system_prompt_includes_catalog_first_guidance(tmp_path: Path):
    profile = AgentProfile(
        context="You are a research assistant.",
        base_dir=tmp_path,
        tools=[
            "read_file",
            "query_catalog",
            "search_chunks",
            "get_catalog_summary",
            "spawn_predefined_agent",
        ],
    )
    context = AgentContext.from_profile(profile, depth=0)

    prompt = build_system_prompt(profile, context, tools_description="")

    assert "Workflow policy for content discovery:" in prompt
    assert "`get_catalog_summary`" in prompt
    assert "`query_catalog`" in prompt
    assert (
        "Use search_chunks when answering questions about document content (what, how, why). "
        "Use query_catalog to discover which files exist or filter by type/name."
    ) in prompt
    assert "Only use `read_file` after shortlisting" in prompt
    assert "Video workflow playbook:" in prompt
    assert "`frame_descriptions`" in prompt


def test_build_system_prompt_omits_search_chunks_rule_when_tool_unavailable(tmp_path: Path):
    profile = AgentProfile(
        context="You are a research assistant.",
        base_dir=tmp_path,
        tools=["read_file", "query_catalog", "get_catalog_summary"],
    )
    context = AgentContext.from_profile(profile, depth=0)

    prompt = build_system_prompt(profile, context, tools_description="")

    assert "Workflow policy for content discovery:" in prompt
    assert "`query_catalog`" in prompt
    assert "Use search_chunks when answering questions about document content" not in prompt


def test_build_system_prompt_omits_catalog_guidance_without_catalog_tools(tmp_path: Path):
    profile = AgentProfile(
        context="You are a coding assistant.",
        base_dir=tmp_path,
        tools=["read_file", "search_files"],
    )
    context = AgentContext.from_profile(profile, depth=0)

    prompt = build_system_prompt(profile, context, tools_description="")

    assert "Workflow policy for content discovery:" not in prompt
    assert "Video workflow playbook:" not in prompt
