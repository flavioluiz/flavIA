"""Interactive CLI interface for flavIA."""

import json
import logging
import os
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
from flavia.config import ProviderConfig, Settings
from flavia.interfaces.commands import CommandContext, dispatch_command, list_commands

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

_COMPLETION_SETTINGS: Optional[Settings] = None

_COMMANDS_WITH_ARGS = {
    "/help",
    "/agent",
    "/model",
    "/tools",
    "/provider-manage",
    "/provider-test",
}


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
        _configure_readline_completion()
        # Keep a plain prompt with readline; styled ANSI prompts can break redraw
        # when deleting characters or navigating history with arrows.
        prefix = f"[{active_agent}] " if has_prefix else ""
        return input(f"{prefix}You: ")

    if has_prefix:
        return console.input(f"[dim][{active_agent}] [/dim][bold green]You:[/bold green] ")
    return console.input("[bold green]You:[/bold green] ")


def _configure_readline_completion() -> None:
    """Enable TAB completion for commands, agent names, and file paths."""
    if _readline is None:
        return
    if not hasattr(_readline, "set_completer"):
        return

    try:
        # Keep "/" in tokens so command and path completion see full fragments.
        if hasattr(_readline, "set_completer_delims"):
            _readline.set_completer_delims(" \t\n")
        _readline.set_completer(_readline_completer)
        if hasattr(_readline, "parse_and_bind"):
            _readline.parse_and_bind("tab: complete")
    except Exception:
        pass


def _readline_completer(text: str, state: int) -> Optional[str]:
    """Readline completion callback."""
    line_buffer = ""
    if _readline is not None and hasattr(_readline, "get_line_buffer"):
        try:
            line_buffer = _readline.get_line_buffer()
        except Exception:
            line_buffer = ""

    matches = _completion_candidates(text, line_buffer, _COMPLETION_SETTINGS)
    if state < len(matches):
        return matches[state]
    return None


def _completion_candidates(
    text: str,
    line_buffer: str,
    settings: Optional[Settings],
) -> list[str]:
    """Build completion candidates for the current prompt fragment."""
    stripped = line_buffer.lstrip()
    if text.startswith("@"):
        return _path_completion_candidates(
            text[1:],
            settings,
            allow_empty=True,
            prefix="@",
        )
    if stripped.startswith("/"):
        return _command_completion_candidates(text, stripped, settings)
    return _path_completion_candidates(text, settings)


def _command_completion_candidates(
    text: str,
    stripped_line: str,
    settings: Optional[Settings],
) -> list[str]:
    """Complete slash commands and command-specific arguments."""
    parts = stripped_line.split()

    if len(parts) <= 1 and not stripped_line.endswith(" "):
        commands = []
        for cmd in list_commands():
            if cmd.startswith(text):
                commands.append(f"{cmd} " if cmd in _COMMANDS_WITH_ARGS else cmd)
        return sorted(commands)

    if not parts:
        return []

    cmd = parts[0]

    if cmd == "/agent" and settings is not None:
        return sorted(
            name for name in _get_available_agents(settings).keys() if name.startswith(text)
        )

    if cmd in {"/provider-manage", "/provider-test"} and settings is not None:
        providers = settings.providers.providers.keys()
        return sorted(pid for pid in providers if pid.startswith(text))

    if cmd == "/model" and settings is not None:
        matches: set[str] = set()
        if "list".startswith(text):
            matches.add("list")
        if settings.providers.providers:
            for provider in settings.providers.providers.values():
                for model in provider.models:
                    prefixed = f"{provider.id}:{model.id}"
                    if prefixed.startswith(text) or model.id.startswith(text):
                        matches.add(prefixed)
            return sorted(matches)
        else:
            for model in settings.models:
                if model.id.startswith(text):
                    matches.add(model.id)
        return sorted(matches)

    if cmd == "/help":
        names = [name.lstrip("/") for name in list_commands()]
        return sorted(name for name in names if name.startswith(text))

    return []


