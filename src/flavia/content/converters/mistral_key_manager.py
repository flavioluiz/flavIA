"""Centralized management of the MISTRAL_API_KEY.

Provides a single entry point for obtaining the Mistral API key across all
converters (OCR, audio transcription, etc.).  When running in an interactive
context the user is prompted to supply the key and choose where to persist it.
"""

import os
import re
from pathlib import Path
from typing import Optional

from rich.console import Console

from flavia.config.loader import get_config_paths, ensure_user_config

console = Console()

# Environment variable name used everywhere in the project.
_ENV_VAR = "MISTRAL_API_KEY"


def get_mistral_api_key(interactive: bool = True) -> Optional[str]:
    """Obtain the Mistral API key, optionally prompting the user.

    Resolution order:
    1. ``os.environ["MISTRAL_API_KEY"]`` (already loaded by dotenv or shell).
    2. Scan ``.flavia/.env`` in the current directory.
    3. Scan ``~/.config/flavia/.env``.
    4. If *interactive* is True, prompt the user and offer to persist the key.

    Args:
        interactive: When True the user is asked for the key if it cannot be
            found automatically.  Set to False for batch / non-interactive
            contexts.

    Returns:
        The API key string, or ``None`` if unavailable.
    """
    # 1. Already in environment (set by dotenv on startup or by the shell)
    key = os.environ.get(_ENV_VAR, "").strip()
    if key:
        return key

    # 2-3. Explicitly check .env files in case load_dotenv was not called yet
    key = _scan_env_files()
    if key:
        os.environ[_ENV_VAR] = key
        return key

    if not interactive:
        return None

    # 4. Interactive prompt
    return _prompt_for_key()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _scan_env_files() -> Optional[str]:
    """Look for MISTRAL_API_KEY in known .env files without loading them."""
    paths = get_config_paths()
    candidates: list[Path] = []

    if paths.local_dir:
        candidates.append(paths.local_dir / ".env")
    if paths.user_dir:
        candidates.append(paths.user_dir / ".env")

    for env_path in candidates:
        if not env_path.is_file():
            continue
        value = _read_key_from_env_file(env_path)
        if value:
            return value

    return None


def _read_key_from_env_file(env_path: Path) -> Optional[str]:
    """Parse a .env file and return the MISTRAL_API_KEY value if present."""
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            name, _, value = line.partition("=")
            name = name.strip()
            if name == _ENV_VAR:
                value = value.strip().strip("\"'")
                if value:
                    return value
    except OSError:
        pass
    return None


def _prompt_for_key() -> Optional[str]:
    """Interactively ask the user for the Mistral API key."""
    console.print()
    console.print(
        "[yellow]MISTRAL_API_KEY not found.[/yellow] "
        "This key is required for Mistral services (OCR, audio transcription)."
    )
    console.print(
        "You can obtain one at [link=https://console.mistral.ai/]https://console.mistral.ai/[/link]"
    )
    console.print()

    try:
        key = console.input(
            "[bold]Enter your MISTRAL_API_KEY (or press Enter to cancel): [/bold]"
        ).strip()
    except (EOFError, KeyboardInterrupt):
        return None

    if not key:
        return None

    # Set immediately for this session
    os.environ[_ENV_VAR] = key

    # Ask where to save
    _offer_persist(key)

    return key


def _offer_persist(key: str) -> None:
    """Ask the user where to persist the key."""
    console.print()
    console.print("[dim]Where should this key be saved?[/dim]")
    console.print("  [bold]1[/bold] - Local project only  ([cyan].flavia/.env[/cyan])")
    console.print(
        "  [bold]2[/bold] - Global for all projects  ([cyan]~/.config/flavia/.env[/cyan])"
    )
    console.print("  [bold]3[/bold] - Don't save (use only for this session)")
    console.print()

    try:
        choice = console.input("[bold]Choice [1/2/3]: [/bold]").strip()
    except (EOFError, KeyboardInterrupt):
        return

    if choice == "1":
        _save_to_local_env(key)
    elif choice == "2":
        _save_to_global_env(key)
    else:
        console.print("[dim]Key will only be available for this session.[/dim]")


def _save_to_local_env(key: str) -> None:
    """Append the key to .flavia/.env in the current directory."""
    local_dir = Path.cwd() / ".flavia"
    local_dir.mkdir(parents=True, exist_ok=True)
    env_file = local_dir / ".env"
    _append_key_to_env(env_file, key)
    console.print(f"[green]Saved to {env_file}[/green]")


def _save_to_global_env(key: str) -> None:
    """Append the key to ~/.config/flavia/.env."""
    user_dir = ensure_user_config()
    env_file = user_dir / ".env"
    _append_key_to_env(env_file, key)
    console.print(f"[green]Saved to {env_file}[/green]")


def _append_key_to_env(env_file: Path, key: str) -> None:
    """Add or update MISTRAL_API_KEY in a .env file."""
    line_to_add = f"{_ENV_VAR}={key}"

    if env_file.is_file():
        content = env_file.read_text(encoding="utf-8")

        # Replace existing (possibly commented) entry
        pattern = rf"^#?\s*{re.escape(_ENV_VAR)}\s*=.*$"
        if re.search(pattern, content, flags=re.MULTILINE):
            content = re.sub(pattern, line_to_add, content, flags=re.MULTILINE)
            env_file.write_text(content, encoding="utf-8")
            return

        # Append
        if not content.endswith("\n"):
            content += "\n"
        content += f"\n# Mistral API key (OCR, transcription)\n{line_to_add}\n"
        env_file.write_text(content, encoding="utf-8")
    else:
        env_file.write_text(
            f"# flavIA configuration\n\n# Mistral API key (OCR, transcription)\n{line_to_add}\n",
            encoding="utf-8",
        )
