"""Live integration tests for context compaction with a real LLM.

These tests are opt-in and skipped by default.

Run with:
  FLAVIA_LIVE_LLM_TEST=1 pytest -q tests/test_context_compaction_live.py

Optional env vars:
  FLAVIA_LIVE_API_KEY
  FLAVIA_LIVE_API_BASE_URL
  FLAVIA_LIVE_MODEL
  FLAVIA_LIVE_PROVIDER_ID
  FLAVIA_LIVE_MAX_TOKENS
  FLAVIA_LIVE_FALLBACK_TEST=1
"""

from __future__ import annotations

import os

import pytest

from flavia.agent.profile import AgentProfile
from flavia.agent.recursive import RecursiveAgent
from flavia.config.providers import ModelConfig, ProviderConfig, ProviderRegistry
from flavia.config.settings import Settings


DEFAULT_PROVIDER_ID = "synthetic"
DEFAULT_MODEL_ID = "hf:moonshotai/Kimi-K2-Instruct-0905"
DEFAULT_API_BASE_URL = "https://api.synthetic.new/openai/v1"


def _enabled() -> bool:
    return os.getenv("FLAVIA_LIVE_LLM_TEST", "").strip() == "1"


def _override_hint() -> str:
    return (
        "Default live config:\n"
        f"- provider: {DEFAULT_PROVIDER_ID}\n"
        f"- model: {DEFAULT_MODEL_ID}\n"
        f"- api_base_url: {DEFAULT_API_BASE_URL}\n"
        "To change, set one or more env vars:\n"
        "- FLAVIA_LIVE_PROVIDER_ID\n"
        "- FLAVIA_LIVE_MODEL\n"
        "- FLAVIA_LIVE_API_BASE_URL\n"
        "- FLAVIA_LIVE_API_KEY"
    )


def _build_live_agent() -> RecursiveAgent:
    api_key = (
        os.getenv("FLAVIA_LIVE_API_KEY")
        or os.getenv("SYNTHETIC_API_KEY")
        or os.getenv("OPENAI_API_KEY")
    )
    if not api_key:
        pytest.skip("No API key found for live LLM test.\n" + _override_hint())

    provider_id = os.getenv("FLAVIA_LIVE_PROVIDER_ID", DEFAULT_PROVIDER_ID)
    model_id = os.getenv("FLAVIA_LIVE_MODEL", DEFAULT_MODEL_ID)
    api_base_url = os.getenv("FLAVIA_LIVE_API_BASE_URL", DEFAULT_API_BASE_URL)
    max_tokens = int(os.getenv("FLAVIA_LIVE_MAX_TOKENS", "128000"))

    provider = ProviderConfig(
        id=provider_id,
        name=provider_id,
        api_base_url=api_base_url,
        api_key=api_key,
        models=[ModelConfig(id=model_id, name=model_id, max_tokens=max_tokens, default=True)],
    )
    registry = ProviderRegistry(providers={provider_id: provider}, default_provider_id=provider_id)
    settings = Settings(
        api_key=api_key,
        api_base_url=api_base_url,
        providers=registry,
        default_model=f"{provider_id}:{model_id}",
    )
    profile = AgentProfile(
        context="You are a helpful assistant.",
        model=f"{provider_id}:{model_id}",
        tools=[],
        subagents={},
        compact_threshold=0.9,
    )
    return RecursiveAgent(settings=settings, profile=profile)


@pytest.mark.skipif(not _enabled(), reason="Set FLAVIA_LIVE_LLM_TEST=1 to run live LLM tests.")
def test_live_compaction_produces_summary_and_resets_context():
    agent = _build_live_agent()

    for i in range(1, 15):
        agent.messages.append(
            {
                "role": "user",
                "content": (
                    f"Task {i}: keep track of decision {i} and file docs/chapter{i}.md. "
                    "Important numbers: budget=12500, deadline=2026-03-31. "
                    "We chose approach B over approach A."
                ),
            }
        )
        agent.messages.append(
            {
                "role": "assistant",
                "content": (
                    f"Acknowledged task {i}. I will remember docs/chapter{i}.md, "
                    "budget 12500, deadline 2026-03-31, and approach B."
                ),
            }
        )

    original_text = agent._serialize_messages_for_compaction(agent.messages[1:])
    try:
        summary = agent.compact_conversation()
    except RuntimeError as exc:
        pytest.fail(f"Live compaction failed: {exc}\n\n{_override_hint()}")

    assert summary.strip()
    assert len(summary) < len(original_text)
    assert len(agent.messages) == 3
    assert agent.messages[0]["role"] == "system"
    assert agent.messages[1]["role"] == "user"
    assert "[Conversation summary from compaction]" in agent.messages[1]["content"]
    assert agent.messages[2]["role"] == "assistant"


@pytest.mark.skipif(not _enabled(), reason="Set FLAVIA_LIVE_LLM_TEST=1 to run live LLM tests.")
def test_live_compaction_timeout_fallback_with_chunking():
    if os.getenv("FLAVIA_LIVE_FALLBACK_TEST", "").strip() != "1":
        pytest.skip("Set FLAVIA_LIVE_FALLBACK_TEST=1 to run timeout fallback live test.")

    agent = _build_live_agent()
    for i in range(1, 9):
        agent.messages.append({"role": "user", "content": f"Long context item {i}: " + ("abc " * 200)})
        agent.messages.append(
            {"role": "assistant", "content": f"Captured item {i} with reference file_{i}.txt"}
        )

    original_call_llm = agent._call_llm
    calls = {"n": 0}

    def flaky_call(messages):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("Request timed out for provider 'live': simulated timeout")
        return original_call_llm(messages)

    agent._call_llm = flaky_call  # type: ignore[method-assign]
    try:
        summary = agent.compact_conversation()
    except RuntimeError as exc:
        pytest.fail(f"Live fallback compaction failed: {exc}\n\n{_override_hint()}")

    assert summary.strip()
    assert calls["n"] > 1
