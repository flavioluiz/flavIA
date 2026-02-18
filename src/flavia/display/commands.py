"""
Shared display functions for flavIA info commands.

This module provides unified display functions used by both CLI flags
and slash commands, with support for Rich formatting (interactive) and
plain text output (piping/CLI).
"""

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from rich.console import Console
    from flavia.config import Settings


def _strip_rich_markup(text: str) -> str:
    """Strip only Rich markup tags used by this module."""
    import re

    return re.sub(r"\[/?(?:bold|cyan|red|green|dim|yellow)\]", "", text)


def display_providers(
    settings: "Settings",
    console: Optional["Console"] = None,
    use_rich: bool = True,
) -> None:
    """
    Display configured providers with their models.

    Args:
        settings: Current settings with provider configuration
        console: Rich console for formatted output (optional)
        use_rich: Whether to use Rich formatting (False for plain text)
    """
    if use_rich and console is None:
        from rich.console import Console
        console = Console()

    def _print(text: str = "", **kwargs) -> None:
        if use_rich and console:
            console.print(text, **kwargs)
        else:
            print(_strip_rich_markup(text))

    _print("\n[bold]Configured Providers:[/bold]")
    _print("-" * 60)

    if not settings.providers.providers:
        _print("  No providers configured")
        _print("  Run 'flavia --setup-provider' to configure providers")
        _print()
        return

    global_index = 0
    for provider_id, provider in settings.providers.providers.items():
        default_marker = ""
        if provider_id == settings.providers.default_provider_id:
            default_marker = " [DEFAULT]"

        _print(f"\n  [bold]{provider.name}[/bold] ({provider_id}){default_marker}")
        _print(f"    URL: {provider.api_base_url}")

        # Show API key status
        if provider.api_key:
            if use_rich and console:
                console.print(f"    API Key: [green]Configured[/green]", end="")
                if provider.api_key_env_var:
                    console.print(f" [dim](from ${provider.api_key_env_var})[/dim]")
                else:
                    console.print()
            else:
                key_info = "Configured"
                if provider.api_key_env_var:
                    key_info += f" (from ${provider.api_key_env_var})"
                print(f"    API Key: {key_info}")
        else:
            _print(f"    API Key: [red]Not set[/red]")

        # Show models with global index
        _print(f"    Models:")
        for model in provider.models:
            default = " (default)" if model.default else ""
            model_id = f"{provider_id}:{model.id}"
            _print(
                f"      [yellow]{global_index}[/yellow]: {model.name} - "
                f"[cyan]{model_id}[/cyan]{default}"
            )
            global_index += 1

    _print()


def display_tools(
    console: Optional["Console"] = None,
    use_rich: bool = True,
    skip_setup: bool = True,
) -> None:
    """
    Display available tools grouped by category.

    Args:
        console: Rich console for formatted output (optional)
        use_rich: Whether to use Rich formatting (False for plain text)
        skip_setup: Whether to skip tools in the "setup" category
    """
    from flavia.tools import get_registry

    if use_rich and console is None:
        from rich.console import Console
        console = Console()

    def _print(text: str = "", **kwargs) -> None:
        if use_rich and console:
            console.print(text, **kwargs)
        else:
            print(_strip_rich_markup(text))

    registry = get_registry()
    all_tools = registry.get_all()

    _print("\n[bold]Available Tools:[/bold]")
    _print("-" * 60)

    # Group by category
    categories: dict[str, list] = {}
    for tool in all_tools.values():
        if skip_setup and tool.category == "setup":
            continue
        cat = tool.category
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(tool)

    for category, tool_list in sorted(categories.items()):
        _print(f"\n[bold][{category.upper()}][/bold]")
        for tool in sorted(tool_list, key=lambda t: t.name):
            _print(f"  [cyan]{tool.name}[/cyan]")
            _print(f"    {tool.description}")

    _print()


def display_tool_schema(
    tool_name: str,
    console: Optional["Console"] = None,
    use_rich: bool = True,
) -> bool:
    """
    Display the full schema of a specific tool.

    Args:
        tool_name: Name of the tool to display
        console: Rich console for formatted output (optional)
        use_rich: Whether to use Rich formatting (False for plain text)

    Returns:
        True if tool was found and displayed, False otherwise
    """
    from flavia.tools import get_registry

    if use_rich and console is None:
        from rich.console import Console
        console = Console()

    def _print(text: str = "", **kwargs) -> None:
        if use_rich and console:
            console.print(text, **kwargs)
        else:
            print(_strip_rich_markup(text))

    registry = get_registry()
    tool = registry.get(tool_name)

    if tool is None:
        _print(f"[red]Error: Tool '{tool_name}' not found[/red]")
        _print("\nUse /tools to see available tools.")
        return False

    schema = tool.get_schema()

    _print(f"\n[bold]Tool: {schema.name}[/bold]")
    _print("-" * 60)
    _print(f"  Category: [cyan]{tool.category}[/cyan]")
    _print(f"  Description: {schema.description}")

    schema_params = (
        schema.parameters_with_common_fields()
        if hasattr(schema, "parameters_with_common_fields")
        else schema.parameters
    )

    if schema_params:
        _print(f"\n  [bold]Parameters:[/bold]")
        for param in schema_params:
            required_marker = " [red](required)[/red]" if param.required else ""
            _print(f"\n    [cyan]{param.name}[/cyan]{required_marker}")
            _print(f"      Type: {param.type}")
            _print(f"      Description: {param.description}")

            if param.enum:
                enum_str = ", ".join(param.enum)
                _print(f"      Allowed values: {enum_str}")

            if param.default is not None:
                _print(f"      Default: {param.default}")
    else:
        _print("\n  [dim]No parameters[/dim]")

    _print()
    return True


