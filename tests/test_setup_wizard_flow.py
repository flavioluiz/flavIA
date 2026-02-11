"""Tests for setup wizard AI flow."""

from pathlib import Path

import yaml

from flavia.config.settings import Settings
from flavia.setup_wizard import (
    create_setup_agent,
    _approve_subagents,
    _build_content_catalog,
    _run_full_reconfiguration,
    _run_ai_setup,
    _run_basic_setup,
    run_agent_setup_command,
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
        files = {}

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
    monkeypatch.setattr(
        "flavia.setup_wizard.safe_confirm", lambda *args, **kwargs: next(confirm_answers)
    )
    monkeypatch.setattr(
        "flavia.setup_wizard.safe_prompt", lambda *args, **kwargs: next(prompt_answers)
    )

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
    monkeypatch.setattr(
        "flavia.config.load_settings", lambda: Settings(default_model="hf:moonshotai/Kimi-K2.5")
    )
    monkeypatch.setattr(
        "flavia.setup_wizard._select_model_for_setup", lambda _settings: "openai:gpt-4o"
    )
    monkeypatch.setattr(
        "flavia.setup_wizard._test_selected_model_connection",
        lambda _settings, _model: (False, False),
    )
    monkeypatch.setattr("flavia.setup_wizard.find_binary_documents", lambda _directory: [])
    monkeypatch.setattr("flavia.setup_wizard._build_content_catalog", lambda *args, **kwargs: None)
    # Option "1" = simple config (no analysis) - mock q_select for the config choice menu
    monkeypatch.setattr("flavia.setup_wizard.q_select", lambda *args, **kwargs: "1")
    monkeypatch.setattr("flavia.setup_wizard.safe_confirm", lambda *args, **kwargs: False)

    def _fake_run_basic_setup(
        _target_dir,
        _config_dir,
        selected_model=None,
        main_agent_can_write=False,
        preserve_existing_providers=False,
        catalog_already_built=False,
    ):
        captured["model"] = selected_model
        captured["main_agent_can_write"] = main_agent_can_write
        captured["preserve"] = preserve_existing_providers
        captured["catalog_already_built"] = catalog_already_built
        return True

    monkeypatch.setattr("flavia.setup_wizard._run_basic_setup", _fake_run_basic_setup)

    assert run_setup_wizard(tmp_path) is True
    assert captured["model"] == "openai:gpt-4o"
    assert captured["main_agent_can_write"] is False
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

    # Answers: convert docs?, write capability?, include subagents?
    confirm_answers = iter([True, False, False])  # convert, read-only, no subagents

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "flavia.config.load_settings", lambda: Settings(default_model="openai:gpt-4o")
    )
    monkeypatch.setattr(
        "flavia.setup_wizard._select_model_for_setup", lambda _settings: "openai:gpt-4o"
    )
    monkeypatch.setattr(
        "flavia.setup_wizard._test_selected_model_connection",
        lambda _settings, _model: (False, False),
    )
    monkeypatch.setattr(
        "flavia.setup_wizard.safe_confirm", lambda *args, **kwargs: next(confirm_answers)
    )
    # Mock q_select to return "2" (analyze content)
    monkeypatch.setattr("flavia.setup_wizard.q_select", lambda *args, **kwargs: "2")
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
        main_agent_can_write=False,
        preserve_existing_providers=False,
        include_subagents=False,
        catalog=None,
    ):
        captured["selected_model"] = selected_model
        captured["convert_pdfs"] = convert_pdfs
        captured["pdf_files"] = pdf_files
        captured["user_guidance"] = user_guidance
        captured["main_agent_can_write"] = main_agent_can_write
        captured["preserve_existing_providers"] = preserve_existing_providers
        captured["include_subagents"] = include_subagents
        return True

    monkeypatch.setattr("flavia.setup_wizard._run_ai_setup", _fake_run_ai_setup)

    assert run_setup_wizard(tmp_path) is True
    assert captured["selected_model"] == "openai:gpt-4o"
    assert captured["convert_pdfs"] is True
    assert captured["pdf_files"] == ["papers/nested.pdf"]
    assert captured["main_agent_can_write"] is False
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

    # overwrite existing config, no summaries, no subagents, no guidance
    confirm_answers = iter([True, False, False, False])

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "flavia.config.load_settings", lambda: Settings(default_model="openai:gpt-4o")
    )
    monkeypatch.setattr(
        "flavia.setup_wizard._select_model_for_setup", lambda _settings: "openai:gpt-4o"
    )
    monkeypatch.setattr(
        "flavia.setup_wizard._test_selected_model_connection",
        lambda _settings, _model: (False, False),
    )
    monkeypatch.setattr("flavia.setup_wizard.find_binary_documents", lambda _directory: [])
    monkeypatch.setattr("flavia.setup_wizard._build_content_catalog", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "flavia.setup_wizard.safe_confirm", lambda *args, **kwargs: next(confirm_answers)
    )
    # Mock q_select to return "1" (simple config)
    monkeypatch.setattr("flavia.setup_wizard.q_select", lambda *args, **kwargs: "1")
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
                    '  context: "Você é um especialista em comparação acadêmica"\n'
                    "  tools:\n"
                    "    - read_file\n"
                    "  subagents:\n"
                    "    comparador:\n"
                    '      context: "Análise de pós-graduação acadêmica e profissional"\n'
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


