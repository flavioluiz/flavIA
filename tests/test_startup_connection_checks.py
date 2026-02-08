"""Tests for startup provider/model connectivity checks."""

import yaml

from flavia.cli import _ensure_default_connection_checked_once
from flavia.config.loader import ConfigPaths
from flavia.config.providers import ModelConfig, ProviderConfig, ProviderRegistry
from flavia.config.settings import Settings


def _make_settings(tmp_path, default_model="openai:gpt-4o", agents_config=None):
    config_dir = tmp_path / ".flavia"
    config_dir.mkdir()
    paths = ConfigPaths(local_dir=config_dir, user_dir=None, package_dir=tmp_path)

    registry = ProviderRegistry(
        providers={
            "openai": ProviderConfig(
                id="openai",
                name="OpenAI",
                api_base_url="https://api.openai.com/v1",
                api_key="test-key",
                models=[ModelConfig(id="gpt-4o", name="GPT-4o", default=True)],
            )
        },
        default_provider_id="openai",
    )

    return Settings(
        providers=registry,
        default_model=default_model,
        config_paths=paths,
        agents_config=agents_config or {},
    )


def test_startup_connection_check_runs_once_and_persists(monkeypatch, tmp_path):
    settings = _make_settings(tmp_path)
    calls: list[tuple[str, str, str]] = []

    def _fake_test_provider_connection(api_key, api_base_url, model_id, headers=None):
        calls.append((api_key, api_base_url, model_id))
        return True, "ok"

    monkeypatch.setattr(
        "flavia.setup.provider_wizard.test_provider_connection",
        _fake_test_provider_connection,
    )

    _ensure_default_connection_checked_once(settings)
    _ensure_default_connection_checked_once(settings)

    assert calls == [("test-key", "https://api.openai.com/v1", "gpt-4o")]

    checks_file = tmp_path / ".flavia" / ".connection_checks.yaml"
    data = yaml.safe_load(checks_file.read_text(encoding="utf-8"))
    assert "checks" in data
    assert len(data["checks"]) == 1


def test_startup_connection_check_uses_main_agent_model_override(monkeypatch, tmp_path):
    settings = _make_settings(
        tmp_path,
        default_model="openai:gpt-4o",
        agents_config={"main": {"model": "openai:gpt-4o"}},
    )
    captured: dict[str, str] = {}

    def _fake_test_provider_connection(api_key, api_base_url, model_id, headers=None):
        captured["model"] = model_id
        return True, "ok"

    monkeypatch.setattr(
        "flavia.setup.provider_wizard.test_provider_connection",
        _fake_test_provider_connection,
    )

    _ensure_default_connection_checked_once(settings)

    assert captured["model"] == "gpt-4o"
