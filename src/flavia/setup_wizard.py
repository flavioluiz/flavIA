"""Setup wizard for initializing flavIA configuration."""

from collections import Counter
import shutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, List, Optional

import yaml
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from flavia.content.scanner import VIDEO_EXTENSIONS
from flavia.setup.prompt_utils import (
    SetupCancelled,
    q_select,
    safe_confirm,
    safe_prompt,
)

if TYPE_CHECKING:
    from flavia.content.catalog import ContentCatalog

console = Console()
MAX_SETUP_REVISIONS = 5
CONVERTED_DIR_NAME = ".converted"
WRITE_TOOLS = [
    "write_file",
    "edit_file",
    "insert_text",
    "append_file",
    "delete_file",
    "create_directory",
    "remove_directory",
]
RUNTIME_CORE_TOOLS = [
    "read_file",
    "list_files",
    "search_files",
    "get_file_info",
    "query_catalog",
    "search_chunks",
    "get_catalog_summary",
    "analyze_image",
    "compact_context",
]
SPAWN_TOOLS = ["spawn_agent", "spawn_predefined_agent"]
WRITE_CAPABLE_RUNTIME_TOOLS = WRITE_TOOLS + ["compile_latex", "refresh_catalog"]


def _default_main_tools(main_agent_can_write: bool) -> list[str]:
    """Return default runtime tools for the main agent."""
    tools = list(RUNTIME_CORE_TOOLS)
    if main_agent_can_write:
        tools.extend(WRITE_CAPABLE_RUNTIME_TOOLS)
    tools.extend(SPAWN_TOOLS)
    return tools


def _count_converted_pdfs(
    base_dir: Path,
    converted_dir: Path,
    pdf_files: List[Path],
    catalog: Optional[Any],
) -> int:
    """Count how many discovered PDFs already have converted markdown."""
    converted_count = 0
    catalog_entries = getattr(catalog, "files", {}) if catalog else {}

    for pdf_path in pdf_files:
        try:
            rel_pdf = pdf_path.relative_to(base_dir)
        except ValueError:
            rel_pdf = Path(pdf_path.name)

        catalog_entry = catalog_entries.get(str(rel_pdf))
        if catalog_entry is not None and getattr(catalog_entry, "converted_to", None):
            converted_count += 1
            continue

        converted_candidates = [
            converted_dir / rel_pdf.with_suffix(".md"),
            converted_dir / rel_pdf.with_suffix(".md").name,
        ]
        if any(path.exists() for path in converted_candidates):
            converted_count += 1

    return converted_count


def _build_documents_preparation_status(
    base_dir: Path,
    converted_dir: Path,
    pdf_files: List[Path],
    catalog: Optional[Any],
) -> tuple[str, str, int]:
    """
    Build icon/text status for the preparation "Documents" step.

    Returns:
        Tuple of (icon_markup, status_text, converted_pdf_count)
    """
    has_pdfs = bool(pdf_files)
    converted_pdf_count = _count_converted_pdfs(base_dir, converted_dir, pdf_files, catalog)

    non_pdf_converted = 0
    non_pdf_by_type: Counter[str] = Counter()
    frame_descriptions = 0

    catalog_entries = getattr(catalog, "files", {}) if catalog else {}
    if catalog_entries:
        for entry in catalog_entries.values():
            if getattr(entry, "status", "current") == "missing":
                continue
            if getattr(entry, "converted_to", None):
                if getattr(entry, "extension", "").lower() != ".pdf":
                    non_pdf_converted += 1
                    non_pdf_by_type[getattr(entry, "file_type", "other")] += 1
            frame_descriptions += len(getattr(entry, "frame_descriptions", []) or [])
    elif converted_dir.exists():
        converted_md_count = len(list(converted_dir.rglob("*.md")))
        non_pdf_converted = max(converted_md_count - converted_pdf_count, 0)

    non_pdf_detail = ""
    if non_pdf_converted > 0:
        if non_pdf_by_type:
            ordered_types = ["video", "audio", "image", "binary_document", "other"]
            type_parts = [
                f"{non_pdf_by_type[t]} {t}"
                for t in ordered_types
                if non_pdf_by_type.get(t, 0) > 0
            ]
            non_pdf_detail = (
                f"{non_pdf_converted} non-PDF file(s) converted/transcribed "
                f"({', '.join(type_parts)})"
            )
        else:
            non_pdf_detail = f"{non_pdf_converted} non-PDF converted file(s)"

    extras = []
    if non_pdf_detail:
        extras.append(non_pdf_detail)
    if frame_descriptions > 0:
        extras.append(f"{frame_descriptions} frame description(s)")

    if has_pdfs:
        doc_icon = (
            "[green]\u2713[/green]"
            if converted_pdf_count >= len(pdf_files)
            else "[yellow]\u2717[/yellow]"
        )
        doc_status = f"{converted_pdf_count}/{len(pdf_files)} PDFs converted"
        if extras:
            doc_status += " | " + "; ".join(extras)
        return doc_icon, doc_status, converted_pdf_count

    if extras:
        return "[green]\u2713[/green]", "; ".join(extras), converted_pdf_count

    return "[dim]-[/dim]", "no PDFs found", converted_pdf_count


# System prompt for the setup agent
SETUP_AGENT_CONTEXT = """You are a setup assistant for flavIA, an AI assistant focused on academic and research work.

Your task is to analyze the user's directory and create an appropriate agents.yaml configuration.

## Your Process:

1. **Check for converted documents**: Look in the '.converted/' directory for .md or .txt files
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
- search_chunks: Semantic search over indexed document chunks with citations
- get_catalog_summary: Get a high-level overview of the project content
- analyze_image: Describe images with a vision-capable model
- compact_context: Compact long conversations and keep key context
- compile_latex: Compile .tex files into PDF (only when write access is allowed)
- refresh_catalog: Rebuild the project catalog (writes catalog data; only with write access)
- spawn_agent: Create dynamic sub-agents
- spawn_predefined_agent: Use predefined subagents

When generating agents.yaml:
- Default `main.tools` should include all read/runtime tools:
  read_file, list_files, search_files, get_file_info, query_catalog, search_chunks, get_catalog_summary,
  analyze_image, compact_context, spawn_agent, spawn_predefined_agent
- Only include write-capable tools when write access is explicitly requested:
  write_file, edit_file, insert_text, append_file, delete_file, create_directory,
  remove_directory, compile_latex, refresh_catalog

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
1. List files in the '.converted/' directory
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

When generating agents.yaml, valid runtime write tools are:
- write_file, edit_file, insert_text, append_file, delete_file, create_directory,
  remove_directory, compile_latex, refresh_catalog
- Also include these read/runtime tools by default:
  read_file, list_files, search_files, get_file_info, query_catalog, search_chunks, get_catalog_summary,
  analyze_image, compact_context, spawn_agent, spawn_predefined_agent

Include a project_description that captures the academic subject.
"""


def find_pdf_files(directory: Path) -> List[Path]:
    """Find all PDF files in a directory (recursive)."""
    return sorted(
        (path for path in directory.rglob("*") if path.is_file() and path.suffix.lower() == ".pdf"),
        key=lambda path: str(path),
    )


