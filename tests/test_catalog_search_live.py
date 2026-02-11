"""Live integration tests for catalog search in converted content.

These tests verify that the agent can find information inside converted
documents (like PDFs converted to markdown) when using query_catalog.

These tests are opt-in and skipped by default.

Run with:
  FLAVIA_LIVE_LLM_TEST=1 pytest -q tests/test_catalog_search_live.py

Optional env vars:
  FLAVIA_LIVE_API_KEY
  FLAVIA_LIVE_API_BASE_URL
  FLAVIA_LIVE_MODEL
  FLAVIA_LIVE_PROVIDER_ID
  FLAVIA_LIVE_MAX_TOKENS
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from flavia.agent.profile import AgentPermissions, AgentProfile
from flavia.agent.recursive import RecursiveAgent
from flavia.config.providers import ModelConfig, ProviderConfig, ProviderRegistry
from flavia.config.settings import Settings
from flavia.content.catalog import ContentCatalog


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


def _setup_catalog_with_converted_content(tmp_path: Path) -> ContentCatalog:
    """Create a catalog with a simulated PDF and its converted content."""
    # Create a simulated PDF file (just needs to exist with PDF-like content)
    (tmp_path / "research_paper.pdf").write_bytes(b"%PDF-1.4 fake pdf content")

    # Create the converted markdown in .converted/
    converted_dir = tmp_path / ".converted"
    converted_dir.mkdir()
    (converted_dir / "research_paper.md").write_text(
        """# Research Paper on Quantum Computing

## Abstract

This paper discusses the revolutionary discovery of quantum entanglement
in superconducting qubits at 15 millikelvin temperatures. The lead researcher
Dr. Helena Vasquez demonstrated that coherence times of 500 microseconds
are achievable using novel error correction codes.

## Key Findings

1. The optimal operating temperature is exactly 15.7 millikelvin
2. Coherence time reached 523 microseconds in controlled conditions
3. The new error correction code is called "Vasquez-Chen Protocol"

## Conclusion

The Vasquez-Chen Protocol represents a breakthrough in quantum computing
stability, enabling practical quantum algorithms for cryptography applications.
"""
    )

    # Create catalog and config directory
    config_dir = tmp_path / ".flavia"
    config_dir.mkdir()

    # Build catalog
    catalog = ContentCatalog(tmp_path)
    catalog.build()

    # Set the converted_to field (simulating what the conversion process does)
    catalog.files["research_paper.pdf"].converted_to = ".converted/research_paper.md"
    catalog.files["research_paper.pdf"].summary = "Research paper about quantum computing"

    # Save catalog
    catalog.save(config_dir)

    return catalog


def _build_live_agent(tmp_path: Path) -> RecursiveAgent:
    """Build an agent with catalog tools enabled."""
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

    # Create profile with catalog tools and proper permissions
    profile = AgentProfile(
        context=(
            "You are a helpful research assistant. "
            "When asked about information in documents, use the query_catalog tool "
            "with text_search to find relevant information. "
            "Always cite specific details from the documents when answering."
        ),
        model=f"{provider_id}:{model_id}",
        tools=["query_catalog", "read_file"],
        subagents={},
        base_dir=tmp_path,
        permissions=AgentPermissions(
            read_paths=[tmp_path],
            write_paths=[],
        ),
    )

    return RecursiveAgent(settings=settings, profile=profile)


@pytest.mark.skipif(not _enabled(), reason="Set FLAVIA_LIVE_LLM_TEST=1 to run live LLM tests.")
def test_live_agent_finds_information_in_converted_content(tmp_path):
    """Test that the agent can find specific information inside converted documents."""
    # Setup catalog with converted content
    _setup_catalog_with_converted_content(tmp_path)

    # Build agent
    agent = _build_live_agent(tmp_path)

    # Ask about information that is ONLY in the converted content
    # (not in the summary)
    question = (
        "What is the exact operating temperature mentioned in the research paper? "
        "And what is the name of the error correction protocol?"
    )

    try:
        response = agent.run(question)
    except Exception as exc:
        pytest.fail(f"Agent run failed: {exc}\n\n{_override_hint()}")

    # The response should contain the specific details from the converted content
    response_lower = response.lower()

    # Check for temperature (15.7 millikelvin)
    assert "15" in response or "millikelvin" in response_lower, (
        f"Expected response to mention the temperature (15.7 millikelvin). "
        f"Got: {response}"
    )

    # Check for protocol name (Vasquez-Chen)
    assert "vasquez" in response_lower or "chen" in response_lower, (
        f"Expected response to mention the Vasquez-Chen Protocol. "
        f"Got: {response}"
    )


@pytest.mark.skipif(not _enabled(), reason="Set FLAVIA_LIVE_LLM_TEST=1 to run live LLM tests.")
def test_live_agent_finds_researcher_name_in_converted_content(tmp_path):
    """Test that the agent finds researcher names only present in converted content."""
    _setup_catalog_with_converted_content(tmp_path)
    agent = _build_live_agent(tmp_path)

    question = "Who is the lead researcher mentioned in the quantum computing paper?"

    try:
        response = agent.run(question)
    except Exception as exc:
        pytest.fail(f"Agent run failed: {exc}\n\n{_override_hint()}")

    # Dr. Helena Vasquez is only mentioned in the converted content
    response_lower = response.lower()
    assert "helena" in response_lower or "vasquez" in response_lower, (
        f"Expected response to mention Dr. Helena Vasquez. Got: {response}"
    )


@pytest.mark.skipif(not _enabled(), reason="Set FLAVIA_LIVE_LLM_TEST=1 to run live LLM tests.")
def test_live_agent_finds_coherence_time_in_converted_content(tmp_path):
    """Test that the agent finds numerical data only present in converted content."""
    _setup_catalog_with_converted_content(tmp_path)
    agent = _build_live_agent(tmp_path)

    question = "What coherence time was achieved in the quantum computing experiments?"

    try:
        response = agent.run(question)
    except Exception as exc:
        pytest.fail(f"Agent run failed: {exc}\n\n{_override_hint()}")

    # 523 microseconds is only in the converted content
    assert "523" in response or "500" in response or "microsecond" in response.lower(), (
        f"Expected response to mention coherence time (523 or ~500 microseconds). "
        f"Got: {response}"
    )