def _path_completion_candidates(
    text: str,
    settings: Optional[Settings],
    allow_empty: bool = False,
    prefix: str = "",
) -> list[str]:
    """Complete file/directory names relative to project base directory."""
    if not text and not allow_empty:
        return []

    base_dir = settings.base_dir if settings is not None else Path.cwd()
    raw_dir, raw_partial = os.path.split(text)
    expanded = os.path.expanduser(text)
    expanded_dir, expanded_partial = os.path.split(expanded)
    search_partial = expanded_partial if expanded_partial is not None else raw_partial

    if os.path.isabs(expanded):
        search_dir = Path(expanded_dir or os.sep)
    else:
        search_dir = (base_dir / expanded_dir) if expanded_dir else base_dir

    try:
        entries = sorted(search_dir.iterdir(), key=lambda p: p.name.lower())
    except Exception:
        return []

    candidates: list[str] = []
    for entry in entries:
        name = entry.name
        if search_partial and not name.startswith(search_partial):
            continue
        candidate = os.path.join(raw_dir, name) if raw_dir else name
        if entry.is_dir():
            candidate += "/"
        candidates.append(f"{prefix}{candidate}")

    return candidates


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


def _display_current_model(agent: RecursiveAgent, settings: Settings, console: Console) -> None:
    """Display current active model information."""
    model_ref = _get_agent_model_ref(agent)
    resolved = _resolve_model_reference(settings, model_ref)
    if resolved is None:
        provider_config, model_id = settings.resolve_model_with_provider(model_ref)
    else:
        provider_config, model_id, _ = resolved

    console.print("\n[bold]Current Model:[/bold]")
    console.print("-" * 60)

    if provider_config:
        console.print(f"  Provider:    [cyan]{provider_config.name}[/cyan] ({provider_config.id})")

        # Find the model config for additional details
        model_config = provider_config.get_model_by_id(model_id)
        if model_config:
            console.print(f"  Model:       [cyan]{model_config.name}[/cyan]")
            console.print(f"  Reference:   [cyan]{model_ref}[/cyan]")
            if model_config.max_tokens:
                console.print(f"  Max Tokens:  {model_config.max_tokens:,}")
            if model_config.description:
                console.print(f"  Description: {model_config.description}")
        else:
            console.print(f"  Model:       [cyan]{model_id}[/cyan]")
            console.print(f"  Reference:   [cyan]{model_ref}[/cyan]")
    else:
        # Fallback display for legacy configs
        console.print(f"  Model:       [cyan]{model_ref}[/cyan]")

    console.print()


def _models_are_equivalent(settings: Settings, current_ref: str, new_ref: str | int) -> bool:
    """Check if two model references point to the same model."""
    current_resolved = _resolve_model_reference(settings, current_ref)
    new_resolved = _resolve_model_reference(settings, new_ref)

    if current_resolved is None or new_resolved is None:
        return False

    current_provider, current_model_id, _ = current_resolved
    new_provider, new_model_id, _ = new_resolved

    if current_provider is None or new_provider is None:
        return current_model_id == new_model_id

    return current_provider.id == new_provider.id and current_model_id == new_model_id


def _resolve_model_reference(
    settings: Settings, model_ref: str | int
) -> tuple[ProviderConfig | None, str, str] | None:
    """Resolve a model reference and ensure it exists."""
    if settings.providers.providers:
        provider, model = settings.providers.resolve_model(model_ref)
        if provider is None or model is None:
            return None
        model_id = model.id
        return provider, model_id, f"{provider.id}:{model_id}"

    if isinstance(model_ref, int):
        model = settings.get_model_by_index(model_ref)
        if model is None:
            return None
        return None, model.id, model.id

    model_id = settings.resolve_model(model_ref)
    return None, model_id, str(model_id)


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


