"""Tests for setup wizard AI flow."""

from pathlib import Path

import yaml

from flavia.config.settings import Settings
from flavia.setup_wizard import (
    create_setup_agent,
    _build_content_catalog,
    _run_ai_setup,
    _run_basic_setup,
    run_setup_wizard,
)


def test_create_setup_agent_exposes_setup_tools(monkeypatch, tmp_path):
    monkeypatch.setenv("SYNTHETIC_API_KEY", "test-key")
    monkeypatch.chdir(tmp_path)

    agent, error = create_setup_agent(
        base_dir=tmp_path,
        include_pdf_tool=True,
        pdf_files=["paper.pdf"],
    )

    assert error is None
    tool_names = {schema["function"]["name"] for schema in agent.tool_schemas}
    assert "create_agents_config" in tool_names
    assert "convert_pdfs" in tool_names


def test_run_ai_setup_analyzes_content_without_conversion(monkeypatch, tmp_path):
    """Test that AI setup analyzes content (conversion is now done before calling _run_ai_setup)."""
    target_dir = tmp_path
    config_dir = tmp_path / ".flavia"
    config_dir.mkdir()
    calls: list[tuple[str, dict]] = []

    class FakeAgent:
        def run(self, task):
            calls.append(("run", {"task": task}))
            (config_dir / "agents.yaml").write_text(
                "main:\n  context: test\n  tools:\n    - read_file\n",
                encoding="utf-8",
            )
            return "done"

    monkeypatch.setattr(
        "flavia.setup_wizard.create_setup_agent",
        lambda *args, **kwargs: (FakeAgent(), None),
    )

    success = _run_ai_setup(
        target_dir=target_dir,
        config_dir=config_dir,
        convert_pdfs=True,  # Flag is passed but conversion already done
        pdf_files=["paper.pdf"],
        interactive_review=False,
    )

    assert success is True
    # Only run() is called, no convert_pdfs tool call (conversion done before)
    assert len(calls) == 1
    assert calls[0][0] == "run"


def test_run_ai_setup_builds_catalog_when_not_prebuilt(monkeypatch, tmp_path):
    target_dir = tmp_path
    config_dir = tmp_path / ".flavia"
    config_dir.mkdir()
    catalog_build_calls: list[bool] = []

    class FakeAgent:
        def run(self, task):
            _ = task
            (config_dir / "agents.yaml").write_text(
                "main:\n  context: test\n  tools:\n    - read_file\n",
                encoding="utf-8",
            )
            return "done"

    class FakeCatalog:
        pass

    monkeypatch.setattr(
        "flavia.setup_wizard.create_setup_agent",
        lambda *args, **kwargs: (FakeAgent(), None),
    )
    monkeypatch.setattr(
        "flavia.setup_wizard._build_content_catalog",
        lambda *args, **kwargs: (catalog_build_calls.append(True), FakeCatalog())[1],
    )

    success = _run_ai_setup(
        target_dir=target_dir,
        config_dir=config_dir,
        convert_pdfs=False,
        interactive_review=False,
        catalog=None,
    )

    assert success is True
    assert len(catalog_build_calls) == 1


def test_run_ai_setup_allows_user_revision_and_regenerates(monkeypatch, tmp_path):
    target_dir = tmp_path
    config_dir = tmp_path / ".flavia"
    config_dir.mkdir()
    run_tasks: list[str] = []

    class FakeAgent:
        def __init__(self):
            self.calls = 0

        def run(self, task):
            self.calls += 1
            run_tasks.append(task)
            if self.calls == 1:
                (config_dir / "agents.yaml").write_text(
                    "main:\n  context: first draft\n  tools:\n    - read_file\n",
                    encoding="utf-8",
                )
            else:
                (config_dir / "agents.yaml").write_text(
                    "main:\n  context: revised draft\n  tools:\n    - read_file\n    - search_files\n",
                    encoding="utf-8",
                )
            return "proposal ready"

    confirm_answers = iter([False, False, True])  # reject, don't use default, then accept
    prompt_answers = iter(["Inclua um subagente de resumos e citações"])

    monkeypatch.setattr(
        "flavia.setup_wizard.create_setup_agent",
        lambda *args, **kwargs: (FakeAgent(), None),
    )
    monkeypatch.setattr("flavia.setup_wizard.safe_confirm", lambda *args, **kwargs: next(confirm_answers))
    monkeypatch.setattr("flavia.setup_wizard.safe_prompt", lambda *args, **kwargs: next(prompt_answers))

    success = _run_ai_setup(
        target_dir=target_dir,
        config_dir=config_dir,
        convert_pdfs=False,
        user_guidance="Foco em análise para alunos de graduação.",
        interactive_review=True,
    )

    assert success is True
    assert len(run_tasks) == 2
    assert "User guidance" in run_tasks[0]
    assert "Revision feedback from user" in run_tasks[1]
    assert "Inclua um subagente de resumos e citações" in run_tasks[1]