def display_config(
    settings: "Settings",
    console: Optional["Console"] = None,
    use_rich: bool = True,
) -> None:
    """
    Display configuration paths and active settings.

    Args:
        settings: Current settings
        console: Rich console for formatted output (optional)
        use_rich: Whether to use Rich formatting (False for plain text)
    """
    if use_rich and console is None:
        from rich.console import Console
        console = Console()

    def _print(text: str = "", **kwargs) -> None:
        if use_rich and console:
            console.print(text, **kwargs)
        else:
            print(_strip_rich_markup(text))

    paths = settings.config_paths
    project_dir = settings.base_dir / ".flavia"
    prompt_history_file = project_dir / ".prompt_history"
    chat_log_file = project_dir / "chat_history.jsonl"

    # Section 1: Configuration paths
    _print("\n[bold]Configuration Paths:[/bold]")
    _print("-" * 60)
    _print(f"  Local:   {paths.local_dir or '(none)'}")
    _print(f"  User:    {paths.user_dir or '(none)'}")
    _print(f"  .env:    {paths.env_file or '(none)'}")
    _print(f"  models:  {paths.models_file or '(none)'}")
    _print(f"  agents:  {paths.agents_file or '(none)'}")
    _print(f"  prompts: {prompt_history_file}")
    _print(f"  chatlog: {chat_log_file}")

    # Section 2: Active settings
    _print(f"\n[bold]Active Settings:[/bold]")
    _print("-" * 60)
    _print(f"  API Base URL:      {settings.api_base_url}")
    _print(f"  Default Model:     {settings.default_model}")
    _print(f"  Summary Model:     {settings.summary_model or '(uses Default Model)'}")
    _print(f"  Base Directory:    {settings.base_dir}")
    _print(f"  Max Depth:         {settings.max_depth}")
    _print(f"  Parallel Workers:  {settings.parallel_workers}")
    _print(f"  Subagents Enabled: {settings.subagents_enabled}")
    _print(f"  Active Agent:      {settings.active_agent or 'main'}")
    _print(f"  RAG Debug Mode:    {settings.rag_debug}")
    _print(
        "  RAG Retrieval:     "
        f"router_k={settings.rag_catalog_router_k}, "
        f"vector_k={settings.rag_vector_k}, "
        f"fts_k={settings.rag_fts_k}, "
        f"rrf_k={settings.rag_rrf_k}, "
        f"max_chunks/doc={settings.rag_max_chunks_per_doc}"
    )
    _print(
        "  RAG Chunking:      "
        f"min_tokens={settings.rag_chunk_min_tokens}, "
        f"max_tokens={settings.rag_chunk_max_tokens}, "
        f"video_window_s={settings.rag_video_window_seconds}, "
        f"expand_temporal={settings.rag_expand_video_temporal}"
    )

    # Count models
    model_count = 0
    if settings.providers.providers:
        for provider in settings.providers.providers.values():
            model_count += len(provider.models)
    else:
        model_count = len(settings.models)
    _print(f"  Models Loaded:     {model_count}")

    _print(f"  Agents Config:     {'Yes' if settings.agents_config else 'No'}")
    _print()


def display_agents(
    settings: "Settings",
    console: Optional["Console"] = None,
    use_rich: bool = True,
) -> None:
    """
    Display available agents with their configurations.

    Args:
        settings: Current settings with agent configuration
        console: Rich console for formatted output (optional)
        use_rich: Whether to use Rich formatting (False for plain text)
    """
    if use_rich and console is None:
        from rich.console import Console

        console = Console()

    def _print(text: str = "", **kwargs) -> None:
        if use_rich and console:
            console.print(text, **kwargs)
        else:
            print(_strip_rich_markup(text))

    _print("\n[bold]Available Agents:[/bold]")
    _print("-" * 60)

    # Check if agents config exists
    if "main" not in settings.agents_config:
        _print("  No agent configuration. Default agent in use.")
        _print()
        return

    main_config = settings.agents_config["main"]
    current_agent = settings.active_agent or "main"

    # Helper to format agent info
    def _format_agent(name: str, config: dict, is_main: bool = False) -> None:
        active_marker = " [green][active][/green]" if name == current_agent else ""
        _print(f"\n  [bold]{name}[/bold]{active_marker}")

        # Model info
        model = config.get("model")
        if model:
            _print(f"    Model: [cyan]{model}[/cyan]")
        elif not is_main:
            main_model = main_config.get("model", "default")
            _print(f"    Model: [cyan]{main_model}[/cyan] [dim](inherited)[/dim]")
        else:
            _print(f"    Model: [dim]default[/dim]")

        # Tools info
        tools = config.get("tools", [])
        if tools:
            tool_count = len(tools)
            preview = ", ".join(tools[:3])
            if tool_count > 3:
                preview += ", ..."
            _print(f"    Tools: {tool_count} ({preview})")
        else:
            _print(f"    Tools: [dim]none[/dim]")

        # Context info (truncated)
        context = config.get("context", "")
        if context:
            truncated = context[:80].replace("\n", " ")
            if len(context) > 80:
                truncated += "..."
            _print(f"    Context: {truncated}")

    # Display main agent
    _format_agent("main", main_config, is_main=True)

    # Display subagents
    subagents = main_config.get("subagents", {})
    if isinstance(subagents, dict):
        for name, config in subagents.items():
            if isinstance(config, dict):
                _format_agent(name, config, is_main=False)

    _print()
