"""Regression tests for provider model management flows."""

import yaml

from flavia.config.providers import ModelConfig, ProviderConfig, ProviderRegistry
from flavia.config.settings import Settings
from flavia.setup.provider_wizard import (
    _collect_provider_choices,
    _models_source_for_provider,
    _save_provider_changes,
    _search_models,
    manage_provider_models,
    run_provider_wizard,
)


def _build_settings(models: list[ModelConfig]) -> Settings:
    provider = ProviderConfig(
        id="openai",
        name="OpenAI",
        api_base_url="https://api.openai.com/v1",
        api_key="test-key",
        models=models,
    )
    return Settings(
        providers=ProviderRegistry(
            providers={"openai": provider},
            default_provider_id="openai",
        )
    )


def test_manage_provider_add_model_handles_empty_model_list(monkeypatch):
    settings = _build_settings([])
    choices = iter(["a", "s"])
    saved: dict[str, object] = {}

    def _save_changes(_settings, _provider_id, provider):
        saved["models"] = list(provider.models)
        return True

    monkeypatch.setattr(
        "flavia.setup.provider_wizard.safe_prompt",
        lambda *args, **kwargs: next(choices),
    )
    monkeypatch.setattr(
        "flavia.setup.provider_wizard._add_custom_model",
        lambda: {"id": "gpt-4o", "name": "GPT-4o", "default": True},
    )
    monkeypatch.setattr(
        "flavia.setup.provider_wizard._save_provider_changes",
        _save_changes,
    )

    assert manage_provider_models(settings, "openai") is True
    assert len(saved["models"]) == 1
    assert isinstance(saved["models"][0], ModelConfig)
    assert saved["models"][0].id == "gpt-4o"
    assert saved["models"][0].default is True


def test_manage_provider_merge_fetch_keeps_model_objects(monkeypatch):
    settings = _build_settings([ModelConfig(id="gpt-4o", name="GPT-4o", default=True)])
    choices = iter(["f", "merge", "s"])
    saved: dict[str, object] = {}

    def _save_changes(_settings, _provider_id, provider):
        saved["models"] = list(provider.models)
        return True

    monkeypatch.setattr(
        "flavia.setup.provider_wizard.safe_prompt",
        lambda *args, **kwargs: next(choices),
    )
    monkeypatch.setattr(
        "flavia.setup.provider_wizard._fetch_models_for_provider",
        lambda _provider: [
            {"id": "gpt-4.1", "name": "GPT-4.1", "default": True},
            {"id": "gpt-4o", "name": "GPT-4o"},
        ],
    )
    monkeypatch.setattr(
        "flavia.setup.provider_wizard._save_provider_changes",
        _save_changes,
    )

    assert manage_provider_models(settings, "openai") is True
    assert len(saved["models"]) == 2
    assert all(isinstance(model, ModelConfig) for model in saved["models"])
    assert {model.id for model in saved["models"]} == {"gpt-4o", "gpt-4.1"}
    assert sum(1 for model in saved["models"] if model.default) == 1


def test_search_models_select_all_returns_all_matches(monkeypatch):
    models = [{"id": f"model-{idx}", "name": f"Model {idx}"} for idx in range(25)]
    answers = iter(["model", "a"])

    monkeypatch.setattr(
        "flavia.setup.provider_wizard.safe_prompt",
        lambda *args, **kwargs: next(answers),
    )

    selected = _search_models(models)

    assert len(selected) == 25


def test_models_source_for_provider_prefers_existing_configured_models():
    settings = Settings(
        providers=ProviderRegistry(
            providers={
                "synthetic": ProviderConfig(
                    id="synthetic",
                    name="Synthetic",
                    api_base_url="https://api.synthetic.new/openai/v1",
                    api_key="test-key",
                    models=[
                        ModelConfig(id="hf:deepseek-ai/DeepSeek-V3", name="DeepSeek-V3", default=True),
                        ModelConfig(id="hf:Qwen/Qwen3-235B-A22B-Instruct-2507", name="Qwen3-235B"),
                    ],
                )
            },
            default_provider_id="synthetic",
        )
    )

    models = _models_source_for_provider("synthetic", settings=settings)

    assert [m["id"] for m in models] == [
        "hf:deepseek-ai/DeepSeek-V3",
        "hf:Qwen/Qwen3-235B-A22B-Instruct-2507",
    ]
    assert models[0]["default"] is True