def test_run_ai_setup_preserves_existing_providers_when_requested(monkeypatch, tmp_path):
    target_dir = tmp_path
    config_dir = tmp_path / ".flavia"
    config_dir.mkdir()
    existing_providers = (
        "providers:\n"
        "  openrouter:\n"
        "    name: OpenRouter\n"
        "    api_base_url: https://openrouter.ai/api/v1\n"
        "    api_key: ${OPENROUTER_API_KEY}\n"
        "    models:\n"
        "      - id: openai/gpt-4o-mini\n"
        "        name: GPT-4o Mini\n"
        "        default: true\n"
        "default_provider: openrouter\n"
    )
    (config_dir / "providers.yaml").write_text(existing_providers, encoding="utf-8")

    class FakeAgent:
        def run(self, task):
            _ = task
            (config_dir / "agents.yaml").write_text(
                "main:\n  context: test\n  tools:\n    - read_file\n",
                encoding="utf-8",
            )
            return "done"

    monkeypatch.setattr(
        "flavia.setup_wizard.create_setup_agent",
        lambda *args, **kwargs: (FakeAgent(), None),
    )

    success = _run_ai_setup(
        target_dir=target_dir,
        config_dir=config_dir,
        selected_model="openai:gpt-4o",
        convert_pdfs=False,
        interactive_review=False,
        preserve_existing_providers=True,
        include_subagents=False,
        catalog=None,
    )

    assert success is True
    assert (config_dir / "providers.yaml").read_text(encoding="utf-8") == existing_providers


def test_run_basic_setup_writes_selected_model_to_env_and_agents(tmp_path):
    config_dir = tmp_path / ".flavia"

    success = _run_basic_setup(tmp_path, config_dir, selected_model="openai:gpt-4o")

    assert success is True
    env_text = (config_dir / ".env").read_text(encoding="utf-8")
    assert "DEFAULT_MODEL=openai:gpt-4o" in env_text

    agents_data = yaml.safe_load((config_dir / "agents.yaml").read_text(encoding="utf-8"))
    assert agents_data["main"]["model"] == "openai:gpt-4o"
    assert agents_data["main"]["subagents"]["summarizer"]["model"] == "openai:gpt-4o"
    assert agents_data["main"]["subagents"]["explainer"]["model"] == "openai:gpt-4o"
    assert agents_data["main"]["subagents"]["researcher"]["model"] == "openai:gpt-4o"

    providers_data = yaml.safe_load((config_dir / "providers.yaml").read_text(encoding="utf-8"))
    assert providers_data["default_provider"] == "openai"
    assert "openai" in providers_data["providers"]
    assert providers_data["providers"]["openai"]["models"][0]["id"] == "gpt-4o"


def test_run_setup_wizard_passes_selected_model_to_basic_setup(monkeypatch, tmp_path):
    captured: dict[str, object] = {}

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("flavia.config.load_settings", lambda: Settings(default_model="hf:moonshotai/Kimi-K2.5"))
    monkeypatch.setattr("flavia.setup_wizard._select_model_for_setup", lambda _settings: "openai:gpt-4o")
    monkeypatch.setattr("flavia.setup_wizard._test_selected_model_connection", lambda _settings, _model: (False, False))
    monkeypatch.setattr("flavia.setup_wizard.find_binary_documents", lambda _directory: [])
    monkeypatch.setattr("flavia.setup_wizard._build_content_catalog", lambda *args, **kwargs: None)
    # Option "1" = simple config (no analysis)
    monkeypatch.setattr("flavia.setup_wizard.safe_prompt", lambda *args, **kwargs: "1")
    monkeypatch.setattr("flavia.setup_wizard.safe_confirm", lambda *args, **kwargs: False)

    def _fake_run_basic_setup(
        _target_dir,
        _config_dir,
        selected_model=None,
        preserve_existing_providers=False,
        catalog_already_built=False,
    ):
        captured["model"] = selected_model
        captured["preserve"] = preserve_existing_providers
        captured["catalog_already_built"] = catalog_already_built
        return True

    monkeypatch.setattr("flavia.setup_wizard._run_basic_setup", _fake_run_basic_setup)

    assert run_setup_wizard(tmp_path) is True
    assert captured["model"] == "openai:gpt-4o"
    assert captured["preserve"] is False
    assert captured["catalog_already_built"] is False


