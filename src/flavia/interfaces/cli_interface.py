"""Interactive CLI interface for flavIA."""

import json
import logging
import os
import random
import sys
import threading
from collections import deque
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.syntax import Syntax
from rich.tree import Tree

from flavia.agent import AgentProfile, RecursiveAgent, StatusPhase, ToolStatus
from flavia.agent.status import sanitize_terminal_text
from flavia.config import ProviderConfig, Settings
from flavia.interfaces.commands import CommandContext, dispatch_command, list_commands
from flavia.tools.write_confirmation import WriteConfirmation
from flavia.tools.write.preview import OperationPreview

console = Console()

try:
    import readline as _readline
except Exception:  # pragma: no cover - platform-dependent
    _readline = None

LOADING_DOTS = (".", "..", "...", "..")
MAX_STATUS_EVENTS = 100
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
    "/compact",
}


_ANSI_RESET = "\033[0m"
_ANSI_BOLD_CYAN = "\033[1;36m"
_ANSI_BOLD_BLUE = "\033[1;34m"
_ANSI_GREEN = "\033[32m"
_ANSI_DIM = "\033[2m"


def _supports_status_colors() -> bool:
    """Return whether ANSI colors should be used for status streaming."""
    if os.getenv("NO_COLOR") is not None:
        return False
    out_stream = getattr(console, "file", None)
    return bool(out_stream and hasattr(out_stream, "isatty") and out_stream.isatty())


def _colorize_status(text: str, ansi_code: str) -> str:
    """Apply ANSI style to a status line when color is supported."""
    if not text or not _supports_status_colors():
        return text
    return f"{ansi_code}{text}{_ANSI_RESET}"


def _build_loading_line(
    message: str,
    step: int,
    model_ref: str = "",
    include_prefix: bool = True,
) -> str:
    """Build one loading frame line."""
    dots = LOADING_DOTS[step % len(LOADING_DOTS)]
    safe_model_ref = sanitize_terminal_text(model_ref)
    safe_message = sanitize_terminal_text(message)
    if not include_prefix:
        return f"{safe_message} {dots}"
    prefix = f"Agent [{safe_model_ref}]" if safe_model_ref else "Agent"
    return f"{prefix}: {safe_message} {dots}"


def _build_session_header_line(model_ref: str = "") -> str:
    """Build one-time session header line shown before streaming status."""
    safe_model_ref = sanitize_terminal_text(model_ref)
    return f"Agent [{safe_model_ref}]" if safe_model_ref else "Agent"


