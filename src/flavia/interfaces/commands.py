"""Command registry and dispatch for CLI slash commands.

This module provides a lightweight command registry that maps command names
to handler functions and metadata, enabling structured help and clean dispatch.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, Optional

from rich.console import Console

if TYPE_CHECKING:
    from flavia.agent import RecursiveAgent
    from flavia.config import Settings


@dataclass
class CommandContext:
    """Shared context passed to command handlers.

    Handlers may mutate settings and agent when needed (e.g., /reset, /model).
    """

    settings: "Settings"
    agent: "RecursiveAgent"
    console: Console
    history_file: "Path"
    chat_log_file: "Path"
    history_enabled: bool

    # Factory function to recreate agent from current settings
    create_agent: Callable[["Settings", Optional[str | int]], "RecursiveAgent"]

    def recreate_agent(self, model_override: Optional[str | int] = None) -> None:
        """Recreate the agent from current settings."""
        if model_override is not None:
            self.agent = self.create_agent(self.settings, model_override)
        else:
            self.agent = self.create_agent(self.settings)


# Import Path here to avoid issues with TYPE_CHECKING
from pathlib import Path


@dataclass
class CommandMetadata:
    """Metadata for a registered CLI command."""

    # Handler function: (ctx, args) -> bool (True = continue loop, False = exit)
    handler: Callable[[CommandContext, str], bool]

    # Category for grouping in /help output
    category: str

    # One-line description for /help listing
    short_desc: str

    # Detailed description for /help <command>
    long_desc: str = ""

    # Usage pattern, e.g., "/model [ref]"
    usage: str = ""

    # Example usage strings
    examples: list[str] = field(default_factory=list)

    # Related command names
    related: list[str] = field(default_factory=list)

    # Command aliases (e.g., /quit also responds to /exit, /q)
    aliases: list[str] = field(default_factory=list)

    # Whether command accepts trailing arguments
    accepts_args: bool = False


# Global command registry
COMMAND_REGISTRY: dict[str, CommandMetadata] = {}

# Category display order
CATEGORY_ORDER = [
    "Session",
    "Agents",
    "Models & Providers",
    "Information",
]


def register_command(
    name: str,
    category: str,
    short_desc: str,
    long_desc: str = "",
    usage: str = "",
    examples: Optional[list[str]] = None,
    related: Optional[list[str]] = None,
    aliases: Optional[list[str]] = None,
    accepts_args: bool = False,
) -> Callable:
    """Decorator to register a command handler with metadata.

    Args:
        name: Primary command name (e.g., "/reset")
        category: Category for grouping (e.g., "Session")
        short_desc: One-line description
        long_desc: Detailed description for /help <command>
        usage: Usage pattern (e.g., "/model [ref]")
        examples: List of example usage strings
        related: List of related command names
        aliases: Alternative command names (e.g., ["/exit", "/q"] for /quit)
    """

    def decorator(handler: Callable[[CommandContext, str], bool]) -> Callable:
        metadata = CommandMetadata(
            handler=handler,
            category=category,
            short_desc=short_desc,
            long_desc=long_desc or short_desc,
            usage=usage or name,
            examples=examples or [],
            related=related or [],
            aliases=aliases or [],
            accepts_args=accepts_args,
        )

        # Register primary name
        COMMAND_REGISTRY[name.lower()] = metadata

        # Register aliases
        for alias in metadata.aliases:
            COMMAND_REGISTRY[alias.lower()] = metadata

        return handler

    return decorator


def get_command(command_input: str) -> tuple[Optional[CommandMetadata], str, str]:
    """Look up a command from user input.

    Args:
        command_input: The full command input (e.g., "/model gpt-4o")

    Returns:
        Tuple of (metadata, command_name, args) or (None, command_name, "") if not found
    """
    parts = command_input.strip().split(maxsplit=1)
    if not parts:
        return None, "", ""

    cmd_name = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""

    # Direct lookup
    if cmd_name in COMMAND_REGISTRY:
        metadata = COMMAND_REGISTRY[cmd_name]
        if args and not metadata.accepts_args:
            return None, cmd_name, args
        return metadata, cmd_name, args

    # Check for commands that accept arguments (e.g., /tools matches /tools <name>)
    # This handles cases where the command is registered as "/tools" but input is "/tools read_file"
    return None, cmd_name, args


def dispatch_command(ctx: CommandContext, command_input: str) -> bool:
    """Dispatch a command to its handler.

    Args:
        ctx: Command context with settings, agent, console, etc.
        command_input: Full command input (e.g., "/model gpt-4o")

    Returns:
        True to continue the CLI loop, False to exit
    """
    metadata, cmd_name, args = get_command(command_input)

    if metadata is None:
        ctx.console.print(f"[red]Unknown command: {cmd_name}[/red]")
        ctx.console.print("Type [cyan]/help[/cyan] for available commands.")
        return True

    return metadata.handler(ctx, args)


def get_help_listing() -> str:
    """Generate the /help command listing organized by category.

    Returns:
        Formatted help text with commands grouped by category
    """
    # Group commands by category (skip aliases to avoid duplicates)
    categories: dict[str, list[tuple[str, CommandMetadata]]] = {}
    seen_handlers = set()

    for cmd_name, metadata in COMMAND_REGISTRY.items():
        # Skip aliases (they point to the same handler)
        handler_id = id(metadata.handler)
        if handler_id in seen_handlers:
            continue
        seen_handlers.add(handler_id)

        # Find the primary name (non-alias)
        primary_name = cmd_name
        for name, meta in COMMAND_REGISTRY.items():
            if meta is metadata and name not in metadata.aliases:
                primary_name = name
                break

        if metadata.category not in categories:
            categories[metadata.category] = []
        categories[metadata.category].append((primary_name, metadata))

    # Sort commands within each category
    for cat in categories:
        categories[cat].sort(key=lambda x: x[0])

    # Build output
    lines = ["[bold]Commands:[/bold]\n"]

    for category in CATEGORY_ORDER:
        if category not in categories:
            continue

        lines.append(f"[bold cyan]{category}:[/bold cyan]")

        for cmd_name, metadata in categories[category]:
            # Format: "  /command          Description"
            usage = metadata.usage if metadata.usage else cmd_name
            padding = " " * max(1, 20 - len(usage))
            lines.append(f"  [green]{usage}[/green]{padding}{metadata.short_desc}")

        lines.append("")

    # Add any categories not in CATEGORY_ORDER
    for category in sorted(categories.keys()):
        if category in CATEGORY_ORDER:
            continue

        lines.append(f"[bold cyan]{category}:[/bold cyan]")

        for cmd_name, metadata in categories[category]:
            usage = metadata.usage if metadata.usage else cmd_name
            padding = " " * max(1, 20 - len(usage))
            lines.append(f"  [green]{usage}[/green]{padding}{metadata.short_desc}")

        lines.append("")

    lines.append("[dim]Type /help <command> for detailed help on a specific command.[/dim]")

    return "\n".join(lines)


def get_command_help(command_name: str) -> Optional[str]:
    """Generate detailed help for a specific command.

    Args:
        command_name: Command name (with or without leading /)

    Returns:
        Formatted help text, or None if command not found
    """
    # Normalize command name
    if not command_name.startswith("/"):
        command_name = "/" + command_name

    metadata = COMMAND_REGISTRY.get(command_name.lower())
    if metadata is None:
        return None

    # Find primary name (non-alias)
    primary_name = command_name
    for name, meta in COMMAND_REGISTRY.items():
        if meta is metadata and name not in metadata.aliases:
            primary_name = name
            break

    lines = [f"[bold]{primary_name}[/bold] - {metadata.short_desc}\n"]

    # Usage
    if metadata.usage:
        lines.append(f"[bold]Usage:[/bold] {metadata.usage}\n")

    # Long description
    if metadata.long_desc and metadata.long_desc != metadata.short_desc:
        lines.append(f"{metadata.long_desc}\n")

    # Examples
    if metadata.examples:
        lines.append("[bold]Examples:[/bold]")
        for example in metadata.examples:
            lines.append(f"  [dim]{example}[/dim]")
        lines.append("")

    # Aliases
    if metadata.aliases:
        alias_str = ", ".join(metadata.aliases)
        lines.append(f"[bold]Aliases:[/bold] {alias_str}\n")

    # Related commands
    if metadata.related:
        related_str = ", ".join(metadata.related)
        lines.append(f"[bold]Related:[/bold] {related_str}")

    return "\n".join(lines)


def list_commands() -> list[str]:
    """Get a list of all registered command names (excluding aliases).

    Returns:
        List of primary command names
    """
    seen_handlers = set()
    commands = []

    for cmd_name, metadata in COMMAND_REGISTRY.items():
        handler_id = id(metadata.handler)
        if handler_id in seen_handlers:
            continue
        seen_handlers.add(handler_id)

        # Find primary name
        for name, meta in COMMAND_REGISTRY.items():
            if meta is metadata and name not in metadata.aliases:
                commands.append(name)
                break

    return sorted(commands)


# =============================================================================
# Command Handlers
# =============================================================================


@register_command(
    name="/quit",
    category="Session",
    short_desc="Exit the CLI",
    long_desc="Exit flavIA and return to the shell.",
    usage="/quit",
    aliases=["/exit", "/q"],
)
def cmd_quit(ctx: CommandContext, args: str) -> bool:
    """Exit the CLI."""
    ctx.console.print("[yellow]Goodbye![/yellow]")
    return False


@register_command(
    name="/reset",
    category="Session",
    short_desc="Reset conversation",
    long_desc="Clear conversation history and reload configuration. "
    "Runtime settings like active agent and subagents mode are preserved.",
    usage="/reset",
    related=["/agent", "/model"],
)
def cmd_reset(ctx: CommandContext, args: str) -> bool:
    """Reset conversation and reload config."""
    from flavia.config import load_settings, reset_settings

    # Reload settings in case config changed
    reset_settings()
    new_settings = load_settings()
    new_settings.verbose = ctx.settings.verbose
    # Preserve runtime-only flags across reset
    new_settings.subagents_enabled = ctx.settings.subagents_enabled
    new_settings.active_agent = ctx.settings.active_agent
    new_settings.parallel_workers = ctx.settings.parallel_workers

    ctx.settings = new_settings

    # Update history paths
    from flavia.interfaces.cli_interface import _history_paths, _configure_prompt_history

    ctx.history_file, ctx.chat_log_file = _history_paths(ctx.settings.base_dir)
    ctx.history_enabled = _configure_prompt_history(ctx.history_file)

    ctx.recreate_agent()
    ctx.console.print("[yellow]Conversation reset and config reloaded.[/yellow]")

    from flavia.interfaces.cli_interface import _print_active_model_hint

    _print_active_model_hint(ctx.agent, ctx.settings)
    return True


@register_command(
    name="/help",
    category="Session",
    short_desc="Show help",
    long_desc="Display available commands organized by category. "
    "Use /help <command> for detailed help on a specific command.",
    usage="/help [command]",
    examples=[
        "/help              Show all commands",
        "/help model        Show detailed help for /model",
        "/help reset        Show detailed help for /reset",
    ],
    accepts_args=True,
)
def cmd_help(ctx: CommandContext, args: str) -> bool:
    """Show help listing or command-specific help."""
    if args.strip():
        # Show help for specific command
        help_text = get_command_help(args.strip())
        if help_text:
            ctx.console.print(help_text)
        else:
            ctx.console.print(f"[red]Unknown command: {args.strip()}[/red]")
            ctx.console.print("Type [cyan]/help[/cyan] for available commands.")
    else:
        # Show all commands
        ctx.console.print(get_help_listing())

        # Add CLI tips
        ctx.console.print("\n[bold]CLI Flags:[/bold]")
        ctx.console.print("  --no-subagents    Disable sub-agent spawning")
        ctx.console.print("  --agent NAME      Use a subagent as the main agent")
        ctx.console.print("  --depth N         Set max recursion depth")
        ctx.console.print("  --parallel-workers N  Max parallel sub-agents")

    return True


@register_command(
    name="/agent_setup",
    category="Agents",
    short_desc="Configure agents interactively",
    long_desc="Launch the interactive agent configuration wizard. "
    "Allows changing models, revising agent context, or full reconfiguration.",
    usage="/agent_setup",
    related=["/agent", "/model"],
)
def cmd_agent_setup(ctx: CommandContext, args: str) -> bool:
    """Run agent setup wizard."""
    from flavia.setup_wizard import run_agent_setup_command

    success = run_agent_setup_command(ctx.settings, ctx.settings.base_dir)
    if success:
        ctx.console.print("[dim]Use /reset to load new configuration.[/dim]")
    return True


@register_command(
    name="/agent",
    category="Agents",
    short_desc="List or switch agents",
    long_desc="Without arguments, lists all available agents. "
    "With an agent name, switches to that agent and resets the conversation.",
    usage="/agent [name]",
    examples=[
        "/agent             List available agents",
        "/agent summarizer  Switch to the 'summarizer' agent",
        "/agent main        Switch back to the main agent",
    ],
    related=["/agent_setup", "/model"],
    accepts_args=True,
)
def cmd_agent(ctx: CommandContext, args: str) -> bool:
    """List or switch agents."""
    from flavia.interfaces.cli_interface import (
        _get_available_agents,
        _print_active_model_hint,
        _resolve_agent_model_ref,
    )

    if args.strip():
        # Switch to specified agent
        agent_name = args.strip()
        current = ctx.settings.active_agent or "main"

        if agent_name == current:
            ctx.console.print(f"[yellow]Already using agent '{agent_name}'.[/yellow]")
            return True

        # Validate agent exists
        available = _get_available_agents(ctx.settings)
        if agent_name not in available:
            ctx.console.print(f"[red]Agent '{agent_name}' not found.[/red]")
            ctx.console.print(f"Available: {', '.join(available.keys()) or '(none)'}")
            return True

        # Validate provider auth for target agent model before switching
        target_model_ref = _resolve_agent_model_ref(ctx.settings, agent_name, available)
        provider, _ = ctx.settings.resolve_model_with_provider(target_model_ref)
        if provider is not None and not provider.api_key:
            ctx.console.print(
                f"[red]Cannot switch to '{agent_name}': API key not configured "
                f"for provider '{provider.id}'.[/red]"
            )
            if provider.api_key_env_var:
                ctx.console.print(
                    f"[dim]Set {provider.api_key_env_var}, run /reset, and try again.[/dim]"
                )
            else:
                ctx.console.print(
                    "[dim]Run 'flavia --setup-provider', run /reset, and try again.[/dim]"
                )
            return True

        # Update settings and create new agent
        previous_active_agent = ctx.settings.active_agent
        ctx.settings.active_agent = None if agent_name == "main" else agent_name
        try:
            ctx.recreate_agent()
        except Exception as e:
            ctx.settings.active_agent = previous_active_agent
            ctx.console.print(f"[red]Failed to switch to agent '{agent_name}': {e}[/red]")
            return True

        ctx.console.print(
            f"[green]Switched to agent '{agent_name}'. Conversation reset.[/green]"
        )
        _print_active_model_hint(ctx.agent, ctx.settings)
    else:
        # List available agents
        from flavia.display import display_agents

        display_agents(ctx.settings, console=ctx.console, use_rich=True)

    return True


@register_command(
    name="/model",
    category="Models & Providers",
    short_desc="Show or switch model",
    long_desc="Without arguments, displays the current active model. "
    "With a model reference, switches to that model and resets the conversation. "
    "Use '/model list' to see all available models.",
    usage="/model [ref]",
    examples=[
        "/model             Show current active model",
        "/model list        List all available models",
        "/model 1           Switch to model at index 1",
        "/model gpt-4o      Switch to model by ID",
        "/model openai:gpt-4  Switch to provider:model",
    ],
    related=["/providers", "/agent"],
    accepts_args=True,
)
def cmd_model(ctx: CommandContext, args: str) -> bool:
    """Show or switch model."""
    from flavia.interfaces.cli_interface import (
        _display_current_model,
        _get_agent_model_ref,
        _models_are_equivalent,
        _print_active_model_hint,
        _resolve_model_reference,
    )

    if not args.strip():
        # No argument: show current model
        _display_current_model(ctx.agent, ctx.settings, ctx.console)
        return True

    model_arg = args.strip()

    # Handle "/model list" as alias for "/providers"
    if model_arg.lower() == "list":
        from flavia.display import display_providers

        display_providers(ctx.settings, console=ctx.console, use_rich=True)
        return True

    # Switch to specified model
    # Try to parse as int (index reference)
    try:
        model_ref: str | int = int(model_arg)
    except ValueError:
        # Keep as string (model_id or provider:model_id)
        model_ref = model_arg

    # Check if already using this model
    current_model_ref = _get_agent_model_ref(ctx.agent)
    if _models_are_equivalent(ctx.settings, current_model_ref, model_ref):
        ctx.console.print(f"[yellow]Already using model '{current_model_ref}'.[/yellow]")
        return True

    resolved_model = _resolve_model_reference(ctx.settings, model_ref)

    # Check if model was found
    if resolved_model is None:
        ctx.console.print(f"[red]Model '{model_arg}' not found.[/red]")
        ctx.console.print("Use [cyan]/model list[/cyan] to see available models.")
        return True

    provider, _, resolved_model_ref = resolved_model

    # Validate provider has API key
    if provider is not None and not provider.api_key:
        ctx.console.print(
            f"[red]Cannot switch to '{model_arg}': API key not configured "
            f"for provider '{provider.id}'.[/red]"
        )
        if provider.api_key_env_var:
            ctx.console.print(
                f"[dim]Set {provider.api_key_env_var}, run /reset, and try again.[/dim]"
            )
        else:
            ctx.console.print(
                "[dim]Run 'flavia --setup-provider', run /reset, and try again.[/dim]"
            )
        return True

    # Update settings and recreate agent
    previous_model = ctx.settings.default_model
    ctx.settings.default_model = resolved_model_ref

    try:
        ctx.recreate_agent(model_override=resolved_model_ref)
    except Exception as e:
        # Rollback on failure
        ctx.settings.default_model = previous_model
        ctx.console.print(f"[red]Failed to switch to model '{model_arg}': {e}[/red]")
        return True

    # Success
    ctx.console.print(
        f"[green]Switched to model '{resolved_model_ref}'. Conversation reset.[/green]"
    )
    _print_active_model_hint(ctx.agent, ctx.settings)
    return True


@register_command(
    name="/providers",
    category="Models & Providers",
    short_desc="List providers and models",
    long_desc="Display all configured providers with their available models. "
    "Shows model indexes that can be used with /model command.",
    usage="/providers",
    related=["/model", "/config"],
)
def cmd_providers(ctx: CommandContext, args: str) -> bool:
    """List configured providers and models."""
    from flavia.display import display_providers

    display_providers(ctx.settings, console=ctx.console, use_rich=True)
    return True


@register_command(
    name="/tools",
    category="Information",
    short_desc="List tools or show tool details",
    long_desc="Without arguments, lists all available tools grouped by category. "
    "With a tool name, shows the tool's schema and parameters.",
    usage="/tools [name]",
    examples=[
        "/tools             List all tools by category",
        "/tools read_file   Show schema for read_file tool",
    ],
    related=["/config"],
    accepts_args=True,
)
def cmd_tools(ctx: CommandContext, args: str) -> bool:
    """List tools or show tool schema."""
    from flavia.display import display_tool_schema, display_tools

    if args.strip():
        tool_name = args.strip()
        display_tool_schema(tool_name, console=ctx.console, use_rich=True)
    else:
        display_tools(console=ctx.console, use_rich=True)

    return True


@register_command(
    name="/config",
    category="Information",
    short_desc="Show configuration",
    long_desc="Display configuration file locations and current active settings.",
    usage="/config",
    related=["/providers", "/tools"],
)
def cmd_config(ctx: CommandContext, args: str) -> bool:
    """Show configuration paths and settings."""
    from flavia.display import display_config

    display_config(ctx.settings, console=ctx.console, use_rich=True)
    return True


@register_command(
    name="/catalog",
    category="Information",
    short_desc="Browse content catalog",
    long_desc="Launch the interactive content catalog browser. "
    "Allows browsing indexed files, viewing summaries, and searching content.",
    usage="/catalog",
)
def cmd_catalog(ctx: CommandContext, args: str) -> bool:
    """Browse content catalog."""
    from flavia.interfaces.catalog_command import run_catalog_command

    run_catalog_command(ctx.settings)
    return True
