"""Tests for CLI agent model management wizard."""

import yaml

from flavia.config.loader import ConfigPaths
from flavia.config.providers import ModelConfig, ProviderConfig, ProviderRegistry
from flavia.config.settings import Settings
from flavia.setup.agent_wizard import manage_agent_models


def _make_settings(tmp_path):
    local_dir = tmp_path / ".flavia"
    local_dir.mkdir()
    paths = ConfigPaths(local_dir=local_dir, user_dir=None, package_dir=tmp_path)

    registry = ProviderRegistry(
        providers={
            "openai": ProviderConfig(
                id="openai",
                name="OpenAI",
                api_base_url="https://api.openai.com/v1",
                api_key="test-key",
                models=[
                    ModelConfig(id="gpt-4o", name="GPT-4o", default=True),
                    ModelConfig(id="gpt-4o-mini", name="GPT-4o Mini"),
                ],
            )
        },
        default_provider_id="openai",
    )

    return Settings(
        providers=registry,
        default_model="openai:gpt-4o",
        config_paths=paths,
    )


def test_manage_agent_models_updates_selected_subagent(monkeypatch, tmp_path):
    settings = _make_settings(tmp_path)
    agents_file = tmp_path / ".flavia" / "agents.yaml"
    agents_file.write_text(
        (
            "main:\n"
            "  model: openai:gpt-4o\n"
            "  context: test\n"
            "  tools:\n"
            "    - read_file\n"
            "  subagents:\n"
            "    summarizer:\n"
            "      context: summarize\n"
            "      tools:\n"
            "        - read_file\n"
        ),
        encoding="utf-8",
    )

    prompts = iter(["2", "2"])
    monkeypatch.setattr("flavia.setup.agent_wizard.safe_prompt", lambda *args, **kwargs: next(prompts))
    monkeypatch.setattr("flavia.setup.agent_wizard.safe_confirm", lambda *args, **kwargs: False)

    changed = manage_agent_models(settings, base_dir=tmp_path)

    assert changed is True
    data = yaml.safe_load(agents_file.read_text(encoding="utf-8"))
    assert data["main"]["subagents"]["summarizer"]["model"] == "openai:gpt-4o-mini"


def test_manage_agent_models_returns_false_without_agents_file(tmp_path):
    settings = _make_settings(tmp_path)
    changed = manage_agent_models(settings, base_dir=tmp_path)
    assert changed is False


def test_manage_agent_models_updates_all_agents_at_once(monkeypatch, tmp_path):
    settings = _make_settings(tmp_path)
    agents_file = tmp_path / ".flavia" / "agents.yaml"
    agents_file.write_text(
        (
            "main:\n"
            "  model: openai:gpt-4o\n"
            "  context: test\n"
            "  tools:\n"
            "    - read_file\n"
            "  subagents:\n"
            "    summarizer:\n"
            "      context: summarize\n"
            "      tools:\n"
            "        - read_file\n"
            "    reviewer:\n"
            "      context: review\n"
            "      model: openai:gpt-4o\n"
            "      tools:\n"
            "        - read_file\n"
        ),
        encoding="utf-8",
    )

    prompts = iter(["a", "2"])
    monkeypatch.setattr("flavia.setup.agent_wizard.safe_prompt", lambda *args, **kwargs: next(prompts))
    monkeypatch.setattr("flavia.setup.agent_wizard.safe_confirm", lambda *args, **kwargs: False)

    changed = manage_agent_models(settings, base_dir=tmp_path)

    assert changed is True
    data = yaml.safe_load(agents_file.read_text(encoding="utf-8"))
    assert data["main"]["model"] == "openai:gpt-4o-mini"
    assert data["main"]["subagents"]["summarizer"]["model"] == "openai:gpt-4o-mini"
    assert data["main"]["subagents"]["reviewer"]["model"] == "openai:gpt-4o-mini"
