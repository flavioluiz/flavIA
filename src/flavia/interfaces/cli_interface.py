"""Interactive CLI interface for flavIA."""

import json
import logging
import random
import sys
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.markdown import Markdown

from flavia.agent import AgentProfile, RecursiveAgent
from flavia.config import Settings, load_settings, reset_settings

console = Console()

try:
    import readline as _readline
except Exception:  # pragma: no cover - platform-dependent
    _readline = None

LOADING_DOTS = (".", "..", "...", "..")
LOADING_MESSAGES = (
    "Skimming conference proceedings",
    "Checking references in the lab notebook",
    "Reviewing lecture notes with coffee",
    "Validating hypotheses on the whiteboard",
    "Comparing citations with suspicious rigor",
    "Preparing arguments for the committee",
)


def _build_loading_line(message: str, step: int, model_ref: str = "") -> str:
    """Build one loading frame line."""
    dots = LOADING_DOTS[step % len(LOADING_DOTS)]
    prefix = f"Agent [{model_ref}]" if model_ref else "Agent"
    return f"{prefix}: {message} {dots}"


def _history_paths(base_dir: Path) -> tuple[Path, Path]:
    """Build per-project prompt history and chat log paths."""
    project_dir = base_dir / ".flavia"
    project_dir.mkdir(parents=True, exist_ok=True)
    return project_dir / ".prompt_history", project_dir / "chat_history.jsonl"


def _configure_prompt_history(history_file: Path) -> bool:
    """Configure readline prompt history for up/down navigation."""
    if _readline is None:
        return False
    if not hasattr(sys.stdin, "isatty") or not sys.stdin.isatty():
        return False

    try:
        if hasattr(_readline, "clear_history"):
            _readline.clear_history()
        if hasattr(_readline, "set_history_length"):
            _readline.set_history_length(1000)
        if hasattr(_readline, "set_auto_history"):
            _readline.set_auto_history(False)
        if history_file.exists():
            _readline.read_history_file(str(history_file))
        return True
    except Exception:
        return False


def _append_prompt_history(user_input: str, history_file: Path, history_enabled: bool) -> None:
    """Persist a user prompt in project history (for up/down reuse)."""
    if not history_enabled or _readline is None:
        return

    text = user_input.strip()
    if not text:
        return

    try:
        current_len = _readline.get_current_history_length()
        if current_len > 0:
            last_item = _readline.get_history_item(current_len)
            if last_item == text:
                return

        _readline.add_history(text)
        _readline.write_history_file(str(history_file))
    except Exception:
        pass


def _read_user_input(history_enabled: bool, active_agent: Optional[str] = None) -> str:
    """Read user prompt with optional active agent prefix."""
    # Show agent prefix only for non-main agents
    has_prefix = active_agent and active_agent != "main"

    if history_enabled and _readline is not None:
        # Keep a plain prompt with readline; styled ANSI prompts can break redraw
        # when deleting characters or navigating history with arrows.
        prefix = f"[{active_agent}] " if has_prefix else ""
        return input(f"{prefix}You: ")

    if has_prefix:
        return console.input(f"[dim][{active_agent}] [/dim][bold green]You:[/bold green] ")
    return console.input("[bold green]You:[/bold green] ")


