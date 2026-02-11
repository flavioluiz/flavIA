"""Tests for CLI runtime model switching command."""

from flavia.config.providers import ModelConfig, ProviderConfig, ProviderRegistry
from flavia.config.settings import Settings
from flavia.interfaces import cli_interface


class _DummyAgent:
    def __init__(self, provider=None, model_id="dummy-model"):
        self.provider = provider
        self.model_id = model_id

    def run(self, _user_message: str) -> str:
        return "ok"


class _CaptureConsole:
    def __init__(self):
        self.lines: list[str] = []

    def print(self, *args, **_kwargs):
        self.lines.append(" ".join(str(a) for a in args))


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
    provider_id: str,
    model_id: str,
    api_key: str,
    name: str,
    api_key_env_var: str | None = None,
) -> ProviderConfig:
    return ProviderConfig(
        id=provider_id,
        name=name,
        api_base_url=f"https://{provider_id}.example/v1",
        api_key=api_key,
        api_key_env_var=api_key_env_var,
        models=[ModelConfig(id=model_id, name=model_id, default=True)],
    )


def _make_settings(tmp_path) -> Settings:
    return Settings(
        base_dir=tmp_path,
        default_model="synthetic:model-main",
        providers=ProviderRegistry(
            providers={
                "synthetic": _make_provider(
                    "synthetic", "model-main", api_key="synthetic-key", name="Synthetic"
                ),
                "openai": _make_provider("openai", "gpt-4o", api_key="openai-key", name="OpenAI"),
            },
            default_provider_id="synthetic",
        ),
        agents_config={
            "main": {
                "context": "Main context",
                "model": "synthetic:model-main",
                "tools": [],
                "subagents": {},
            }
        },
    )


def test_model_switch_rejects_unknown_model_reference(monkeypatch, tmp_path):
    settings = _make_settings(tmp_path)
    create_calls: list[str | int | None] = []

    def _fake_create_agent(configured_settings: Settings, model_override=None):
        create_calls.append(model_override)
        model_ref = model_override or configured_settings.agents_config["main"]["model"]
        provider, model = configured_settings.providers.resolve_model(model_ref)
        model_id = model.id if model else str(model_ref)
        return _DummyAgent(provider=provider, model_id=model_id)

    monkeypatch.setattr(cli_interface, "create_agent_from_settings", _fake_create_agent)

    printed = _run_cli_with_inputs(monkeypatch, settings, ["/model missing-model", "/quit"])

    assert create_calls == [None]
    assert settings.default_model == "synthetic:model-main"
    assert any("Model 'missing-model' not found." in line for line in printed)


def test_model_switch_rejects_out_of_range_index(monkeypatch, tmp_path):
    settings = _make_settings(tmp_path)
    create_calls: list[str | int | None] = []

    def _fake_create_agent(configured_settings: Settings, model_override=None):
        create_calls.append(model_override)
        model_ref = model_override or configured_settings.agents_config["main"]["model"]
        provider, model = configured_settings.providers.resolve_model(model_ref)
        model_id = model.id if model else str(model_ref)
        return _DummyAgent(provider=provider, model_id=model_id)

    monkeypatch.setattr(cli_interface, "create_agent_from_settings", _fake_create_agent)

    printed = _run_cli_with_inputs(monkeypatch, settings, ["/model 99", "/quit"])

    assert create_calls == [None]
    assert settings.default_model == "synthetic:model-main"
    assert any("Model '99' not found." in line for line in printed)


def test_model_switch_applies_runtime_override_even_with_main_agent_model(monkeypatch, tmp_path):
    settings = _make_settings(tmp_path)
    create_calls: list[str | int | None] = []

    def _fake_create_agent(configured_settings: Settings, model_override=None):
        create_calls.append(model_override)
        model_ref = model_override or configured_settings.agents_config["main"]["model"]
        provider, model = configured_settings.providers.resolve_model(model_ref)
        assert provider is not None
        assert model is not None
        return _DummyAgent(provider=provider, model_id=model.id)

    monkeypatch.setattr(cli_interface, "create_agent_from_settings", _fake_create_agent)

    printed = _run_cli_with_inputs(monkeypatch, settings, ["/model openai:gpt-4o", "/quit"])

    assert create_calls == [None, "openai:gpt-4o"]
    assert settings.default_model == "openai:gpt-4o"
    assert any("Switched to model 'openai:gpt-4o'. Conversation reset." in line for line in printed)


def test_model_switch_accepts_combined_index_reference(monkeypatch, tmp_path):
    settings = _make_settings(tmp_path)
    create_calls: list[str | int | None] = []

    def _fake_create_agent(configured_settings: Settings, model_override=None):
        create_calls.append(model_override)
        model_ref = model_override or configured_settings.agents_config["main"]["model"]
        provider, model = configured_settings.providers.resolve_model(model_ref)
        assert provider is not None
        assert model is not None
        return _DummyAgent(provider=provider, model_id=model.id)

    monkeypatch.setattr(cli_interface, "create_agent_from_settings", _fake_create_agent)

    printed = _run_cli_with_inputs(monkeypatch, settings, ["/model 1_openai:gpt-4o", "/quit"])

    assert create_calls == [None, "openai:gpt-4o"]
    assert settings.default_model == "openai:gpt-4o"
    assert any("Switched to model 'openai:gpt-4o'. Conversation reset." in line for line in printed)


def test_model_switch_rolls_back_default_model_on_agent_creation_failure(monkeypatch, tmp_path):
    settings = _make_settings(tmp_path)
    create_calls: list[str | int | None] = []

    def _fake_create_agent(configured_settings: Settings, model_override=None):
        create_calls.append(model_override)
        if model_override == "openai:gpt-4o":
            raise RuntimeError("boom")
        model_ref = model_override or configured_settings.agents_config["main"]["model"]
        provider, model = configured_settings.providers.resolve_model(model_ref)
        model_id = model.id if model else str(model_ref)
        return _DummyAgent(provider=provider, model_id=model_id)

    monkeypatch.setattr(cli_interface, "create_agent_from_settings", _fake_create_agent)

    printed = _run_cli_with_inputs(monkeypatch, settings, ["/model openai:gpt-4o", "/quit"])

    assert create_calls == [None, "openai:gpt-4o"]
    assert settings.default_model == "synthetic:model-main"
    assert any("Failed to switch to model 'openai:gpt-4o': boom" in line for line in printed)


def test_display_current_model_uses_active_agent_model_details(tmp_path):
    settings = _make_settings(tmp_path)
    provider = settings.providers.get_provider("openai")
    assert provider is not None

    agent = _DummyAgent(provider=provider, model_id="gpt-4o")
    capture_console = _CaptureConsole()

    cli_interface._display_current_model(agent, settings, capture_console)

    assert any("Provider:" in line and "(openai)" in line for line in capture_console.lines)
    assert any("Reference:" in line and "openai:gpt-4o" in line for line in capture_console.lines)
