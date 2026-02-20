"""Tests for default agent toolset when agents.yaml is missing."""

from pathlib import Path

from flavia.config.settings import Settings
from flavia.interfaces import cli_interface


def test_create_agent_from_settings_fallback_includes_web_search(monkeypatch, tmp_path: Path):
    settings = Settings(base_dir=tmp_path, agents_config={})

    class _FakeRecursiveAgent:
        def __init__(self, settings, profile):
            self.settings = settings
            self.profile = profile

    monkeypatch.setattr(cli_interface, "RecursiveAgent", _FakeRecursiveAgent)

    agent = cli_interface.create_agent_from_settings(settings)

    assert "web_search" in agent.profile.tools
