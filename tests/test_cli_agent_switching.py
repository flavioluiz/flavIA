"""Tests for CLI runtime agent switching command."""

from flavia.config.providers import ModelConfig, ProviderConfig, ProviderRegistry
from flavia.config.settings import Settings
from flavia.interfaces import cli_interface


class _DummyAgent:
    provider = None
    model_id = "dummy-model"

    def run(self, _user_message: str) -> str:
        return "ok"


def _run_cli_with_inputs(monkeypatch, settings: Settings, inputs: list[str]) -> list[str]:
    input_iter = iter(inputs)
    printed: list[str] = []

    monkeypatch.setattr(cli_interface, "print_welcome", lambda _settings: None)
    monkeypatch.setattr(cli_interface, "_configure_prompt_history", lambda _history_file: False)
    monkeypatch.setattr(cli_interface, "_print_active_model_hint", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        cli_interface,
        "_read_user_input",
        lambda _history_enabled, _active_agent=None: next(input_iter),
    )
    monkeypatch.setattr(
        cli_interface.console,
        "print",
        lambda *args, **_kwargs: printed.append(" ".join(str(a) for a in args)),
    )

    cli_interface.run_cli(settings)
    return printed


def _make_provider(
    provider_id: str, model_id: str, api_key: str, api_key_env_var: str | None = None
) -> ProviderConfig:
    return ProviderConfig(
        id=provider_id,
        name=provider_id.title(),
        api_base_url=f"https://{provider_id}.example/v1",
        api_key=api_key,
        api_key_env_var=api_key_env_var,
        models=[ModelConfig(id=model_id, name=model_id, default=True)],
    )


def test_agent_switch_changes_active_agent(monkeypatch, tmp_path):
    settings = Settings(
        base_dir=tmp_path,
        default_model="synthetic:model-main",
        providers=ProviderRegistry(
            providers={
                "synthetic": _make_provider("synthetic", "model-main", api_key="synthetic-key"),
                "openai": _make_provider("openai", "gpt-4o", api_key="openai-key"),
            },
            default_provider_id="synthetic",
        ),
        agents_config={
            "main": {
                "context": "Main context",
                "model": "synthetic:model-main",
                "tools": [],
                "subagents": {
                    "summarizer": {
                        "context": "Summarizer context",
                        "model": "openai:gpt-4o",
                        "tools": [],
                    }
                },
            }
        },
    )
    create_calls: list[str | None] = []

    def _fake_create_agent(configured_settings: Settings):
        create_calls.append(configured_settings.active_agent)
        return _DummyAgent()

    monkeypatch.setattr(cli_interface, "create_agent_from_settings", _fake_create_agent)

    printed = _run_cli_with_inputs(monkeypatch, settings, ["/agent summarizer", "/quit"])

    assert create_calls == [None, "summarizer"]
    assert settings.active_agent == "summarizer"
    assert any("Switched to agent 'summarizer'" in line for line in printed)


def test_agent_switch_rejects_provider_without_api_key(monkeypatch, tmp_path):
    settings = Settings(
        base_dir=tmp_path,
        default_model="synthetic:model-main",
        providers=ProviderRegistry(
            providers={
                "synthetic": _make_provider("synthetic", "model-main", api_key="synthetic-key"),
                "openai": _make_provider(
                    "openai",
                    "gpt-4o",
                    api_key="",
                    api_key_env_var="OPENAI_API_KEY",
                ),
            },
            default_provider_id="synthetic",
        ),
        agents_config={
            "main": {
                "context": "Main context",
                "model": "synthetic:model-main",
                "tools": [],
                "subagents": {
                    "summarizer": {
                        "context": "Summarizer context",
                        "model": "openai:gpt-4o",
                        "tools": [],
                    }
                },
            }
        },
    )
    create_calls: list[str | None] = []

    def _fake_create_agent(configured_settings: Settings):
        create_calls.append(configured_settings.active_agent)
        return _DummyAgent()

    monkeypatch.setattr(cli_interface, "create_agent_from_settings", _fake_create_agent)

    printed = _run_cli_with_inputs(monkeypatch, settings, ["/agent summarizer", "/quit"])

    assert create_calls == [None]
    assert settings.active_agent is None
    assert any("Cannot switch to 'summarizer'" in line for line in printed)
    assert any("OPENAI_API_KEY" in line for line in printed)


def test_agent_command_without_args_lists_available_agents(monkeypatch, tmp_path):
    settings = Settings(base_dir=tmp_path)
    settings.agents_config = {
        "main": {
            "context": "Main context",
            "tools": [],
            "subagents": {"reviewer": {"context": "Review context", "tools": []}},
        }
    }
    calls: list[tuple[Settings, bool]] = []

    def _fake_create_agent(_configured_settings: Settings):
        return _DummyAgent()

    def _fake_display_agents(configured_settings: Settings, console=None, use_rich=True):
        _ = console
        calls.append((configured_settings, use_rich))

    monkeypatch.setattr(cli_interface, "create_agent_from_settings", _fake_create_agent)
    monkeypatch.setattr("flavia.display.display_agents", _fake_display_agents)

    _run_cli_with_inputs(monkeypatch, settings, ["/agent", "/quit"])

    assert calls == [(settings, True)]