def _append_chat_log(chat_log_file: Path, role: str, content: str, model_ref: str = "") -> None:
    """Append chat message to project-local jsonl history."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "role": role,
        "content": content,
    }
    if model_ref:
        entry["model"] = model_ref

    try:
        with open(chat_log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _get_agent_model_ref(agent: RecursiveAgent) -> str:
    """Build visible model reference used by the current replying agent."""
    provider = getattr(agent, "provider", None)
    model_id = str(getattr(agent, "model_id", "unknown"))
    if provider is not None and getattr(provider, "id", None):
        return f"{provider.id}:{model_id}"
    return model_id


def _build_agent_prefix(agent: RecursiveAgent) -> str:
    """Build response prefix with active model reference."""
    return f"Agent [{_get_agent_model_ref(agent)}]:"


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


def _run_loading_animation(stop_event: threading.Event, model_ref: str) -> None:
    """Render loading frames until the stop event is set."""
    message = _choose_loading_message()
    step = 0
    next_message_step = random.randint(14, 24)

    while not stop_event.is_set():
        line = _build_loading_line(message, step, model_ref=model_ref)
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
    model_ref = _get_agent_model_ref(agent)
    animation_thread = threading.Thread(
        target=_run_loading_animation,
        args=(stop_event, model_ref),
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
    """Create an agent from settings and optional agents.yaml config.

    Respects:
    - settings.active_agent: use a subagent config as the main agent
    - settings.subagents_enabled: when False, strips subagents and spawn tools
    """
    if "main" in settings.agents_config:
        main_config = settings.agents_config["main"]

        # If active_agent is set, promote that subagent config to act as main
        if settings.active_agent and settings.active_agent != "main":
            subagents = main_config.get("subagents", {})
            agent_name = settings.active_agent
            if agent_name in subagents and isinstance(subagents[agent_name], dict):
                config = subagents[agent_name].copy()
                # Inherit model from main if not explicitly set in subagent
                if "model" not in config and "model" in main_config:
                    config["model"] = main_config["model"]
                # Subagent promoted to main has no subagents of its own
                config.pop("subagents", None)
                config["name"] = agent_name
            else:
                available = list(subagents.keys()) if isinstance(subagents, dict) else []
                console.print(
                    f"[yellow]Agent '{agent_name}' not found. "
                    f"Available: {', '.join(available) or '(none)'}. Using 'main'.[/yellow]"
                )
                config = main_config
        else:
            config = main_config

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

    # Apply settings overrides
    profile.max_depth = settings.max_depth

    # When subagents are disabled, strip spawn tools and subagent definitions
    if not settings.subagents_enabled:
        profile.subagents = {}
        spawn_tools = {"spawn_agent", "spawn_predefined_agent"}
        profile.tools = [t for t in profile.tools if t not in spawn_tools]

    return RecursiveAgent(settings=settings, profile=profile)


def _get_available_agents(settings: Settings) -> dict[str, dict]:
    """Get all available agents from settings.

    Returns dict mapping agent name to its config.
    Always includes 'main' if agents_config exists.
    """
    agents = {}
    if "main" not in settings.agents_config:
        return agents

    main_config = settings.agents_config["main"]
    agents["main"] = main_config

    subagents = main_config.get("subagents", {})
    if isinstance(subagents, dict):
        for name, config in subagents.items():
            if isinstance(config, dict):
                agents[name] = config

    return agents


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
    console.print(
        "[dim]Tip: use Up/Down arrows to browse previous prompts in this project.[/dim]\n"
    )


def _print_active_model_hint(agent: RecursiveAgent, settings: Optional[Settings] = None) -> None:
    """Print current active model and agent configuration used by main replies."""
    parts = [f"Active model: [cyan]{_get_agent_model_ref(agent)}[/cyan]"]

    if settings:
        if settings.active_agent and settings.active_agent != "main":
            parts.append(f" | agent: [cyan]{settings.active_agent}[/cyan]")
        if not settings.subagents_enabled:
            parts.append(" | [yellow]subagents disabled[/yellow]")

    console.print(f"[dim]{''.join(parts)}[/dim]\n")


def print_help() -> None:
    """Print help message."""
    help_text = """
**Commands:**
- `/help` - Show this message
- `/reset` - Reset conversation
- `/setup` - Configure agents for this project
- `/agents` - Configure model per agent/subagent
- `/agent` - List available agents
- `/agent <name>` - Switch to agent (resets conversation)
- `/catalog` - Browse content catalog
- `/quit` - Exit
- `/providers` - List configured providers and models
- `/tools` - List available tools by category
- `/tools <name>` - Show tool schema and parameters
- `/config` - Show config paths and active settings

