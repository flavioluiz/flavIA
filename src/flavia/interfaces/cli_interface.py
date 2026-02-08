"""Interactive CLI interface for flavIA."""

import logging
from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown

from flavia.config import Settings, reset_settings, load_settings
from flavia.agent import RecursiveAgent, AgentProfile


console = Console()


def create_agent_from_settings(settings: Settings) -> RecursiveAgent:
    """Create an agent from settings and optional agents.yaml config."""
    if "main" in settings.agents_config:
        config = settings.agents_config["main"]
        profile = AgentProfile.from_config(config)

        # Use current directory as base unless specified in config
        if "path" not in config:
            profile.base_dir = settings.base_dir
    else:
        profile = AgentProfile(
            context="You are a helpful assistant that can read and analyze files.",
            model=settings.default_model,
            base_dir=settings.base_dir,
            tools=["read_file", "list_files", "search_files", "get_file_info"],
            subagents={},
            name="main",
            max_depth=settings.max_depth,
        )

    return RecursiveAgent(settings=settings, profile=profile)


def print_welcome(settings: Settings) -> None:
    """Print welcome message."""
    banner = r"""
__ _                Welcome to
 / _| | __ ___   __   Isle of Knowledge.
| |_| |/ _` \ \ / /
|  _| | (_| |\ V /    ██╗  █████╗
|_| |_|\__,_| \_/     ██║ ██╔══██╗
                      ██║ ███████║
                      ██║ ██╔══██║
                      ██║ ██║  ██║
                      ╚═╝ ╚═╝  ╚═╝

 > flavIA: Your Scholarly Companion ready.
"""
    console.print(banner)
    console.print("\nType [bold]/help[/bold] for commands\n")


def print_help() -> None:
    """Print help message."""
    help_text = """
**Commands:**
- `/help` - Show this message
- `/reset` - Reset conversation
- `/setup` - Configure agents for this project
- `/quit` - Exit
- `/models` - List models
- `/tools` - List tools
- `/config` - Show config paths

**Tips:**
- Run `flavia --init` to create initial config
- Use `/setup` to reconfigure agents
"""
    console.print(Markdown(help_text))


def run_cli(settings: Settings) -> None:
    """Run the interactive CLI."""
    # Keep CLI output clean even if logging is configured elsewhere.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)

    print_welcome(settings)

    agent = create_agent_from_settings(settings)

    while True:
        try:
            user_input = console.input("[bold green]You:[/bold green] ").strip()

            if not user_input:
                continue

            if user_input.startswith("/"):
                command = user_input.lower()

                if command in ("/quit", "/exit", "/q"):
                    console.print("[yellow]Goodbye![/yellow]")
                    break

                elif command == "/help":
                    print_help()
                    continue

                elif command == "/reset":
                    # Reload settings in case config changed
                    reset_settings()
                    new_settings = load_settings()
                    new_settings.verbose = settings.verbose
                    settings = new_settings

                    agent = create_agent_from_settings(settings)
                    console.print("[yellow]Conversation reset and config reloaded.[/yellow]")
                    continue

                elif command == "/setup":
                    from flavia.setup_wizard import run_setup_command_in_cli
                    success = run_setup_command_in_cli(settings, settings.base_dir)
                    if success:
                        console.print("[dim]Use /reset to load new configuration.[/dim]")
                    continue

                elif command == "/models":
                    console.print("\n[bold]Available Models:[/bold]")
                    for i, model in enumerate(settings.models):
                        default = " (default)" if model.default else ""
                        console.print(f"  {i}: {model.name} - {model.id}{default}")
                    console.print()
                    continue

                elif command == "/tools":
                    from flavia.tools import list_available_tools
                    tools = list_available_tools()
                    console.print("\n[bold]Available Tools:[/bold]")
                    for tool in tools:
                        console.print(f"  - {tool}")
                    console.print()
                    continue

                elif command == "/config":
                    paths = settings.config_paths
                    console.print("\n[bold]Configuration:[/bold]")
                    console.print(f"  Local:   {paths.local_dir or '(none)'}")
                    console.print(f"  User:    {paths.user_dir or '(none)'}")
                    console.print(f"  .env:    {paths.env_file or '(none)'}")
                    console.print(f"  models:  {paths.models_file or '(none)'}")
                    console.print(f"  agents:  {paths.agents_file or '(none)'}")
                    console.print()
                    continue

                else:
                    console.print(f"[red]Unknown command: {command}[/red]")
                    continue

            console.print("[bold blue]Agent:[/bold blue] ", end="")

            try:
                response = agent.run(user_input)
                console.print(Markdown(response))
            except KeyboardInterrupt:
                console.print("\n[yellow]Interrupted[/yellow]")
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")
                if settings.verbose:
                    import traceback
                    traceback.print_exc()

            console.print()

        except KeyboardInterrupt:
            console.print("\n[yellow]Use /quit to exit[/yellow]")
        except EOFError:
            console.print("\n[yellow]Goodbye![/yellow]")
            break
