"""Interactive CLI interface for flavIA."""

import logging
import random
import sys
import threading
from contextlib import contextmanager
from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown

from flavia.config import Settings, reset_settings, load_settings
from flavia.agent import RecursiveAgent, AgentProfile


console = Console()

LOADING_DOTS = (".", "..", "...", "..")
LOADING_MESSAGES = (
    "Skimming conference proceedings",
    "Checking references in the lab notebook",
    "Reviewing lecture notes with coffee",
    "Validating hypotheses on the whiteboard",
    "Comparing citations with suspicious rigor",
    "Preparing arguments for the committee",
)


def _build_loading_line(message: str, step: int) -> str:
    """Build one loading frame line."""
    dots = LOADING_DOTS[step % len(LOADING_DOTS)]
    return f"Agent: {message} {dots}"


def _choose_loading_message(current: str = "") -> str:
    """Pick a loading message, avoiding immediate repetition when possible."""
    if len(LOADING_MESSAGES) <= 1:
        return LOADING_MESSAGES[0] if LOADING_MESSAGES else "Processando"

    candidates = [msg for msg in LOADING_MESSAGES if msg != current]
    return random.choice(candidates) if candidates else LOADING_MESSAGES[0]


def _clear_terminal_line() -> None:
    """Clear current terminal line."""
    output = console.file
    output.write("\r\033[2K\r")
    output.flush()


def _supports_wait_feedback() -> bool:
    """Return whether runtime supports interactive wait feedback."""
    in_stream = sys.stdin
    out_stream = getattr(console, "file", None)
    return bool(
        in_stream
        and out_stream
        and hasattr(in_stream, "isatty")
        and hasattr(out_stream, "isatty")
        and in_stream.isatty()
        and out_stream.isatty()
    )


@contextmanager
def _suppress_terminal_input() -> None:
    """Hide and discard user input while waiting for model response."""
    if not _supports_wait_feedback():
        yield
        return

    try:
        import termios
    except Exception:
        # Non-POSIX fallback: keep normal input behavior.
        yield
        return

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    new_settings = termios.tcgetattr(fd)

    # Disable echo and canonical mode while preserving signals (Ctrl-C still works).
    new_settings[3] &= ~(termios.ECHO | termios.ICANON)
    new_settings[6][termios.VMIN] = 0
    new_settings[6][termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, new_settings)

    try:
        yield
    finally:
        # Drop buffered keystrokes typed while waiting.
        termios.tcflush(fd, termios.TCIFLUSH)
        termios.tcsetattr(fd, termios.TCSANOW, old_settings)


def _run_loading_animation(stop_event: threading.Event) -> None:
    """Render loading frames until the stop event is set."""
    message = _choose_loading_message()
    step = 0
    next_message_step = random.randint(14, 24)

    while not stop_event.is_set():
        line = _build_loading_line(message, step)
        output = console.file
        output.write("\r\033[2K" + line)
        output.flush()

        step += 1
        if step % next_message_step == 0:
            message = _choose_loading_message(message)
            next_message_step = random.randint(14, 24)

        if stop_event.wait(0.35):
            break


def _run_agent_with_feedback(agent: RecursiveAgent, user_input: str) -> str:
    """Run agent with visual processing feedback."""
    if not _supports_wait_feedback():
        return agent.run(user_input)

    stop_event = threading.Event()
    animation_thread = threading.Thread(
        target=_run_loading_animation,
        args=(stop_event,),
        daemon=True,
    )
    animation_thread.start()

    try:
        with _suppress_terminal_input():
            return agent.run(user_input)
    finally:
        stop_event.set()
        animation_thread.join(timeout=1.0)
        _clear_terminal_line()


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
- `/agents` - Configure model per agent/subagent
- `/quit` - Exit
- `/models` - List models (with provider info)
- `/providers` - List configured providers
- `/tools` - List tools
- `/config` - Show config paths

**Tips:**
- Run `flavia --init` to create initial config
- Run `flavia --setup-provider` to configure providers
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

                elif command == "/agents":
                    from flavia.setup import manage_agent_models
                    success = manage_agent_models(settings, settings.base_dir)
                    if success:
                        console.print("[dim]Use /reset to reload updated agent models.[/dim]")
                    continue

                elif command == "/models":
                    console.print("\n[bold]Available Models:[/bold]")
                    # Show models from providers if available
                    if settings.providers.providers:
                        index = 0
                        for provider in settings.providers.providers.values():
                            console.print(f"\n  [dim]{provider.name}:[/dim]")
                            for model in provider.models:
                                default = " (default)" if model.default else ""
                                console.print(
                                    f"    {index}: {model.name} - "
                                    f"[cyan]{provider.id}:{model.id}[/cyan]{default}"
                                )
                                index += 1
                    else:
                        # Fall back to legacy models list
                        for i, model in enumerate(settings.models):
                            default = " (default)" if model.default else ""
                            console.print(f"  {i}: {model.name} - {model.id}{default}")
                    console.print()
                    continue

                elif command == "/providers":
                    from flavia.setup.provider_wizard import list_providers
                    list_providers(settings)
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

            try:
                response = _run_agent_with_feedback(agent, user_input)
                console.print("[bold blue]Agent:[/bold blue] ", end="")
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
