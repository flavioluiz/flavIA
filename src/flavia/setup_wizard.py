"""Setup wizard for initializing flavIA configuration."""

import shutil
import sys
from pathlib import Path
from typing import Optional, List, Any

import yaml
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.table import Table

from flavia.setup.prompt_utils import safe_confirm, safe_prompt

console = Console()
MAX_SETUP_REVISIONS = 5


# System prompt for the setup agent
SETUP_AGENT_CONTEXT = """You are a setup assistant for flavIA, an AI assistant focused on academic and research work.

Your task is to analyze the user's directory and create an appropriate agents.yaml configuration.

## Your Process:

1. **Check for converted documents**: Look in the 'converted/' directory for .md or .txt files
2. **Explore the directory**: Use list_files to understand the structure
3. **Identify key files**: Look for README, converted documents, papers, notes
4. **Read important files**: Read converted documents to understand the subject matter
5. **Design agents**: Based on your analysis, design:
   - A main agent specialized for the content (research topic, course, subject area)
   - Optional specialist subagents for specific tasks

## Guidelines for Agent Design:

For academic/research projects, consider:
- What is the subject area? (physics, biology, history, computer science, etc.)
- What type of documents are these? (papers, textbooks, notes, articles)
- What tasks would be helpful? (summarizing, explaining concepts, finding citations, comparing arguments)

The main agent context should:
- Describe the subject area and type of content
- Specify how the agent should help (research assistant, tutor, etc.)
- Mention the working directory via {base_dir}

Common academic subagent patterns:
- `summarizer`: Creates concise summaries of papers/chapters
- `explainer`: Explains complex concepts in simpler terms
- `citation_finder`: Finds relevant quotes and references
- `comparator`: Compares arguments or findings across documents
- `quiz_maker`: Creates study questions from the material

Available tools:
- read_file: Read file contents
- list_files: List directory contents
- search_files: Search for patterns in files
- get_file_info: Get file metadata
- query_catalog: Search the content catalog for files by name, type, or content
- get_catalog_summary: Get a high-level overview of the project content
- spawn_agent: Create dynamic sub-agents
- spawn_predefined_agent: Use predefined subagents

## Final Step:

After analyzing, use `create_agents_config` to create the configuration.
Include a project_description that captures the academic subject/purpose.

Be concise in your analysis. Create a useful configuration for academic work.
"""


SETUP_AGENT_CONTEXT_WITH_PDFS = """You are a setup assistant for flavIA, an AI assistant focused on academic and research work.

Your task is to:
1. Convert PDF documents to text format
2. Analyze the content
3. Create an appropriate agents.yaml configuration

## Step 1: Convert PDFs

First, use the `convert_pdfs` tool to convert the PDF files to markdown format.
This will make them searchable and readable by the agent.

PDF files to convert: {pdf_files}

Use output_format="md" and preserve_structure=true for best results.

## Step 2: Analyze Content

After conversion:
1. List files in the 'converted/' directory
2. Read a few converted files to understand the subject matter
3. Identify the academic topic, document types, and potential use cases

## Step 3: Design Agents

Based on your analysis, design:
- A main agent specialized for the content (research topic, course, subject)
- Specialist subagents for specific academic tasks

Consider:
- What subject area is this? (physics, biology, law, literature, etc.)
- What type of documents? (papers, textbooks, lecture notes, articles)
- What tasks would help? (summarizing, explaining, finding citations, etc.)

Common academic subagent patterns:
- `summarizer`: Summarizes papers/chapters
- `explainer`: Explains complex concepts simply
- `citation_finder`: Finds quotes and references
- `comparator`: Compares arguments across documents
- `quiz_maker`: Creates study questions

## Final Step:

Use `create_agents_config` to create the configuration with:
- A descriptive context mentioning the subject area
- Appropriate tools for research work
- Helpful specialist subagents

Include a project_description that captures the academic subject.
"""


def find_pdf_files(directory: Path) -> List[Path]:
    """Find all PDF files in a directory (recursive)."""
    return sorted(
        (path for path in directory.rglob("*") if path.is_file() and path.suffix.lower() == ".pdf"),
        key=lambda path: str(path),
    )


def _pdf_paths_for_tools(base_dir: Path, pdf_files: List[Path]) -> List[str]:
    """Build path references for tool calls, preserving subdirectory structure."""
    refs: list[str] = []
    for pdf in pdf_files:
        try:
            refs.append(str(pdf.relative_to(base_dir)))
        except ValueError:
            refs.append(str(pdf))
    return refs