def find_binary_documents(directory: Path) -> List[Path]:
    """Find all files that can be converted to text (docs, audio, video)."""
    from flavia.content.scanner import AUDIO_EXTENSIONS, VIDEO_EXTENSIONS

    convertible_extensions = (
        {
            ".pdf",
            # Modern Office
            ".docx",
            ".xlsx",
            ".pptx",
            # Legacy Office (requires LibreOffice)
            ".doc",
            ".xls",
            ".ppt",
            # OpenDocument
            ".odt",
            ".ods",
            ".odp",
        }
        | set(AUDIO_EXTENSIONS)
        | set(VIDEO_EXTENSIONS)
    )

    return sorted(
        (
            path
            for path in directory.rglob("*")
            if path.is_file() and path.suffix.lower() in convertible_extensions
        ),
        key=lambda path: str(path),
    )


def find_image_files(directory: Path) -> List[Path]:
    """Find image files that can be converted to text descriptions."""
    from flavia.content.scanner import IMAGE_EXTENSIONS

    return sorted(
        (
            path
            for path in directory.rglob("*")
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
        ),
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
    model_override: Optional[str] = None,
):
    """Create the setup agent with special tools."""
    from flavia.agent import AgentProfile, RecursiveAgent
    from flavia.config import load_settings
    from flavia.tools.registry import registry
    from flavia.tools.setup.convert_pdfs import ConvertPdfsTool
    from flavia.tools.setup.create_agents_config import CreateAgentsConfigTool

    # Load settings
    settings = load_settings()

    # Use model_override if provided, otherwise use selected_model or default
    model_ref = model_override or selected_model or settings.default_model

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


def _select_model_for_setup(settings, allow_cancel: bool = False) -> str:
    """
    Select model/provider to use during setup.

    Shows the default model and asks user to confirm or choose another.
    Single-step interaction (no redundant confirmations).

    Args:
        settings: Application settings
        allow_cancel: If True, raise SetupCancelled on Ctrl+C

    Returns:
        Selected model reference string
    """
    choices, default_ref = _collect_model_choices(settings)
    default_choice = next(
        (choice for choice in choices if choice["ref"] == default_ref), choices[0]
    )
    default_label = (
        f"{default_choice['provider_id']}:{default_choice['model_id']}"
        if default_choice["provider_id"]
        else default_choice["model_id"]
    )

    console.print(f"  Model: [cyan]{default_label}[/cyan]")

    if not safe_confirm(
        "Use this model or choose another?",
        default=True,
        allow_cancel=allow_cancel,
    ):
        # Build choices for q_select
        try:
            import questionary

            model_choices = [
                questionary.Choice(
                    title=f"{choice['provider']} / {choice['name']}",
                    value=choice["ref"],
                )
                for choice in choices
            ]
        except ImportError:
            model_choices = [f"{choice['provider']} / {choice['name']}" for choice in choices]

        selected = q_select(
            "Select model:",
            choices=model_choices,
            default=default_ref,
            allow_cancel=allow_cancel,
        )

        if selected is not None:
            # Map back to ref if we got a title string
            if not any(c["ref"] == selected for c in choices):
                for i, choice in enumerate(choices):
                    if f"{choice['provider']} / {choice['name']}" == selected:
                        return choice["ref"]
            return selected

        console.print("[yellow]No selection made, using default.[/yellow]")

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

    # Check for convertible files
    binary_docs = find_binary_documents(target_dir)
    image_files = find_image_files(target_dir)
    convert_docs = False
    files_to_convert: list[Path] = []
    extract_visual_frames = False

    if binary_docs:
        # Group by extension for display
        ext_counts: dict[str, int] = {}
        for doc in binary_docs:
            ext = doc.suffix.lower()
            ext_counts[ext] = ext_counts.get(ext, 0) + 1

        ext_summary = ", ".join(f"{count} {ext.upper()}" for ext, count in ext_counts.items())
        console.print(
            f"\n[bold]Found {len(binary_docs)} convertible file(s) ({ext_summary}):[/bold]"
        )

        table = Table(show_header=False, box=None, padding=(0, 2))
        for doc in binary_docs[:10]:  # Show first 10
            size_kb = doc.stat().st_size / 1024
            table.add_row(f"  [cyan]{doc.name}[/cyan]", f"[dim]{size_kb:.1f} KB[/dim]")
        if len(binary_docs) > 10:
            table.add_row(f"  [dim]... and {len(binary_docs) - 10} more[/dim]", "")
        console.print(table)

        console.print("\n[bold]Convert these files to text for analysis?[/bold]")
        console.print("  (Includes document conversion and audio/video transcription)")
        if safe_confirm("Convert documents?", default=True):
            files_to_convert.extend(binary_docs)

    if image_files:
        ext_counts: dict[str, int] = {}
        for image in image_files:
            ext = image.suffix.lower()
            ext_counts[ext] = ext_counts.get(ext, 0) + 1

        ext_summary = ", ".join(f"{count} {ext.upper()}" for ext, count in ext_counts.items())
        console.print(f"\n[bold]Found {len(image_files)} image file(s) ({ext_summary}):[/bold]")

        table = Table(show_header=False, box=None, padding=(0, 2))
        for image in image_files[:10]:  # Show first 10
            size_kb = image.stat().st_size / 1024
            table.add_row(f"  [cyan]{image.name}[/cyan]", f"[dim]{size_kb:.1f} KB[/dim]")
        if len(image_files) > 10:
            table.add_row(f"  [dim]... and {len(image_files) - 10} more[/dim]", "")
        console.print(table)

        console.print("\n[bold]Generate text descriptions for images?[/bold]")
        console.print("  (Uses vision-capable LLM calls and can consume tokens)")
        if safe_confirm("Convert images to descriptions?", default=False):
            files_to_convert.extend(image_files)

    convert_docs = bool(files_to_convert)

    # Ask about visual frame extraction for video files
    video_files = (
        [doc for doc in binary_docs if doc.suffix.lower() in VIDEO_EXTENSIONS]
        if binary_docs
        else []
    )
    if convert_docs and video_files:
        console.print(
            f"\n[bold]Found {len(video_files)} video file(s) that will be transcribed:[/bold]"
        )

        table = Table(show_header=False, box=None, padding=(0, 2))
        for video in video_files[:10]:
            size_kb = video.stat().st_size / 1024
            table.add_row(f"  [cyan]{video.name}[/cyan]", f"[dim]{size_kb:.1f} KB[/dim]")
        if len(video_files) > 10:
            table.add_row(f"  [dim]... and {len(video_files) - 10} more[/dim]", "")
        console.print(table)

        console.print("\n[bold]Extract and describe visual frames from videos?[/bold]")
        console.print("  (Uses vision-capable LLM calls and can consume tokens)")
        extract_visual_frames = safe_confirm("Extract visual frames from videos?", default=False)

    # Build content catalog BEFORE AI analysis (so summaries can be used as context)
    config_dir.mkdir(parents=True, exist_ok=True)
    catalog_kwargs = {
        "convert_docs": convert_docs,
        "binary_docs": files_to_convert if convert_docs else None,
    }
    if convert_docs and extract_visual_frames:
        catalog_kwargs["extract_visual_frames"] = True

    catalog = _build_content_catalog(
        target_dir,
        config_dir,
        **catalog_kwargs,
    )

    # Ask about LLM summaries
    generate_summaries = False
    if catalog:
        files_needing_summary = catalog.get_files_needing_summary()
        if files_needing_summary:
            console.print(
                f"\n[bold]Generate LLM summaries for {len(files_needing_summary)} file(s)?[/bold]"
            )
            console.print("  (Improves AI understanding of your content, but uses LLM tokens)")
            generate_summaries = safe_confirm("Generate summaries?", default=False)

            if generate_summaries:
                _run_summarization(catalog, config_dir, selected_model)

    # Ask about agent configuration
    try:
        import questionary

        config_choices = [
            questionary.Choice(
                title="Simple configuration (generic agent, no content analysis)",
                value="1",
            ),
            questionary.Choice(
                title="Analyze content and suggest specialized configuration",
                value="2",
            ),
        ]
    except ImportError:
        config_choices = [
            "Simple configuration (generic agent, no content analysis)",
            "Analyze content and suggest specialized configuration",
        ]

    config_choice = q_select(
        "How do you want to configure the agent?",
        choices=config_choices,
        default="2",
    )

    if config_choice is None:
        config_choice = "2"
    elif hasattr(config_choice, "value"):
        config_choice = config_choice.value
    elif config_choice == "1" or config_choice.startswith("Simple"):
        config_choice = "1"
    elif config_choice == "2" or config_choice.startswith("Analyze"):
        config_choice = "2"
    else:
        config_choice = "2"

    if config_choice == "1":
        main_agent_can_write = _ask_main_agent_write_capability()
        return _run_basic_setup(
            target_dir,
            config_dir,
            selected_model=selected_model,
            main_agent_can_write=main_agent_can_write,
            preserve_existing_providers=preserve_existing_providers,
            catalog_already_built=catalog is not None,
        )

    # Option 2: AI-assisted setup
    main_agent_can_write = _ask_main_agent_write_capability()
    include_subagents = False
    console.print("\n[bold]Include specialized subagents?[/bold]")
    console.print("  (The AI may suggest subagents like summarizer, explainer, etc.)")
    include_subagents = safe_confirm("Include subagents?", default=False)

    user_guidance = _ask_user_guidance()

    # Use legacy pdf_files variable for compatibility with existing code
    pdf_files = [p for p in binary_docs if p.suffix.lower() == ".pdf"]
    pdf_file_refs = _pdf_paths_for_tools(target_dir, pdf_files) if convert_docs else None

    return _run_ai_setup(
        target_dir,
        config_dir,
        selected_model=selected_model,
        convert_pdfs=convert_docs,
        pdf_files=pdf_file_refs,
        user_guidance=user_guidance,
        main_agent_can_write=main_agent_can_write,
        preserve_existing_providers=preserve_existing_providers,
        include_subagents=include_subagents,
        catalog=catalog,
    )


