"""Provider configuration wizard for flavIA."""

import os
from pathlib import Path
from typing import Optional, List

import yaml
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt, IntPrompt
from rich.table import Table

console = Console()


# Known provider templates
KNOWN_PROVIDERS = {
    "synthetic": {
        "name": "synthetic",
        "endpoint": "https://api.synthetic.new/openai/v1",
        "api_key_env": "SYNTHETIC_API_KEY",
        "description": "Synthetic.new - Free hosted models",
    },
    "openai": {
        "name": "openai",
        "endpoint": "https://api.openai.com/v1",
        "api_key_env": "OPENAI_API_KEY",
        "description": "OpenAI - Commercial GPT models",
    },
    "openrouter": {
        "name": "openrouter",
        "endpoint": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "description": "OpenRouter - Multi-provider aggregator",
    },
}


PROVIDER_MODEL_TEMPLATES = {
    "openai": [
        {"id": "gpt-4o", "name": "GPT-4o", "description": "Most capable model", "max_tokens": 128000},
        {"id": "gpt-4o-mini", "name": "GPT-4o-mini", "description": "Faster and cheaper", "max_tokens": 128000},
        {"id": "gpt-4-turbo", "name": "GPT-4 Turbo", "max_tokens": 128000},
        {"id": "gpt-3.5-turbo", "name": "GPT-3.5 Turbo", "max_tokens": 16385},
    ],
    "openrouter": [
        {"id": "anthropic/claude-3.5-sonnet", "name": "Claude 3.5 Sonnet", "max_tokens": 200000},
        {"id": "openai/gpt-4o", "name": "GPT-4o", "max_tokens": 128000},
        {"id": "google/gemini-pro-1.5", "name": "Gemini Pro 1.5", "max_tokens": 1000000},
    ],
    "synthetic": [
        {"id": "hf:moonshotai/Kimi-K2.5", "name": "Kimi-K2.5", "max_tokens": 8192},
        {"id": "hf:zai-org/GLM-4.7", "name": "GLM-4.7", "max_tokens": 8192},
        {"id": "hf:MiniMaxAI/MiniMax-M2.1", "name": "MiniMax-M2.1", "max_tokens": 8192},
    ],
}


def get_target_config_dir(is_global: bool) -> Path:
    """Get the target configuration directory."""
    if is_global:
        user_dir = Path.home() / ".config" / "flavia"
        user_dir.mkdir(parents=True, exist_ok=True)
        return user_dir
    else:
        local_dir = Path.cwd() / ".flavia"
        if not local_dir.exists():
            console.print("[yellow]Note:[/yellow] Local .flavia/ directory doesn't exist yet.")
            if Confirm.ask("Create it now?", default=True):
                local_dir.mkdir(parents=True)
            else:
                console.print("[red]Cannot save to local directory.[/red]")
                return None
        return local_dir


