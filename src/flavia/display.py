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

    return re.sub(r"\[/?(?:bold|cyan|red|green|dim)\]", "", text)


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
            _print(f"      {global_index}: {model.name} - [cyan]{model_id}[/cyan]{default}")
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

    if schema.parameters:
        _print(f"\n  [bold]Parameters:[/bold]")
        for param in schema.parameters:
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
    _print(f"  Base Directory:    {settings.base_dir}")
    _print(f"  Max Depth:         {settings.max_depth}")
    _print(f"  Parallel Workers:  {settings.parallel_workers}")
    _print(f"  Subagents Enabled: {settings.subagents_enabled}")
    _print(f"  Active Agent:      {settings.active_agent or 'main'}")

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