def create_setup_agent(
    base_dir: Path,
    include_pdf_tool: bool = False,
    pdf_files: List[str] = None,
    selected_model: Optional[str] = None,
):
    """Create the setup agent with special tools."""
    from flavia.config import load_settings
    from flavia.agent import RecursiveAgent, AgentProfile
    from flavia.tools.registry import registry
    from flavia.tools.setup.create_agents_config import CreateAgentsConfigTool
    from flavia.tools.setup.convert_pdfs import ConvertPdfsTool

    # Load settings
    settings = load_settings()
    model_ref = selected_model or settings.default_model

    # Check API key availability (providers or legacy)
    selected_provider, _ = settings.resolve_model_with_provider(model_ref)
    if selected_provider is not None:
        if not selected_provider.api_key:
            env_hint = (
                f" Set {selected_provider.api_key_env_var} and try again."
                if selected_provider.api_key_env_var
                else ""
            )
            return None, f"API key not configured for provider '{selected_provider.id}'.{env_hint}"
    elif not settings.api_key:
        return None, "API key not configured. Please set SYNTHETIC_API_KEY environment variable."

    # Register setup tools
    registry.register(CreateAgentsConfigTool())

    tools = [
        "read_file",
        "list_files",
        "search_files",
        "get_file_info",
        "create_agents_config",
    ]

    # Add PDF conversion tool if needed
    if include_pdf_tool:
        registry.register(ConvertPdfsTool())
        tools.append("convert_pdfs")
        context = SETUP_AGENT_CONTEXT_WITH_PDFS.format(
            pdf_files=", ".join(pdf_files) if pdf_files else "none"
        )
    else:
        context = SETUP_AGENT_CONTEXT

    # Create profile
    profile = AgentProfile(
        context=context,
        model=model_ref,
        base_dir=base_dir,
        tools=tools,
        subagents={},
        name="setup",
        max_depth=1,
    )

    # Create agent with setup_mode flag
    agent = RecursiveAgent(
        settings=settings,
        profile=profile,
        agent_id="setup",
    )
    agent.context.setup_mode = True
    # Rebuild tool schemas after enabling setup mode so setup-only tools become available.
    agent.tool_schemas = agent._build_tool_schemas()
    agent.reset()

    return agent, None


def _format_provider_model_ref(provider_id: str, model_id: str) -> str:
    """Build provider-prefixed model reference."""
    return f"{provider_id}:{model_id}"


def _collect_model_choices(settings) -> tuple[list[dict[str, Any]], str]:
    """Collect model choices for setup selection."""
    choices: list[dict[str, Any]] = []
    default_provider, default_model_id = settings.resolve_model_with_provider(
        settings.default_model
    )
    preferred_ref = (
        _format_provider_model_ref(default_provider.id, default_model_id)
        if default_provider is not None
        else settings.default_model
    )

    if settings.providers.providers:
        for provider in settings.providers.providers.values():
            for model in provider.models:
                ref = _format_provider_model_ref(provider.id, model.id)
                choices.append(
                    {
                        "ref": ref,
                        "provider": provider.name,
                        "provider_id": provider.id,
                        "name": model.name,
                        "model_id": model.id,
                    }
                )
    else:
        for model in settings.models:
            choices.append(
                {
                    "ref": model.id,
                    "provider": "legacy",
                    "provider_id": "",
                    "name": model.name,
                    "model_id": model.id,
                }
            )

    if not choices:
        fallback = settings.default_model
        return (
            [
                {
                    "ref": fallback,
                    "provider": "default",
                    "provider_id": "",
                    "name": fallback,
                    "model_id": fallback,
                }
            ],
            fallback,
        )

    refs = {choice["ref"] for choice in choices}
    if preferred_ref in refs:
        return choices, preferred_ref

    return choices, choices[0]["ref"]


