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
        # Preserve write confirmation across agent recreation.
        old_ctx = getattr(self.agent, "context", None)
        old_wc = getattr(old_ctx, "write_confirmation", None) if old_ctx else None
        if model_override is not None:
            self.agent = self.create_agent(self.settings, model_override)
        else:
            self.agent = self.create_agent(self.settings)
        if old_wc is not None and hasattr(self.agent, "context"):
            self.agent.context.write_confirmation = old_wc


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
    "Index",
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
    new_settings.rag_debug = ctx.settings.rag_debug
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
    long_desc="Without arguments, lists all available agents (or offers interactive selection). "
    "With an agent name, switches to that agent and resets the conversation.",
    usage="/agent [name]",
    examples=[
        "/agent             List available agents (or interactive selection)",
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
    from flavia.setup.prompt_utils import SetupCancelled, is_interactive, q_select

    available = _get_available_agents(ctx.settings)

    if not args.strip():
        # No args - either offer autocomplete or list
        if is_interactive() and available:
            try:
                current_agent = ctx.settings.active_agent or "main"
                agent_name = q_select(
                    "Select agent:",
                    choices=list(available.keys()),
                    default=current_agent,
                    allow_cancel=True,
                )
            except SetupCancelled:
                agent_name = ""
            if agent_name and agent_name in available:
                args = agent_name
            else:
                # User cancelled or invalid - show list
                from flavia.display import display_agents

                display_agents(ctx.settings, console=ctx.console, use_rich=True)
                return True
        else:
            # Non-interactive or no agents - show list
            from flavia.display import display_agents

            display_agents(ctx.settings, console=ctx.console, use_rich=True)
            return True

    # Switch to specified agent
    agent_name = args.strip()
    current = ctx.settings.active_agent or "main"

    if agent_name == current:
        ctx.console.print(f"[yellow]Already using agent '{agent_name}'.[/yellow]")
        return True

    # Validate agent exists
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

    ctx.console.print(f"[green]Switched to agent '{agent_name}'. Conversation reset.[/green]")
    _print_active_model_hint(ctx.agent, ctx.settings)

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


@register_command(
    name="/provider-setup",
    category="Models & Providers",
    short_desc="Run provider configuration wizard",
    long_desc="Launch the interactive provider configuration wizard to add or reconfigure "
    "LLM providers. Supports known providers (OpenAI, Anthropic, OpenRouter, Synthetic) "
    "and custom OpenAI-compatible endpoints.",
    usage="/provider-setup",
    examples=["/provider-setup       Launch the provider configuration wizard"],
    related=["/provider-manage", "/provider-test", "/providers", "/model"],
)
def cmd_provider_setup(ctx: CommandContext, args: str) -> bool:
    """Run provider configuration wizard."""
    from flavia.setup.provider_wizard import run_provider_wizard

    success = run_provider_wizard(target_dir=ctx.settings.base_dir)
    if success:
        ctx.console.print("[dim]Use /reset to reload configuration.[/dim]")
    return True


@register_command(
    name="/provider-manage",
    category="Models & Providers",
    short_desc="Manage provider models and settings",
    long_desc="Open the provider management interface to add, remove, or fetch models, "
    "change settings, or delete a provider. Without ID, prompts to select from configured providers.",
    usage="/provider-manage [id]",
    examples=[
        "/provider-manage          Select provider interactively",
        "/provider-manage openai   Manage the 'openai' provider directly",
    ],
    related=["/provider-setup", "/provider-test", "/providers"],
    accepts_args=True,
)
def cmd_provider_manage(ctx: CommandContext, args: str) -> bool:
    """Manage provider models and settings."""
    from flavia.setup.provider_wizard import manage_provider_models

    provider_id = args.strip() if args.strip() else None
    success = manage_provider_models(
        ctx.settings,
        provider_id,
        target_dir=ctx.settings.base_dir,
    )
    if success:
        ctx.console.print("[dim]Use /reset to reload configuration.[/dim]")
    return True


@register_command(
    name="/provider-test",
    category="Models & Providers",
    short_desc="Test provider connection",
    long_desc="Test connectivity to a provider by making a small API request. "
    "Without arguments, tests the default provider. With a provider ID, tests that specific provider.",
    usage="/provider-test [id]",
    examples=[
        "/provider-test           Test the default provider",
        "/provider-test openai    Test the 'openai' provider",
    ],
    related=["/provider-setup", "/provider-manage", "/providers"],
    accepts_args=True,
)
def cmd_provider_test(ctx: CommandContext, args: str) -> bool:
    """Test provider connection."""
    from flavia.setup.provider_wizard import test_provider_connection

    provider_id = args.strip() if args.strip() else None

    # Resolve provider
    if provider_id:
        provider = ctx.settings.providers.get_provider(provider_id)
        if not provider:
            ctx.console.print(f"[red]Provider '{provider_id}' not found.[/red]")
            available = list(ctx.settings.providers.providers.keys())
            if available:
                ctx.console.print(f"Available: {', '.join(available)}")
            return True
    else:
        provider = ctx.settings.providers.get_default_provider()
        if not provider:
            ctx.console.print("[red]No default provider configured.[/red]")
            ctx.console.print("Use [cyan]/provider-setup[/cyan] to configure one.")
            return True

    ctx.console.print(f"\n[bold]Testing: {provider.name}[/bold] ({provider.id})")
    ctx.console.print(f"  URL: [dim]{provider.api_base_url}[/dim]")

    if not provider.api_key:
        ctx.console.print("\n[red]Error: API key not configured[/red]")
        if provider.api_key_env_var:
            ctx.console.print(f"[dim]Set {provider.api_key_env_var} environment variable[/dim]")
        return True

    model = provider.get_default_model()
    if not model:
        ctx.console.print("[red]Error: No models configured[/red]")
        return True

    ctx.console.print(f"  Model: [cyan]{model.id}[/cyan]")
    ctx.console.print("\n[dim]Connecting...[/dim]")

    success, message = test_provider_connection(
        provider.api_key,
        provider.api_base_url,
        model.id,
        provider.headers if provider.headers else None,
    )

    if success:
        ctx.console.print(f"\n[green]SUCCESS[/green] {message}")
    else:
        ctx.console.print(f"\n[red]FAILED[/red] {message}")

    return True


@register_command(
    name="/compact",
    category="Session",
    short_desc="Compact conversation",
    long_desc="Manually trigger conversation compaction to summarize and reduce token usage. "
    "Shows current context utilization, asks for confirmation, then summarizes the conversation "
    "and displays the new token usage.",
    usage="/compact",
    related=["/reset"],
)
def cmd_compact(ctx: CommandContext, args: str) -> bool:
    """Manually compact the conversation."""
    prompt_tokens = ctx.agent.last_prompt_tokens
    max_tokens = ctx.agent.max_context_tokens
    pct = ctx.agent.context_utilization * 100

    ctx.console.print(
        f"Context: {prompt_tokens:,}/{max_tokens:,} ({pct:.0f}%). Compact conversation? \\[y/N] ",
        end="",
    )

    try:
        answer = input().strip().lower()
    except (EOFError, KeyboardInterrupt):
        ctx.console.print()
        return True

    if answer in ("y", "yes"):
        ctx.console.print("[dim]Compacting conversation...[/dim]")
        try:
            summary = ctx.agent.compact_conversation()
            if not summary:
                ctx.console.print("[yellow]Nothing to compact (conversation is empty).[/yellow]")
                return True

            ctx.console.print("[green]Conversation compacted.[/green]")
            ctx.console.print(f"[bold]Summary:[/bold]")
            ctx.console.print(summary)

            new_pct = ctx.agent.context_utilization * 100
            new_prompt = ctx.agent.last_prompt_tokens
            ctx.console.print(
                f"[dim]New context: {new_prompt:,}/{max_tokens:,} ({new_pct:.1f}%)[/dim]"
            )
        except Exception as e:
            ctx.console.print(f"[red]Compaction failed: {e}[/red]")
    else:
        ctx.console.print("[yellow]Compaction cancelled.[/yellow]")

    return True


@register_command(
    name="/rag-debug",
    category="Index",
    short_desc="Toggle RAG diagnostics mode",
    long_desc="Enable/disable RAG diagnostics capture for search_chunks. "
    "When enabled, diagnostics are saved to `.flavia/rag_debug.jsonl` and can be inspected with "
    "`/rag-debug last` without injecting verbose traces into model context.",
    usage="/rag-debug [on|off|status|last [N]|turn [N]]",
    examples=[
        "/rag-debug           Show current state",
        "/rag-debug on        Enable detailed RAG diagnostics",
        "/rag-debug off       Disable detailed RAG diagnostics",
        "/rag-debug last      Show the most recent diagnostics trace",
        "/rag-debug last 5    Show the 5 most recent diagnostics traces",
        "/rag-debug turn      Show traces captured in current turn",
        "/rag-debug turn 10   Show up to 10 traces from current turn",
    ],
    related=["/index diagnose", "/config"],
    accepts_args=True,
)
def cmd_rag_debug(ctx: CommandContext, args: str) -> bool:
    """Enable/disable runtime RAG diagnostics mode and inspect recent traces."""
    from flavia.content.indexer.rag_debug_log import (
        format_rag_debug_trace,
        read_recent_rag_debug_traces,
    )

    raw = args.strip()
    parts = raw.split() if raw else []
    option = parts[0].lower() if parts else "status"
    if option == "last-turn":
        option = "turn"

    if option not in {"on", "off", "status", "last", "turn"}:
        ctx.console.print("[red]Usage: /rag-debug [on|off|status|last [N]|turn [N]][/red]")
        return True

    if option == "on":
        ctx.settings.rag_debug = True
        if hasattr(ctx.agent, "context"):
            ctx.agent.context.rag_debug = True
        ctx.console.print("[green]RAG debug mode enabled for this session.[/green]")
        ctx.console.print(
            "[dim]Diagnostics are persisted to .flavia/rag_debug.jsonl "
            "(not injected into model context).[/dim]"
        )
        return True

    if option == "off":
        ctx.settings.rag_debug = False
        if hasattr(ctx.agent, "context"):
            ctx.agent.context.rag_debug = False
        ctx.console.print("[yellow]RAG debug mode disabled.[/yellow]")
        return True

    if option == "last":
        if len(parts) > 2:
            ctx.console.print("[red]Usage: /rag-debug last [N][/red]")
            return True

        limit = 1
        if len(parts) == 2:
            if not parts[1].isdigit():
                ctx.console.print("[red]Usage: /rag-debug last [N][/red]")
                return True
            limit = int(parts[1])
            if limit <= 0 or limit > 50:
                ctx.console.print("[red]N must be between 1 and 50.[/red]")
                return True

        entries = read_recent_rag_debug_traces(ctx.settings.base_dir, limit=limit)
        if not entries:
            ctx.console.print("[yellow]No RAG diagnostics traces found.[/yellow]")
            ctx.console.print("[dim]Enable with /rag-debug on and run a retrieval query.[/dim]")
            return True

        for idx, entry in enumerate(entries, start=1):
            trace_id = str(entry.get("trace_id", "unknown"))
            timestamp = str(entry.get("timestamp", ""))
            query = str(entry.get("query_effective") or entry.get("query_raw") or "")
            mentions = entry.get("mentions") or []
            ctx.console.print(
                f"[bold]Trace {idx}/{len(entries)}[/bold] "
                f"[cyan]{trace_id}[/cyan] "
                f"[dim]{timestamp}[/dim]"
            )
            if query:
                ctx.console.print(f"query: {query}")
            turn_id = str(entry.get("turn_id") or "")
            if turn_id:
                ctx.console.print(f"turn_id: {turn_id}")
            if mentions:
                ctx.console.print("mentions: " + ", ".join(str(m) for m in mentions))
            formatted = format_rag_debug_trace(entry.get("trace", {}))
            ctx.console.print(formatted, markup=False)
            if idx != len(entries):
                ctx.console.print("")
        return True

    if option == "turn":
        if len(parts) > 2:
            ctx.console.print("[red]Usage: /rag-debug turn [N][/red]")
            return True

        limit = 50
        if len(parts) == 2:
            if not parts[1].isdigit():
                ctx.console.print("[red]Usage: /rag-debug turn [N][/red]")
                return True
            limit = int(parts[1])
            if limit <= 0 or limit > 200:
                ctx.console.print("[red]N must be between 1 and 200.[/red]")
                return True

        turn_id = str(getattr(getattr(ctx.agent, "context", None), "rag_turn_id", "") or "")
        if not turn_id:
            ctx.console.print("[yellow]No active turn id found.[/yellow]")
            ctx.console.print(
                "[dim]Send a new prompt first, then run /rag-debug turn to inspect retrieval traces for that turn.[/dim]"
            )
            return True

        entries = read_recent_rag_debug_traces(
            ctx.settings.base_dir,
            limit=limit,
            turn_id=turn_id,
        )
        if not entries:
            ctx.console.print(
                f"[yellow]No RAG diagnostics traces found for current turn ({turn_id}).[/yellow]"
            )
            if not bool(getattr(ctx.settings, "rag_debug", False)):
                ctx.console.print(
                    "[dim]RAG debug mode is currently OFF. Use /rag-debug on, run the prompt again, then /rag-debug turn.[/dim]"
                )
            else:
                ctx.console.print(
                    "[dim]If the turn did not call search_chunks, no retrieval trace is generated.[/dim]"
                )
            return True

        for idx, entry in enumerate(entries, start=1):
            trace_id = str(entry.get("trace_id", "unknown"))
            timestamp = str(entry.get("timestamp", ""))
            query = str(entry.get("query_effective") or entry.get("query_raw") or "")
            mentions = entry.get("mentions") or []
            ctx.console.print(
                f"[bold]Trace {idx}/{len(entries)}[/bold] "
                f"[cyan]{trace_id}[/cyan] "
                f"[dim]{timestamp}[/dim]"
            )
            if query:
                ctx.console.print(f"query: {query}")
            ctx.console.print(f"turn_id: {turn_id}")
            if mentions:
                ctx.console.print("mentions: " + ", ".join(str(m) for m in mentions))
            formatted = format_rag_debug_trace(entry.get("trace", {}))
            ctx.console.print(formatted, markup=False)
            if idx != len(entries):
                ctx.console.print("")
        return True

    state = bool(getattr(ctx.settings, "rag_debug", False))
    ctx.console.print(f"RAG debug mode: [cyan]{state}[/cyan]")
    if state:
        ctx.console.print(
            "[dim]Diagnostics are being saved to .flavia/rag_debug.jsonl. "
            "Use /rag-debug last to inspect.[/dim]"
        )
    else:
        ctx.console.print("[dim]Use /rag-debug on to enable diagnostics capture.[/dim]")
    return True


@register_command(
    name="/index",
    category="Index",
    short_desc="Manage retrieval index",
    long_desc="Index subcommands: build (full rebuild), update (incremental), "
    "stats (current index statistics), diagnose (detailed tuning diagnostics).",
    usage="/index <build|update|stats|diagnose>",
    examples=["/index build", "/index update", "/index stats", "/index diagnose"],
    related=["/index-build", "/index-update", "/index-stats", "/index-diagnose", "/rag-debug"],
    accepts_args=True,
)
def cmd_index(ctx: CommandContext, args: str) -> bool:
    """Dispatch /index subcommands for index lifecycle actions."""
    subcommand = args.strip().split(maxsplit=1)[0].lower() if args.strip() else ""

    if subcommand == "build":
        return cmd_index_build(ctx, "")
    if subcommand == "update":
        return cmd_index_update(ctx, "")
    if subcommand == "stats":
        return cmd_index_stats(ctx, "")
    if subcommand == "diagnose":
        return cmd_index_diagnose(ctx, "")

    ctx.console.print("[red]Usage: /index <build|update|stats|diagnose>[/red]")
    return True


@register_command(
    name="/index-build",
    category="Index",
    short_desc="Rebuild entire index (legacy alias)",
    long_desc="Full rebuild: rechunk and re-embed all converted documents. "
    "This clears existing chunks and vectors and rebuilds from scratch.",
    usage="/index-build",
    related=["/index", "/index-update", "/index-stats"],
)
def cmd_index_build(ctx: CommandContext, args: str) -> bool:
    """Full rebuild: rechunk + re-embed all converted docs."""
    from flavia.content.indexer.index_manager import build_index, display_build_results

    results = build_index(ctx.settings.base_dir, ctx.settings, ctx.console)
    if not results.get("cancelled"):
        display_build_results(results, ctx.console)

    return True


@register_command(
    name="/index-update",
    category="Index",
    short_desc="Update index incrementally (legacy alias)",
    long_desc="Incremental update: only process new/modified files detected by checksum. "
    "Much faster than full rebuild for small changes.",
    usage="/index-update",
    related=["/index", "/index-build", "/index-stats"],
)
def cmd_index_update(ctx: CommandContext, args: str) -> bool:
    """Incremental: only new/modified docs (by checksum)."""
    from flavia.content.indexer.index_manager import update_index, display_build_results

    results = update_index(ctx.settings.base_dir, ctx.settings, ctx.console)
    display_build_results(results, ctx.console)

    return True


@register_command(
    name="/index-stats",
    category="Index",
    short_desc="Show index statistics (legacy alias)",
    long_desc="Display index statistics: chunk count, vector count, document count, "
    "index DB size, last indexed timestamp, and modalities present.",
    usage="/index-stats",
    related=["/index", "/index-build", "/index-update"],
)
def cmd_index_stats(ctx: CommandContext, args: str) -> bool:
    """Show chunk count, vector count, index DB size, last updated."""
    from flavia.content.indexer.index_manager import show_index_stats

    show_index_stats(ctx.settings.base_dir, ctx.console)

    return True


@register_command(
    name="/index-diagnose",
    category="Index",
    short_desc="Show detailed RAG diagnostics (legacy alias)",
    long_desc="Show detailed diagnostics for retrieval tuning: runtime RAG parameters, "
    "chunk distributions, top documents by chunk count, and actionable hints.",
    usage="/index-diagnose",
    related=["/index", "/index-stats", "/rag-debug"],
)
def cmd_index_diagnose(ctx: CommandContext, args: str) -> bool:
    """Show detailed index diagnostics for tuning."""
    from flavia.content.indexer.index_manager import show_index_diagnostics

    show_index_diagnostics(ctx.settings.base_dir, ctx.settings, ctx.console)
    return True