def test_run_agent_setup_command_quick_mode_delegates_to_model_manager(monkeypatch, tmp_path):
    settings = Settings(default_model="openai:gpt-4o")
    captured: dict[str, object] = {}

    # Mock q_select to return "1" (quick mode)
    monkeypatch.setattr("flavia.setup_wizard.q_select", lambda *args, **kwargs: "1")

    def _fake_manage_agent_models(_settings, _base_dir):
        captured["settings"] = _settings
        captured["base_dir"] = _base_dir
        return True

    monkeypatch.setattr("flavia.setup.manage_agent_models", _fake_manage_agent_models)

    assert run_agent_setup_command(settings, tmp_path) is True
    assert captured["settings"] is settings
    assert captured["base_dir"] == tmp_path


def test_run_agent_setup_command_full_mode_delegates_to_full_reconfiguration(monkeypatch, tmp_path):
    settings = Settings(default_model="openai:gpt-4o")
    captured: dict[str, object] = {}

    # Mock q_select to return "3" (full mode)
    monkeypatch.setattr("flavia.setup_wizard.q_select", lambda *args, **kwargs: "3")

    def _fake_run_full(_settings, _base_dir):
        captured["settings"] = _settings
        captured["base_dir"] = _base_dir
        return True

    monkeypatch.setattr("flavia.setup_wizard._run_full_reconfiguration", _fake_run_full)

    assert run_agent_setup_command(settings, tmp_path) is True
    assert captured["settings"] is settings
    assert captured["base_dir"] == tmp_path


def test_run_agent_setup_command_revise_mode_delegates_to_agent_revision(
    monkeypatch, tmp_path
):
    settings = Settings(default_model="openai:gpt-4o")
    captured: dict[str, object] = {}

    # Mock q_select to return "2" (revise mode)
    monkeypatch.setattr("flavia.setup_wizard.q_select", lambda *args, **kwargs: "2")

    def _fake_run_revision(_settings, _base_dir):
        captured["settings"] = _settings
        captured["base_dir"] = _base_dir
        return True

    monkeypatch.setattr("flavia.setup_wizard._run_agent_revision", _fake_run_revision)

    assert run_agent_setup_command(settings, tmp_path) is True
    assert captured["settings"] is settings
    assert captured["base_dir"] == tmp_path


def test_run_agent_setup_command_returns_false_on_cancelled(monkeypatch, tmp_path):
    settings = Settings(default_model="openai:gpt-4o")
    # Mock q_select to return None (cancelled)
    monkeypatch.setattr("flavia.setup_wizard.q_select", lambda *args, **kwargs: None)

    assert run_agent_setup_command(settings, tmp_path) is False


