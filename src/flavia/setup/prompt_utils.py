"""Safe terminal prompt utilities that avoid Rich's readline conflicts.

Rich's Prompt.ask() and Confirm.ask() use ANSI control sequences that can
break terminal redraw when deleting characters or navigating with arrows.
These utilities use plain input() to avoid such issues.

This module also provides questionary wrappers for interactive prompts
with automatic non-TTY fallback support.
"""

import getpass
import sys
from typing import Any, Callable, Optional, Sequence, TypeVar

from rich.console import Console

console = Console()

T = TypeVar("T")


class SetupCancelled(Exception):
    """Raised when the user cancels the setup flow (e.g., Ctrl+C)."""

    pass


def safe_prompt(
    prompt: str,
    default: str = "",
    password: bool = False,
    show_default: bool = True,
    allow_cancel: bool = False,
) -> str:
    """
    Safe input prompt using plain input() to avoid terminal issues.

    Args:
        prompt: The prompt text to display
        default: Default value if user presses Enter
        password: If True, hide input (for API keys, etc.)
        show_default: If True, show default value in prompt
        allow_cancel: If True, raise SetupCancelled on Ctrl+C instead of
                      returning the default value

    Returns:
        User input or default value

    Raises:
        SetupCancelled: If allow_cancel=True and user presses Ctrl+C
    """
    if password:
        # Use getpass for password input
        full_prompt = f"{prompt}: "
        try:
            result = getpass.getpass(full_prompt)
            return result if result else default
        except (EOFError, KeyboardInterrupt):
            print()  # Newline after interrupt
            if allow_cancel:
                raise SetupCancelled()
            return default

    if default and show_default:
        full_prompt = f"{prompt} ({default}): "
    else:
        full_prompt = f"{prompt}: "

    try:
        result = input(full_prompt).strip()
        return result if result else default
    except (EOFError, KeyboardInterrupt):
        print()  # Newline after interrupt
        if allow_cancel:
            raise SetupCancelled()
        return default


def safe_confirm(
    prompt: str,
    default: bool = False,
    allow_cancel: bool = False,
) -> bool:
    """
    Safe confirmation prompt using plain input().

    Args:
        prompt: The prompt text to display
        default: Default value if user presses Enter
        allow_cancel: If True, raise SetupCancelled on Ctrl+C instead of
                      returning the default value

    Returns:
        True for yes, False for no

    Raises:
        SetupCancelled: If allow_cancel=True and user presses Ctrl+C
    """
    default_hint = "[Y/n]" if default else "[y/N]"
    full_prompt = f"{prompt} {default_hint}: "

    try:
        result = input(full_prompt).strip().lower()
        if not result:
            return default
        return result in ("y", "yes", "true", "1")
    except (EOFError, KeyboardInterrupt):
        print()  # Newline after interrupt
        if allow_cancel:
            raise SetupCancelled()
        return default


# =============================================================================
# Questionary Wrapper Functions with Non-TTY Fallback
# =============================================================================


def is_interactive() -> bool:
    """Check if stdin/stdout support interactive prompts.

    Returns:
        True if running in an interactive terminal, False otherwise.
    """
    return (
        hasattr(sys.stdin, "isatty")
        and sys.stdin.isatty()
        and hasattr(sys.stdout, "isatty")
        and sys.stdout.isatty()
    )


def _fallback_select(
    message: str,
    choices: Sequence[Any],
    default: Optional[str] = None,
) -> Optional[str]:
    """Fallback numbered menu selection for non-interactive mode.

    Args:
        message: Prompt message
        choices: List of choices (strings or questionary.Choice objects)
        default: Default value

    Returns:
        Selected value or None if cancelled
    """
    console.print(f"\n[bold]{message}[/bold]")

    # Extract value and title from choices
    choice_items: list[tuple[str, str]] = []
    for choice in choices:
        if hasattr(choice, "value") and hasattr(choice, "title"):
            # questionary.Choice object
            choice_items.append((str(choice.value), str(choice.title)))
        else:
            # Plain string
            choice_items.append((str(choice), str(choice)))

    # Find default index
    default_index = 1
    for i, (value, _) in enumerate(choice_items, 1):
        if value == default:
            default_index = i
            break

    # Display numbered list
    for i, (value, title) in enumerate(choice_items, 1):
        marker = " [default]" if value == default else ""
        console.print(f"  [{i}] {title}{marker}")

    selection = safe_prompt("Enter number", default=str(default_index))
    try:
        idx = int(selection) - 1
        if 0 <= idx < len(choice_items):
            return choice_items[idx][0]
    except ValueError:
        pass

    # Return default on invalid input
    return default