def _ask_user_guidance(allow_cancel: bool = False) -> str:
    """Ask the user for optional setup guidance for the LLM."""
    console.print("[bold]Do you want to add brief guidance for agent creation?[/bold]")
    console.print("  (e.g., preferred style, focus areas, sub-agents, constraints)")
    wants_guidance = safe_confirm("Add guidance?", default=False, allow_cancel=allow_cancel)
    if not wants_guidance:
        return ""

    guidance = safe_prompt(
        "Enter your guidance (single line, optional)",
        default="",
        allow_cancel=allow_cancel,
    ).strip()
    if guidance:
        console.print("[dim]Guidance noted and will be used for agent generation.[/dim]")
    return guidance


def _ask_main_agent_write_capability(allow_cancel: bool = False) -> bool:
    """Ask whether the generated main agent should include write tools."""
    console.print("\n[bold]Should the main agent be able to modify files?[/bold]")
    console.print("  (Enables write/edit/delete tools; still constrained by permissions)")
    return safe_confirm(
        "Enable file-writing tools for main agent?",
        default=False,
        allow_cancel=allow_cancel,
    )


def _offer_provider_setup(config_dir: Path) -> None:
    """Offer to run the provider wizard after basic setup."""

    # Skip if not running interactively (e.g., in tests)
    if not sys.stdin.isatty():
        return

    console.print("\n[bold]Configure LLM providers now?[/bold]")
    console.print("  (Set up API keys and models for OpenAI, OpenRouter, etc.)")
    if safe_confirm("Configure providers?", default=False):
        from flavia.setup.provider_wizard import run_provider_wizard

        run_provider_wizard(config_dir.parent)


def _build_content_catalog(
    target_dir: Path,
    config_dir: Path,
    convert_docs: bool = False,
    binary_docs: Optional[List[Path]] = None,
    extract_visual_frames: bool = False,
) -> Optional["ContentCatalog"]:
    """
    Build and save the content catalog during setup.

    Args:
        target_dir: Project root directory.
        config_dir: The .flavia/ directory.
        convert_docs: Whether to convert files first.
        binary_docs: List of file paths to convert (binary docs and/or images).
        extract_visual_frames: Whether to extract and describe visual frames from videos.

    Returns:
        The ContentCatalog instance, or None on failure.
    """
    from flavia.content.catalog import ContentCatalog
    from flavia.content.converters import converter_registry

    # Convert files first if requested
    if convert_docs and binary_docs:
        console.print("\n[dim]Converting files...[/dim]")
        converted_dir = target_dir / CONVERTED_DIR_NAME
        converted_count = 0
        failed_count = 0
        skipped_count = 0

        for doc in binary_docs:
            converter = converter_registry.get_for_file(doc)
            if not converter:
                skipped_count += 1
                continue

            # Check if dependencies are available for this converter
            deps_ok, missing = converter.check_dependencies()
            if not deps_ok:
                skipped_count += 1
                console.print(
                    f"  [yellow]Skipping {doc.name}: missing deps ({', '.join(missing)})[/yellow]"
                )
                continue

            try:
                result_path = converter.convert(doc, converted_dir)
            except Exception as exc:
                failed_count += 1
                console.print(f"  [yellow]Failed to convert: {doc.name} ({exc})[/yellow]")
                continue

            if result_path:
                converted_count += 1
                console.print(f"  [dim]Converted: {doc.name}[/dim]")

        if converted_count > 0:
            console.print(f"[dim]  {converted_count} file(s) converted[/dim]")
        if failed_count > 0:
            console.print(f"[yellow]  {failed_count} file(s) failed conversion[/yellow]")
        if skipped_count > 0:
            console.print(f"[dim]  {skipped_count} file(s) skipped (no converter)[/dim]")

    console.print("\n[dim]Building content catalog...[/dim]")
    try:
        catalog = ContentCatalog(target_dir)
        catalog.build()

        # Link converted files if they exist in .converted/
        converted_dir = target_dir / CONVERTED_DIR_NAME
        if converted_dir.exists():
            # Categories that can be converted to text/markdown
            convertible_categories = {
                "pdf",
                "word",
                "spreadsheet",
                "presentation",
                "document",
            }
            for entry in catalog.files.values():
                is_convertible_binary_doc = (
                    entry.file_type == "binary_document"
                    and entry.category in convertible_categories
                )
                is_convertible_av = entry.file_type in {"audio", "video"}
                is_convertible_image = entry.file_type == "image"

                if is_convertible_binary_doc or is_convertible_av or is_convertible_image:
                    # Check both preserved relative structure and flat output naming.
                    relative_md = Path(entry.path).with_suffix(".md")
                    candidates = [
                        converted_dir / relative_md,
                        converted_dir / relative_md.name,
                    ]
                    for converted_path in candidates:
                        if not converted_path.exists():
                            continue
                        try:
                            entry.converted_to = str(converted_path.relative_to(target_dir))
                        except ValueError:
                            entry.converted_to = str(converted_path)
                        break

        catalog.save(config_dir)
        stats = catalog.get_stats()
        console.print(
            f"[dim]Content catalog created: {stats['total_files']} files indexed "
            f"({stats['total_size_bytes'] / 1024 / 1024:.1f} MB)[/dim]"
        )

        # Extract and describe visual frames from videos if requested
        if extract_visual_frames:
            from flavia.content.converters import VideoConverter

            video_entries = [
                entry
                for entry in catalog.files.values()
                if entry.file_type == "video" and entry.converted_to
            ]

            if video_entries:
                console.print("\n[dim]Extracting and describing visual frames...[/dim]")
                converter = VideoConverter()
                video_count = 0

                for entry in video_entries:
                    transcript_path = (target_dir / entry.converted_to).resolve()
                    try:
                        transcript_path.relative_to(target_dir.resolve())
                    except ValueError:
                        console.print(
                            f"    [yellow]Skipping unsafe transcript path: {entry.converted_to}[/yellow]"
                        )
                        continue

                    if not transcript_path.exists():
                        continue

                    console.print(f"  [dim]Processing video: {entry.path}[/dim]")

                    transcript = transcript_path.read_text(encoding="utf-8")
                    video_path = (target_dir / entry.path).resolve()
                    try:
                        video_path.relative_to(target_dir.resolve())
                    except ValueError:
                        console.print(
                            f"    [yellow]Skipping unsafe video path: {entry.path}[/yellow]"
                        )
                        continue

                    try:
                        description_files, description_timestamps = (
                            converter.extract_and_describe_frames(
                                transcript=transcript,
                                video_path=video_path,
                                base_output_dir=converted_dir,
                            )
                        )

                        if description_files:
                            for i, (desc_file_path, timestamp) in enumerate(
                                zip(description_files, description_timestamps), 1
                            ):
                                console.print(
                                    f"    [dim]Frame {i}/{len(description_files)} at "
                                    f"timestamp {timestamp:.1f}s: {desc_file_path.name}[/dim]"
                                )

                            frame_description_paths = []
                            for desc_path in description_files:
                                try:
                                    frame_description_paths.append(
                                        str(desc_path.relative_to(target_dir))
                                    )
                                except ValueError:
                                    frame_description_paths.append(str(desc_path))

                            entry.frame_descriptions = frame_description_paths
                            video_count += 1

                    except Exception as e:
                        console.print(f"    [yellow]Failed to extract frames: {e}[/yellow]")

                if video_count > 0:
                    console.print(f"[dim]  {video_count} video(s) processed with frames[/dim]")
                    catalog.save(config_dir)
                    console.print("[dim]  Catalog saved with frame descriptions.[/dim]")

        return catalog
    except Exception as e:
        console.print(f"[yellow]Warning: Could not build content catalog: {e}[/yellow]")
        return None