def test_run_full_reconfiguration_skips_missing_steps_when_user_declines(monkeypatch, tmp_path):
    settings = Settings(default_model="openai:gpt-4o")
    build_calls: list[bool] = []
    summary_calls: list[str] = []

    confirm_answers = iter(
        [
            True,  # Step 1: Use this model (accept default)
            False,  # Step 2: Run missing steps (build catalog) — decline
            False,  # Step 3: include subagents
            False,  # Step 4: write capability (read-only)
            False,  # Step 5: add guidance
            True,  # Accept configuration
        ]
    )

    monkeypatch.setattr(
        "flavia.setup_wizard.safe_confirm", lambda *args, **kwargs: next(confirm_answers)
    )
    monkeypatch.setattr("flavia.setup_wizard._show_agents_preview", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "flavia.setup_wizard._test_selected_model_connection",
        lambda *args, **kwargs: (False, False),
    )
    monkeypatch.setattr(
        "flavia.setup_wizard._build_content_catalog",
        lambda *args, **kwargs: build_calls.append(True),
    )
    monkeypatch.setattr(
        "flavia.setup_wizard._run_summarization",
        lambda _catalog, _config_dir, _model: summary_calls.append(_model),
    )

    class FakeAgent:
        def run(self, task):
            _ = task
            config_dir = tmp_path / ".flavia"
            config_dir.mkdir(exist_ok=True)
            (config_dir / "agents.yaml").write_text(
                "main:\n  context: test\n  tools:\n    - read_file\n",
                encoding="utf-8",
            )
            return "done"

    monkeypatch.setattr(
        "flavia.setup_wizard.create_setup_agent",
        lambda *args, **kwargs: (FakeAgent(), None),
    )

    assert _run_full_reconfiguration(settings, tmp_path) is True
    assert build_calls == []
    assert summary_calls == []


def test_run_full_reconfiguration_can_generate_summaries_after_new_catalog(
    monkeypatch, tmp_path
):
    settings = Settings(default_model="openai:gpt-4o")
    summary_calls: list[str] = []
    build_calls: list[bool] = []

    confirm_answers = iter(
        [
            True,  # Step 1: Use this model (accept default)
            True,  # Step 2: Run missing steps (build catalog)
            True,  # Step 2: Generate summaries with LLM
            False,  # Step 3: include subagents
            False,  # Step 4: write capability (read-only)
            False,  # Step 5: add guidance
            True,  # Accept configuration
        ]
    )

    monkeypatch.setattr(
        "flavia.setup_wizard.safe_confirm", lambda *args, **kwargs: next(confirm_answers)
    )
    monkeypatch.setattr("flavia.setup_wizard._show_agents_preview", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "flavia.setup_wizard._test_selected_model_connection",
        lambda *args, **kwargs: (False, False),
    )

    class FakeCatalog:
        files = {}

    monkeypatch.setattr(
        "flavia.setup_wizard._build_content_catalog",
        lambda *args, **kwargs: (build_calls.append(True), FakeCatalog())[1],
    )
    monkeypatch.setattr(
        "flavia.setup_wizard._run_summarization",
        lambda _catalog, _config_dir, _model: summary_calls.append(_model),
    )

    class FakeAgent:
        def run(self, task):
            _ = task
            config_dir = tmp_path / ".flavia"
            config_dir.mkdir(exist_ok=True)
            (config_dir / "agents.yaml").write_text(
                "main:\n  context: test\n  tools:\n    - read_file\n",
                encoding="utf-8",
            )
            return "done"

    monkeypatch.setattr(
        "flavia.setup_wizard.create_setup_agent",
        lambda *args, **kwargs: (FakeAgent(), None),
    )

    assert _run_full_reconfiguration(settings, tmp_path) is True
    assert build_calls == [True]
    assert summary_calls == ["openai:gpt-4o"]


def test_run_full_reconfiguration_rebuild_fallback_without_questionary(monkeypatch, tmp_path):
    settings = Settings(default_model="openai:gpt-4o")
    build_calls: list[bool] = []

    # Make preparation appear complete
    pdf_path = tmp_path / "papers" / "nested.pdf"
    pdf_path.parent.mkdir(parents=True)
    pdf_path.write_text("dummy", encoding="utf-8")
    converted_md = tmp_path / ".converted" / "papers" / "nested.md"
    converted_md.parent.mkdir(parents=True)
    converted_md.write_text("# nested", encoding="utf-8")

    config_dir = tmp_path / ".flavia"
    config_dir.mkdir(exist_ok=True)
    (config_dir / "content_catalog.json").write_text("{}", encoding="utf-8")

    class FakeCatalog:
        class _Entry:
            summary = "ready"

        files = {"papers/nested.pdf": _Entry()}

        def get_files_needing_summary(self):
            return []

    monkeypatch.setattr(
        "flavia.content.catalog.ContentCatalog.load",
        lambda _config_dir: FakeCatalog(),
    )

    confirm_answers = iter(
        [
            True,  # Step 1: Use this model (accept default)
            True,  # Step 2: All complete -> Rebuild any? yes
            False,  # Step 3: include subagents
            False,  # Step 4: write capability (read-only)
            False,  # Step 5: add guidance
            True,  # Accept configuration
        ]
    )

    monkeypatch.setattr(
        "flavia.setup_wizard.safe_confirm", lambda *args, **kwargs: next(confirm_answers)
    )
    monkeypatch.setattr("flavia.setup_wizard._show_agents_preview", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "flavia.setup_wizard._test_selected_model_connection",
        lambda *args, **kwargs: (False, False),
    )
    monkeypatch.setattr("flavia.setup_wizard.safe_prompt", lambda *args, **kwargs: "2")
    monkeypatch.setattr(
        "flavia.setup_wizard._build_content_catalog",
        lambda *args, **kwargs: (build_calls.append(True), FakeCatalog())[1],
    )

    # Force rebuild selection to use fallback path.
    import builtins

    real_import = builtins.__import__

    def _block_questionary(name, *args, **kwargs):
        if name == "questionary":
            raise ImportError("mocked")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _block_questionary)

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

    assert _run_full_reconfiguration(settings, tmp_path) is True
    assert build_calls == [True]