def _fallback_checkbox(
    message: str,
    choices: Sequence[Any],
) -> list[str]:
    """Fallback comma-separated selection for non-interactive mode.

    Args:
        message: Prompt message
        choices: List of choices (strings or questionary.Choice objects)

    Returns:
        List of selected values
    """
    console.print(f"\n[bold]{message}[/bold]")

    # Extract value and title from choices
    choice_items: list[tuple[str, str]] = []
    for choice in choices:
        if hasattr(choice, "value") and hasattr(choice, "title"):
            choice_items.append((str(choice.value), str(choice.title)))
        else:
            choice_items.append((str(choice), str(choice)))

    # Display numbered list
    for i, (_, title) in enumerate(choice_items, 1):
        console.print(f"  [{i}] {title}")

    console.print("[dim]Enter numbers separated by comma, or 'a' for all[/dim]")
    selection = safe_prompt("Selection", default="a")

    if selection.lower() == "a":
        return [value for value, _ in choice_items]

    selected: list[str] = []
    for part in selection.split(","):
        try:
            idx = int(part.strip()) - 1
            if 0 <= idx < len(choice_items):
                selected.append(choice_items[idx][0])
        except ValueError:
            continue

    return selected if selected else [value for value, _ in choice_items]


def q_select(
    message: str,
    choices: Sequence[Any],
    default: Optional[str] = None,
    allow_cancel: bool = False,
) -> Optional[str]:
    """Interactive select prompt with non-TTY fallback.

    Args:
        message: Prompt message
        choices: List of choices (strings or questionary.Choice objects)
        default: Default value to pre-select
        allow_cancel: If True, raise SetupCancelled on Ctrl+C

    Returns:
        Selected value or None if cancelled

    Raises:
        SetupCancelled: If allow_cancel=True and user presses Ctrl+C
    """
    if not is_interactive():
        return _fallback_select(message, choices, default)

    try:
        import questionary

        result = questionary.select(
            message,
            choices=choices,
            default=default,
        ).ask()

        if result is None and allow_cancel:
            raise SetupCancelled()

        return result

    except KeyboardInterrupt:
        print()
        if allow_cancel:
            raise SetupCancelled()
        return None
    except ImportError:
        # Fallback if questionary not available
        return _fallback_select(message, choices, default)


def q_autocomplete(
    message: str,
    choices: Sequence[str],
    default: str = "",
    match_middle: bool = True,
    allow_cancel: bool = False,
) -> str:
    """Interactive autocomplete prompt with non-TTY fallback.

    Args:
        message: Prompt message
        choices: List of completion choices
        default: Default value
        match_middle: If True, match anywhere in string (not just prefix)
        allow_cancel: If True, raise SetupCancelled on Ctrl+C

    Returns:
        User input or selected choice

    Raises:
        SetupCancelled: If allow_cancel=True and user presses Ctrl+C
    """
    if not is_interactive():
        return safe_prompt(message, default=default, allow_cancel=allow_cancel)

    try:
        import questionary

        result = questionary.autocomplete(
            message,
            choices=list(choices),
            default=default,
            match_middle=match_middle,
            ignore_case=True,
        ).ask()

        if result is None:
            if allow_cancel:
                raise SetupCancelled()
            return default

        return result

    except KeyboardInterrupt:
        print()
        if allow_cancel:
            raise SetupCancelled()
        return default
    except ImportError:
        return safe_prompt(message, default=default, allow_cancel=allow_cancel)


