"""Compatibility tests for OpenAI client initialization."""

from pathlib import Path

import pytest

from flavia.agent.base import BaseAgent
from flavia.agent.profile import AgentProfile
from flavia.config.providers import ModelConfig, ProviderConfig, ProviderRegistry
from flavia.config.settings import Settings


class DummyAgent(BaseAgent):
    """Concrete agent used for BaseAgent initialization tests."""

    def run(self, user_message: str) -> str:
        return user_message


def _make_settings() -> Settings:
    return Settings(
        api_key="test-key",
        api_base_url="https://api.synthetic.new/openai/v1",
    )


def _make_profile() -> AgentProfile:
    return AgentProfile(
        context="test",
        base_dir=Path.cwd(),
        tools=[],
        subagents={},
        name="main",
    )


def test_openai_client_fallback_for_httpx_proxy_typeerror(monkeypatch):
    calls: list[dict] = []

    class FakeOpenAI:
        def __init__(self, **kwargs):
            calls.append(kwargs)
            if "http_client" not in kwargs:
                raise TypeError("Client.__init__() got an unexpected keyword argument 'proxies'")

    monkeypatch.setattr("flavia.agent.base.OpenAI", FakeOpenAI)

    DummyAgent(settings=_make_settings(), profile=_make_profile())

    assert len(calls) == 2
    assert "http_client" not in calls[0]
    assert "http_client" in calls[1]


def test_openai_client_does_not_swallow_unrelated_typeerror(monkeypatch):
    class FakeOpenAI:
        def __init__(self, **kwargs):
            raise TypeError("boom")

    monkeypatch.setattr("flavia.agent.base.OpenAI", FakeOpenAI)

    with pytest.raises(TypeError, match="boom"):
        DummyAgent(settings=_make_settings(), profile=_make_profile())


def test_provider_without_api_key_fails_instead_of_falling_back():
    settings = Settings(
        api_key="legacy-key",
        api_base_url="https://api.synthetic.new/openai/v1",
        providers=ProviderRegistry(
            providers={
                "openai": ProviderConfig(
                    id="openai",
                    name="OpenAI",
                    api_base_url="https://api.openai.com/v1",
                    api_key="",
                    models=[ModelConfig(id="gpt-4o", name="GPT-4o", default=True)],
                )
            },
            default_provider_id="openai",
        ),
    )
    profile = AgentProfile(
        context="test",
        model="openai:gpt-4o",
        base_dir=Path.cwd(),
        tools=[],
        subagents={},
        name="main",
    )

    with pytest.raises(ValueError, match="API key not configured for provider 'openai'"):
        DummyAgent(settings=settings, profile=profile)
