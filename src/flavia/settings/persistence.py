"""Settings persistence with .env file management and origin tracking.

This module handles reading and writing settings to .env files,
tracking the origin of each setting value (local, global, env, or default).
"""

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Optional


SettingSourceType = Literal["local", "global", "env", "default"]


@dataclass
class SettingSource:
    """Origin information for a setting value."""

    value: str
    source: SettingSourceType
    path: Optional[Path] = None

    @property
    def source_indicator(self) -> str:
        """Return short indicator for display: [L], [G], [E], or [D]."""
        indicators = {
            "local": "[L]",
            "global": "[G]",
            "env": "[E]",
            "default": "[D]",
        }
        return indicators.get(self.source, "[?]")


def get_local_env_path() -> Path:
    """Get the local .env file path (.flavia/.env in current directory)."""
    return Path.cwd() / ".flavia" / ".env"


def get_global_env_path() -> Path:
    """Get the global .env file path (~/.config/flavia/.env)."""
    return Path.home() / ".config" / "flavia" / ".env"


def _read_env_file(env_path: Path) -> dict[str, str]:
    """Read key-value pairs from a .env file.

    Args:
        env_path: Path to the .env file.

    Returns:
        Dictionary of environment variable names to values.
    """
    result: dict[str, str] = {}
    if not env_path.exists():
        return result

    try:
        content = env_path.read_text(encoding="utf-8")
    except OSError:
        return result

    for line in content.splitlines():
        line = line.strip()
        # Skip empty lines and comments
        if not line or line.startswith("#"):
            continue

        # Parse KEY=value format
        match = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)=(.*)$', line)
        if match:
            key = match.group(1)
            value = match.group(2)
            # Remove surrounding quotes if present
            if (value.startswith('"') and value.endswith('"')) or \
               (value.startswith("'") and value.endswith("'")):
                value = value[1:-1]
            result[key] = value

    return result


def get_setting_source(env_var: str, default: Any) -> SettingSource:
    """Determine where a setting value comes from.

    Checks in order of priority:
    1. Environment variable (including loaded from .env by dotenv)
    2. Local .env file (.flavia/.env)
    3. Global .env file (~/.config/flavia/.env)
    4. Default value

    Args:
        env_var: The environment variable name.
        default: The default value if not found anywhere.

    Returns:
        SettingSource with the value and its origin.
    """
    local_path = get_local_env_path()
    global_path = get_global_env_path()

    # Read both .env files
    local_vars = _read_env_file(local_path)
    global_vars = _read_env_file(global_path)

    # Check if value is in local .env
    if env_var in local_vars:
        return SettingSource(
            value=local_vars[env_var],
            source="local",
            path=local_path,
        )

    # Check if value is in global .env
    if env_var in global_vars:
        return SettingSource(
            value=global_vars[env_var],
            source="global",
            path=global_path,
        )

    # Check if value is in environment (could be from shell, not from .env files)
    env_value = os.getenv(env_var)
    if env_value is not None:
        return SettingSource(
            value=env_value,
            source="env",
            path=None,
        )

    # Fall back to default
    return SettingSource(
        value=str(default) if default is not None else "",
        source="default",
        path=None,
    )


def write_to_env_file(env_file: Path, env_var: str, value: str) -> bool:
    """Write or update an environment variable in a .env file.

    If the variable already exists, it will be updated in place.
    If it doesn't exist, it will be appended to the file.
    Creates the file and parent directories if they don't exist.

    Args:
        env_file: Path to the .env file.
        env_var: The environment variable name.
        value: The value to set.

    Returns:
        True if successful, False otherwise.
    """
    try:
        # Ensure parent directory exists
        env_file.parent.mkdir(parents=True, exist_ok=True)

        # Read existing content if file exists
        if env_file.exists():
            content = env_file.read_text(encoding="utf-8")
        else:
            content = ""

        # Prepare the new line
        # Quote the value if it contains spaces or special characters
        if " " in value or "'" in value or '"' in value or "=" in value:
            # Use double quotes, escaping any internal double quotes
            escaped_value = value.replace('"', '\\"')
            new_line = f'{env_var}="{escaped_value}"'
        else:
            new_line = f"{env_var}={value}"

        # Check if variable already exists
        pattern = re.compile(
            rf'^(\s*#?\s*)?{re.escape(env_var)}\s*=.*$',
            re.MULTILINE
        )

        if pattern.search(content):
            # Update existing line (also uncomments if commented)
            content = pattern.sub(new_line, content)
        else:
            # Append new line
            if content and not content.endswith("\n"):
                content += "\n"
            content += new_line + "\n"

        # Write back to file
        env_file.write_text(content, encoding="utf-8")
        return True

    except OSError:
        return False


def remove_from_env_file(env_file: Path, env_var: str) -> bool:
    """Remove an environment variable from a .env file.

    Args:
        env_file: Path to the .env file.
        env_var: The environment variable name to remove.

    Returns:
        True if successful (or variable didn't exist), False on error.
    """
    if not env_file.exists():
        return True

    try:
        content = env_file.read_text(encoding="utf-8")

        # Remove the line containing the variable
        pattern = re.compile(
            rf'^{re.escape(env_var)}\s*=.*\n?',
            re.MULTILINE
        )
        new_content = pattern.sub("", content)

        env_file.write_text(new_content, encoding="utf-8")
        return True

    except OSError:
        return False


def local_env_exists() -> bool:
    """Check if local .env file exists."""
    return get_local_env_path().exists()


def global_env_exists() -> bool:
    """Check if global .env file exists."""
    return get_global_env_path().exists()


def ensure_global_config_dir() -> Path:
    """Ensure global config directory exists and return its path."""
    global_dir = Path.home() / ".config" / "flavia"
    global_dir.mkdir(parents=True, exist_ok=True)
    return global_dir