def q_path(
    message: str,
    default: str = "",
    only_directories: bool = False,
    file_filter: Optional[Callable[[str], bool]] = None,
    allow_cancel: bool = False,
) -> str:
    """Interactive path prompt with completion and non-TTY fallback.

    Args:
        message: Prompt message
        default: Default path
        only_directories: If True, only show directories
        file_filter: Optional filter function for files
        allow_cancel: If True, raise SetupCancelled on Ctrl+C

    Returns:
        Selected path

    Raises:
        SetupCancelled: If allow_cancel=True and user presses Ctrl+C
    """
    if not is_interactive():
        return safe_prompt(message, default=default, allow_cancel=allow_cancel)

    try:
        import questionary

        result = questionary.path(
            message,
            default=default,
            only_directories=only_directories,
            file_filter=file_filter,
        ).ask()

        if result is None:
            if allow_cancel:
                raise SetupCancelled()
            return default

        return result

    except KeyboardInterrupt:
        print()
        if allow_cancel:
            raise SetupCancelled()
        return default
    except ImportError:
        return safe_prompt(message, default=default, allow_cancel=allow_cancel)


def q_password(
    message: str,
    allow_cancel: bool = False,
) -> str:
    """Interactive password prompt with non-TTY fallback.

    Args:
        message: Prompt message
        allow_cancel: If True, raise SetupCancelled on Ctrl+C

    Returns:
        Entered password (empty string if cancelled)

    Raises:
        SetupCancelled: If allow_cancel=True and user presses Ctrl+C
    """
    if not is_interactive():
        return safe_prompt(message, password=True, allow_cancel=allow_cancel)

    try:
        import questionary

        result = questionary.password(message).ask()

        if result is None:
            if allow_cancel:
                raise SetupCancelled()
            return ""

        return result

    except KeyboardInterrupt:
        print()
        if allow_cancel:
            raise SetupCancelled()
        return ""
    except ImportError:
        return safe_prompt(message, password=True, allow_cancel=allow_cancel)


def q_confirm(
    message: str,
    default: bool = False,
    allow_cancel: bool = False,
) -> bool:
    """Interactive confirmation prompt with non-TTY fallback.

    Args:
        message: Prompt message
        default: Default value (True for yes, False for no)
        allow_cancel: If True, raise SetupCancelled on Ctrl+C

    Returns:
        True for yes, False for no

    Raises:
        SetupCancelled: If allow_cancel=True and user presses Ctrl+C
    """
    if not is_interactive():
        return safe_confirm(message, default=default, allow_cancel=allow_cancel)

    try:
        import questionary

        result = questionary.confirm(message, default=default).ask()

        if result is None:
            if allow_cancel:
                raise SetupCancelled()
            return default

        return result

    except KeyboardInterrupt:
        print()
        if allow_cancel:
            raise SetupCancelled()
        return default
    except ImportError:
        return safe_confirm(message, default=default, allow_cancel=allow_cancel)


def q_checkbox(
    message: str,
    choices: Sequence[Any],
    allow_cancel: bool = False,
) -> list[str]:
    """Interactive checkbox (multi-select) prompt with non-TTY fallback.

    Args:
        message: Prompt message
        choices: List of choices (strings or questionary.Choice objects)
        allow_cancel: If True, raise SetupCancelled on Ctrl+C

    Returns:
        List of selected values

    Raises:
        SetupCancelled: If allow_cancel=True and user presses Ctrl+C
    """
    if not is_interactive():
        return _fallback_checkbox(message, choices)

    try:
        import questionary

        result = questionary.checkbox(
            message,
            choices=choices,
        ).ask()

        if result is None:
            if allow_cancel:
                raise SetupCancelled()
            return []

        return result

    except KeyboardInterrupt:
        print()
        if allow_cancel:
            raise SetupCancelled()
        return []
    except ImportError:
        return _fallback_checkbox(message, choices)