def _select_model_for_setup(settings) -> str:
    """Select model/provider to use during setup."""
    choices, default_ref = _collect_model_choices(settings)
    default_choice = next(
        (choice for choice in choices if choice["ref"] == default_ref), choices[0]
    )
    default_label = (
        f"{default_choice['provider_id']}:{default_choice['model_id']}"
        if default_choice["provider_id"]
        else default_choice["model_id"]
    )

    console.print(f"\n[bold]Use default model/provider?[/bold]\n  [cyan]{default_label}[/cyan]")
    if safe_confirm("Use this model?", default=True):
        return default_ref

    console.print("\n[bold]Select model/provider for initial setup:[/bold]")
    table = Table(show_header=False, box=None, padding=(0, 2))
    for i, choice in enumerate(choices, 1):
        default_marker = " [default]" if choice["ref"] == default_ref else ""
        provider_label = choice["provider"]
        table.add_row(
            f"  [{i}]",
            f"{provider_label} / {choice['name']}{default_marker}",
            f"[dim]{choice['ref']}[/dim]",
        )
    console.print(table)

    default_index = next(
        (i + 1 for i, choice in enumerate(choices) if choice["ref"] == default_ref), 1
    )
    selection = safe_prompt("Enter number", default=str(default_index))
    try:
        idx = int(selection) - 1
        if 0 <= idx < len(choices):
            return choices[idx]["ref"]
    except ValueError:
        pass

    console.print("[yellow]Invalid selection, using default.[/yellow]")
    return default_ref


def _test_selected_model_connection(settings, model_ref: str) -> tuple[bool, bool]:
    """
    Test selected model connection.

    Returns:
        Tuple of (was_test_attempted, test_success)
    """
    from flavia.setup.provider_wizard import test_provider_connection

    provider, model_id = settings.resolve_model_with_provider(model_ref)

    console.print("\n[bold]Connection check[/bold]")
    if provider is not None:
        console.print(f"  Provider: [cyan]{provider.name} ({provider.id})[/cyan]")
        console.print(f"  Model: [cyan]{model_id}[/cyan]")

        if not provider.api_key:
            if provider.api_key_env_var:
                console.print(
                    f"[yellow]Cannot test connection yet: {provider.api_key_env_var} is not configured.[/yellow]"
                )
            else:
                console.print(
                    "[yellow]Cannot test connection yet: provider API key is not configured.[/yellow]"
                )
            return False, False

        console.print("[dim]Testing provider/model connectivity...[/dim]")
        success, message = test_provider_connection(
            provider.api_key,
            provider.api_base_url,
            model_id,
            provider.headers if provider.headers else None,
        )
    else:
        console.print(f"  Model: [cyan]{model_id}[/cyan]")
        if not settings.api_key:
            console.print(
                "[yellow]Cannot test connection yet: SYNTHETIC_API_KEY is not configured.[/yellow]"
            )
            return False, False

        console.print("[dim]Testing connectivity using legacy API settings...[/dim]")
        success, message = test_provider_connection(
            settings.api_key,
            settings.api_base_url,
            model_id,
        )

    if success:
        console.print(f"[green]{message}[/green]")
    else:
        console.print(f"[red]{message}[/red]")

    return True, success


def _build_env_content(selected_model: str, include_optional_settings: bool) -> str:
    """Build .env template with selected default model."""
    optional_block = ""
    if include_optional_settings:
        optional_block = "\n# Optional settings\n# AGENT_MAX_DEPTH=3\n"

    return (
        "# flavIA Configuration\n"
        "# Uncomment and set your API key if not already configured elsewhere\n"
        "# (e.g., in ~/.config/flavia/.env or environment variables)\n"
        "\n"
        "# SYNTHETIC_API_KEY=your_api_key_here\n"
        "# API_BASE_URL=https://api.synthetic.new/openai/v1\n"
        "\n"
        f"DEFAULT_MODEL={selected_model}\n"
        f"{optional_block}\n"
        "# Telegram bot (optional)\n"
        "# TELEGRAM_BOT_TOKEN=123456:ABC-DEF...\n"
        "# Restrict bot to specific Telegram user IDs (comma-separated)\n"
        "# TELEGRAM_ALLOWED_USER_IDS=123456789,987654321\n"
        "# Public mode without whitelist (optional)\n"
        "# TELEGRAM_ALLOW_ALL_USERS=true\n"
    )


def _guess_api_key_env_var(provider_id: str) -> str:
    """Guess API key env var name from provider ID."""
    clean = "".join(c if c.isalnum() else "_" for c in provider_id).upper()
    return f"{clean}_API_KEY"