def test_run_full_reconfiguration_uses_relative_pdf_paths_from_subfolders(monkeypatch, tmp_path):
    captured: dict[str, object] = {}
    settings = Settings(default_model="openai:gpt-4o")
    pdf_path = tmp_path / "papers" / "nested.pdf"
    pdf_path.parent.mkdir(parents=True)
    pdf_path.write_text("dummy", encoding="utf-8")

    confirm_answers = iter(
        [
            True,  # Step 1: Use this model (accept default)
            True,  # Step 2: Run missing steps (convert documents, build catalog)
            False,  # Step 2: Generate summaries with LLM
            False,  # Step 3: include subagents
            False,  # Step 4: write capability (read-only)
            False,  # Step 5: add guidance
            True,  # Accept configuration
        ]
    )

    monkeypatch.setattr(
        "flavia.setup_wizard.safe_confirm", lambda *args, **kwargs: next(confirm_answers)
    )
    monkeypatch.setattr("flavia.setup_wizard._show_agents_preview", lambda *args, **kwargs: None)
    monkeypatch.setattr("flavia.setup_wizard._build_content_catalog", lambda *args, **kwargs: None)

    class FakeAgent:
        def run(self, task):
            captured["task"] = task
            config_dir = tmp_path / ".flavia"
            config_dir.mkdir(exist_ok=True)
            (config_dir / "agents.yaml").write_text(
                "main:\n  context: test\n  tools:\n    - read_file\n",
                encoding="utf-8",
            )
            return "done"

    def _fake_create_setup_agent(
        _base_dir,
        include_pdf_tool=False,
        pdf_files=None,
        selected_model=None,
        model_override=None,
    ):
        captured["include_pdf_tool"] = include_pdf_tool
        captured["pdf_files"] = pdf_files
        captured["selected_model"] = selected_model
        captured["model_override"] = model_override
        return FakeAgent(), None

    monkeypatch.setattr("flavia.setup_wizard.create_setup_agent", _fake_create_setup_agent)
    monkeypatch.setattr(
        "flavia.setup_wizard._test_selected_model_connection",
        lambda *args, **kwargs: (False, False),
    )

    assert _run_full_reconfiguration(settings, tmp_path) is True
    assert captured["include_pdf_tool"] is True
    assert captured["pdf_files"] == ["papers/nested.pdf"]


