"""Regression tests for multi-provider model selection and defaults."""

import argparse

from flavia.cli import apply_args_to_settings, main
from flavia.config.providers import ModelConfig, ProviderConfig, ProviderRegistry
from flavia.config.settings import Settings, load_settings
from flavia.setup.provider_wizard import _save_provider_config, run_provider_wizard


def _make_provider(provider_id: str, api_key: str, model_id: str) -> ProviderConfig:
    return ProviderConfig(
        id=provider_id,
        name=provider_id.title(),
        api_base_url=f"https://{provider_id}.example/v1",
        api_key=api_key,
        models=[ModelConfig(id=model_id, name=model_id, default=True)],
    )


def test_load_settings_respects_highest_priority_default_provider(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    monkeypatch.delenv("SYNTHETIC_API_KEY", raising=False)

    local_config = tmp_path / ".flavia"
    local_config.mkdir()
    (local_config / "providers.yaml").write_text(
        """
providers:
  openai:
    name: OpenAI
    api_base_url: https://api.openai.com/v1
    api_key: ${OPENAI_API_KEY}
    models:
      - id: gpt-4o
        name: GPT-4o
        default: true
default_provider: openai
""".strip()
        + "\n",
        encoding="utf-8",
    )

    settings = load_settings()

    assert settings.providers.default_provider_id == "openai"
    assert settings.providers.get_default_provider().id == "openai"
    assert settings.api_key == "openai-key"


def test_apply_args_uses_provider_index_when_registry_is_loaded():
    registry = ProviderRegistry(
        providers={
            "synthetic": _make_provider("synthetic", "synthetic-key", "hf:moonshotai/Kimi-K2.5"),
            "openai": _make_provider("openai", "openai-key", "gpt-4o"),
        },
        default_provider_id="synthetic",
    )
    settings = Settings(providers=registry, default_model="synthetic:hf:moonshotai/Kimi-K2.5")
    args = argparse.Namespace(verbose=False, model="1", depth=None, path=None)

    apply_args_to_settings(args, settings)

    assert settings.default_model == "openai:gpt-4o"


def test_apply_args_tolerates_partial_namespace():
    registry = ProviderRegistry(
        providers={
            "synthetic": _make_provider("synthetic", "synthetic-key", "hf:moonshotai/Kimi-K2.5"),
        },
        default_provider_id="synthetic",
    )
    settings = Settings(providers=registry, default_model="synthetic:hf:moonshotai/Kimi-K2.5")
    args = argparse.Namespace(verbose=False, model=None, depth=None, path=None)

    updated = apply_args_to_settings(args, settings)

    assert updated is settings
    assert settings.subagents_enabled is True
    assert settings.active_agent is None
    assert settings.parallel_workers == 4


def test_apply_args_rejects_non_positive_parallel_workers(capsys):
    settings = Settings(parallel_workers=4)
    args = argparse.Namespace(
        verbose=False,
        model=None,
        depth=None,
        path=None,
        parallel_workers=0,
    )

    apply_args_to_settings(args, settings)

    out = capsys.readouterr().out
    assert "--parallel-workers must be >= 1" in out
    assert settings.parallel_workers == 4


def test_main_checks_api_key_for_selected_provider(monkeypatch):
    run_cli_calls: list[str] = []
    args = argparse.Namespace(
        init=False,
        telegram=False,
        model="openai:gpt-4o",
        verbose=False,
        depth=None,
        path=None,
        list_models=False,
        list_tools=False,
        list_providers=False,
        setup_provider=False,
        setup_telegram=False,
        manage_provider=None,
        test_provider=None,
        config=False,
        version=False,
    )
    settings = Settings(
        api_key="",
        providers=ProviderRegistry(
            providers={
                "synthetic": _make_provider("synthetic", "", "hf:moonshotai/Kimi-K2.5"),
                "openai": _make_provider("openai", "openai-key", "gpt-4o"),
            },
            default_provider_id="synthetic",
        ),
        default_model="hf:moonshotai/Kimi-K2.5",
    )

    monkeypatch.setattr("flavia.cli.ensure_project_venv_and_reexec", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("flavia.cli.parse_args", lambda: args)
    monkeypatch.setattr("flavia.cli.load_settings", lambda: settings)
    monkeypatch.setattr("flavia.cli._ensure_default_connection_checked_once", lambda _settings: None)
    monkeypatch.setattr("flavia.interfaces.run_cli", lambda cfg: run_cli_calls.append(cfg.default_model))

    assert main() == 0
    assert run_cli_calls == ["openai:gpt-4o"]


def test_main_runs_setup_wizard_on_first_run_when_provider_key_is_missing(monkeypatch):
    args = argparse.Namespace(
        init=False,
        telegram=False,
        model=None,
        verbose=False,
        depth=None,
        path=None,
        list_models=False,
        list_tools=False,
        list_providers=False,
        setup_provider=False,
        setup_telegram=False,
        manage_provider=None,
        test_provider=None,
        config=False,
        version=False,
    )
    settings = Settings(
        api_key="",
        providers=ProviderRegistry(
            providers={
                "synthetic": _make_provider("synthetic", "", "hf:moonshotai/Kimi-K2.5"),
            },
            default_provider_id="synthetic",
        ),
        default_model="synthetic:hf:moonshotai/Kimi-K2.5",
    )
    wizard_runs: list[bool] = []

    monkeypatch.setattr("flavia.cli.ensure_project_venv_and_reexec", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("flavia.cli.parse_args", lambda: args)
    monkeypatch.setattr("flavia.cli.load_settings", lambda: settings)
    monkeypatch.setattr("flavia.cli._ensure_default_connection_checked_once", lambda _settings: None)
    monkeypatch.setattr("flavia.cli._should_offer_initial_setup", lambda: True)
    monkeypatch.setattr("flavia.setup_wizard.run_setup_wizard", lambda: wizard_runs.append(True) or True)
    monkeypatch.setattr("flavia.interfaces.run_cli", lambda _cfg: (_ for _ in ()).throw(RuntimeError("should not run")))

    assert main() == 0
    assert wizard_runs == [True]


def test_main_validates_main_agent_model_provider_key(monkeypatch, capsys):
    args = argparse.Namespace(
        init=False,
        telegram=False,
        model=None,
        verbose=False,
        depth=None,
        path=None,
        list_models=False,
        list_tools=False,
        list_providers=False,
        setup_provider=False,
        setup_telegram=False,
        manage_provider=None,
        test_provider=None,
        config=False,
        version=False,
    )
    settings = Settings(
        api_key="synthetic-key",
        providers=ProviderRegistry(
            providers={
                "synthetic": _make_provider("synthetic", "synthetic-key", "hf:moonshotai/Kimi-K2.5"),
                "openai": _make_provider("openai", "", "gpt-4o"),
            },
            default_provider_id="synthetic",
        ),
        default_model="synthetic:hf:moonshotai/Kimi-K2.5",
        agents_config={
            "main": {
                "context": "test",
                "model": "openai:gpt-4o",
                "tools": [],
            }
        },
    )

    monkeypatch.setattr("flavia.cli.ensure_project_venv_and_reexec", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("flavia.cli.parse_args", lambda: args)
    monkeypatch.setattr("flavia.cli.load_settings", lambda: settings)
    monkeypatch.setattr("flavia.cli._ensure_default_connection_checked_once", lambda _settings: None)
    monkeypatch.setattr("flavia.interfaces.run_cli", lambda _cfg: (_ for _ in ()).throw(RuntimeError("should not run")))

    assert main() == 1
    assert "provider 'openai'" in capsys.readouterr().out


def test_main_validates_promoted_subagent_model_provider_key(monkeypatch, capsys):
    args = argparse.Namespace(
        init=False,
        telegram=False,
        model=None,
        verbose=False,
        depth=None,
        path=None,
        no_subagents=False,
        agent="summarizer",
        parallel_workers=None,
        list_models=False,
        list_tools=False,
        list_providers=False,
        setup_provider=False,
        setup_telegram=False,
        manage_provider=None,
        test_provider=None,
        config=False,
        version=False,
    )
    settings = Settings(
        api_key="synthetic-key",
        providers=ProviderRegistry(
            providers={
                "synthetic": _make_provider("synthetic", "synthetic-key", "hf:moonshotai/Kimi-K2.5"),
                "openai": _make_provider("openai", "", "gpt-4o"),
            },
            default_provider_id="synthetic",
        ),
        default_model="synthetic:hf:moonshotai/Kimi-K2.5",
        agents_config={
            "main": {
                "context": "test",
                "model": "synthetic:hf:moonshotai/Kimi-K2.5",
                "tools": [],
                "subagents": {
                    "summarizer": {
                        "context": "summarize",
                        "model": "openai:gpt-4o",
                        "tools": [],
                    }
                },
            }
        },
    )

    monkeypatch.setattr("flavia.cli.ensure_project_venv_and_reexec", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("flavia.cli.parse_args", lambda: args)
    monkeypatch.setattr("flavia.cli.load_settings", lambda: settings)
    monkeypatch.setattr("flavia.cli._ensure_default_connection_checked_once", lambda _settings: None)
    monkeypatch.setattr("flavia.interfaces.run_cli", lambda _cfg: (_ for _ in ()).throw(RuntimeError("should not run")))

    assert main() == 1
    assert "provider 'openai'" in capsys.readouterr().out


def test_save_provider_config_uses_target_dir_for_local_location(tmp_path):
    target_dir = tmp_path / "project"
    target_dir.mkdir()

    output_path = _save_provider_config(
        provider_id="openai",
        provider_config={
            "name": "OpenAI",
            "api_base_url": "https://api.openai.com/v1",
            "api_key": "${OPENAI_API_KEY}",
            "models": [{"id": "gpt-4o", "name": "GPT-4o", "default": True}],
        },
        location="local",
        set_default=True,
        target_dir=target_dir,
    )

    assert output_path == target_dir / ".flavia" / "providers.yaml"
    assert output_path.exists()


def test_run_provider_wizard_loads_settings_from_target_dir(monkeypatch, tmp_path):
    project_a = tmp_path / "project-a"
    project_b = tmp_path / "project-b"
    project_a.mkdir()
    project_b.mkdir()

    providers_a = project_a / ".flavia"
    providers_b = project_b / ".flavia"
    providers_a.mkdir()
    providers_b.mkdir()

    (providers_a / "providers.yaml").write_text(
        (
            "providers:\n"
            "  from_a:\n"
            "    name: From A\n"
            "    api_base_url: https://a.example/v1\n"
            "    api_key: ${A_API_KEY}\n"
            "    models:\n"
            "      - id: model-a\n"
            "        name: Model A\n"
            "        default: true\n"
            "default_provider: from_a\n"
        ),
        encoding="utf-8",
    )
    (providers_b / "providers.yaml").write_text(
        (
            "providers:\n"
            "  from_b:\n"
            "    name: From B\n"
            "    api_base_url: https://b.example/v1\n"
            "    api_key: ${B_API_KEY}\n"
            "    models:\n"
            "      - id: model-b\n"
            "        name: Model B\n"
            "        default: true\n"
            "default_provider: from_b\n"
        ),
        encoding="utf-8",
    )

    monkeypatch.chdir(project_a)
    captured: dict[str, list[str]] = {}

    def _fake_select_provider_type(settings=None):
        captured["provider_ids"] = list(settings.providers.providers.keys())
        return None

    monkeypatch.setattr("flavia.setup.provider_wizard._select_provider_type", _fake_select_provider_type)

    assert run_provider_wizard(target_dir=project_b) is False
    assert "from_b" in captured["provider_ids"]
    assert "from_a" not in captured["provider_ids"]