def create_agent_from_settings(
    settings: Settings, model_override: str | int | None = None
) -> RecursiveAgent:
    """Create an agent from settings and optional agents.yaml config.

    Respects:
    - settings.active_agent: use a subagent config as the main agent
    - settings.subagents_enabled: when False, strips subagents and spawn tools
    - model_override: when provided, forces the runtime model for the returned agent
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
    if model_override is not None:
        profile.model = model_override
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


def _resolve_agent_model_ref(
    settings: Settings,
    agent_name: str,
    available_agents: Optional[dict[str, dict]] = None,
) -> str | int:
    """Resolve the model reference that would be used by a specific agent."""
    available = (
        available_agents if available_agents is not None else _get_available_agents(settings)
    )
    main_config = available.get("main", {})
    main_model = (
        main_config.get("model", settings.default_model)
        if isinstance(main_config, dict)
        else settings.default_model
    )

    if agent_name == "main":
        return main_model

    agent_config = available.get(agent_name, {})
    if isinstance(agent_config, dict):
        return agent_config.get("model", main_model)
    return main_model


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
    console.print("[dim]Tip: press Tab to autocomplete commands, agents, and paths.[/dim]\n")


def _print_active_model_hint(agent: RecursiveAgent, settings: Optional[Settings] = None) -> None:
    """Print current active model and agent configuration used by main replies."""
    parts = [f"Active model: [cyan]{_get_agent_model_ref(agent)}[/cyan]"]

    if settings:
        if settings.active_agent and settings.active_agent != "main":
            parts.append(f" | agent: [cyan]{settings.active_agent}[/cyan]")
        if not settings.subagents_enabled:
            parts.append(" | [yellow]subagents disabled[/yellow]")

    console.print(f"[dim]{''.join(parts)}[/dim]\n")


def _display_token_usage(agent: RecursiveAgent) -> None:
    """Display compact token usage line with color coding after agent response.

    Format: ``[tokens: 12,450 / 128,000 (9.7%) | response: 850 tokens]``

    Color coding based on context utilization:
    - green: < 70%
    - yellow: 70-89%
    - red: >= 90%
    """
    prompt_tokens = agent.last_prompt_tokens
    max_tokens = agent.max_context_tokens
    completion_tokens = agent.last_completion_tokens
    pct = agent.context_utilization * 100

    if pct >= 90:
        color = "red"
    elif pct >= 70:
        color = "yellow"
    else:
        color = "green"

    console.print(
        f"[dim][{color}]\\[tokens: {prompt_tokens:,} / {max_tokens:,} "
        f"({pct:.1f}%) | response: {completion_tokens:,} tokens][/{color}][/dim]"
    )


def run_cli(settings: Settings) -> None:
    """Run the interactive CLI."""
    global _COMPLETION_SETTINGS

    # Keep CLI output clean even if logging is configured elsewhere.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)

    print_welcome(settings)

    history_file, chat_log_file = _history_paths(settings.base_dir)
    history_enabled = _configure_prompt_history(history_file)

    agent = create_agent_from_settings(settings)
    _print_active_model_hint(agent, settings)

    # Create command context for dispatch
    ctx = CommandContext(
        settings=settings,
        agent=agent,
        console=console,
        history_file=history_file,
        chat_log_file=chat_log_file,
        history_enabled=history_enabled,
        create_agent=create_agent_from_settings,
    )

    while True:
        _COMPLETION_SETTINGS = ctx.settings
        try:
            user_input = _read_user_input(ctx.history_enabled, ctx.settings.active_agent).strip()

            if not user_input:
                continue

            if user_input.startswith("/"):
                # Dispatch to command registry
                should_continue = dispatch_command(ctx, user_input)
                if not should_continue:
                    break
                continue

            # Regular message: send to agent
            try:
                active_model = _get_agent_model_ref(ctx.agent)
                _append_prompt_history(user_input, ctx.history_file, ctx.history_enabled)
                _append_chat_log(ctx.chat_log_file, "user", user_input, model_ref=active_model)
                response = _run_agent_with_feedback(ctx.agent, user_input)
                console.print(f"[bold blue]{_build_agent_prefix(ctx.agent)}[/bold blue] ", end="")
                console.print(Markdown(response))
                _display_token_usage(ctx.agent)
                _append_chat_log(ctx.chat_log_file, "assistant", response, model_ref=active_model)
            except KeyboardInterrupt:
                console.print("\n[yellow]Interrupted[/yellow]")
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")
                if ctx.settings.verbose:
                    import traceback

                    traceback.print_exc()

            console.print()

        except KeyboardInterrupt:
            console.print("\n[yellow]Use /quit to exit[/yellow]")
        except EOFError:
            console.print("\n[yellow]Goodbye![/yellow]")
            break
