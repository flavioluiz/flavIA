"""Interactive settings menu command for flavIA CLI.

Provides a /settings command that allows users to view and modify
settings interactively, with clear scope indicators (LOCAL/GLOBAL/DEFAULT).
"""

from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from flavia.interfaces.commands import CommandContext, register_command
from flavia.settings.categories import (
    SETTINGS_CATEGORIES,
    SettingDefinition,
    SettingsCategory,
    get_category_by_id,
)
from flavia.settings.persistence import (
    SettingSource,
    get_global_env_path,
    get_local_env_path,
    get_setting_source,
    global_env_exists,
    local_env_exists,
    write_to_env_file,
)
from flavia.settings.validators import (
    ValidationResult,
    format_value_for_env,
    validate_bool,
    validate_choice,
    validate_float,
    validate_int,
    validate_string,
)
from flavia.setup.prompt_utils import (
    SetupCancelled,
    is_interactive,
    q_select,
    safe_confirm,
    safe_prompt,
)


def _mask_value(value: str) -> str:
    """Mask a sensitive value for display."""
    if not value:
        return "(not set)"
    if len(value) <= 8:
        return "*" * len(value)
    return value[:4] + "*" * (len(value) - 8) + value[-4:]


def _format_value_for_display(
    setting: SettingDefinition,
    source: SettingSource,
) -> str:
    """Format a setting value for display."""
    if not source.value:
        return "(not set)"
    if setting.masked:
        return _mask_value(source.value)
    if setting.setting_type == "bool":
        return "true" if source.value.lower() in ("true", "1", "yes", "on") else "false"
    return source.value


def _print_header(console: Console) -> None:
    """Print the settings menu header with scope information."""
    local_exists = local_env_exists()
    global_exists = global_env_exists()

    local_status = "[green]exists[/green]" if local_exists else "[dim]not found[/dim]"
    global_status = "[green]exists[/green]" if global_exists else "[dim]not found[/dim]"

    header = (
        "[bold]flavIA Settings[/bold]\n\n"
        f"Scope: [cyan][LOCAL][/cyan] .flavia/.env ({local_status})\n"
        f"       [cyan][GLOBAL][/cyan] ~/.config/flavia/.env ({global_status})"
    )
    console.print(Panel(header, border_style="cyan"))


def _print_category_settings(
    console: Console,
    category: SettingsCategory,
) -> None:
    """Print settings for a category with current values and origins."""
    table = Table(show_header=True, header_style="bold", box=None)
    table.add_column("Setting", style="cyan", width=25)
    table.add_column("Value", width=30)
    table.add_column("Origin", width=5)

    for setting in category.settings:
        source = get_setting_source(setting.env_var, setting.default)
        value_display = _format_value_for_display(setting, source)
        origin = source.source_indicator

        table.add_row(setting.display_name, value_display, origin)

    console.print(f"\n[bold]{category.name}[/bold]")
    console.print(table)


def _validate_setting_value(
    setting: SettingDefinition,
    value: str,
) -> ValidationResult:
    """Validate a setting value based on its type."""
    if setting.setting_type == "int":
        return validate_int(
            value,
            min_value=int(setting.min_value) if setting.min_value is not None else None,
            max_value=int(setting.max_value) if setting.max_value is not None else None,
        )
    elif setting.setting_type == "float":
        return validate_float(
            value,
            min_value=setting.min_value,
            max_value=setting.max_value,
        )
    elif setting.setting_type == "bool":
        return validate_bool(value)
    elif setting.setting_type == "choice":
        return validate_choice(value, setting.choices or [])
    else:
        return validate_string(value)


def _edit_setting(
    console: Console,
    setting: SettingDefinition,
) -> bool:
    """Interactive flow to edit a single setting.

    Returns True if a change was saved, False otherwise.
    """
    source = get_setting_source(setting.env_var, setting.default)

    console.print(f"\n[bold]{setting.display_name}[/bold]")
    console.print(f"  [dim]{setting.description}[/dim]")
    console.print()
    console.print(f"  Current: {_format_value_for_display(setting, source)} {source.source_indicator}")
    console.print(f"  Default: {setting.default}")

    if setting.min_value is not None and setting.max_value is not None:
        console.print(f"  Range:   {setting.min_value} - {setting.max_value}")
    elif setting.min_value is not None:
        console.print(f"  Min:     {setting.min_value}")
    elif setting.max_value is not None:
        console.print(f"  Max:     {setting.max_value}")

    if setting.choices:
        console.print(f"  Options: {', '.join(setting.choices)}")

    console.print()

    # Get new value
    try:
        if setting.masked:
            new_value = safe_prompt(
                "Enter new value (Enter to keep)",
                default="",
                password=True,
                allow_cancel=True,
            )
        else:
            current = source.value if source.value else ""
            new_value = safe_prompt(
                "Enter new value (Enter to keep)",
                default=current,
                allow_cancel=True,
            )
    except SetupCancelled:
        console.print("[yellow]Cancelled.[/yellow]")
        return False

    # Handle empty input (keep current)
    if not new_value.strip():
        console.print("[dim]No change.[/dim]")
        return False

    # Validate
    result = _validate_setting_value(setting, new_value)
    if not result.valid:
        console.print(f"[red]Error: {result.error}[/red]")
        return False

    # Format for .env file
    env_value = format_value_for_env(result.value, setting.setting_type)

    # Ask where to save
    console.print("\nSave to:")
    console.print("  [1] Local  (.flavia/.env) - only this project")
    console.print("  [2] Global (~/.config/flavia/.env) - all projects")

    try:
        choice = safe_prompt("Choice", default="1", allow_cancel=True)
    except SetupCancelled:
        console.print("[yellow]Cancelled.[/yellow]")
        return False

    if choice == "2":
        target_path = get_global_env_path()
        scope = "GLOBAL"
    else:
        target_path = get_local_env_path()
        scope = "LOCAL"

    # Write to file
    if write_to_env_file(target_path, setting.env_var, env_value):
        console.print(
            f"[green]Saved:[/green] {setting.env_var}={env_value} -> {scope} ({target_path})"
        )
        return True
    else:
        console.print(f"[red]Error: Failed to write to {target_path}[/red]")
        return False


