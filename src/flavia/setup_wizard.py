"""Setup wizard for initializing flavIA configuration."""

import sys
from pathlib import Path
from typing import Optional, List

from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.prompt import Confirm
from rich.table import Table

console = Console()


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
    """Find all PDF files in a directory (non-recursive)."""
    return list(directory.glob("*.pdf"))


def create_setup_agent(base_dir: Path, include_pdf_tool: bool = False, pdf_files: List[str] = None):
    """Create the setup agent with special tools."""
    from flavia.config import load_settings
    from flavia.agent import RecursiveAgent, AgentProfile
    from flavia.tools.registry import registry
    from flavia.tools.setup.create_agents_config import CreateAgentsConfigTool
    from flavia.tools.setup.convert_pdfs import ConvertPdfsTool

    # Load settings
    settings = load_settings()

    if not settings.api_key:
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
        model=settings.default_model,
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

    console.print(Panel.fit(
        "[bold blue]flavIA Setup Wizard[/bold blue]\n\n"
        "[dim]AI assistant for academic and research work[/dim]\n\n"
        f"Initializing in:\n[cyan]{target_dir}[/cyan]",
        title="Welcome",
    ))

    # Check if already exists
    if config_dir.exists():
        if not Confirm.ask(f"\n[yellow].flavia/ already exists.[/yellow] Overwrite?", default=False):
            console.print("[yellow]Setup cancelled.[/yellow]")
            return False
        import shutil
        shutil.rmtree(config_dir)

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

        convert_pdfs = Confirm.ask(
            "\n[bold]Convert PDFs to text for analysis?[/bold]\n"
            "  (This allows the AI to read and search the documents)",
            default=True,
        )
    else:
        convert_pdfs = False

    # Ask about AI analysis
    console.print("\n")
    analyze = Confirm.ask(
        "[bold]Have the AI analyze your content and suggest an agent configuration?[/bold]\n"
        "  (The AI will read files to understand your project/research area)",
        default=True,
    )

    if analyze or convert_pdfs:
        return _run_ai_setup(
            target_dir,
            config_dir,
            convert_pdfs=convert_pdfs,
            pdf_files=[p.name for p in pdf_files] if convert_pdfs else None,
        )
    else:
        return _run_basic_setup(target_dir, config_dir)


def _run_basic_setup(target_dir: Path, config_dir: Path) -> bool:
    """Create basic default configuration."""
    console.print("\n[dim]Creating default configuration...[/dim]")

    try:
        config_dir.mkdir(parents=True, exist_ok=True)

        # Create .env
        env_content = """\
# flavIA Configuration
# Add your API key here

SYNTHETIC_API_KEY=your_api_key_here
API_BASE_URL=https://api.synthetic.new/openai/v1

# Optional settings
# DEFAULT_MODEL=hf:moonshotai/Kimi-K2.5
# AGENT_MAX_DEPTH=3
"""
        (config_dir / ".env").write_text(env_content)

        # Create models.yaml
        models_content = """\
models:
  - id: "hf:moonshotai/Kimi-K2.5"
    name: "Kimi-K2.5"
    default: true

  - id: "hf:zai-org/GLM-4.7"
    name: "GLM-4.7"

  - id: "hf:MiniMaxAI/MiniMax-M2.1"
    name: "MiniMax-M2.1"
"""
        (config_dir / "models.yaml").write_text(models_content)

        # Create academic-focused default agents.yaml
        agents_content = """\
# flavIA Agent Configuration
# Default academic assistant

main:
  context: |
    You are an academic research assistant.
    You help analyze documents, explain concepts, find information, and assist with research tasks.
    Working directory: {base_dir}

    When answering questions:
    - Be precise and cite specific passages when relevant
    - Explain complex concepts clearly
    - Help the user understand and work with their documents

  tools:
    - read_file
    - list_files
    - search_files
    - get_file_info
    - spawn_agent
    - spawn_predefined_agent

  subagents:
    summarizer:
      context: |
        You are a summarization specialist.
        Create clear, concise summaries that capture the key points.
        Include important details, arguments, and conclusions.
      tools:
        - read_file

    explainer:
      context: |
        You are an expert at explaining complex concepts.
        Break down difficult ideas into understandable parts.
        Use analogies and examples when helpful.
      tools:
        - read_file
        - search_files

    researcher:
      context: |
        You are a research specialist.
        Find specific information, quotes, and references across documents.
        Be thorough and precise in your searches.
      tools:
        - read_file
        - list_files
        - search_files
"""
        (config_dir / "agents.yaml").write_text(agents_content)

        # Create .gitignore
        (config_dir / ".gitignore").write_text(".env\n")

        _print_success(config_dir)
        return True

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        return False