**Tips:**
- Run `flavia --init` to create initial config
- Run `flavia --setup-provider` to configure providers
- Use `/setup` to reconfigure agents

**CLI flags:**
- `--no-subagents` - Disable sub-agent spawning
- `--agent NAME` - Use a subagent as the main agent
- `--depth N` - Set max recursion depth
- `--parallel-workers N` - Max parallel sub-agents
"""
    console.print(Markdown(help_text))


def run_cli(settings: Settings) -> None:
    """Run the interactive CLI."""
    # Keep CLI output clean even if logging is configured elsewhere.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)

    print_welcome(settings)

    history_file, chat_log_file = _history_paths(settings.base_dir)
    history_enabled = _configure_prompt_history(history_file)

    agent = create_agent_from_settings(settings)
    _print_active_model_hint(agent, settings)

    while True:
        try:
            user_input = _read_user_input(history_enabled, settings.active_agent).strip()

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
                    # Preserve runtime-only flags across reset
                    new_settings.subagents_enabled = settings.subagents_enabled
                    new_settings.active_agent = settings.active_agent
                    new_settings.parallel_workers = settings.parallel_workers
                    settings = new_settings
                    history_file, chat_log_file = _history_paths(settings.base_dir)
                    history_enabled = _configure_prompt_history(history_file)

                    agent = create_agent_from_settings(settings)
                    console.print("[yellow]Conversation reset and config reloaded.[/yellow]")
                    _print_active_model_hint(agent, settings)
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

                elif command == "/providers":
                    from flavia.display import display_providers

                    display_providers(settings, console=console, use_rich=True)
                    continue

                elif command == "/tools" or command.startswith("/tools "):
                    from flavia.display import display_tools, display_tool_schema

                    # Check if a specific tool was requested
                    parts = user_input.split(maxsplit=1)
                    if len(parts) > 1:
                        tool_name = parts[1].strip()
                        display_tool_schema(tool_name, console=console, use_rich=True)
                    else:
                        display_tools(console=console, use_rich=True)
                    continue

                elif command == "/config":
                    from flavia.display import display_config

                    display_config(settings, console=console, use_rich=True)
                    continue

                elif command == "/catalog":
                    from flavia.interfaces.catalog_command import run_catalog_command

                    run_catalog_command(settings)
                    continue

                elif command == "/agent" or command.startswith("/agent "):
                    parts = user_input.split(maxsplit=1)
                    if len(parts) > 1:
                        # Switch to specified agent
                        agent_name = parts[1].strip()
                        current = settings.active_agent or "main"

                        if agent_name == current:
                            console.print(f"[yellow]Already using agent '{agent_name}'.[/yellow]")
                            continue

                        # Validate agent exists
                        available = _get_available_agents(settings)
                        if agent_name not in available:
                            console.print(f"[red]Agent '{agent_name}' not found.[/red]")
                            console.print(f"Available: {', '.join(available.keys())}")
                            continue

                        # Update settings and create new agent
                        settings.active_agent = None if agent_name == "main" else agent_name
                        agent = create_agent_from_settings(settings)
                        console.print(
                            f"[green]Switched to agent '{agent_name}'. Conversation reset.[/green]"
                        )
                        _print_active_model_hint(agent, settings)
                    else:
                        # List available agents
                        from flavia.display import display_agents

                        display_agents(settings, console=console, use_rich=True)
                    continue

                else:
                    console.print(f"[red]Unknown command: {command}[/red]")
                    continue

            try:
                active_model = _get_agent_model_ref(agent)
                _append_prompt_history(user_input, history_file, history_enabled)
                _append_chat_log(chat_log_file, "user", user_input, model_ref=active_model)
                response = _run_agent_with_feedback(agent, user_input)
                console.print(f"[bold blue]{_build_agent_prefix(agent)}[/bold blue] ", end="")
                console.print(Markdown(response))
                _append_chat_log(chat_log_file, "assistant", response, model_ref=active_model)
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