def test_collect_provider_choices_includes_existing_non_template_provider():
    settings = Settings(
        providers=ProviderRegistry(
            providers={
                "openai": ProviderConfig(
                    id="openai",
                    name="OpenAI",
                    api_base_url="https://api.openai.com/v1",
                    api_key="openai-key",
                    models=[ModelConfig(id="gpt-4o", name="GPT-4o", default=True)],
                ),
                "xai": ProviderConfig(
                    id="xai",
                    name="xAI",
                    api_base_url="https://api.x.ai/v1",
                    api_key="xai-key",
                    models=[ModelConfig(id="grok-2", name="Grok 2", default=True)],
                ),
            },
            default_provider_id="openai",
        )
    )

    choices = _collect_provider_choices(settings=settings)

    assert any(c["kind"] == "known" and c["provider_id"] == "openai" for c in choices)
    assert any(c["kind"] == "existing" and c["provider_id"] == "xai" for c in choices)


def test_save_provider_changes_creates_local_override_without_secret_leak(monkeypatch, tmp_path):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    monkeypatch.chdir(project_dir)

    home_dir = tmp_path / "home"
    home_dir.mkdir()
    monkeypatch.setenv("HOME", str(home_dir))

    user_config_dir = home_dir / ".config" / "flavia"
    user_config_dir.mkdir(parents=True)
    (user_config_dir / "providers.yaml").write_text(
        (
            "providers:\n"
            "  xai:\n"
            "    name: xAI\n"
            "    api_base_url: https://api.x.ai/v1\n"
            "    api_key: ${XAI_API_KEY}\n"
            "    headers:\n"
            "      X-App-Name: ${XAI_APP_NAME}\n"
            "    models:\n"
            "      - id: grok-2\n"
            "        name: Grok 2\n"
            "        default: true\n"
            "default_provider: xai\n"
        ),
        encoding="utf-8",
    )

    provider = ProviderConfig(
        id="xai",
        name="xAI",
        api_base_url="https://api.x.ai/v1",
        api_key="resolved-secret-value",
        api_key_env_var=None,
        headers={"X-App-Name": ""},
        models=[ModelConfig(id="grok-2", name="Grok 2", default=True)],
    )
    settings = Settings(
        providers=ProviderRegistry(
            providers={"xai": provider},
            default_provider_id="xai",
        )
    )

    prompts = iter(["1"])  # Save locally
    monkeypatch.setattr(
        "flavia.setup.provider_wizard.safe_prompt",
        lambda *args, **kwargs: next(prompts),
    )
    monkeypatch.setattr("flavia.setup.provider_wizard.safe_confirm", lambda *args, **kwargs: True)

    assert _save_provider_changes(settings, "xai", provider) is True

    local_file = project_dir / ".flavia" / "providers.yaml"
    data = yaml.safe_load(local_file.read_text(encoding="utf-8"))
    provider_data = data["providers"]["xai"]

    assert provider_data["api_key"] == "${XAI_API_KEY}"
    assert provider_data["api_key"] != "resolved-secret-value"
    assert provider_data["headers"]["X-App-Name"] == "${XAI_APP_NAME}"


def test_run_provider_wizard_uses_current_default_model_as_prompt_default(monkeypatch, tmp_path):
    settings = Settings(
        providers=ProviderRegistry(
            providers={
                "openai": ProviderConfig(
                    id="openai",
                    name="OpenAI",
                    api_base_url="https://api.openai.com/v1",
                    api_key="test-key",
                    models=[
                        ModelConfig(id="gpt-4o", name="GPT-4o", default=False),
                        ModelConfig(id="gpt-4o-mini", name="GPT-4o Mini", default=True),
                    ],
                )
            },
            default_provider_id="openai",
        )
    )
    captured: dict[str, str] = {}
    confirm_answers = iter([False, True])  # Skip connection test, set as default provider.

    monkeypatch.setattr("flavia.setup.provider_wizard._load_settings_for_target_dir", lambda _target_dir: settings)
    monkeypatch.setattr(
        "flavia.setup.provider_wizard._select_provider_type",
        lambda settings=None: {"kind": "known", "provider_id": "openai"},
    )
    monkeypatch.setattr(
        "flavia.setup.provider_wizard._get_api_key",
        lambda _provider_name, _default_env_var="": ("test-key", "${OPENAI_API_KEY}"),
    )
    monkeypatch.setattr(
        "flavia.setup.provider_wizard._select_models",
        lambda available_models, **kwargs: available_models,
    )
    monkeypatch.setattr("flavia.setup.provider_wizard._select_location", lambda **kwargs: "local")
    monkeypatch.setattr("flavia.setup.provider_wizard.safe_confirm", lambda *args, **kwargs: next(confirm_answers))
    monkeypatch.setattr(
        "flavia.setup.provider_wizard._save_provider_config",
        lambda *args, **kwargs: tmp_path / ".flavia" / "providers.yaml",
    )

    def _safe_prompt(prompt, *args, default="", **kwargs):
        if prompt == "Select default model":
            captured["default_choice"] = default
        return default

    monkeypatch.setattr("flavia.setup.provider_wizard.safe_prompt", _safe_prompt)

    assert run_provider_wizard(tmp_path) is True
    assert captured["default_choice"] == "2"