def _run_ai_setup(
    target_dir: Path,
    config_dir: Path,
    convert_pdfs: bool = False,
    pdf_files: List[str] = None,
) -> bool:
    """Run AI-assisted setup."""
    console.print("\n[dim]Initializing AI setup agent...[/dim]")

    agent, error = create_setup_agent(
        target_dir,
        include_pdf_tool=convert_pdfs,
        pdf_files=pdf_files,
    )

    if error:
        console.print(f"[red]{error}[/red]")
        console.print("\n[yellow]Falling back to basic setup...[/yellow]")
        return _run_basic_setup(target_dir, config_dir)

    # Create the config dir first
    config_dir.mkdir(parents=True, exist_ok=True)

    # Create .env
    env_content = """\
# flavIA Configuration
# Add your API key here

SYNTHETIC_API_KEY=your_api_key_here
API_BASE_URL=https://api.synthetic.new/openai/v1
"""
    (config_dir / ".env").write_text(env_content)

    # Create models.yaml
    models_content = """\
models:
  - id: "hf:moonshotai/Kimi-K2.5"
    name: "Kimi-K2.5"
    default: true

  - id: "hf:zai-org/GLM-4.7"
    name: "GLM-4.7"

  - id: "hf:MiniMaxAI/MiniMax-M2.1"
    name: "MiniMax-M2.1"
"""
    (config_dir / "models.yaml").write_text(models_content)

    # Create .gitignore
    (config_dir / ".gitignore").write_text(".env\nconverted/\n")

    # Build the task message
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

        task = (
            "Analyze the converted content in the 'converted/' directory and create an "
            "appropriate agents.yaml configuration specialized for this academic material. "
            "Use create_agents_config to write the file."
        )
    else:
        task = (
            "Analyze this directory and create an appropriate agents.yaml configuration. "
            "Look for documents, understand the subject matter, and create an agent "
            "specialized for this academic/research content. Use create_agents_config to write the file."
        )
        console.print("\n[bold]Analyzing content...[/bold]\n")

    try:
        response = agent.run(task)
        console.print(Markdown(response))

        # Verify the file was created
        if (config_dir / "agents.yaml").exists():
            _print_success(config_dir, has_pdfs=convert_pdfs)
            return True
        else:
            console.print("\n[yellow]AI did not create the config file. Creating default...[/yellow]")
            return _run_basic_setup(target_dir, config_dir)

    except KeyboardInterrupt:
        console.print("\n[yellow]Setup interrupted.[/yellow]")
        return False
    except Exception as e:
        console.print(f"\n[red]Error during AI setup: {e}[/red]")
        console.print("[yellow]Falling back to basic setup...[/yellow]")
        return _run_basic_setup(target_dir, config_dir)


def _print_success(config_dir: Path, has_pdfs: bool = False):
    """Print success message."""
    extra_info = ""
    if has_pdfs:
        extra_info = "\n[dim]Converted documents are in: converted/[/dim]\n"

    console.print(Panel.fit(
        "[bold green]Setup complete![/bold green]\n\n"
        f"Configuration created at:\n"
        f"  [cyan]{config_dir}/.env[/cyan] - API keys\n"
        f"  [cyan]{config_dir}/models.yaml[/cyan] - Models\n"
        f"  [cyan]{config_dir}/agents.yaml[/cyan] - Agents\n"
        f"{extra_info}\n"
        "[bold]Next steps:[/bold]\n"
        f"  1. Edit [cyan]{config_dir}/.env[/cyan] with your API key\n"
        "  2. Run [bold]flavia[/bold] to start chatting with your documents",
        title="Success",
    ))


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
        if not Confirm.ask("[yellow]agents.yaml already exists.[/yellow] Overwrite?", default=False):
            return False

    # Check for PDFs
    pdf_files = find_pdf_files(base_dir)
    convert_pdfs = False

    if pdf_files:
        # Check if already converted
        converted_dir = base_dir / "converted"
        if converted_dir.exists() and list(converted_dir.glob("*.md")):
            console.print(f"[dim]Found existing converted documents in converted/[/dim]")
        else:
            console.print(f"[dim]Found {len(pdf_files)} PDF file(s)[/dim]")
            convert_pdfs = Confirm.ask("Convert PDFs to text first?", default=True)

    analyze = Confirm.ask(
        "Analyze content and suggest agent configuration?",
        default=True,
    )

    if not analyze and not convert_pdfs:
        return False

    agent, error = create_setup_agent(
        base_dir,
        include_pdf_tool=convert_pdfs,
        pdf_files=[p.name for p in pdf_files] if convert_pdfs else None,
    )

    if error:
        console.print(f"[red]{error}[/red]")
        return False

    # Build task
    if convert_pdfs:
        task = (
            f"First convert the PDFs to markdown: {', '.join(p.name for p in pdf_files)}. "
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
            console.print("\n[green]Configuration updated![/green]")
            console.print("[yellow]Run /reset to load the new configuration.[/yellow]")
            return True

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")

    return False