def _run_summarization(
    catalog: "ContentCatalog",
    config_dir: Path,
    selected_model: str,
) -> None:
    """Generate LLM summaries for files that need them."""
    from flavia.config import load_settings
    from flavia.content.summarizer import summarize_file

    settings = load_settings()
    provider, model_id = settings.resolve_model_with_provider(selected_model)

    if not provider or not provider.api_key:
        console.print("[yellow]Cannot generate summaries: API key not configured.[/yellow]")
        return

    files_needing_summary = catalog.get_files_needing_summary()
    if not files_needing_summary:
        return

    console.print(f"\n[dim]Generating summaries for {len(files_needing_summary)} file(s)...[/dim]")
    summarized = 0

    for entry in files_needing_summary:
        summary = summarize_file(
            entry,
            catalog.base_dir,
            api_key=provider.api_key,
            api_base_url=provider.api_base_url,
            model=model_id,
            headers=provider.headers if provider.headers else None,
        )
        if summary:
            entry.summary = summary
            summarized += 1
            # Show progress every 5 files
            if summarized % 5 == 0:
                console.print(
                    f"  [dim]Summarized {summarized}/{len(files_needing_summary)}...[/dim]"
                )

    console.print(f"[dim]  {summarized} file(s) summarized[/dim]")

    # Save updated catalog
    catalog.save(config_dir)