def load_existing_providers(config_dir: Path) -> dict:
    """Load existing providers.yaml if it exists."""
    providers_file = config_dir / "providers.yaml"
    if providers_file.exists():
        try:
            with open(providers_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                return data if data else {"providers": []}
        except Exception:
            pass
    return {"providers": []}


def save_providers(config_dir: Path, providers_data: dict) -> bool:
    """Save providers configuration."""
    providers_file = config_dir / "providers.yaml"
    try:
        with open(providers_file, "w", encoding="utf-8") as f:
            yaml.safe_dump(providers_data, f, default_flow_style=False, sort_keys=False)
        console.print(f"\n[green]✓[/green] Configuration saved to [cyan]{providers_file}[/cyan]")
        return True
    except Exception as e:
        console.print(f"[red]Error saving configuration: {e}[/red]")
        return False


def configure_known_provider(provider_key: str) -> dict:
    """Configure a known provider interactively."""
    template = KNOWN_PROVIDERS[provider_key]
    
    console.print(f"\n[bold]Configuring {template['name']}[/bold]")
    console.print(f"[dim]{template['description']}[/dim]\n")
    
    # API key configuration
    api_key_env = template.get("api_key_env")
    if api_key_env:
        console.print(f"This provider uses the [cyan]{api_key_env}[/cyan] environment variable.")
        
        # Check if the env var is already set
        current_value = os.getenv(api_key_env)
        if current_value:
            console.print(f"[green]✓[/green] {api_key_env} is already set")
        else:
            console.print(f"[yellow]![/yellow] {api_key_env} is not set")
            console.print(f"\nAdd this to your .env file:")
            console.print(f"[cyan]{api_key_env}=your_api_key_here[/cyan]\n")
    
    # Model selection
    models_data = []
    if provider_key in PROVIDER_MODEL_TEMPLATES:
        console.print("\n[bold]Available models:[/bold]")
        templates = PROVIDER_MODEL_TEMPLATES[provider_key]
        
        table = Table(show_header=True, box=None, padding=(0, 2))
        table.add_column("#", style="dim")
        table.add_column("Model ID", style="cyan")
        table.add_column("Name")
        
        for idx, model in enumerate(templates):
            table.add_row(str(idx + 1), model["id"], model.get("name", model["id"]))
        
        console.print(table)
        
        if Confirm.ask("\nAdd all models?", default=True):
            models_data = templates
        else:
            console.print("\n[dim]Enter model numbers to add (comma-separated), or 'all':[/dim]")
            selection = Prompt.ask("Models")
            
            if selection.strip().lower() == "all":
                models_data = templates
            else:
                try:
                    indices = [int(x.strip()) - 1 for x in selection.split(",")]
                    models_data = [templates[i] for i in indices if 0 <= i < len(templates)]
                except (ValueError, IndexError):
                    console.print("[yellow]Invalid selection, adding all models[/yellow]")
                    models_data = templates
    
    # Set default model
    if models_data:
        console.print("\n[bold]Which model should be default?[/bold]")
        for idx, model in enumerate(models_data):
            console.print(f"  {idx + 1}. {model.get('name', model['id'])}")
        
        try:
            default_idx = IntPrompt.ask("Default model number", default=1) - 1
            if 0 <= default_idx < len(models_data):
                for i, m in enumerate(models_data):
                    m["default"] = (i == default_idx)
        except (ValueError, KeyboardInterrupt):
            if models_data:
                models_data[0]["default"] = True
    
    # Build provider config
    provider_config = {
        "name": template["name"],
        "endpoint": template["endpoint"],
    }
    
    if api_key_env:
        provider_config["api_key_env"] = api_key_env
    
    if models_data:
        provider_config["models"] = models_data
    
    return provider_config


def configure_custom_provider() -> Optional[dict]:
    """Configure a custom provider interactively."""
    console.print("\n[bold]Configure Custom Provider[/bold]\n")
    
    name = Prompt.ask("Provider name", default="custom")
    endpoint = Prompt.ask("API endpoint", default="https://api.example.com/v1")
    
    # API key configuration
    console.print("\n[bold]How should the API key be provided?[/bold]")
    console.print("  1. Environment variable (recommended)")
    console.print("  2. Direct value (stored in file)")
    
    key_method = Prompt.ask("Method", choices=["1", "2"], default="1")
    
    provider_config = {
        "name": name,
        "endpoint": endpoint,
    }
    
    if key_method == "1":
        env_var = Prompt.ask("Environment variable name", default=f"{name.upper()}_API_KEY")
        provider_config["api_key_env"] = env_var
    else:
        api_key = Prompt.ask("API key")
        provider_config["api_key"] = api_key
    
    # Models
    console.print("\n[bold]Add models:[/bold]")
    models_data = []
    
    while True:
        model_id = Prompt.ask("\nModel ID (or press Enter to finish)", default="")
        if not model_id:
            break
        
        model_name = Prompt.ask("Model name", default=model_id)
        description = Prompt.ask("Description (optional)", default="")
        
        try:
            max_tokens_str = Prompt.ask("Max tokens (optional)", default="")
            max_tokens = int(max_tokens_str) if max_tokens_str else None
        except ValueError:
            max_tokens = None
        
        model_config = {
            "id": model_id,
            "name": model_name,
        }
        
        if description:
            model_config["description"] = description
        if max_tokens:
            model_config["max_tokens"] = max_tokens
        
        models_data.append(model_config)
        
        if not Confirm.ask("Add another model?", default=False):
            break
    
    if models_data:
        # Set first model as default
        models_data[0]["default"] = True
        provider_config["models"] = models_data
    
    return provider_config


def list_existing_providers(providers_data: dict):
    """Display existing providers."""
    if not providers_data.get("providers"):
        console.print("[dim]No providers configured yet.[/dim]")
        return
    
    console.print("\n[bold]Currently configured providers:[/bold]")
    table = Table(show_header=True)
    table.add_column("Provider", style="cyan")
    table.add_column("Endpoint")
    table.add_column("Models", style="dim")
    
    for provider in providers_data["providers"]:
        models_count = len(provider.get("models", []))
        table.add_row(
            provider["name"],
            provider["endpoint"],
            f"{models_count} model(s)"
        )
    
    console.print(table)


def run_provider_wizard() -> bool:
    """
    Run the interactive provider configuration wizard.
    
    Returns:
        True if successful
    """
    console.print(Panel.fit(
        "[bold blue]Provider Configuration Wizard[/bold blue]\n\n"
        "[dim]Configure LLM providers and models for flavIA[/dim]",
        title="Welcome",
    ))
    
    # Ask where to save
    console.print("\n[bold]Where should this configuration be saved?[/bold]")
    console.print("  1. [cyan]Local[/cyan] - Current project only (.flavia/)")
    console.print("  2. [cyan]Global[/cyan] - All projects (~/.config/flavia/)")
    
    scope = Prompt.ask("Scope", choices=["1", "2"], default="1")
    is_global = (scope == "2")
    
    # Get target directory
    config_dir = get_target_config_dir(is_global)
    if not config_dir:
        return False
    
    # Load existing configuration
    providers_data = load_existing_providers(config_dir)
    
    # Show existing providers
    list_existing_providers(providers_data)
    
    # Main menu
    while True:
        console.print("\n[bold]What would you like to do?[/bold]")
        console.print("  1. Add a known provider (Synthetic, OpenAI, OpenRouter)")
        console.print("  2. Add a custom provider")
        console.print("  3. Remove a provider")
        console.print("  4. View configuration")
        console.print("  5. Save and exit")
        console.print("  6. Cancel without saving")
        
        choice = Prompt.ask("Choice", choices=["1", "2", "3", "4", "5", "6"], default="1")
        
        if choice == "1":
            # Add known provider
            console.print("\n[bold]Select provider:[/bold]")
            console.print("  1. Synthetic.new (free hosted models)")
            console.print("  2. OpenAI (commercial)")
            console.print("  3. OpenRouter (multi-provider)")
            
            provider_choice = Prompt.ask("Provider", choices=["1", "2", "3"], default="1")
            provider_keys = ["synthetic", "openai", "openrouter"]
            provider_key = provider_keys[int(provider_choice) - 1]
            
            provider_config = configure_known_provider(provider_key)
            
            # Check if provider already exists
            existing_names = [p["name"] for p in providers_data.get("providers", [])]
            if provider_config["name"] in existing_names:
                if Confirm.ask(f"\n[yellow]Provider '{provider_config['name']}' already exists. Replace?[/yellow]", default=False):
                    # Remove old one
                    providers_data["providers"] = [
                        p for p in providers_data["providers"]
                        if p["name"] != provider_config["name"]
                    ]
                else:
                    continue
            
            providers_data.setdefault("providers", []).append(provider_config)
            console.print(f"[green]✓[/green] Added provider: {provider_config['name']}")
        
        elif choice == "2":
            # Add custom provider
            provider_config = configure_custom_provider()
            if provider_config:
                providers_data.setdefault("providers", []).append(provider_config)
                console.print(f"[green]✓[/green] Added provider: {provider_config['name']}")
        
        elif choice == "3":
            # Remove provider
            if not providers_data.get("providers"):
                console.print("[yellow]No providers to remove[/yellow]")
                continue
            
            console.print("\n[bold]Select provider to remove:[/bold]")
            for idx, p in enumerate(providers_data["providers"]):
                console.print(f"  {idx + 1}. {p['name']}")
            
            try:
                remove_idx = IntPrompt.ask("Provider number") - 1
                if 0 <= remove_idx < len(providers_data["providers"]):
                    removed = providers_data["providers"].pop(remove_idx)
                    console.print(f"[green]✓[/green] Removed provider: {removed['name']}")
            except (ValueError, KeyboardInterrupt):
                continue
        
        elif choice == "4":
            # View configuration
            list_existing_providers(providers_data)
        
        elif choice == "5":
            # Save and exit
            if save_providers(config_dir, providers_data):
                console.print("\n[bold green]Configuration saved successfully![/bold green]")
                return True
            return False
        
        elif choice == "6":
            # Cancel
            if Confirm.ask("\n[yellow]Discard changes?[/yellow]", default=False):
                console.print("[yellow]Configuration not saved[/yellow]")
                return False
    
    return False