def _build_providers_config(selected_model: str) -> dict[str, Any]:
    """Build local providers.yaml data for the selected model/provider."""
    from flavia.config import load_settings

    settings = load_settings()
    provider, model_id = settings.resolve_model_with_provider(selected_model)

    if provider is None:
        return {
            "providers": {
                "synthetic": {
                    "name": "Synthetic",
                    "api_base_url": "https://api.synthetic.new/openai/v1",
                    "api_key": "${SYNTHETIC_API_KEY}",
                    "models": [
                        {
                            "id": model_id,
                            "name": model_id.split(":")[-1] if ":" in model_id else model_id,
                            "default": True,
                        }
                    ],
                }
            },
            "default_provider": "synthetic",
        }

    api_key_env_var = provider.api_key_env_var or _guess_api_key_env_var(provider.id)
    models: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for model in provider.models:
        if model.id in seen_ids:
            continue
        seen_ids.add(model.id)
        model_data: dict[str, Any] = {
            "id": model.id,
            "name": model.name,
        }
        if model.id == model_id:
            model_data["default"] = True
        models.append(model_data)

    if model_id not in seen_ids:
        models.insert(
            0,
            {
                "id": model_id,
                "name": model_id.split("/")[-1],
                "default": True,
            },
        )

    if not any(m.get("default") for m in models) and models:
        models[0]["default"] = True

    provider_config: dict[str, Any] = {
        "name": provider.name,
        "api_base_url": provider.api_base_url,
        "api_key": f"${{{api_key_env_var}}}",
        "models": models,
    }

    # Keep OpenRouter headers templated in generated config.
    if provider.id == "openrouter":
        provider_config["headers"] = {
            "HTTP-Referer": "${OPENROUTER_SITE_URL}",
            "X-Title": "${OPENROUTER_APP_NAME}",
        }

    return {
        "providers": {
            provider.id: provider_config,
        },
        "default_provider": provider.id,
    }


def _write_providers_file(config_dir: Path, selected_model: str) -> None:
    """Write providers.yaml for selected default provider/model."""
    providers_data = _build_providers_config(selected_model)
    with open(config_dir / "providers.yaml", "w", encoding="utf-8") as f:
        yaml.dump(
            providers_data,
            f,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )


def _ensure_agent_models(agents_file: Path, selected_model: str) -> None:
    """Ensure main agent and subagents have explicit model configuration."""
    if not agents_file.exists():
        return

    try:
        with open(agents_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception:
        return

    if not isinstance(data, dict):
        return

    main = data.get("main")
    if not isinstance(main, dict):
        return

    changed = False
    if main.get("model") != selected_model:
        main["model"] = selected_model
        changed = True

    subagents = main.get("subagents")
    if isinstance(subagents, dict):
        for sub_config in subagents.values():
            if isinstance(sub_config, dict) and "model" not in sub_config:
                sub_config["model"] = selected_model
                changed = True

    if not changed:
        return

    data["main"] = main

    with open(agents_file, "w", encoding="utf-8") as f:
        yaml.dump(
            data,
            f,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )


def _reset_config_dir(config_dir: Path, keep_files: Optional[set[str]] = None) -> None:
    """Reset .flavia contents while optionally preserving specific files."""
    keep = keep_files or set()

    config_dir.mkdir(parents=True, exist_ok=True)
    for entry in config_dir.iterdir():
        if entry.name in keep:
            continue
        if entry.is_dir():
            shutil.rmtree(entry)
        else:
            entry.unlink()


def run_setup_wizard(target_dir: Optional[Path] = None) -> bool:
    """
    Run the interactive setup wizard.

    Args:
        target_dir: Directory to initialize (default: current directory)

    Returns:
        True if successful
    """
    if target_dir is None:
        target_dir = Path.cwd()

    config_dir = target_dir / ".flavia"

    console.print(
        Panel.fit(
            "[bold blue]flavIA Setup Wizard[/bold blue]\n\n"
            "[dim]AI assistant for academic and research work[/dim]\n\n"
            f"Initializing in:\n[cyan]{target_dir}[/cyan]",
            title="Welcome",
        )
    )

    preserve_existing_providers = False

    # Check if already exists
    if config_dir.exists():
        console.print("\n[yellow].flavia/ already exists.[/yellow]")
        if not safe_confirm("Overwrite?", default=False):
            console.print("[yellow]Setup cancelled.[/yellow]")
            return False

        preserve_existing_providers = (config_dir / "providers.yaml").exists()
        keep_files = {"providers.yaml"} if preserve_existing_providers else None
        _reset_config_dir(config_dir, keep_files=keep_files)

    from flavia.config import load_settings

    settings = load_settings()

    selected_model = _select_model_for_setup(settings)

    while True:
        attempted, success = _test_selected_model_connection(settings, selected_model)
        if not attempted or success:
            break

        if not safe_confirm(
            "Connection failed. Do you want to select another model/provider?",
            default=True,
        ):
            break
        selected_model = _select_model_for_setup(settings)

    # Check for PDFs
    pdf_files = find_pdf_files(target_dir)

    if pdf_files:
        console.print(f"\n[bold]Found {len(pdf_files)} PDF file(s):[/bold]")
        table = Table(show_header=False, box=None, padding=(0, 2))
        for pdf in pdf_files[:10]:  # Show first 10
            size_kb = pdf.stat().st_size / 1024
            table.add_row(f"  [cyan]{pdf.name}[/cyan]", f"[dim]{size_kb:.1f} KB[/dim]")
        if len(pdf_files) > 10:
            table.add_row(f"  [dim]... and {len(pdf_files) - 10} more[/dim]", "")
        console.print(table)

        console.print("\n[bold]Convert PDFs to text for analysis?[/bold]")
        console.print("  (This allows the AI to read and search the documents)")
        convert_pdfs = safe_confirm("Convert PDFs?", default=True)
    else:
        convert_pdfs = False

    # Ask about AI analysis
    console.print("\n")
    console.print(
        "[bold]Have the AI analyze your content and suggest an agent configuration?[/bold]"
    )
    console.print("  (The AI will read files to understand your project/research area)")
    analyze = safe_confirm("Analyze content?", default=True)

    user_guidance = ""
    if analyze or convert_pdfs:
        pdf_file_refs = _pdf_paths_for_tools(target_dir, pdf_files) if convert_pdfs else None
        user_guidance = _ask_user_guidance()
        return _run_ai_setup(
            target_dir,
            config_dir,
            selected_model=selected_model,
            convert_pdfs=convert_pdfs,
            pdf_files=pdf_file_refs,
            user_guidance=user_guidance,
            preserve_existing_providers=preserve_existing_providers,
        )
    else:
        return _run_basic_setup(
            target_dir,
            config_dir,
            selected_model=selected_model,
            preserve_existing_providers=preserve_existing_providers,
        )


def _ask_user_guidance() -> str:
    """Ask the user for optional setup guidance for the LLM."""
    console.print("[bold]Do you want to add brief guidance for agent creation?[/bold]")
    console.print("  (e.g., preferred style, focus areas, sub-agents, constraints)")
    wants_guidance = safe_confirm("Add guidance?", default=False)
    if not wants_guidance:
        return ""

    guidance = safe_prompt(
        "Enter your guidance (single line, optional)",
        default="",
    ).strip()
    if guidance:
        console.print("[dim]Guidance noted and will be used for agent generation.[/dim]")
    return guidance


def _offer_provider_setup(config_dir: Path) -> None:
    """Offer to run the provider wizard after basic setup."""
    import sys

    # Skip if not running interactively (e.g., in tests)
    if not sys.stdin.isatty():
        return

    console.print("\n[bold]Configure LLM providers now?[/bold]")
    console.print("  (Set up API keys and models for OpenAI, OpenRouter, etc.)")
    if safe_confirm("Configure providers?", default=False):
        from flavia.setup.provider_wizard import run_provider_wizard

        run_provider_wizard(config_dir.parent)


def _build_content_catalog(target_dir: Path, config_dir: Path) -> None:
    """Build and save the content catalog during setup."""
    from flavia.content.catalog import ContentCatalog

    console.print("\n[dim]Building content catalog...[/dim]")
    try:
        catalog = ContentCatalog(target_dir)
        catalog.build()

        # Link converted files if they exist
        converted_dir = target_dir / "converted"
        if converted_dir.exists():
            for entry in catalog.files.values():
                if entry.file_type == "binary_document" and entry.category == "pdf":
                    # Prefer preserved relative structure, but support legacy flat outputs.
                    relative_md = Path(entry.path).with_suffix(".md")
                    candidates = [converted_dir / relative_md, converted_dir / relative_md.name]
                    for converted_path in candidates:
                        if not converted_path.exists():
                            continue
                        try:
                            entry.converted_to = str(converted_path.relative_to(target_dir))
                        except ValueError:
                            entry.converted_to = str(converted_path)
                        break

        catalog_path = catalog.save(config_dir)
        stats = catalog.get_stats()
        console.print(
            f"[dim]Content catalog created: {stats['total_files']} files indexed "
            f"({stats['total_size_bytes'] / 1024 / 1024:.1f} MB)[/dim]"
        )
    except Exception as e:
        console.print(f"[yellow]Warning: Could not build content catalog: {e}[/yellow]")


def _run_basic_setup(
    target_dir: Path,
    config_dir: Path,
    selected_model: Optional[str] = None,
    preserve_existing_providers: bool = False,
) -> bool:
    """Create basic default configuration."""
    console.print("\n[dim]Creating default configuration...[/dim]")
    effective_model = selected_model or "synthetic:hf:moonshotai/Kimi-K2.5"

    try:
        config_dir.mkdir(parents=True, exist_ok=True)

        # Create .env (API keys are commented out to avoid overriding existing config)
        env_content = _build_env_content(effective_model, include_optional_settings=True)
        (config_dir / ".env").write_text(env_content)

        # Create providers.yaml unless user asked to keep existing project-level providers.
        providers_file = config_dir / "providers.yaml"
        if not (preserve_existing_providers and providers_file.exists()):
            _write_providers_file(config_dir, effective_model)

        # Create academic-focused default agents.yaml
        agents_content = f"""\
# flavIA Agent Configuration
# Default academic assistant

main:
  model: "{effective_model}"
  context: |
    You are an academic research assistant.
    You help analyze documents, explain concepts, find information, and assist with research tasks.
    Working directory: {{base_dir}}

    When answering questions:
    - Be precise and cite specific passages when relevant
    - Explain complex concepts clearly
    - Help the user understand and work with their documents

  tools:
    - read_file
    - list_files
    - search_files
    - get_file_info
    - query_catalog
    - get_catalog_summary
    - refresh_catalog
    - spawn_agent
    - spawn_predefined_agent

  subagents:
    summarizer:
      model: "{effective_model}"
      context: |
        You are a summarization specialist.
        Create clear, concise summaries that capture the key points.
        Include important details, arguments, and conclusions.
      tools:
        - read_file
        - query_catalog

    explainer:
      model: "{effective_model}"
      context: |
        You are an expert at explaining complex concepts.
        Break down difficult ideas into understandable parts.
        Use analogies and examples when helpful.
      tools:
        - read_file
        - search_files
        - query_catalog

    researcher:
      model: "{effective_model}"
      context: |
        You are a research specialist.
        Find specific information, quotes, and references across documents.
        Be thorough and precise in your searches.
      tools:
        - read_file
        - list_files
        - search_files
        - query_catalog
"""
        (config_dir / "agents.yaml").write_text(agents_content)

        # Create .gitignore
        (config_dir / ".gitignore").write_text(
            ".env\n.connection_checks.yaml\ncontent_catalog.json\n"
        )

        # Build content catalog
        _build_content_catalog(target_dir, config_dir)

        _print_success(config_dir)

        # Offer provider configuration
        _offer_provider_setup(config_dir)

        return True

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        return False


def _run_ai_setup(
    target_dir: Path,
    config_dir: Path,
    selected_model: Optional[str] = None,
    convert_pdfs: bool = False,
    pdf_files: List[str] = None,
    user_guidance: str = "",
    interactive_review: bool = True,
    preserve_existing_providers: bool = False,
) -> bool:
    """Run AI-assisted setup."""
    console.print("\n[dim]Initializing AI setup agent...[/dim]")
    effective_model = selected_model or "synthetic:hf:moonshotai/Kimi-K2.5"

    agent, error = create_setup_agent(
        target_dir,
        include_pdf_tool=convert_pdfs,
        pdf_files=pdf_files,
        selected_model=effective_model,
    )

    if error:
        console.print(f"[red]{error}[/red]")
        console.print("\n[yellow]Falling back to basic setup...[/yellow]")
        return _run_basic_setup(target_dir, config_dir, selected_model=effective_model)

    # Create the config dir first
    config_dir.mkdir(parents=True, exist_ok=True)

    # Create .env (API keys are commented out to avoid overriding existing config)
    env_content = _build_env_content(effective_model, include_optional_settings=False)
    (config_dir / ".env").write_text(env_content)

    # Create providers.yaml unless user asked to keep existing project-level providers.
    providers_file = config_dir / "providers.yaml"
    if not (preserve_existing_providers and providers_file.exists()):
        _write_providers_file(config_dir, effective_model)

    # Create .gitignore
    (config_dir / ".gitignore").write_text(
        ".env\n.connection_checks.yaml\ncontent_catalog.json\nconverted/\n"
    )

    # Convert PDFs first when requested
    if convert_pdfs and pdf_files:
        console.print("\n[bold]Converting PDFs and analyzing content...[/bold]\n")
        try:
            conversion_result = agent._execute_tool(
                "convert_pdfs",
                {
                    "pdf_files": pdf_files,
                    "output_format": "md",
                    "preserve_structure": True,
                },
            )
            console.print(Markdown(f"```text\n{conversion_result}\n```"))
        except Exception as e:
            console.print(f"[yellow]Warning: PDF conversion step failed: {e}[/yellow]")
    else:
        console.print("\n[bold]Analyzing content...[/bold]\n")

    agents_file = config_dir / "agents.yaml"
    revision_notes: list[str] = []

    try:
        for attempt in range(1, MAX_SETUP_REVISIONS + 1):
            if agents_file.exists():
                agents_file.unlink()

            task = _build_setup_task(
                convert_pdfs=convert_pdfs,
                selected_model=effective_model,
                user_guidance=user_guidance,
                revision_notes=revision_notes,
            )

            response = agent.run(task)
            console.print(Markdown(response))

            if not agents_file.exists():
                console.print("\n[yellow]AI did not create the config file.[/yellow]")
                if not interactive_review:
                    console.print("[yellow]Creating default configuration...[/yellow]")
                    return _run_basic_setup(target_dir, config_dir, selected_model=effective_model)

                if safe_confirm("Use default configuration instead?", default=True):
                    return _run_basic_setup(target_dir, config_dir, selected_model=effective_model)

                feedback = safe_prompt(
                    "What should be changed in the next proposal?",
                    default="",
                ).strip()
                if feedback:
                    revision_notes.append(feedback)
                    continue
                console.print(
                    "[yellow]No feedback provided. Creating default configuration.[/yellow]"
                )
                return _run_basic_setup(target_dir, config_dir, selected_model=effective_model)

            _ensure_agent_models(agents_file, effective_model)

            if not interactive_review:
                _build_content_catalog(target_dir, config_dir)
                _print_success(config_dir, has_pdfs=convert_pdfs)
                return True

            _show_agents_preview(agents_file)
            if safe_confirm("Accept this agent configuration?", default=True):
                _build_content_catalog(target_dir, config_dir)
                _print_success(config_dir, has_pdfs=convert_pdfs)
                return True

            if safe_confirm("Use default configuration instead?", default=False):
                return _run_basic_setup(target_dir, config_dir, selected_model=effective_model)

            feedback = safe_prompt(
                "Describe the changes you want in the next version",
                default="",
            ).strip()
            if not feedback:
                console.print(
                    "[yellow]No feedback provided. Creating default configuration.[/yellow]"
                )
                return _run_basic_setup(target_dir, config_dir, selected_model=effective_model)

            revision_notes.append(feedback)
            if attempt < MAX_SETUP_REVISIONS:
                console.print("\n[dim]Regenerating configuration with your feedback...[/dim]\n")

        console.print(
            "\n[yellow]Maximum revision attempts reached. Creating default configuration...[/yellow]"
        )
        return _run_basic_setup(target_dir, config_dir, selected_model=effective_model)

    except KeyboardInterrupt:
        console.print("\n[yellow]Setup interrupted.[/yellow]")
        return False
    except Exception as e:
        console.print(f"\n[red]Error during AI setup: {e}[/red]")
        console.print("[yellow]Falling back to basic setup...[/yellow]")
        return _run_basic_setup(target_dir, config_dir, selected_model=effective_model)


def _build_setup_task(
    convert_pdfs: bool,
    selected_model: str,
    user_guidance: str,
    revision_notes: List[str],
) -> str:
    """Build setup task including optional user guidance and revision feedback."""
    if convert_pdfs:
        base = (
            "Analyze the converted content in the 'converted/' directory and create an "
            "appropriate agents.yaml configuration specialized for this academic material. "
            "Use create_agents_config to write the file."
        )
    else:
        base = (
            "Analyze this directory and create an appropriate agents.yaml configuration. "
            "Look for documents, understand the subject matter, and create an agent "
            "specialized for this academic/research content. Use create_agents_config to write the file."
        )

    parts = [
        base,
        (
            "The generated main agent must explicitly set "
            f"model to '{selected_model}' in agents.yaml."
        ),
    ]
    if user_guidance:
        parts.append(f"User guidance:\n{user_guidance}")
    if revision_notes:
        notes = "\n".join(f"- {note}" for note in revision_notes)
        parts.append(
            f"Revision feedback from user (apply all points below in this new proposal):\n{notes}"
        )
    return "\n\n".join(parts)


def _show_agents_preview(agents_file: Path, max_lines: int = 80) -> None:
    """Show a preview of generated agents.yaml for user validation."""
    try:
        content = agents_file.read_text(encoding="utf-8")
    except Exception:
        console.print(f"[yellow]Could not read {agents_file} for preview.[/yellow]")
        return

    lines = content.splitlines()
    truncated = len(lines) > max_lines
    preview = "\n".join(lines[:max_lines])
    if truncated:
        preview += "\n... (truncated)"

    console.print("\n[bold]Proposed agents.yaml:[/bold]")
    console.print(Markdown(f"```yaml\n{preview}\n```"))


def _print_success(config_dir: Path, has_pdfs: bool = False):
    """Print success message."""
    extra_info = ""
    if has_pdfs:
        extra_info = "\n[dim]Converted documents are in: converted/[/dim]\n"

    console.print(
        Panel.fit(
            "[bold green]Setup complete![/bold green]\n\n"
            f"Configuration created at:\n"
            f"  [cyan]{config_dir}/.env[/cyan] - API keys\n"
            f"  [cyan]{config_dir}/providers.yaml[/cyan] - Providers and models\n"
            f"  [cyan]{config_dir}/agents.yaml[/cyan] - Agents\n"
            f"{extra_info}\n"
            "[bold]Next steps:[/bold]\n"
            f"  1. Edit [cyan]{config_dir}/.env[/cyan] with your API key\n"
            "  2. Run [bold]flavia[/bold] to start chatting with your documents\n\n"
            "[dim]Tip: Run 'flavia --setup-provider' to configure multiple LLM providers[/dim]",
            title="Success",
        )
    )


def run_setup_command_in_cli(settings, base_dir: Path) -> bool:
    """
    Run setup from within CLI (via /setup command).

    Args:
        settings: Current settings
        base_dir: Base directory

    Returns:
        True if successful
    """
    config_dir = base_dir / ".flavia"

    console.print("\n[bold blue]Agent Configuration Setup[/bold blue]\n")

    # Check if agents.yaml exists
    if (config_dir / "agents.yaml").exists():
        console.print("[yellow]agents.yaml already exists.[/yellow]")
        if not safe_confirm("Overwrite?", default=False):
            return False

    # Check for PDFs
    pdf_files = find_pdf_files(base_dir)
    convert_pdfs = False

    if pdf_files:
        # Check if already converted
        converted_dir = base_dir / "converted"
        if converted_dir.exists() and list(converted_dir.rglob("*.md")):
            console.print(f"[dim]Found existing converted documents in converted/[/dim]")
        else:
            console.print(f"[dim]Found {len(pdf_files)} PDF file(s)[/dim]")
            convert_pdfs = safe_confirm("Convert PDFs to text first?", default=True)

    analyze = safe_confirm(
        "Analyze content and suggest agent configuration?",
        default=True,
    )

    if not analyze and not convert_pdfs:
        return False

    pdf_file_refs = _pdf_paths_for_tools(base_dir, pdf_files) if convert_pdfs else None

    agent, error = create_setup_agent(
        base_dir,
        include_pdf_tool=convert_pdfs,
        pdf_files=pdf_file_refs,
    )

    if error:
        console.print(f"[red]{error}[/red]")
        return False

    # Build task
    if convert_pdfs:
        task = (
            f"First convert the PDFs to markdown: {', '.join(pdf_file_refs or [])}. "
            f"Then analyze and create agents.yaml."
        )
        console.print("\n[bold]Converting and analyzing...[/bold]\n")
    else:
        task = "Analyze this directory and create an appropriate agents.yaml configuration."
        console.print("\n[bold]Analyzing...[/bold]\n")

    try:
        response = agent.run(task)
        console.print(Markdown(response))

        if (config_dir / "agents.yaml").exists():
            _ensure_agent_models(config_dir / "agents.yaml", str(settings.default_model))
            console.print("\n[green]Configuration updated![/green]")
            console.print("[yellow]Run /reset to load the new configuration.[/yellow]")
            return True

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")

    return False
