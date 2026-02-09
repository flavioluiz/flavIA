"""Interactive agent model configuration wizard for flavIA CLI."""

from pathlib import Path
from typing import Any, Optional

import yaml
from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.table import Table

console = Console()


def _resolve_agents_file(settings, base_dir: Optional[Path] = None) -> Path:
    """Resolve the agents.yaml path to manage."""
    if base_dir is not None:
        local_file = base_dir / ".flavia" / "agents.yaml"
        if local_file.exists():
            return local_file

    paths = getattr(settings, "config_paths", None)
    if paths and paths.agents_file:
        return paths.agents_file

    if base_dir is not None:
        return base_dir / ".flavia" / "agents.yaml"
    return Path.cwd() / ".flavia" / "agents.yaml"


def _load_agents_config(agents_file: Path) -> Optional[dict[str, Any]]:
    """Load agent configuration from agents.yaml."""
    if not agents_file.exists():
        return None

    try:
        with open(agents_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception:
        return None

    return data if isinstance(data, dict) else None


def _save_agents_config(agents_file: Path, data: dict[str, Any]) -> bool:
    """Persist agent configuration to file."""
    try:
        agents_file.parent.mkdir(parents=True, exist_ok=True)
        with open(agents_file, "w", encoding="utf-8") as f:
            yaml.dump(
                data,
                f,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
            )
        return True
    except Exception:
        return False


def _collect_agent_targets(config: dict[str, Any], default_model: str) -> list[dict[str, str]]:
    """Collect editable agent/subagent targets."""
    main = config.get("main")
    if not isinstance(main, dict):
        return []

    main_explicit = main.get("model")
    main_effective = str(main_explicit or default_model)
    targets = [
        {
            "label": "main",
            "path": "main",
            "explicit_model": str(main_explicit) if main_explicit else "",
            "effective_model": main_effective,
        }
    ]

    subagents = main.get("subagents")
    if not isinstance(subagents, dict):
        return targets

    for name, sub in subagents.items():
        if not isinstance(sub, dict):
            continue
        explicit = sub.get("model")
        targets.append(
            {
                "label": f"main.{name}",
                "path": f"main.subagents.{name}",
                "explicit_model": str(explicit) if explicit else "",
                "effective_model": str(explicit or main_effective),
            }
        )

    return targets


def _collect_model_options(settings) -> list[dict[str, str]]:
    """Collect selectable model references from providers/models settings."""
    options: list[dict[str, str]] = []

    if settings.providers.providers:
        for provider in settings.providers.providers.values():
            for model in provider.models:
                options.append(
                    {
                        "ref": f"{provider.id}:{model.id}",
                        "name": model.name,
                        "provider": provider.name,
                    }
                )
        return options

    for model in settings.models:
        options.append(
            {
                "ref": model.id,
                "name": model.name,
                "provider": "legacy",
            }
        )

    return options


def _set_model_at_path(config: dict[str, Any], path: str, model_ref: str) -> bool:
    """Set model value in the target path."""
    parts = path.split(".")
    cursor: Any = config
    for part in parts:
        if not isinstance(cursor, dict) or part not in cursor:
            return False
        cursor = cursor[part]

    if not isinstance(cursor, dict):
        return False
    cursor["model"] = model_ref
    return True


def manage_agent_models(settings, base_dir: Optional[Path] = None) -> bool:
    """
    Interactively assign models to agents/subagents in agents.yaml.

    Returns:
        True when at least one change was saved.
    """
    agents_file = _resolve_agents_file(settings, base_dir=base_dir)
    config = _load_agents_config(agents_file)
    if not config:
        console.print(f"[red]Could not load agent config from {agents_file}.[/red]")
        console.print("[yellow]Run 'flavia --init' or '/setup' first.[/yellow]")
        return False

    model_options = _collect_model_options(settings)
    if not model_options:
        console.print("[red]No models available. Configure providers first.[/red]")
        console.print("[yellow]Run 'flavia --setup-provider' to configure providers.[/yellow]")
        return False

    changed = False

    while True:
        targets = _collect_agent_targets(config, settings.default_model)
        if not targets:
            console.print("[red]No editable agents found in agents.yaml.[/red]")
            return changed

        console.print("\n[bold]Agent Model Settings[/bold]")
        table = Table(show_header=False, box=None, padding=(0, 2))
        for i, target in enumerate(targets, 1):
            explicit = target["explicit_model"] if target["explicit_model"] else "(inherit)"
            table.add_row(
                f"  [{i}]",
                target["label"],
                f"[dim]explicit: {explicit}[/dim]",
                f"[cyan]effective: {target['effective_model']}[/cyan]",
            )
        console.print(table)

        selection = Prompt.ask("Select agent/subagent number (or 'q' to exit)", default="q").strip().lower()
        if selection in {"q", "quit", "exit"}:
            return changed

        try:
            target_index = int(selection) - 1
        except ValueError:
            console.print("[yellow]Invalid selection.[/yellow]")
            continue

        if not 0 <= target_index < len(targets):
            console.print("[yellow]Invalid selection.[/yellow]")
            continue

        target = targets[target_index]

        console.print("\n[bold]Available models:[/bold]")
        model_table = Table(show_header=False, box=None, padding=(0, 2))
        for i, option in enumerate(model_options, 1):
            model_table.add_row(
                f"  [{i}]",
                f"{option['provider']} / {option['name']}",
                f"[dim]{option['ref']}[/dim]",
            )
        console.print(model_table)

        current_ref = target["effective_model"]
        default_choice = next(
            (str(i + 1) for i, option in enumerate(model_options) if option["ref"] == current_ref),
            "1",
        )
        model_selection = Prompt.ask("Select model number", default=default_choice).strip().lower()
        if model_selection in {"q", "quit", "exit"}:
            continue

        try:
            model_index = int(model_selection) - 1
        except ValueError:
            console.print("[yellow]Invalid model selection.[/yellow]")
            continue

        if not 0 <= model_index < len(model_options):
            console.print("[yellow]Invalid model selection.[/yellow]")
            continue

        selected_model = model_options[model_index]["ref"]
        if not _set_model_at_path(config, target["path"], selected_model):
            console.print("[red]Could not update selected agent entry.[/red]")
            continue

        if not _save_agents_config(agents_file, config):
            console.print(f"[red]Failed to save {agents_file}.[/red]")
            continue

        changed = True
        console.print(
            f"[green]Updated {target['label']} model to {selected_model} in {agents_file}.[/green]"
        )

        if not Confirm.ask("Edit another agent?", default=False):
            return changed