def _category_menu(
    console: Console,
    category: SettingsCategory,
) -> bool:
    """Display and handle the category sub-menu.

    Returns True if any settings were changed.
    """
    changed = False

    while True:
        _print_category_settings(console, category)

        # Build menu options
        console.print("\n[bold]Options:[/bold]")
        for i, setting in enumerate(category.settings, 1):
            console.print(f"  [{i}] Edit {setting.display_name}")
        console.print("  [r] Reset to Defaults")
        console.print("  [b] Back")

        try:
            choice = safe_prompt("\nChoice", default="b", allow_cancel=True).lower()
        except SetupCancelled:
            break

        if choice == "b" or choice == "":
            break
        elif choice == "r":
            if safe_confirm("Reset all settings in this category to defaults?", default=False):
                console.print("[yellow]Reset not yet implemented - remove from .env manually[/yellow]")
        else:
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(category.settings):
                    if _edit_setting(console, category.settings[idx]):
                        changed = True
                else:
                    console.print("[red]Invalid option[/red]")
            except ValueError:
                console.print("[red]Invalid option[/red]")

    return changed


def _main_menu(console: Console) -> bool:
    """Display and handle the main settings menu.

    Returns True if any settings were changed.
    """
    changed = False

    while True:
        _print_header(console)

        # Category selection
        console.print("\n[bold]Categories:[/bold]")
        for i, category in enumerate(SETTINGS_CATEGORIES, 1):
            console.print(f"  [{i}] {category.name}")
        console.print("  [q] Back")

        try:
            choice = safe_prompt("\nChoice", default="q", allow_cancel=True).lower()
        except SetupCancelled:
            break

        if choice == "q" or choice == "":
            break

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(SETTINGS_CATEGORIES):
                if _category_menu(console, SETTINGS_CATEGORIES[idx]):
                    changed = True
            else:
                console.print("[red]Invalid option[/red]")
        except ValueError:
            # Check if it's a category ID shortcut
            category = get_category_by_id(choice)
            if category:
                if _category_menu(console, category):
                    changed = True
            else:
                console.print("[red]Invalid option[/red]")

    return changed


def _quick_category_menu(console: Console, category_arg: str) -> bool:
    """Jump directly to a specific category menu."""
    # Try exact ID match
    category = get_category_by_id(category_arg.lower())

    # Try partial name match
    if not category:
        arg_lower = category_arg.lower()
        for cat in SETTINGS_CATEGORIES:
            if arg_lower in cat.name.lower() or arg_lower in cat.id.lower():
                category = cat
                break

    if not category:
        console.print(f"[red]Unknown category: {category_arg}[/red]")
        console.print("Available categories:")
        for cat in SETTINGS_CATEGORIES:
            console.print(f"  - {cat.id}: {cat.name}")
        return False

    return _category_menu(console, category)


@register_command(
    name="/settings",
    category="Session",
    short_desc="Configure flavIA settings",
    long_desc="Open the interactive settings menu to view and modify flavIA configuration. "
    "Settings are stored in .env files with clear LOCAL/GLOBAL scope indicators. "
    "You can jump directly to a category by name (e.g., /settings rag).",
    usage="/settings [category]",
    examples=[
        "/settings              Open main settings menu",
        "/settings models       Jump to Model Settings",
        "/settings rag          Jump to RAG Parameters",
        "/settings agent        Jump to Agent Parameters",
        "/settings timeouts     Jump to Timeouts & Limits",
    ],
    related=["/config", "/reset"],
    accepts_args=True,
)
def cmd_settings(ctx: CommandContext, args: str) -> bool:
    """Open the interactive settings menu."""
    console = ctx.console

    if args.strip():
        # Jump to specific category
        changed = _quick_category_menu(console, args.strip())
    else:
        # Main menu
        changed = _main_menu(console)

    if changed:
        console.print(
            "\n[dim]Settings saved. Use /reset to apply changes to the current session.[/dim]"
        )

    return True