def _truncate_status_text(text: str, max_len: int = 30) -> str:
    """Truncate text for compact single-line status rendering."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _agent_label_from_id(agent_id: str) -> str:
    """Map internal agent IDs to compact hierarchical labels for CLI status.

    Examples:
        "main" -> "main"
        "main.sub.1" -> "sub-1"
        "main.sub.1.sub.2" -> "sub-1.sub-2"
        "main.summarizer.1" -> "summarizer"
        "main.summarizer.1.sub.1" -> "summarizer.sub-1"
    """
    safe_id = sanitize_terminal_text(agent_id).strip() or "main"
    if safe_id == "main":
        return "main"

    # Strip "main." prefix if present
    if safe_id.startswith("main."):
        safe_id = safe_id[5:]

    parts = safe_id.split(".")
    result_parts = []
    i = 0
    while i < len(parts):
        if i + 1 < len(parts) and parts[i] == "sub" and parts[i + 1].isdigit():
            # "sub.N" -> "sub-N"
            result_parts.append(f"sub-{parts[i + 1]}")
            i += 2
        elif i + 1 < len(parts) and parts[i + 1].isdigit():
            # "name.N" -> "name" (named agent with numeric suffix)
            result_parts.append(parts[i])
            i += 2
        else:
            result_parts.append(parts[i])
            i += 1

    return ".".join(result_parts) if result_parts else "agent"


def _build_tool_status_line(
    status: ToolStatus,
    step: int,
    model_ref: str = "",
    verbose: bool = False,
    show_dots: bool = True,
    include_prefix: bool = True,
) -> str:
    """Build a status line for tool execution.

    Args:
        status: Current tool status.
        step: Animation step for dots.
        model_ref: Model reference for display.
        verbose: Whether to show detailed arguments.
        show_dots: Whether to append animated dots.
        include_prefix: Whether to include "Agent [model]" prefix.

    Returns:
        Formatted status line string.
    """
    dots = LOADING_DOTS[step % len(LOADING_DOTS)] if show_dots else ""
    indent = "  " * status.depth
    safe_model_ref = sanitize_terminal_text(model_ref)
    prefix = f"Agent [{safe_model_ref}]" if safe_model_ref else "Agent"

    if verbose and status.args:
        # Verbose: show tool name with arguments
        def _format_arg_value(value: object) -> str:
            if isinstance(value, str):
                value_repr = repr(sanitize_terminal_text(value))
            else:
                value_repr = repr(value)
            return _truncate_status_text(sanitize_terminal_text(value_repr))

        args_str = ", ".join(
            f"{sanitize_terminal_text(k)}={_format_arg_value(v)}"
            for k, v in list(status.args.items())[:3]
        )
        display = f"{sanitize_terminal_text(status.tool_name)}({args_str})"
    else:
        display = sanitize_terminal_text(status.tool_display or status.tool_name or "Working")

    if include_prefix:
        line = f"{indent}{prefix}: {display}"
    else:
        line = f"{indent}{display}"

    if show_dots:
        return f"{line} {dots}"
    return line


def _build_agent_header_line(status: ToolStatus) -> str:
    """Build one-time header line for an agent/sub-agent section."""
    indent = "  " * status.depth
    return f"{indent}{_agent_label_from_id(status.agent_id)}:"


def _build_agent_activity_line(
    status: ToolStatus,
    step: int,
    model_ref: str = "",
    verbose: bool = False,
) -> str:
    """Build a tool activity line nested under the agent header."""
    display = _build_tool_status_line(
        status,
        step,
        model_ref,
        verbose,
        show_dots=False,
        include_prefix=False,
    ).strip()
    indent = "  " * (status.depth + 1)
    return f"{indent}{display}"


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
        return LOADING_MESSAGES[0] if LOADING_MESSAGES else "Processing"

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


# Lock used by the write-confirmation callback to safely pause the
# status animation thread while prompting the user.
_confirmation_lock = threading.Lock()
# Event for signaling animation pause/resume (set = running, clear = paused)
_confirmation_pause_event = threading.Event()
_confirmation_pause_event.set()  # Not paused by default


def _cli_write_confirmation_callback(
    operation: str,
    path: str,
    details: str,
    preview: Optional[OperationPreview] = None,
) -> bool:
    """Prompt the user to confirm a write operation from the agent thread.

    This callback is invoked from within `_suppress_terminal_input`.
    We temporarily restore the terminal so the user can type "y/N".
    """
    try:
        import termios as _termios
    except Exception:
        _termios = None

    fd = sys.stdin.fileno() if hasattr(sys.stdin, "fileno") else None
    old_settings = None

    # Signal animation to pause
    _confirmation_pause_event.clear()

    with _confirmation_lock:
        try:
            # Restore terminal so the user can type.
            if _termios is not None and fd is not None:
                try:
                    old_settings = _termios.tcgetattr(fd)
                    restore = _termios.tcgetattr(fd)
                    restore[3] |= _termios.ECHO | _termios.ICANON
                    _termios.tcsetattr(fd, _termios.TCSANOW, restore)
                except Exception:
                    old_settings = None

            # Clear animation line and show prompt.
            _clear_terminal_line()
            detail_str = f" ({details})" if details else ""
            console.print(
                f"\n[bold yellow]Write confirmation:[/bold yellow] "
                f"{operation}: [cyan]{path}[/cyan]{detail_str}"
            )

            # Display preview if available
            if preview is not None:
                _display_operation_preview(preview)

            console.print("[bold yellow]Allow? [y/N][/bold yellow] ", end="")

            try:
                answer = input().strip().lower()
            except (EOFError, KeyboardInterrupt):
                console.print()
                return False

            approved = answer in ("y", "yes")
            if approved:
                console.print("[green]Approved[/green]")
            else:
                console.print("[yellow]Denied[/yellow]")
            return approved

        finally:
            # Re-suppress terminal input.
            if _termios is not None and old_settings is not None and fd is not None:
                try:
                    _termios.tcflush(fd, _termios.TCIFLUSH)
                    _termios.tcsetattr(fd, _termios.TCSANOW, old_settings)
                except Exception:
                    pass
            # Resume animation
            _confirmation_pause_event.set()


def _display_operation_preview(preview: OperationPreview) -> None:
    """Display operation preview with appropriate formatting."""
    # Display diff for edit operations
    if preview.diff:
        console.print("\n[dim]Changes:[/dim]")
        # Use Syntax for colored diff display
        syntax = Syntax(
            preview.diff,
            "diff",
            theme="monokai",
            line_numbers=False,
            word_wrap=True,
        )
        console.print(syntax)

    # Display content preview for write/append operations
    elif preview.content_preview:
        console.print(
            f"\n[dim]Content ({preview.content_lines} lines, {preview.content_bytes} bytes):[/dim]"
        )
        # Truncate display if too long
        lines = preview.content_preview.split("\n")
        if len(lines) > 15:
            display_content = "\n".join(lines[:15]) + f"\n... ({len(lines) - 15} more lines)"
        else:
            display_content = preview.content_preview
        console.print(f"[dim]{display_content}[/dim]")

    # Display insertion context
    if preview.context_before or preview.context_after:
        if preview.context_before:
            console.print("\n[dim]Lines before insertion:[/dim]")
            console.print(f"[dim]{preview.context_before}[/dim]")
        console.print("[bold green]>>> INSERT HERE <<<[/bold green]")
        if preview.context_after:
            console.print("[dim]Lines after insertion:[/dim]")
            console.print(f"[dim]{preview.context_after}[/dim]")

    # Display file preview for delete operations
    if preview.file_preview and preview.operation == "delete":
        console.print(f"\n[dim]File content ({preview.file_size} bytes):[/dim]")
        console.print(f"[dim]{preview.file_preview}[/dim]")

    # Display directory contents for directory operations
    if preview.dir_contents:
        console.print("\n[dim]Directory contents:[/dim]")
        for item in preview.dir_contents[:10]:
            console.print(f"[dim]  {item}[/dim]")
        if len(preview.dir_contents) > 10:
            console.print(f"[dim]  ... ({len(preview.dir_contents) - 10} more items)[/dim]")

    console.print()


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


class _AnimationState:
    """Shared state for status animation, allowing access after interruption."""

    def __init__(self) -> None:
        self.agent_order: list[str] = []
        self.agent_tasks: dict[str, list[str]] = {}
        self.agent_omitted_count: dict[str, int] = {}
        self.agent_children: dict[str, list[str]] = {}  # parent -> [children]
        self.current_task: Optional[str] = None
        self.current_agent_id: Optional[str] = None
        self.model_ref: str = ""


def _get_parent_agent_id(agent_id: str) -> Optional[str]:
    """Get the parent agent ID from a hierarchical agent ID.

    Examples:
        "main" -> None
        "main.sub.1" -> "main"
        "main.sub.1.sub.2" -> "main.sub.1"
    """
    if agent_id == "main" or not agent_id:
        return None

    parts = agent_id.split(".")
    if len(parts) <= 1:
        return None

    # Find the last "sub.N" or "name.N" pattern and return everything before it
    # e.g., "main.sub.1.sub.2" -> parts = ["main", "sub", "1", "sub", "2"]
    # parent is "main.sub.1"
    i = len(parts) - 1
    while i > 0:
        if parts[i].isdigit() and i > 0:
            # Found "name.N" pattern, parent is everything before "name.N"
            return ".".join(parts[: i - 1]) if i > 1 else parts[0]
        i -= 1

    return None


def _get_agent_depth(agent_id: str) -> int:
    """Get the nesting depth of an agent (0 for main, 1 for sub.N, 2 for sub.N.sub.M, etc.)."""
    if agent_id == "main":
        return 0
    # Count "sub.N" patterns
    parts = agent_id.split(".")
    depth = 0
    i = 0
    while i < len(parts):
        if i + 1 < len(parts) and parts[i + 1].isdigit():
            depth += 1
            i += 2
        else:
            i += 1
    return depth


def _render_agent_branch(
    state: _AnimationState,
    agent_id: str,
    parent_branch: Tree,
    interrupted: bool = False,
) -> None:
    """Recursively render an agent and its children as nested branches."""
    label = _agent_label_from_id(agent_id)

    # For nested agents, show just the last part of the label
    if "." in label:
        label = label.split(".")[-1]

    branch = parent_branch.add(f"[bold blue]{label}:[/bold blue]")

    omitted_count = state.agent_omitted_count.get(agent_id, 0)
    if omitted_count > 0:
        branch.add(f"[dim]... ({omitted_count} previous)[/dim]")

    tasks = state.agent_tasks.get(agent_id, [])
    children = state.agent_children.get(agent_id, [])

    # Build a map of which task index spawned which child
    # This is approximate - we assume children appear in order after spawn tasks
    child_iter = iter(children)
    current_child: Optional[str] = None
    try:
        current_child = next(child_iter)
    except StopIteration:
        current_child = None

    for i, task in enumerate(tasks):
        is_last_task = (i == len(tasks) - 1)
        is_interrupted_agent = (agent_id == state.current_agent_id)
        is_spawn_task = "Spawning" in task

        if interrupted and is_last_task and is_interrupted_agent and state.current_task:
            branch.add(f"[yellow]{task} (interrupted)[/yellow]")
        elif interrupted:
            branch.add(f"[green]{task}[/green] [dim]✓[/dim]")
        else:
            branch.add(f"[green]{task}[/green]")

        # If this is a spawn task and we have a pending child, render it nested
        if is_spawn_task and current_child:
            _render_agent_branch(state, current_child, branch, interrupted)
            try:
                current_child = next(child_iter)
            except StopIteration:
                current_child = None

    # Render any remaining children that weren't matched to spawn tasks
    while current_child:
        _render_agent_branch(state, current_child, branch, interrupted)
        try:
            current_child = next(child_iter)
        except StopIteration:
            current_child = None


def _render_interrupted_summary(state: _AnimationState) -> None:
    """Render a summary of completed and interrupted tasks after Ctrl+C."""
    if not state.agent_order:
        console.print("[yellow]Interrupted (no tasks started)[/yellow]")
        return

    tree = Tree(f"[bold cyan]Agent [{state.model_ref}][/bold cyan] [yellow](interrupted)[/yellow]")

    # Find root agents (those with no parent or parent is "main")
    root_agents = []
    for agent_id in state.agent_order:
        parent = _get_parent_agent_id(agent_id)
        if parent is None or parent == "main" or parent not in state.agent_tasks:
            root_agents.append(agent_id)

    for agent_id in root_agents:
        _render_agent_branch(state, agent_id, tree, interrupted=True)

    console.print(tree)


def _run_status_animation(
    stop_event: threading.Event,
    model_ref: str,
    status_holder: list[Optional[ToolStatus]],
    status_events: deque[ToolStatus],
    status_lock: threading.Lock,
    verbose: bool = False,
    animation_state: Optional[_AnimationState] = None,
    max_tasks_main: int = 5,
    max_tasks_subagent: int = 3,
) -> None:
    """Render status animation with tool status updates using Rich Live display.

    Shows tool-specific status when available, falls back to loading messages.
    Uses Rich Live for robust terminal handling that automatically manages
    cursor positioning and cleanup.

    Args:
        stop_event: Event to signal animation stop.
        model_ref: Model reference for display.
        status_holder: Single-element list holding current ToolStatus.
        status_events: Bounded deque of status events (maxlen=MAX_STATUS_EVENTS).
        status_lock: Lock protecting shared status structures.
        verbose: Whether to show detailed tool arguments.
        animation_state: Optional shared state for interrupt handling.
        max_tasks_main: Max tasks to show for main agent (-1 = unlimited).
        max_tasks_subagent: Max tasks to show for subagents (-1 = unlimited).
    """
    step = 0
    fallback_message = _choose_loading_message()
    next_message_step = random.randint(14, 24)

    # Use shared state if provided, otherwise create local state
    state = animation_state or _AnimationState()
    state.model_ref = model_ref
    agent_order = state.agent_order
    agent_tasks = state.agent_tasks
    agent_omitted_count = state.agent_omitted_count
    agent_children = state.agent_children

    def _get_max_tasks_for_agent(agent_id: str) -> int:
        """Get the max tasks limit for an agent based on its type."""
        if agent_id == "main":
            return max_tasks_main
        return max_tasks_subagent

    def _render_agent_live(agent_id: str, parent_branch: Tree) -> None:
        """Recursively render an agent and its children as nested branches."""
        label = _agent_label_from_id(agent_id)
        # For nested agents, show just the last part of the label
        if "." in label:
            label = label.split(".")[-1]

        branch = parent_branch.add(f"[bold blue]{label}:[/bold blue]")

        omitted_count = agent_omitted_count.get(agent_id, 0)
        if omitted_count > 0:
            branch.add(f"[dim]... ({omitted_count} previous)[/dim]")

        tasks = agent_tasks.get(agent_id, [])
        children = agent_children.get(agent_id, [])

        # Build iterator for children to interleave with spawn tasks
        child_iter = iter(children)
        current_child: Optional[str] = None
        try:
            current_child = next(child_iter)
        except StopIteration:
            current_child = None

        for task in tasks:
            is_spawn_task = "Spawning" in task
            branch.add(f"[green]{task}[/green]")

            # If this is a spawn task and we have a pending child, render it nested
            if is_spawn_task and current_child:
                _render_agent_live(current_child, branch)
                try:
                    current_child = next(child_iter)
                except StopIteration:
                    current_child = None

        # Render any remaining children
        while current_child:
            _render_agent_live(current_child, branch)
            try:
                current_child = next(child_iter)
            except StopIteration:
                current_child = None

    def build_status_tree() -> Tree:
        """Build a Rich Tree representing current agent status."""
        nonlocal step, fallback_message, next_message_step

        with status_lock:
            current_status = status_holder[0] if status_holder else None
            pending_events = list(status_events)
            status_events.clear()

        # Track current task for interrupt handling
        if current_status and current_status.phase in (
            StatusPhase.EXECUTING_TOOL,
            StatusPhase.SPAWNING_AGENT,
        ):
            state.current_agent_id = current_status.agent_id
            state.current_task = _build_agent_activity_line(
                current_status, step, model_ref, verbose
            ).strip()
        else:
            state.current_task = None
            state.current_agent_id = None

        # Process pending events
        for event in pending_events:
            if event.phase not in (StatusPhase.EXECUTING_TOOL, StatusPhase.SPAWNING_AGENT):
                continue

            agent_id = event.agent_id
            if agent_id not in agent_tasks:
                agent_tasks[agent_id] = []
                agent_omitted_count[agent_id] = 0
                agent_order.append(agent_id)

                # Track parent-child relationship
                parent = _get_parent_agent_id(agent_id)
                if parent:
                    if parent not in agent_children:
                        agent_children[parent] = []
                    if agent_id not in agent_children[parent]:
                        agent_children[parent].append(agent_id)

            task_line = _build_agent_activity_line(event, step, model_ref, verbose).strip()
            tasks = agent_tasks[agent_id]
            tasks.append(task_line)

        # Trim each agent's task list based on configured limits
        for agent_id in agent_order:
            max_tasks = _get_max_tasks_for_agent(agent_id)
            if max_tasks < 0:
                continue  # Unlimited
            tasks = agent_tasks.get(agent_id, [])
            if len(tasks) > max_tasks:
                removed = len(tasks) - max_tasks
                agent_omitted_count[agent_id] = agent_omitted_count.get(agent_id, 0) + removed
                del tasks[0:removed]

        tool_active = bool(
            current_status
            and current_status.phase in (StatusPhase.EXECUTING_TOOL, StatusPhase.SPAWNING_AGENT)
        )

        # Build footer message
        dots = LOADING_DOTS[step % len(LOADING_DOTS)]
        if tool_active:
            footer_text = f"Working {dots}"
        else:
            footer_text = f"{fallback_message} {dots}"

        # Build the tree with hierarchical structure
        tree = Tree(f"[bold cyan]Agent [{model_ref}][/bold cyan]")

        # Find root agents (those with no parent in our tracked agents)
        root_agents = []
        for agent_id in agent_order:
            parent = _get_parent_agent_id(agent_id)
            if parent is None or parent == "main" or parent not in agent_tasks:
                root_agents.append(agent_id)

        for agent_id in root_agents:
            _render_agent_live(agent_id, tree)

        # Add footer
        tree.add(f"[dim]{footer_text}[/dim]")

        # Update step and message rotation
        step += 1
        if (not tool_active) and step % next_message_step == 0:
            fallback_message = _choose_loading_message(fallback_message)
            next_message_step = random.randint(14, 24)

        return tree

    # Use Rich Live for automatic cursor management and cleanup
    with Live(build_status_tree(), console=console, refresh_per_second=4, transient=True) as live:
        while not stop_event.is_set():
            # Pause status rendering while a write-confirmation prompt is active
            if not _confirmation_pause_event.wait(timeout=0.05):
                if stop_event.is_set():
                    break
                continue

            live.update(build_status_tree())

            # Check for stop with 0.25s interval
            if stop_event.wait(0.25):
                break


def _run_agent_with_feedback(
    agent: RecursiveAgent,
    user_input: str,
    verbose: bool = False,
    run_kwargs: Optional[dict[str, Any]] = None,
    settings: Optional[Settings] = None,
) -> str:
    """Run agent with visual processing feedback.

    Args:
        agent: The agent to run.
        user_input: User's input message.
        verbose: Whether to show detailed tool arguments in status.
        run_kwargs: Optional extra kwargs forwarded to ``agent.run()``.
        settings: Optional settings for status display configuration.

    Returns:
        Agent's response string.

    Raises:
        KeyboardInterrupt: Re-raised after rendering interrupted state summary.
    """
    kwargs = run_kwargs or {}
    if not _supports_wait_feedback():
        return agent.run(user_input, **kwargs)

    stop_event = threading.Event()
    model_ref = _get_agent_model_ref(agent)

    # Get task limits from settings or use defaults
    max_tasks_main = settings.status_max_tasks_main if settings else 5
    max_tasks_subagent = settings.status_max_tasks_subagent if settings else 3

    # Thread-safe container for status updates
    status_holder: list[Optional[ToolStatus]] = [None]
    status_events: deque[ToolStatus] = deque(maxlen=MAX_STATUS_EVENTS)
    status_lock = threading.Lock()

    # Shared state for interrupt handling - allows us to show what was done
    animation_state = _AnimationState()

    def update_status(status: ToolStatus) -> None:
        with status_lock:
            status_holder[0] = status
            status_events.append(status)

    agent.status_callback = update_status

    animation_thread = threading.Thread(
        target=_run_status_animation,
        args=(
            stop_event,
            model_ref,
            status_holder,
            status_events,
            status_lock,
            verbose,
            animation_state,
            max_tasks_main,
            max_tasks_subagent,
        ),
        daemon=True,
    )
    animation_thread.start()

    interrupted = False
    try:
        with _suppress_terminal_input():
            return agent.run(user_input, **kwargs)
    except KeyboardInterrupt:
        interrupted = True
        raise
    finally:
        agent.status_callback = None
        stop_event.set()
        animation_thread.join(timeout=1.0)
        if interrupted:
            # Show what was completed and what was interrupted
            _render_interrupted_summary(animation_state)
        else:
            _clear_terminal_line()


def _prompt_continue_after_max_iterations(limit: int) -> bool:
    """Ask whether to continue after max-iterations termination."""
    console.print(
        f"\n[bold yellow]Agent reached the maximum iteration limit ({limit}). "
        f"Continue with {limit} more iterations? [y/N][/bold yellow] ",
        end="",
    )
    try:
        answer = input().strip().lower()
    except (EOFError, KeyboardInterrupt):
        console.print()
        return False
    return answer in ("y", "yes")


def _continue_after_max_iterations(
    agent: RecursiveAgent,
    response: str,
    verbose: bool = False,
    settings: Optional[Settings] = None,
) -> str:
    """Optionally continue agent execution when max iterations is reached."""
    current_response = response

    while True:
        limit = RecursiveAgent.extract_max_iterations_limit(current_response)
        if limit is None:
            return current_response

        if not _prompt_continue_after_max_iterations(limit):
            return current_response

        current_response = _run_agent_with_feedback(
            agent,
            "",
            verbose,
            run_kwargs={"continue_from_current": True, "max_iterations": limit},
            settings=settings,
        )


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
        if settings.dry_run:
            parts.append(" | [bold yellow]DRY-RUN MODE[/bold yellow]")

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


def _prompt_compaction(agent: RecursiveAgent) -> bool:
    """Check if compaction is needed and prompt user for confirmation.

    Returns True if compaction was performed, False otherwise.
    """
    warning_pending = getattr(agent, "compaction_warning_pending", False)
    if not warning_pending and not agent.needs_compaction:
        return False

    max_tokens = agent.max_context_tokens
    prompt_tokens = agent.last_prompt_tokens
    if warning_pending:
        prompt_tokens = max(
            prompt_tokens,
            getattr(agent, "compaction_warning_prompt_tokens", prompt_tokens),
        )
    pct = (prompt_tokens / max_tokens * 100) if max_tokens > 0 else 0.0

    console.print(
        f"\n[bold red]\u26a0 Context usage at {pct:.0f}% "
        f"({prompt_tokens:,}/{max_tokens:,} tokens). "
        f"Compact conversation? \\[y/N][/bold red] ",
        end="",
    )

    try:
        answer = input().strip().lower()
    except (EOFError, KeyboardInterrupt):
        console.print()
        return False

    if answer in ("y", "yes"):
        console.print("[dim]Compacting conversation...[/dim]")
        try:
            summary = agent.compact_conversation()
            console.print("[green]Conversation compacted.[/green]")
            if summary:
                console.print("[bold]Summary:[/bold]")
                console.print(summary)
            new_pct = agent.context_utilization * 100
            new_prompt = agent.last_prompt_tokens
            console.print(f"[dim]New context: {new_prompt:,}/{max_tokens:,} ({new_pct:.1f}%)[/dim]")
            return True
        except Exception as e:
            console.print(f"[red]Compaction failed: {e}[/red]")
            return False

    return False


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

    # Set up write confirmation callback for write tools
    write_confirm = WriteConfirmation()
    write_confirm.set_callback(_cli_write_confirmation_callback)
    if hasattr(agent, "context"):
        agent.context.write_confirmation = write_confirm
        agent.context.dry_run = settings.dry_run

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
                response = _run_agent_with_feedback(
                    ctx.agent, user_input, ctx.settings.verbose, settings=ctx.settings
                )
                response = _continue_after_max_iterations(
                    ctx.agent, response, ctx.settings.verbose, settings=ctx.settings
                )
                console.print(f"[bold blue]{_build_agent_prefix(ctx.agent)}[/bold blue] ", end="")
                console.print(Markdown(response))
                _display_token_usage(ctx.agent)
                _prompt_compaction(ctx.agent)
                _append_chat_log(ctx.chat_log_file, "assistant", response, model_ref=active_model)
            except KeyboardInterrupt:
                # Summary already rendered by _run_agent_with_feedback
                pass
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
