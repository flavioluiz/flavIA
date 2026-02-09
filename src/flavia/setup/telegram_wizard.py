"""Interactive Telegram bot configuration wizard for flavIA."""

import os
import re
import sys
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown

from flavia.setup.prompt_utils import safe_confirm, safe_prompt

console = Console()

# Instructions for getting a Telegram bot token
BOTFATHER_INSTRUCTIONS = """
## How to get a Telegram Bot Token

1. Open Telegram and search for **@BotFather**
2. Start a chat and send `/newbot`
3. Follow the prompts:
   - Choose a **name** for your bot (e.g., "My Research Assistant")
   - Choose a **username** ending in `bot` (e.g., "my_research_bot")
4. BotFather will send you a token like:
   `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`
5. Copy and paste this token below

**Important:** Keep your token secret! Anyone with the token can control your bot.
"""

# Instructions for getting Telegram user ID
USERID_INSTRUCTIONS = """
## How to find your Telegram User ID

1. Open Telegram and search for **@userinfobot**
2. Start a chat and send any message
3. The bot will reply with your user ID (a number like `123456789`)
4. Copy this number

You can add multiple user IDs separated by commas to allow multiple users.
"""


def validate_bot_token(token: str) -> bool:
    """Validate Telegram bot token format."""
    # Token format: numbers:alphanumeric (e.g., 123456789:ABCdefGHI...)
    pattern = r"^\d+:[A-Za-z0-9_-]+$"
    return bool(re.match(pattern, token.strip()))


def validate_user_ids(ids_str: str) -> tuple[list[int], list[str]]:
    """
    Validate and parse user IDs string.

    Returns:
        Tuple of (valid_ids, invalid_entries)
    """
    valid = []
    invalid = []

    for part in ids_str.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            user_id = int(part)
            if user_id > 0:
                valid.append(user_id)
            else:
                invalid.append(part)
        except ValueError:
            invalid.append(part)

    return valid, invalid


def test_bot_token(token: str) -> tuple[bool, str]:
    """
    Test if a bot token is valid by calling Telegram API.

    Returns:
        Tuple of (success, message)
    """
    try:
        import httpx

        response = httpx.get(
            f"https://api.telegram.org/bot{token}/getMe",
            timeout=10.0,
        )

        data = response.json()

        if data.get("ok"):
            bot_info = data.get("result", {})
            username = bot_info.get("username", "unknown")
            name = bot_info.get("first_name", "Bot")
            return True, f"Connected to @{username} ({name})"
        else:
            error = data.get("description", "Unknown error")
            return False, f"Invalid token: {error}"

    except Exception as e:
        # Avoid echoing bot token if it appears in transport errors.
        return False, f"Connection error: {str(e).replace(token, '***')}"


def _get_config_file_path(location: str, target_dir: Optional[Path] = None) -> Path:
    """Get the path to the .env file based on location preference."""
    if location == "global":
        config_dir = Path.home() / ".config" / "flavia"
        config_dir.mkdir(parents=True, exist_ok=True)
    else:
        base_dir = target_dir if target_dir is not None else Path.cwd()
        config_dir = base_dir / ".flavia"
        config_dir.mkdir(parents=True, exist_ok=True)

    return config_dir / ".env"