def test_build_content_catalog_continues_on_conversion_error(monkeypatch, tmp_path):
    target_dir = tmp_path
    config_dir = tmp_path / ".flavia"
    config_dir.mkdir()
    pdf_file = tmp_path / "broken.pdf"
    pdf_file.write_text("not a real pdf", encoding="utf-8")

    def _raise_conversion_error(self, _source_path, _output_dir):
        raise RuntimeError("conversion exploded")

    monkeypatch.setattr(
        "flavia.content.converters.PdfConverter.convert",
        _raise_conversion_error,
    )

    catalog = _build_content_catalog(
        target_dir,
        config_dir,
        convert_docs=True,
        binary_docs=[pdf_file],
    )

    assert catalog is not None
    assert "broken.pdf" in catalog.files
    assert (config_dir / "content_catalog.json").exists()


def test_run_basic_setup_preserves_existing_providers_when_requested(tmp_path):
    config_dir = tmp_path / ".flavia"
    config_dir.mkdir()
    existing_providers = (
        "providers:\n"
        "  openrouter:\n"
        "    name: OpenRouter\n"
        "    api_base_url: https://openrouter.ai/api/v1\n"
        "    api_key: ${OPENROUTER_API_KEY}\n"
        "    models:\n"
        "      - id: anthropic/claude-3.7-sonnet\n"
        "        name: Claude 3.7 Sonnet\n"
        "        default: true\n"
        "default_provider: openrouter\n"
    )
    (config_dir / "providers.yaml").write_text(existing_providers, encoding="utf-8")

    success = _run_basic_setup(
        tmp_path,
        config_dir,
        selected_model="openai:gpt-4o",
        preserve_existing_providers=True,
    )

    assert success is True
    assert (config_dir / "providers.yaml").read_text(encoding="utf-8") == existing_providers


def test_run_setup_wizard_passes_relative_pdf_paths_from_subfolders(monkeypatch, tmp_path):
    captured: dict[str, object] = {}
    pdf_path = tmp_path / "papers" / "nested.pdf"
    pdf_path.parent.mkdir(parents=True)
    pdf_path.write_text("dummy", encoding="utf-8")

    # Answers: convert docs?, generate summaries?, config choice "2", include subagents?
    confirm_answers = iter([True, False, False])  # convert, no summaries, no subagents
    prompt_answers = iter(["2"])  # analyze content

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("flavia.config.load_settings", lambda: Settings(default_model="openai:gpt-4o"))
    monkeypatch.setattr("flavia.setup_wizard._select_model_for_setup", lambda _settings: "openai:gpt-4o")
    monkeypatch.setattr("flavia.setup_wizard._test_selected_model_connection", lambda _settings, _model: (False, False))
    monkeypatch.setattr("flavia.setup_wizard.safe_confirm", lambda *args, **kwargs: next(confirm_answers))
    monkeypatch.setattr("flavia.setup_wizard.safe_prompt", lambda *args, **kwargs: next(prompt_answers))
    monkeypatch.setattr("flavia.setup_wizard._ask_user_guidance", lambda: "")

    # Mock catalog build to avoid actual file scanning
    class FakeCatalog:
        def get_files_needing_summary(self):
            return []

    monkeypatch.setattr(
        "flavia.setup_wizard._build_content_catalog",
        lambda *args, **kwargs: FakeCatalog(),
    )

    def _fake_run_ai_setup(
        _target_dir,
        _config_dir,
        selected_model=None,
        convert_pdfs=False,
        pdf_files=None,
        user_guidance="",
        preserve_existing_providers=False,
        include_subagents=False,
        catalog=None,
    ):
        captured["selected_model"] = selected_model
        captured["convert_pdfs"] = convert_pdfs
        captured["pdf_files"] = pdf_files
        captured["user_guidance"] = user_guidance
        captured["preserve_existing_providers"] = preserve_existing_providers
        captured["include_subagents"] = include_subagents
        return True

    monkeypatch.setattr("flavia.setup_wizard._run_ai_setup", _fake_run_ai_setup)

    assert run_setup_wizard(tmp_path) is True
    assert captured["selected_model"] == "openai:gpt-4o"
    assert captured["convert_pdfs"] is True
    assert captured["pdf_files"] == ["papers/nested.pdf"]
    assert captured["include_subagents"] is False