def test_run_full_reconfiguration_skips_pdf_prompt_when_nested_converted_exists(
    monkeypatch, tmp_path
):
    asked: list[str] = []
    captured: dict[str, object] = {}
    settings = Settings(default_model="openai:gpt-4o")

    pdf_path = tmp_path / "papers" / "nested.pdf"
    pdf_path.parent.mkdir(parents=True)
    pdf_path.write_text("dummy", encoding="utf-8")

    converted_md = tmp_path / ".converted" / "papers" / "nested.md"
    converted_md.parent.mkdir(parents=True)
    converted_md.write_text("# nested", encoding="utf-8")

    def _fake_confirm(prompt, *args, **kwargs):
        asked.append(prompt)
        responses = {
            "Use this model or choose another?": True,
            "All preparation steps are complete. Rebuild any?": False,
            "Run missing steps (build catalog)?": False,
            "Include specialized subagents?": False,
            "Enable file-writing tools for main agent?": False,
            "Add guidance?": False,
            "\nAccept this configuration?": True,
        }
        for key, val in responses.items():
            if key in prompt:
                return val
        return False

    monkeypatch.setattr("flavia.setup_wizard.safe_confirm", _fake_confirm)
    monkeypatch.setattr("flavia.setup_wizard._show_agents_preview", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "flavia.setup_wizard._test_selected_model_connection",
        lambda *args, **kwargs: (False, False),
    )

    class FakeAgent:
        def run(self, task):
            _ = task
            config_dir = tmp_path / ".flavia"
            config_dir.mkdir(exist_ok=True)
            (config_dir / "agents.yaml").write_text(
                "main:\n  context: test\n  tools:\n    - read_file\n",
                encoding="utf-8",
            )
            return "done"

    def _fake_create_setup_agent(
        _base_dir,
        include_pdf_tool=False,
        pdf_files=None,
        selected_model=None,
        model_override=None,
    ):
        captured["include_pdf_tool"] = include_pdf_tool
        captured["pdf_files"] = pdf_files
        captured["selected_model"] = selected_model
        captured["model_override"] = model_override
        return FakeAgent(), None

    monkeypatch.setattr("flavia.setup_wizard.create_setup_agent", _fake_create_setup_agent)

    assert _run_full_reconfiguration(settings, tmp_path) is True
    assert captured["include_pdf_tool"] is False
    assert captured["pdf_files"] is None
    # Should not ask about converting PDFs since converted docs already exist
    assert "Convert PDFs to text first?" not in asked


def test_run_full_reconfiguration_aborts_when_subagent_approval_cannot_be_applied(
    monkeypatch, tmp_path
):
    settings = Settings(default_model="openai:gpt-4o")
    confirm_answers = iter(
        [
            True,  # Step 1: Use this model (accept default)
            False,  # Step 2: Run missing steps (build catalog) — decline
            True,  # Step 3: Include subagents
            False,  # Step 4: write capability (read-only)
            False,  # Step 5: Add guidance — decline
        ]
    )

    monkeypatch.setattr(
        "flavia.setup_wizard.safe_confirm", lambda *args, **kwargs: next(confirm_answers)
    )
    monkeypatch.setattr("flavia.setup_wizard._show_agents_preview", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "flavia.setup_wizard._approve_subagents", lambda *_args, **_kwargs: ["summarizer"]
    )
    monkeypatch.setattr(
        "flavia.setup_wizard._update_config_with_approved_subagents",
        lambda *_args, **_kwargs: False,
    )
    monkeypatch.setattr(
        "flavia.setup_wizard._test_selected_model_connection",
        lambda *args, **kwargs: (False, False),
    )

    class FakeAgent:
        def run(self, task):
            _ = task
            config_dir = tmp_path / ".flavia"
            config_dir.mkdir(exist_ok=True)
            (config_dir / "agents.yaml").write_text(
                (
                    "main:\n"
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
            return "done"

    monkeypatch.setattr(
        "flavia.setup_wizard.create_setup_agent",
        lambda *args, **kwargs: (FakeAgent(), None),
    )

    assert _run_full_reconfiguration(settings, tmp_path) is False


def test_approve_subagents_handles_non_string_tools(monkeypatch, tmp_path):
    """Test that _approve_subagents handles non-string tool values without crashing.

    Uses the fallback path (no questionary) with batch rejection to verify
    non-string tools are displayed correctly.
    """
    agents_file = tmp_path / "agents.yaml"
    agents_file.write_text(
        (
            "main:\n"
            "  context: test\n"
            "  subagents:\n"
            "    reviewer:\n"
            "      context: review\n"
            "      tools:\n"
            "        - read_file\n"
            "        - 123\n"
        ),
        encoding="utf-8",
    )

    # Force questionary import to fail so we use the fallback path
    import builtins

    _real_import = builtins.__import__

    def _block_questionary(name, *args, **kwargs):
        if name == "questionary":
            raise ImportError("mocked")
        return _real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _block_questionary)

    # Fallback path: "Accept all subagents?" -> No (reject all)
    monkeypatch.setattr("flavia.setup_wizard.safe_confirm", lambda *args, **kwargs: False)
    # Then "Enter numbers to remove" -> remove item 1
    monkeypatch.setattr("flavia.setup_wizard.safe_prompt", lambda *args, **kwargs: "1")

    approved = _approve_subagents(agents_file)
    assert approved == []