def _update_env_file(env_path: Path, updates: dict[str, Optional[str]]) -> None:
    """
    Update .env file with new values.

    Args:
        env_path: Path to .env file
        updates: Dict of key -> value (None to comment out/remove)
    """
    existing_lines = []
    if env_path.exists():
        existing_lines = env_path.read_text().splitlines()

    # Track which keys we've updated
    updated_keys = set()
    new_lines = []

    for line in existing_lines:
        stripped = line.strip()

        # Check if this line sets one of our keys
        matched_key = None
        for key in updates:
            if stripped.startswith(f"{key}=") or stripped.startswith(f"# {key}="):
                matched_key = key
                break

        if matched_key:
            value = updates[matched_key]
            if value is not None:
                new_lines.append(f"{matched_key}={value}")
            else:
                # Comment out the line
                if not stripped.startswith("#"):
                    new_lines.append(f"# {line}")
                else:
                    new_lines.append(line)
            updated_keys.add(matched_key)
        else:
            new_lines.append(line)

    # Add any new keys that weren't in the file
    for key, value in updates.items():
        if key not in updated_keys and value is not None:
            # Add a blank line before new telegram config if needed
            if new_lines and not new_lines[-1].strip().startswith("#") and new_lines[-1].strip():
                new_lines.append("")
            if key == "TELEGRAM_BOT_TOKEN" and not any("Telegram" in l for l in new_lines):
                new_lines.append("# Telegram bot configuration")
            new_lines.append(f"{key}={value}")

    env_path.write_text("\n".join(new_lines) + "\n")


def run_telegram_wizard(target_dir: Optional[Path] = None) -> bool:
    """
    Run the interactive Telegram bot configuration wizard.

    Args:
        target_dir: Target directory for local config (default: current directory)

    Returns:
        True if configuration was saved successfully
    """
    if not sys.stdin.isatty():
        console.print(
            "[yellow]Interactive Telegram setup requires a TTY.[/yellow]\n"
            "[dim]Run 'flavia --setup-telegram' in an interactive terminal.[/dim]"
        )
        return False

    if target_dir is None:
        target_dir = Path.cwd()

    console.print(
        Panel.fit(
            "[bold blue]Telegram Bot Configuration[/bold blue]\n\n"
            "[dim]Set up flavIA as a Telegram bot[/dim]",
            title="Setup",
        )
    )

    # Show instructions for getting token
    console.print(Markdown(BOTFATHER_INSTRUCTIONS))

    # Get bot token
    while True:
        console.print("\n[bold]Bot Token[/bold]")
        token = safe_prompt("Enter token", password=True)

        if not token:
            if safe_confirm("Cancel Telegram setup?", default=False):
                return False
            continue

        if not validate_bot_token(token):
            console.print("[red]Invalid token format.[/red]")
            console.print("[dim]Token should look like: 123456789:ABCdefGHIjklMNO...[/dim]")
            continue

        # Test the token
        console.print("[dim]Testing token...[/dim]")
        success, message = test_bot_token(token)

        if success:
            console.print(f"[green]{message}[/green]")
            break
        else:
            console.print(f"[red]{message}[/red]")
            if not safe_confirm("Try a different token?", default=True):
                return False

    # Ask about access control
    console.print("\n[bold]Access Control[/bold]")
    console.print(
        "[dim]You can restrict who can use your bot by specifying Telegram user IDs.[/dim]"
    )

    restrict_access = safe_confirm(
        "Restrict access to specific users?",
        default=True,
    )

    user_ids: list[int] = []
    allow_all = False

    if restrict_access:
        console.print(Markdown(USERID_INSTRUCTIONS))

        while True:
            console.print("\n[bold]User IDs[/bold] (comma-separated)")
            ids_input = safe_prompt("Enter user IDs", default="")

            if not ids_input.strip():
                console.print("[yellow]No user IDs provided.[/yellow]")
                if safe_confirm("Leave access unrestricted?", default=False):
                    allow_all = True
                    break
                continue

            valid_ids, invalid_entries = validate_user_ids(ids_input)

            if invalid_entries:
                console.print(f"[red]Invalid entries: {', '.join(invalid_entries)}[/red]")
                console.print("[dim]User IDs should be numbers only.[/dim]")

            if valid_ids:
                user_ids = valid_ids
                console.print(f"[green]Will allow {len(user_ids)} user(s): {', '.join(map(str, user_ids))}[/green]")
                break
            else:
                console.print("[yellow]No valid user IDs entered.[/yellow]")
    else:
        allow_all = True

    # Warning for public access
    if allow_all:
        console.print(
            Panel(
                "[bold yellow]Warning: Public Access[/bold yellow]\n\n"
                "Your bot will be accessible by [bold]anyone[/bold] who finds it on Telegram.\n"
                "Anyone can search for your bot by its username and start chatting.\n\n"
                "This may:\n"
                "- Use your API credits\n"
                "- Expose your documents to strangers\n"
                "- Allow spam or abuse\n\n"
                "[dim]Consider adding user restrictions later via .env file.[/dim]",
                title="Security Notice",
                border_style="yellow",
            )
        )

        console.print("[bold]Confirm public access?[/bold]")
        if not safe_confirm("Allow public access?", default=False):
            console.print("[yellow]Setup cancelled.[/yellow]")
            return False

    # Select save location
    console.print("\n[bold]Where to save configuration?[/bold]")
    console.print("  [1] Local (.flavia/.env) - Project-specific")
    console.print("  [2] Global (~/.config/flavia/.env) - User-wide")

    choice = safe_prompt("Enter number", default="1")
    location = "global" if choice == "2" else "local"

    # Prepare updates
    updates: dict[str, Optional[str]] = {
        "TELEGRAM_BOT_TOKEN": token,
    }

    if user_ids:
        updates["TELEGRAM_ALLOWED_USER_IDS"] = ",".join(map(str, user_ids))
        updates["TELEGRAM_ALLOW_ALL_USERS"] = None  # Comment out if present
    elif allow_all:
        updates["TELEGRAM_ALLOW_ALL_USERS"] = "true"
        updates["TELEGRAM_ALLOWED_USER_IDS"] = None  # Comment out if present

    # Save configuration
    env_path = _get_config_file_path(location, target_dir)
    _update_env_file(env_path, updates)

    console.print(
        Panel.fit(
            "[bold green]Telegram bot configured![/bold green]\n\n"
            f"Saved to: [cyan]{env_path}[/cyan]\n\n"
            f"Access: {'Restricted to ' + str(len(user_ids)) + ' user(s)' if user_ids else '[yellow]Public[/yellow]'}\n\n"
            "[bold]To start the bot:[/bold]\n"
            "  flavia --telegram",
            title="Success",
        )
    )

    return True


