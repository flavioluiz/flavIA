"""Safe terminal prompt utilities that avoid Rich's readline conflicts.

Rich's Prompt.ask() and Confirm.ask() use ANSI control sequences that can
break terminal redraw when deleting characters or navigating with arrows.
These utilities use plain input() to avoid such issues.
"""

import getpass
from typing import Optional

from rich.console import Console

console = Console()


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


def safe_prompt_with_style(
    prompt: str,
    default: str = "",
    style: Optional[str] = None,
) -> str:
    """
    Prompt with Rich styling for the prompt text, but safe input handling.

    Prints the styled prompt, then uses plain input() for the actual input.

    Args:
        prompt: The prompt text (can include Rich markup)
        default: Default value if user presses Enter
        style: Optional Rich style to apply

    Returns:
        User input or default value
    """
    # Print the styled prompt without newline
    if default:
        console.print(f"{prompt} ({default}): ", end="", style=style)
    else:
        console.print(f"{prompt}: ", end="", style=style)

    try:
        result = input().strip()
        return result if result else default
    except (EOFError, KeyboardInterrupt):
        print()
        return default


def safe_confirm_with_style(
    prompt: str, default: bool = False, style: Optional[str] = None
) -> bool:
    """
    Confirmation with Rich styling for the prompt text, but safe input handling.

    Args:
        prompt: The prompt text (can include Rich markup)
        default: Default value if user presses Enter
        style: Optional Rich style to apply

    Returns:
        True for yes, False for no
    """
    default_hint = "[Y/n]" if default else "[y/N]"
    console.print(f"{prompt} {default_hint}: ", end="", style=style)

    try:
        result = input().strip().lower()
        if not result:
            return default
        return result in ("y", "yes", "true", "1")
    except (EOFError, KeyboardInterrupt):
        print()
        return default