def test_run_setup_wizard_preserves_existing_providers_on_overwrite(monkeypatch, tmp_path):
    config_dir = tmp_path / ".flavia"
    config_dir.mkdir()
    existing_providers = (
        "providers:\n"
        "  openai:\n"
        "    name: OpenAI\n"
        "    api_base_url: https://api.openai.com/v1\n"
        "    api_key: ${OPENAI_API_KEY}\n"
        "    models:\n"
        "      - id: gpt-4o\n"
        "        name: GPT-4o\n"
        "        default: true\n"
        "default_provider: openai\n"
    )
    (config_dir / "providers.yaml").write_text(existing_providers, encoding="utf-8")
    (config_dir / ".env").write_text("SYNTHETIC_API_KEY=old\n", encoding="utf-8")
    (config_dir / "agents.yaml").write_text("main:\n  context: old\n", encoding="utf-8")

    confirm_answers = iter([True, False])  # overwrite existing config, no summaries

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("flavia.config.load_settings", lambda: Settings(default_model="openai:gpt-4o"))
    monkeypatch.setattr("flavia.setup_wizard._select_model_for_setup", lambda _settings: "openai:gpt-4o")
    monkeypatch.setattr("flavia.setup_wizard._test_selected_model_connection", lambda _settings, _model: (False, False))
    monkeypatch.setattr("flavia.setup_wizard.find_binary_documents", lambda _directory: [])
    monkeypatch.setattr("flavia.setup_wizard._build_content_catalog", lambda *args, **kwargs: None)
    monkeypatch.setattr("flavia.setup_wizard.safe_confirm", lambda *args, **kwargs: next(confirm_answers))
    monkeypatch.setattr("flavia.setup_wizard.safe_prompt", lambda *args, **kwargs: "1")  # simple config
    monkeypatch.setattr("flavia.setup_wizard._offer_provider_setup", lambda _config_dir: None)

    assert run_setup_wizard(tmp_path) is True
    assert (config_dir / "providers.yaml").read_text(encoding="utf-8") == existing_providers
    assert (config_dir / ".env").exists()
    assert (config_dir / "agents.yaml").exists()


def test_run_ai_setup_backfills_subagent_models_with_selected_default(monkeypatch, tmp_path):
    target_dir = tmp_path
    config_dir = tmp_path / ".flavia"
    config_dir.mkdir()

    class FakeAgent:
        def run(self, task):
            _ = task
            (config_dir / "agents.yaml").write_text(
                (
                    "main:\n"
                    "  context: test\n"
                    "  tools:\n"
                    "    - read_file\n"
                    "  subagents:\n"
                    "    helper:\n"
                    "      context: helper\n"
                    "      tools:\n"
                    "        - read_file\n"
                ),
                encoding="utf-8",
            )
            return "done"

    monkeypatch.setattr(
        "flavia.setup_wizard.create_setup_agent",
        lambda *args, **kwargs: (FakeAgent(), None),
    )

    success = _run_ai_setup(
        target_dir=target_dir,
        config_dir=config_dir,
        selected_model="openai:gpt-4o",
        convert_pdfs=False,
        interactive_review=False,
        include_subagents=True,
        catalog=None,
    )

    assert success is True
    agents_data = yaml.safe_load((config_dir / "agents.yaml").read_text(encoding="utf-8"))
    assert agents_data["main"]["model"] == "openai:gpt-4o"
    assert agents_data["main"]["subagents"]["helper"]["model"] == "openai:gpt-4o"


def test_run_ai_setup_preserves_portuguese_accents_in_agents_yaml(monkeypatch, tmp_path):
    target_dir = tmp_path
    config_dir = tmp_path / ".flavia"
    config_dir.mkdir()

    class FakeAgent:
        def run(self, task):
            _ = task
            (config_dir / "agents.yaml").write_text(
                (
                    "main:\n"
                    "  context: \"Você é um especialista em comparação acadêmica\"\n"
                    "  tools:\n"
                    "    - read_file\n"
                    "  subagents:\n"
                    "    comparador:\n"
                    "      context: \"Análise de pós-graduação acadêmica e profissional\"\n"
                    "      tools:\n"
                    "        - read_file\n"
                ),
                encoding="utf-8",
            )
            return "done"

    monkeypatch.setattr(
        "flavia.setup_wizard.create_setup_agent",
        lambda *args, **kwargs: (FakeAgent(), None),
    )

    success = _run_ai_setup(
        target_dir=target_dir,
        config_dir=config_dir,
        selected_model="openai:gpt-4o",
        convert_pdfs=False,
        interactive_review=False,
        include_subagents=True,
        catalog=None,
    )

    assert success is True
    content = (config_dir / "agents.yaml").read_text(encoding="utf-8")
    assert "Você é um especialista em comparação acadêmica" in content
    assert "Análise de pós-graduação acadêmica e profissional" in content
    assert "Voc\\xEA" not in content