def check_telegram_config() -> tuple[bool, Optional[str], Optional[str]]:
    """
    Check if Telegram is properly configured.

    Returns:
        Tuple of (is_configured, token, error_message)
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")

    if not token:
        return False, None, "TELEGRAM_BOT_TOKEN not set"

    if not validate_bot_token(token):
        return False, None, "TELEGRAM_BOT_TOKEN has invalid format"

    return True, token, None


def prompt_telegram_setup_if_needed(target_dir: Optional[Path] = None) -> bool:
    """
    Check Telegram config and prompt for setup if needed.

    Returns:
        True if configured (existing or newly set up), False if user declined
    """
    is_configured, token, error = check_telegram_config()

    if is_configured:
        return True

    console.print(
        Panel(
            f"[bold yellow]Telegram not configured[/bold yellow]\n\n"
            f"[dim]Reason: {error}[/dim]\n\n"
            "The Telegram bot requires a bot token from @BotFather.",
            title="Configuration Required",
            border_style="yellow",
        )
    )

    if not sys.stdin.isatty():
        console.print(
            "\n[yellow]Interactive setup unavailable (stdin is not interactive).[/yellow]\n"
            "[dim]Run flavia --setup-telegram in an interactive terminal.[/dim]"
        )
        return False

    console.print("\n[bold]Set up Telegram bot now?[/bold]")
    should_setup = safe_confirm("Set up now?", default=True)

    if should_setup:
        return run_telegram_wizard(target_dir)

    console.print(
        "\n[dim]To configure later, run:[/dim]\n"
        "  flavia --setup-telegram\n\n"
        "[dim]Or manually add to .flavia/.env:[/dim]\n"
        "  TELEGRAM_BOT_TOKEN=your_token_here"
    )
    return False