def _run_basic_setup(
    target_dir: Path,
    config_dir: Path,
    selected_model: Optional[str] = None,
    main_agent_can_write: bool = False,
    preserve_existing_providers: bool = False,
    catalog_already_built: bool = False,
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
        main_tools_block = "".join(
            f"    - {tool}\n" for tool in _default_main_tools(main_agent_can_write)
        )

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
    - Prefer catalog-first workflow: get_catalog_summary/query_catalog before reading many files

  tools:
{main_tools_block}\

  subagents:
    summarizer:
      model: "{effective_model}"
      context: |
        You are a summarization specialist.
        Create clear, concise summaries that capture the key points.
        Include important details, arguments, and conclusions.
        Start by querying the catalog to identify the most relevant documents.
      tools:
        - read_file
        - query_catalog

    explainer:
      model: "{effective_model}"
      context: |
        You are an expert at explaining complex concepts.
        Break down difficult ideas into understandable parts.
        Use analogies and examples when helpful.
        Use the catalog to shortlist sources before reading full files.
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
        Prefer catalog queries before broad file-by-file reading.
      tools:
        - read_file
        - list_files
        - search_files
        - query_catalog
"""
        (config_dir / "agents.yaml").write_text(agents_content)

        # Create .gitignore
        (config_dir / ".gitignore").write_text(
            f".env\n.connection_checks.yaml\ncontent_catalog.json\n{CONVERTED_DIR_NAME}/\n"
        )

        # Build content catalog only if not already done
        if not catalog_already_built:
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
    main_agent_can_write: bool = False,
    interactive_review: bool = True,
    preserve_existing_providers: bool = False,
    include_subagents: bool = False,
    catalog: Optional[Any] = None,
) -> bool:
    """Run AI-assisted setup."""
    console.print("\n[dim]Initializing AI setup agent...[/dim]")
    effective_model = selected_model or "synthetic:hf:moonshotai/Kimi-K2.5"
    catalog_already_built = catalog is not None

    def _ensure_catalog_built() -> None:
        nonlocal catalog_already_built
        if catalog_already_built:
            return
        rebuilt_catalog = _build_content_catalog(target_dir, config_dir)
        catalog_already_built = rebuilt_catalog is not None

    # Documents already converted and catalog already built at this point
    # Just need to create the agent for analysis
    agent, error = create_setup_agent(
        target_dir,
        include_pdf_tool=False,  # Conversion already done
        pdf_files=None,
        selected_model=effective_model,
    )

    if error:
        console.print(f"[red]{error}[/red]")
        console.print("\n[yellow]Falling back to basic setup...[/yellow]")
        return _run_basic_setup(
            target_dir,
            config_dir,
            selected_model=effective_model,
            main_agent_can_write=main_agent_can_write,
            catalog_already_built=catalog_already_built,
        )

    # Create the config dir first (should already exist from catalog build)
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
        f".env\n.connection_checks.yaml\ncontent_catalog.json\n{CONVERTED_DIR_NAME}/\n"
    )

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
                main_agent_can_write=main_agent_can_write,
                revision_notes=revision_notes,
                include_subagents=include_subagents,
                catalog=catalog,
                subagent_approval_mode=False,
            )

            response = agent.run(task)
            console.print(Markdown(response))

            if not agents_file.exists():
                console.print("\n[yellow]AI did not create the config file.[/yellow]")
                if not interactive_review:
                    console.print("[yellow]Creating default configuration...[/yellow]")
                    return _run_basic_setup(
                        target_dir,
                        config_dir,
                        selected_model=effective_model,
                        main_agent_can_write=main_agent_can_write,
                        catalog_already_built=catalog_already_built,
                    )

                if safe_confirm("Use default configuration instead?", default=True):
                    return _run_basic_setup(
                        target_dir,
                        config_dir,
                        selected_model=effective_model,
                        main_agent_can_write=main_agent_can_write,
                        catalog_already_built=catalog_already_built,
                    )

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
                return _run_basic_setup(
                    target_dir,
                    config_dir,
                    selected_model=effective_model,
                    main_agent_can_write=main_agent_can_write,
                    catalog_already_built=catalog_already_built,
                )

            _ensure_agent_models(agents_file, effective_model)

            if not interactive_review:
                _ensure_catalog_built()
                _print_success(config_dir, has_converted_files=convert_pdfs)
                return True

            _show_agents_preview(agents_file)
            if safe_confirm("Accept this agent configuration?", default=True):
                _ensure_catalog_built()
                _print_success(config_dir, has_converted_files=convert_pdfs)
                return True

            if safe_confirm("Use default configuration instead?", default=False):
                return _run_basic_setup(
                    target_dir,
                    config_dir,
                    selected_model=effective_model,
                    main_agent_can_write=main_agent_can_write,
                    catalog_already_built=catalog_already_built,
                )

            feedback = safe_prompt(
                "Describe the changes you want in the next version",
                default="",
            ).strip()
            if not feedback:
                console.print(
                    "[yellow]No feedback provided. Creating default configuration.[/yellow]"
                )
                return _run_basic_setup(
                    target_dir,
                    config_dir,
                    selected_model=effective_model,
                    main_agent_can_write=main_agent_can_write,
                    catalog_already_built=catalog_already_built,
                )

            revision_notes.append(feedback)
            if attempt < MAX_SETUP_REVISIONS:
                console.print("\n[dim]Regenerating configuration with your feedback...[/dim]\n")

        console.print(
            "\n[yellow]Maximum revision attempts reached. Creating default configuration...[/yellow]"
        )
        return _run_basic_setup(
            target_dir,
            config_dir,
            selected_model=effective_model,
            main_agent_can_write=main_agent_can_write,
            catalog_already_built=catalog_already_built,
        )

    except KeyboardInterrupt:
        console.print("\n[yellow]Setup interrupted.[/yellow]")
        return False
    except Exception as e:
        console.print(f"\n[red]Error during AI setup: {e}[/red]")
        console.print("[yellow]Falling back to basic setup...[/yellow]")
        return _run_basic_setup(
            target_dir,
            config_dir,
            selected_model=effective_model,
            main_agent_can_write=main_agent_can_write,
            catalog_already_built=catalog_already_built,
        )


def _build_setup_task(
    convert_pdfs: bool,
    selected_model: str,
    user_guidance: str,
    main_agent_can_write: bool,
    revision_notes: List[str],
    include_subagents: bool = False,
    catalog: Optional[Any] = None,
    subagent_approval_mode: bool = False,
) -> str:
    """Build setup task including optional user guidance and revision feedback."""
    if convert_pdfs:
        base = (
            f"Analyze the converted content in the '{CONVERTED_DIR_NAME}/' directory and create an "
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

    read_only_tools_str = ", ".join(_default_main_tools(False))
    write_enabled_tools_str = ", ".join(_default_main_tools(True))
    write_capable_tools_str = ", ".join(WRITE_CAPABLE_RUNTIME_TOOLS)
    if main_agent_can_write:
        parts.append(
            "The user explicitly wants the main agent to be able to modify files. "
            "Set `main.tools` to the full default runtime toolset with write access: "
            f"{write_enabled_tools_str}. "
            "Also include `permissions.write` with appropriate writable directories."
        )
    else:
        parts.append(
            "The user wants a read-only main agent. "
            "Set `main.tools` to the read-only default runtime toolset: "
            f"{read_only_tools_str}. "
            f"Do NOT include write-capable tools ({write_capable_tools_str})."
        )

    # Subagent instructions
    if include_subagents:
        if subagent_approval_mode:
            parts.append(
                "Include specialized subagents that would be helpful for this content. "
                "The user will review and approve each subagent you propose, so feel free "
                "to suggest multiple useful options. "
                "(e.g., summarizer, explainer, researcher, quiz_maker, citation_finder, etc.)"
            )
        else:
            parts.append(
                "Include specialized subagents that would be helpful for this content "
                "(e.g., summarizer, explainer, researcher). Each subagent should have a clear purpose."
            )
    else:
        parts.append(
            "Create ONLY a main agent, without any subagents. "
            "The user will configure subagents later if needed."
        )

    # Include catalog context if available (summaries provide rich context)
    if catalog:
        try:
            context_summary = catalog.generate_context_summary(max_length=3000)
            if context_summary:
                parts.append(
                    f"Here is a summary of the project content catalog:\n\n{context_summary}"
                )
        except Exception:
            pass  # Ignore errors generating context

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


def _print_success(config_dir: Path, has_converted_files: bool = False):
    """Print success message."""
    extra_info = ""
    if has_converted_files:
        extra_info = f"\n[dim]Converted files are in: {CONVERTED_DIR_NAME}/[/dim]\n"

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


def _approve_subagents(agents_file: Path) -> Optional[list[str]]:
    """
    Show proposed subagents with interactive checkboxes for batch approval.

    Uses questionary.checkbox for interactive selection. All subagents
    start checked; the user can uncheck those they want to remove.

    Args:
        agents_file: Path to agents.yaml

    Returns:
        List of approved subagent names, or None if no subagents or error

    Raises:
        SetupCancelled: If user presses Ctrl+C
    """
    try:
        with open(agents_file, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
    except Exception as e:
        console.print(f"[red]Could not load agents.yaml: {e}[/red]")
        return None

    subagents = config.get("main", {}).get("subagents", {})
    if not subagents or not isinstance(subagents, dict):
        console.print("[dim]No subagents found in configuration.[/dim]")
        return []

    console.print(f"The AI proposed [cyan]{len(subagents)}[/cyan] subagent(s).\n")

    # Show details of each subagent before the checkbox
    for name, sub_config in subagents.items():
        if not isinstance(sub_config, dict):
            continue
        context = sub_config.get("context", "(no description)")
        tools = sub_config.get("tools", [])
        tool_str = ""
        if isinstance(tools, (list, tuple)) and tools:
            tool_str = f"  Tools: {', '.join(str(t) for t in tools)}"
        console.print(f"  [bold cyan]{name}[/bold cyan] - {context}")
        if tool_str:
            console.print(f"  {tool_str}")

    console.print()

    # Build checkbox choices (all checked by default)
    try:
        import questionary

        choices = [
            questionary.Choice(
                title=f"{name} - {sub_config.get('context', '(no description)')[:60]}",
                value=name,
                checked=True,
            )
            for name, sub_config in subagents.items()
            if isinstance(sub_config, dict)
        ]

        approved = questionary.checkbox(
            "Select subagents to include (space to toggle, enter to confirm):",
            choices=choices,
        ).ask()

        if approved is None:
            # User pressed Ctrl+C
            raise SetupCancelled()

        return approved

    except ImportError:
        # Fallback: batch approval without questionary
        console.print("[dim]Tip: install 'questionary' for interactive checkboxes[/dim]\n")

        accept_all = safe_confirm("Accept all subagents?", default=True, allow_cancel=True)
        if accept_all:
            return [name for name, sub_config in subagents.items() if isinstance(sub_config, dict)]

        # Ask which to remove
        names = [name for name, sub_config in subagents.items() if isinstance(sub_config, dict)]
        for i, name in enumerate(names, 1):
            console.print(f"  [{i}] {name}")

        to_remove = safe_prompt(
            "Enter numbers to remove (comma-separated, or empty to keep all)",
            default="",
            allow_cancel=True,
        ).strip()

        if not to_remove:
            return names

        try:
            remove_indices = {int(x.strip()) - 1 for x in to_remove.split(",")}
            return [name for i, name in enumerate(names) if i not in remove_indices]
        except ValueError:
            console.print("[yellow]Invalid input, keeping all subagents.[/yellow]")
            return names


def _update_config_with_approved_subagents(agents_file: Path, approved: list[str]) -> bool:
    """
    Remove rejected subagents from configuration.

    Args:
        agents_file: Path to agents.yaml
        approved: List of approved subagent names

    Returns:
        True if successful
    """
    try:
        with open(agents_file, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

        main = config.get("main", {})
        if not isinstance(main, dict):
            return False

        subagents = main.get("subagents", {})
        if not isinstance(subagents, dict):
            return False

        # Filter to keep only approved subagents
        filtered_subagents = {
            name: sub_config for name, sub_config in subagents.items() if name in approved
        }

        main["subagents"] = filtered_subagents
        config["main"] = main

        # Save updated config
        with open(agents_file, "w", encoding="utf-8") as f:
            yaml.dump(
                config,
                f,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
            )

        return True

    except Exception as e:
        console.print(f"[red]Could not update agents.yaml: {e}[/red]")
        return False


def _run_full_reconfiguration(settings, base_dir: Path) -> bool:
    """
    Complete agent reconfiguration with all --init features.

    Includes:
    - Model selection
    - PDF conversion
    - Catalog build/refresh
    - Summary generation
    - Subagent selection with approval
    - LLM analysis
    - Iterative revision

    Changes are only saved when the user accepts the final configuration.
    Pressing Ctrl+C at any point cancels without saving.

    Returns:
        True if successful
    """
    config_dir = base_dir / ".flavia"
    agents_file = config_dir / "agents.yaml"

    console.print("\n[bold blue]Full Agent Reconfiguration[/bold blue]")
    console.print("[dim](Press Ctrl+C at any time to cancel without saving)[/dim]\n")

    # Backup existing agents.yaml (to restore on cancel)
    original_agents_content: Optional[str] = None
    if agents_file.exists():
        try:
            original_agents_content = agents_file.read_text(encoding="utf-8")
        except Exception:
            pass

    try:
        return _run_full_reconfiguration_inner(
            settings, base_dir, config_dir, agents_file, original_agents_content
        )
    except SetupCancelled:
        console.print("\n[yellow]Setup cancelled. No changes saved.[/yellow]")
        # Restore original agents.yaml if it existed
        if original_agents_content is not None:
            try:
                agents_file.write_text(original_agents_content, encoding="utf-8")
            except Exception:
                pass
        elif agents_file.exists():
            # The file was created during setup but didn't exist before
            try:
                agents_file.unlink()
            except Exception:
                pass
        return False


def _run_full_reconfiguration_inner(
    settings,
    base_dir: Path,
    config_dir: Path,
    agents_file: Path,
    original_agents_content: Optional[str],
) -> bool:
    """Inner implementation of full reconfiguration (wrapped by cancel handler)."""

    # 1. Model selection for setup
    console.print("\n[bold]Step 1: Model Selection[/bold]")
    console.print("Choose which model to use for analyzing your project.")

    selected_model = _select_model_for_setup(settings, allow_cancel=True)

    # Test connection
    attempted, success = _test_selected_model_connection(settings, selected_model)
    if attempted and not success:
        console.print("[red]Model connection test failed. Aborting.[/red]")
        return False

    # 2. Preparation Status (Documents, Catalog, Summaries)
    console.print("\n[bold]Step 2: Preparation[/bold]")

    pdf_files = find_pdf_files(base_dir)
    convert_pdfs = False
    pdf_file_refs = None
    catalog = None

    # Detect current state of each preparation step
    converted_dir = base_dir / CONVERTED_DIR_NAME
    has_pdfs = bool(pdf_files)

    catalog_file = config_dir / "content_catalog.json"
    has_catalog = catalog_file.exists()
    catalog_file_count = 0
    catalog_summary_count = 0
    catalog_files_needing_summary = 0

    if has_catalog:
        from flavia.content.catalog import ContentCatalog

        existing_catalog = ContentCatalog.load(config_dir)
        if existing_catalog:
            catalog_file_count = len(existing_catalog.files)
            catalog_summary_count = sum(1 for e in existing_catalog.files.values() if e.summary)
            catalog_files_needing_summary = len(existing_catalog.get_files_needing_summary())
            catalog = existing_catalog

    # Show preparation status
    doc_icon, doc_status, converted_pdf_count = _build_documents_preparation_status(
        base_dir=base_dir,
        converted_dir=converted_dir,
        pdf_files=pdf_files,
        catalog=catalog,
    )

    catalog_status = "not built"
    catalog_icon = "[yellow]\u2717[/yellow]"
    if has_catalog and catalog_file_count > 0:
        catalog_status = f"{catalog_file_count} files indexed"
        catalog_icon = "[green]\u2713[/green]"

    summary_status = "not generated"
    summary_icon = "[yellow]\u2717[/yellow]"
    if catalog_files_needing_summary == 0 and catalog_file_count > 0:
        summary_status = f"{catalog_summary_count} files summarized"
        summary_icon = "[green]\u2713[/green]"
    elif catalog_summary_count > 0 and catalog_file_count > 0:
        summary_status = f"{catalog_summary_count}/{catalog_file_count} files summarized"
    elif not has_catalog:
        summary_status = "requires catalog"
        summary_icon = "[dim]-[/dim]"

    console.print(f"  {doc_icon} Documents:       {doc_status}")
    console.print(f"  {catalog_icon} Content catalog: {catalog_status}")
    console.print(f"  {summary_icon} Summaries:       {summary_status}")
    console.print()

    # Determine what needs to be done
    needs_conversion = has_pdfs and converted_pdf_count < len(pdf_files)
    needs_catalog = not has_catalog or catalog_file_count == 0
    needs_summaries = has_catalog and catalog_files_needing_summary > 0
    run_catalog_build = False
    run_summaries = False

    if not needs_conversion and not needs_catalog and not needs_summaries:
        # Everything is ready
        rebuild = safe_confirm(
            "All preparation steps are complete. Rebuild any?",
            default=False,
            allow_cancel=True,
        )
        if rebuild:
            rebuild_choices: list[str] = []
            try:
                import questionary

                rebuild_choices = questionary.checkbox(
                    "Select what to rebuild:",
                    choices=[
                        questionary.Choice(
                            f"Documents ({doc_status})",
                            value="docs",
                            checked=False,
                        ),
                        questionary.Choice(
                            f"Content catalog ({catalog_status})",
                            value="catalog",
                            checked=False,
                        ),
                        questionary.Choice(
                            f"Summaries ({summary_status})",
                            value="summaries",
                            checked=False,
                        ),
                    ],
                ).ask()
            except ImportError:
                console.print(
                    "[dim]Tip: install 'questionary' for interactive rebuild selection[/dim]"
                )

                rebuild_options = [
                    ("docs", f"Documents ({doc_status})"),
                    ("catalog", f"Content catalog ({catalog_status})"),
                    ("summaries", f"Summaries ({summary_status})"),
                ]
                for i, (_, label) in enumerate(rebuild_options, 1):
                    console.print(f"  [{i}] {label}")

                selected = safe_prompt(
                    "Enter numbers to rebuild (comma-separated, or empty for none)",
                    default="",
                    allow_cancel=True,
                ).strip()
                if selected:
                    try:
                        selected_indexes = {
                            int(value.strip()) - 1 for value in selected.split(",") if value.strip()
                        }
                        rebuild_choices = [
                            key
                            for i, (key, _) in enumerate(rebuild_options)
                            if i in selected_indexes
                        ]
                    except ValueError:
                        console.print("[yellow]Invalid input, skipping rebuild.[/yellow]")
                        rebuild_choices = []

            if rebuild_choices is None:
                raise SetupCancelled()

            if "docs" in rebuild_choices and has_pdfs:
                convert_pdfs = True
                pdf_file_refs = _pdf_paths_for_tools(base_dir, pdf_files)
            if "catalog" in rebuild_choices or "docs" in rebuild_choices:
                run_catalog_build = True
            if "summaries" in rebuild_choices:
                run_summaries = True
    else:
        # Some steps need to be done
        missing_parts = []
        if needs_conversion:
            missing_parts.append("convert documents")
        if needs_catalog:
            missing_parts.append("build catalog")
        if needs_summaries:
            missing_parts.append("generate summaries")

        run_prep = safe_confirm(
            f"Run missing steps ({', '.join(missing_parts)})?",
            default=True,
            allow_cancel=True,
        )
        if run_prep:
            if needs_conversion:
                convert_pdfs = True
                pdf_file_refs = _pdf_paths_for_tools(base_dir, pdf_files)
            run_catalog_build = needs_catalog or convert_pdfs

            # Keep summary generation as explicit opt-in since it consumes tokens.
            if needs_summaries or needs_catalog:
                console.print("  (Generating summaries improves context, but uses LLM tokens)")
                run_summaries = safe_confirm(
                    "Generate summaries with LLM?",
                    default=False,
                    allow_cancel=True,
                )

    # Execute preparation steps as needed
    if run_catalog_build:
        config_dir.mkdir(parents=True, exist_ok=True)
        catalog = _build_content_catalog(
            base_dir,
            config_dir,
            convert_docs=convert_pdfs,
            binary_docs=pdf_files if convert_pdfs else None,
        )
        if catalog:
            console.print(f"[green]Catalog built: {len(catalog.files)} files indexed[/green]")

    if run_summaries and catalog:
        _run_summarization(catalog, config_dir, selected_model)

    # 3. Subagent configuration
    console.print("\n[bold]Step 3: Subagent Configuration[/bold]")
    console.print("Subagents are specialized assistants (e.g., summarizer, explainer).")

    include_subagents = safe_confirm(
        "Include specialized subagents?", default=False, allow_cancel=True
    )
    subagent_approval_mode = include_subagents  # Flag for approval UI

    # 4. Main-agent write capability
    console.print("\n[bold]Step 4: Main Agent File Modification[/bold]")
    main_agent_can_write = _ask_main_agent_write_capability(allow_cancel=True)

    # 5. User guidance
    console.print("\n[bold]Step 5: Project Guidance (Optional)[/bold]")
    user_guidance = _ask_user_guidance(allow_cancel=True)

    # 6. Create setup agent
    agent, error = create_setup_agent(
        base_dir,
        include_pdf_tool=convert_pdfs,
        pdf_files=pdf_file_refs,
        model_override=selected_model,
    )

    if error:
        console.print(f"[red]{error}[/red]")
        return False

    # 7. Iterative analysis and generation
    console.print("\n[bold]Step 6: Analyzing Project[/bold]\n")

    config_dir.mkdir(parents=True, exist_ok=True)
    agents_file = config_dir / "agents.yaml"
    revision_notes: list[str] = []

    for revision in range(MAX_SETUP_REVISIONS):
        if agents_file.exists():
            agents_file.unlink()

        task = _build_setup_task(
            convert_pdfs=convert_pdfs,
            selected_model=selected_model,
            user_guidance=user_guidance,
            main_agent_can_write=main_agent_can_write,
            revision_notes=revision_notes,
            include_subagents=include_subagents,
            catalog=catalog,
            subagent_approval_mode=subagent_approval_mode,
        )

        # Execute analysis
        try:
            response = agent.run(task)
            console.print(Markdown(response))
        except Exception as e:
            console.print(f"[red]Error during analysis: {e}[/red]")
            return False

        # Check if agents.yaml was created
        if not agents_file.exists():
            console.print("[red]agents.yaml was not created. Retrying...[/red]")
            if revision < MAX_SETUP_REVISIONS - 1:
                continue
            else:
                console.print("[red]Max revisions reached. Aborting.[/red]")
                return False

        # Preview generated config
        console.print("\n[bold]Generated Configuration:[/bold]\n")
        _show_agents_preview(agents_file)

        # 9. Subagent approval interface
        if subagent_approval_mode:
            console.print("\n[bold]Subagent Approval[/bold]\n")
            approved_subagents = _approve_subagents(agents_file)
            if approved_subagents is not None:  # None means error
                updated = _update_config_with_approved_subagents(agents_file, approved_subagents)
                if not updated:
                    console.print("[red]Failed to apply subagent approvals. Aborting.[/red]")
                    return False
                if approved_subagents:
                    console.print(f"[green]Kept {len(approved_subagents)} subagent(s)[/green]")
                else:
                    console.print("[green]Removed all subagents[/green]")

        # Ask for confirmation or revision
        satisfied = safe_confirm("\nAccept this configuration?", default=True, allow_cancel=True)

        if satisfied:
            # Ensure all agents have models
            _ensure_agent_models(agents_file, str(selected_model))

            console.print("\n[green]Configuration saved![/green]")
            console.print("[yellow]Use /reset to load the new configuration.[/yellow]")
            return True

        # Ask for revision feedback
        if revision < MAX_SETUP_REVISIONS - 1:
            console.print(f"\n[dim]Revision {revision + 1}/{MAX_SETUP_REVISIONS}[/dim]")
            feedback = safe_prompt("What would you like to change?", allow_cancel=True).strip()
            if not feedback:
                console.print(
                    "[yellow]No feedback provided. Using previous configuration.[/yellow]"
                )
                _ensure_agent_models(agents_file, str(selected_model))
                return True
            revision_notes.append(feedback)
        else:
            console.print("[yellow]Max revisions reached. Using last configuration.[/yellow]")
            _ensure_agent_models(agents_file, str(selected_model))
            return True

    return False


def _run_agent_revision(settings, base_dir: Path) -> bool:
    """
    Modify existing agents.yaml with LLM assistance.

    Loads the current configuration, shows it to the user, and allows
    iterative text-free modifications via LLM. Changes are only saved
    when the user accepts the final configuration.

    Returns:
        True if successful
    """
    config_dir = base_dir / ".flavia"
    agents_file = config_dir / "agents.yaml"

    if not agents_file.exists():
        console.print("[yellow]No agents.yaml found. Use 'Full' mode to create one.[/yellow]")
        return False

    console.print("\n[bold blue]Agent Revision[/bold blue]")
    console.print("[dim](Press Ctrl+C at any time to cancel without saving)[/dim]\n")

    # Backup original
    try:
        original_content = agents_file.read_text(encoding="utf-8")
    except Exception as e:
        console.print(f"[red]Could not read agents.yaml: {e}[/red]")
        return False

    try:
        return _run_agent_revision_inner(
            settings, base_dir, config_dir, agents_file, original_content
        )
    except SetupCancelled:
        console.print("\n[yellow]Revision cancelled. No changes saved.[/yellow]")
        # Restore original
        try:
            agents_file.write_text(original_content, encoding="utf-8")
        except Exception:
            pass
        return False


def _run_agent_revision_inner(
    settings,
    base_dir: Path,
    config_dir: Path,
    agents_file: Path,
    original_content: str,
) -> bool:
    """Inner implementation of agent revision (wrapped by cancel handler)."""

    # Show current configuration
    console.print("[bold]Current Configuration:[/bold]\n")
    _show_agents_preview(agents_file)

    # Model selection
    console.print("\n[bold]Model for revision:[/bold]")
    selected_model = _select_model_for_setup(settings, allow_cancel=True)
    main_agent_can_write = _ask_main_agent_write_capability(allow_cancel=True)

    # Test connection
    attempted, success = _test_selected_model_connection(settings, selected_model)
    if attempted and not success:
        console.print("[red]Model connection test failed. Aborting.[/red]")
        return False

    # Load catalog if available (for context)
    catalog = None
    catalog_file = config_dir / "content_catalog.json"
    if catalog_file.exists():
        from flavia.content.catalog import ContentCatalog

        catalog = ContentCatalog.load(config_dir)

    # Create setup agent
    agent, error = create_setup_agent(
        base_dir,
        include_pdf_tool=False,
        pdf_files=None,
        model_override=selected_model,
    )

    if error:
        console.print(f"[red]{error}[/red]")
        return False

    config_dir.mkdir(parents=True, exist_ok=True)

    for revision in range(MAX_SETUP_REVISIONS):
        # Ask what to change
        console.print()
        feedback = safe_prompt("What would you like to change?", allow_cancel=True).strip()

        if not feedback:
            console.print("[yellow]No changes requested. Keeping current configuration.[/yellow]")
            return True

        # Build revision task with current config as context
        current_config = agents_file.read_text(encoding="utf-8")
        task = _build_revision_task(
            current_config=current_config,
            selected_model=selected_model,
            main_agent_can_write=main_agent_can_write,
            feedback=feedback,
            catalog=catalog,
        )

        # Delete current file so the tool can recreate it
        if agents_file.exists():
            agents_file.unlink()

        # Execute revision
        try:
            response = agent.run(task)
            console.print(Markdown(response))
        except Exception as e:
            console.print(f"[red]Error during revision: {e}[/red]")
            # Restore original on error
            agents_file.write_text(original_content, encoding="utf-8")
            return False

        # Check if agents.yaml was created
        if not agents_file.exists():
            console.print("[red]agents.yaml was not created. Restoring original.[/red]")
            agents_file.write_text(original_content, encoding="utf-8")
            if revision < MAX_SETUP_REVISIONS - 1:
                continue
            else:
                return False

        # Preview revised config
        console.print("\n[bold]Revised Configuration:[/bold]\n")
        _show_agents_preview(agents_file)

        # Accept or continue revising
        satisfied = safe_confirm("\nAccept this configuration?", default=True, allow_cancel=True)

        if satisfied:
            _ensure_agent_models(agents_file, str(selected_model))
            console.print("\n[green]Configuration saved![/green]")
            console.print("[yellow]Use /reset to load the new configuration.[/yellow]")
            return True

        if revision >= MAX_SETUP_REVISIONS - 1:
            console.print("[yellow]Max revisions reached. Using last configuration.[/yellow]")
            _ensure_agent_models(agents_file, str(selected_model))
            return True

        console.print(f"\n[dim]Revision {revision + 1}/{MAX_SETUP_REVISIONS}[/dim]")

    return False


def _build_revision_task(
    current_config: str,
    selected_model: str,
    main_agent_can_write: bool,
    feedback: str,
    catalog: Optional[Any] = None,
) -> str:
    """Build a revision task that includes the current config and user feedback."""
    read_only_tools_str = ", ".join(_default_main_tools(False))
    write_enabled_tools_str = ", ".join(_default_main_tools(True))
    write_capable_tools_str = ", ".join(WRITE_CAPABLE_RUNTIME_TOOLS)
    if main_agent_can_write:
        write_instruction = (
            "Keep or enable write capability for the main agent. "
            "Set `main.tools` to the full default runtime toolset with write access: "
            f"{write_enabled_tools_str}. "
            "and `permissions.write` includes allowed writable paths."
        )
    else:
        write_instruction = (
            "Enforce read-only behavior for the main agent. "
            "Set `main.tools` to the read-only default runtime toolset: "
            f"{read_only_tools_str}. "
            f"Ensure `main.tools` does NOT include write-capable tools ({write_capable_tools_str})."
        )

    parts = [
        "You are revising an existing agents.yaml configuration. "
        "The user wants to modify the current setup. "
        "Read the current configuration below, apply the requested changes, "
        "and use create_agents_config to write the updated file.\n\n"
        f"CURRENT agents.yaml:\n```yaml\n{current_config}\n```",
        (
            "The generated main agent must explicitly set "
            f"model to '{selected_model}' in agents.yaml."
        ),
        write_instruction,
        f"User requested changes:\n{feedback}",
    ]

    # Include catalog context if available
    if catalog:
        try:
            context_summary = catalog.generate_context_summary(max_length=2000)
            if context_summary:
                parts.append(f"Project content catalog summary:\n\n{context_summary}")
        except Exception:
            pass

    return "\n\n".join(parts)


def run_agent_setup_command(settings, base_dir: Path) -> bool:
    """
    Unified agent setup command with three modes:
    1. Quick model change
    2. Revise existing agents with LLM assistance
    3. Full reconfiguration from scratch

    Returns:
        True if successful
    """
    try:
        import questionary

        choices = [
            questionary.Choice(
                title="Quick:  Change models for existing agents",
                value="1",
            ),
            questionary.Choice(
                title="Revise: Modify current agents with LLM assistance",
                value="2",
            ),
            questionary.Choice(
                title="Full:   Delete current agents and start fresh",
                value="3",
            ),
        ]
    except ImportError:
        choices = [
            "Quick:  Change models for existing agents",
            "Revise: Modify current agents with LLM assistance",
            "Full:   Delete current agents and start fresh",
        ]

    console.print("\n[bold blue]Agent Setup[/bold blue]\n")

    choice = q_select("Choose setup mode:", choices=choices, default="1")

    if choice is None:
        console.print("[yellow]Setup cancelled.[/yellow]")
        return False

    # Handle both Choice objects and plain strings
    if hasattr(choice, "value"):
        choice = choice.value
    elif choice.startswith("Quick"):
        choice = "1"
    elif choice.startswith("Revise"):
        choice = "2"
    elif choice.startswith("Full"):
        choice = "3"

    if choice == "1":
        # Quick mode: just change models
        from flavia.setup import manage_agent_models

        return manage_agent_models(settings, base_dir)

    elif choice == "2":
        # Revise mode: modify existing agents with LLM
        return _run_agent_revision(settings, base_dir)

    elif choice == "3":
        # Full mode: complete reconfiguration from scratch
        return _run_full_reconfiguration(settings, base_dir)

    else:
        console.print("[yellow]Invalid choice. Aborting.[/yellow]")
        return False
