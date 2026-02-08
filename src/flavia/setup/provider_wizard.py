"""Interactive provider configuration wizard for flavIA."""

import os
from pathlib import Path
from typing import Optional

import yaml
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from flavia.config.loader import ensure_user_config
from flavia.config.providers import (
    ProviderConfig,
    ModelConfig,
    expand_env_vars,
    load_providers_from_file,
)

console = Console()

# Known provider templates
KNOWN_PROVIDERS = {
    "synthetic": {
        "name": "Synthetic",
        "api_base_url": "https://api.synthetic.new/openai/v1",
        "api_key_env": "SYNTHETIC_API_KEY",
        "models": [
            {"id": "hf:moonshotai/Kimi-K2.5", "name": "Kimi-K2.5", "default": True},
            {"id": "hf:zai-org/GLM-4.7", "name": "GLM-4.7"},
            {"id": "hf:MiniMaxAI/MiniMax-M2.1", "name": "MiniMax-M2.1"},
            {"id": "hf:moonshotai/Kimi-K2-Thinking", "name": "Kimi-K2-Thinking"},
        ],
    },
    "openai": {
        "name": "OpenAI",
        "api_base_url": "https://api.openai.com/v1",
        "api_key_env": "OPENAI_API_KEY",
        "models": [
            {"id": "gpt-4o", "name": "GPT-4o", "default": True},
            {"id": "gpt-4o-mini", "name": "GPT-4o Mini"},
            {"id": "gpt-4-turbo", "name": "GPT-4 Turbo"},
        ],
    },
    "openrouter": {
        "name": "OpenRouter",
        "api_base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "headers": {
            "HTTP-Referer": "${OPENROUTER_SITE_URL}",
            "X-Title": "${OPENROUTER_APP_NAME}",
        },
        "models": [
            {"id": "anthropic/claude-3.5-sonnet", "name": "Claude 3.5 Sonnet", "default": True},
            {"id": "anthropic/claude-3-opus", "name": "Claude 3 Opus"},
            {"id": "google/gemini-pro-1.5", "name": "Gemini Pro 1.5"},
        ],
    },
    "anthropic": {
        "name": "Anthropic",
        "api_base_url": "https://api.anthropic.com/v1",
        "api_key_env": "ANTHROPIC_API_KEY",
        "models": [
            {"id": "claude-3-5-sonnet-20241022", "name": "Claude 3.5 Sonnet", "default": True},
            {"id": "claude-3-opus-20240229", "name": "Claude 3 Opus"},
        ],
    },
}


def test_provider_connection(
    api_key: str,
    api_base_url: str,
    model_id: str,
    headers: Optional[dict[str, str]] = None,
) -> tuple[bool, str]:
    """
    Test connection to a provider.

    Args:
        api_key: API key to use
        api_base_url: Base URL of the API
        model_id: Model ID to test with
        headers: Optional custom headers

    Returns:
        Tuple of (success, message)
    """
    try:
        import httpx
        from openai import OpenAI

        kwargs: dict = {
            "api_key": api_key,
            "base_url": api_base_url,
        }
        if headers:
            kwargs["default_headers"] = headers

        try:
            client = OpenAI(**kwargs)
        except TypeError as exc:
            if "unexpected keyword argument 'proxies'" not in str(exc):
                raise
            # Compatibility fallback for environments where OpenAI SDK and httpx versions mismatch.
            http_kwargs = {k: v for k, v in kwargs.items() if k != "default_headers"}
            client = OpenAI(**http_kwargs, http_client=httpx.Client())

        # Try a simple completion
        response = client.chat.completions.create(
            model=model_id,
            messages=[{"role": "user", "content": "Say 'test' in one word."}],
            max_tokens=10,
        )

        if response.choices:
            content = response.choices[0].message.content
            if content:
                return True, f"Connection successful! Response: {content.strip()}"
            return True, "Connection successful (empty response)"
        return False, "No response received"

    except Exception as e:
        return False, f"Connection failed: {e}"


def _select_provider_type() -> Optional[str]:
    """Ask user to select a provider type."""
    console.print("\n[bold]Select a provider:[/bold]")

    table = Table(show_header=False, box=None, padding=(0, 2))
    providers = list(KNOWN_PROVIDERS.keys()) + ["custom"]
    for i, provider_id in enumerate(providers, 1):
        if provider_id == "custom":
            name = "Custom Provider"
            desc = "Configure a custom OpenAI-compatible provider"
        else:
            name = KNOWN_PROVIDERS[provider_id]["name"]
            desc = KNOWN_PROVIDERS[provider_id]["api_base_url"]
        table.add_row(f"  [{i}]", f"[bold]{name}[/bold]", f"[dim]{desc}[/dim]")
    console.print(table)

    choice = Prompt.ask(
        "\nEnter number",
        default="1",
    )

    try:
        index = int(choice) - 1
        if 0 <= index < len(providers):
            return providers[index]
    except ValueError:
        pass

    console.print("[red]Invalid choice[/red]")
    return None


def _get_api_key(provider_name: str, env_var: str) -> tuple[str, str]:
    """
    Get API key from user.

    Returns:
        Tuple of (api_key_value, api_key_config_string)
        The config string is either the literal value or ${ENV_VAR}
    """
    # Check if env var is already set
    existing = os.getenv(env_var, "")

    if existing:
        console.print(f"\n[green]Found existing {env_var} in environment[/green]")
        if Confirm.ask(f"Use existing {env_var}?", default=True):
            return existing, f"${{{env_var}}}"

    console.print(f"\n[bold]API Key for {provider_name}[/bold]")
    console.print(f"[dim]You can enter the key directly or use ${{{env_var}}} syntax[/dim]")

    key_input = Prompt.ask("API Key", password=True)

    if key_input.startswith("${") and key_input.endswith("}"):
        # Environment variable reference
        resolved, _ = expand_env_vars(key_input)
        return resolved, key_input
    else:
        # Direct value - suggest using env var
        console.print(f"\n[yellow]Tip: Set {env_var}={key_input[:8]}... in your shell[/yellow]")
        console.print(f"[dim]Then use ${{{env_var}}} in config to avoid storing secrets[/dim]")

        if Confirm.ask(f"Store as ${{{env_var}}} reference instead?", default=True):
            return key_input, f"${{{env_var}}}"

        return key_input, key_input


def _select_models(available_models: list[dict]) -> list[dict]:
    """Let user select which models to enable."""
    console.print("\n[bold]Select models to enable:[/bold]")

    table = Table(show_header=False, box=None, padding=(0, 2))
    for i, model in enumerate(available_models, 1):
        default_marker = " [default]" if model.get("default") else ""
        table.add_row(f"  [{i}]", f"{model['name']}{default_marker}", f"[dim]{model['id']}[/dim]")
    console.print(table)
    console.print("  [a] All models")

    choice = Prompt.ask(
        "\nEnter numbers separated by comma (e.g., 1,2,3) or 'a' for all",
        default="a",
    )

    if choice.lower() == "a":
        return available_models

    selected = []
    for part in choice.split(","):
        try:
            index = int(part.strip()) - 1
            if 0 <= index < len(available_models):
                selected.append(available_models[index])
        except ValueError:
            continue

    return selected if selected else available_models


def _select_location() -> str:
    """Ask user where to save the configuration."""
    console.print("\n[bold]Where to save provider configuration?[/bold]")
    console.print("  [1] Local (.flavia/providers.yaml) - Project-specific")
    console.print("  [2] Global (~/.config/flavia/providers.yaml) - User-wide")

    choice = Prompt.ask("Enter number", default="1")

    if choice == "2":
        return "global"
    return "local"


def _build_provider_config(
    provider_id: str,
    provider_name: str,
    api_base_url: str,
    api_key_config: str,
    models: list[dict],
    headers: Optional[dict[str, str]] = None,
) -> dict:
    """Build provider configuration dictionary."""
    config = {
        "name": provider_name,
        "api_base_url": api_base_url,
        "api_key": api_key_config,
        "models": models,
    }

    if headers:
        config["headers"] = headers

    return config


def _save_provider_config(
    provider_id: str,
    provider_config: dict,
    location: str,
    set_default: bool = True,
) -> Path:
    """Save provider configuration to file."""
    if location == "global":
        config_dir = ensure_user_config()
    else:
        config_dir = Path.cwd() / ".flavia"
        config_dir.mkdir(parents=True, exist_ok=True)

    providers_file = config_dir / "providers.yaml"

    # Load existing config if present
    existing_data = {}
    if providers_file.exists():
        try:
            with open(providers_file, "r", encoding="utf-8") as f:
                existing_data = yaml.safe_load(f) or {}
        except Exception:
            pass

    # Ensure providers dict exists
    if "providers" not in existing_data:
        existing_data["providers"] = {}

    # Add/update the provider
    existing_data["providers"][provider_id] = provider_config

    # Set as default if requested
    if set_default:
        existing_data["default_provider"] = provider_id

    # Write back
    with open(providers_file, "w", encoding="utf-8") as f:
        yaml.dump(existing_data, f, default_flow_style=False, sort_keys=False)

    return providers_file


def run_provider_wizard(target_dir: Optional[Path] = None) -> bool:
    """
    Run the interactive provider configuration wizard.

    Args:
        target_dir: Target directory for local config (default: current directory)

    Returns:
        True if successful
    """
    if target_dir is None:
        target_dir = Path.cwd()

    console.print(
        Panel.fit(
            "[bold blue]Provider Configuration Wizard[/bold blue]\n\n"
            "[dim]Configure LLM providers for flavIA[/dim]",
            title="Setup",
        )
    )

    # Step 1: Select provider type
    provider_type = _select_provider_type()
    if not provider_type:
        return False

    # Step 2: Get configuration based on provider type
    if provider_type == "custom":
        # Custom provider
        provider_id = Prompt.ask("\nProvider ID (short name)", default="custom")
        provider_name = Prompt.ask("Provider display name", default="Custom Provider")
        api_base_url = Prompt.ask(
            "API Base URL",
            default="https://api.example.com/v1",
        )
        api_key_env = Prompt.ask("API Key env variable name", default="CUSTOM_API_KEY")

        api_key, api_key_config = _get_api_key(provider_name, api_key_env)

        # Custom model
        model_id = Prompt.ask("Model ID", default="model-name")
        model_name = Prompt.ask("Model display name", default=model_id)

        models = [{"id": model_id, "name": model_name, "default": True}]
        headers = None

    else:
        # Known provider
        template = KNOWN_PROVIDERS[provider_type]
        provider_id = provider_type
        provider_name = template["name"]
        api_base_url = template["api_base_url"]
        api_key_env = template["api_key_env"]
        headers = template.get("headers")

        api_key, api_key_config = _get_api_key(provider_name, api_key_env)

        # Select models
        models = _select_models(template["models"])

    # Step 3: Test connection (optional)
    if api_key and Confirm.ask("\nTest connection?", default=True):
        console.print("[dim]Testing connection...[/dim]")

        # Resolve headers if present
        resolved_headers = {}
        if headers:
            for k, v in headers.items():
                resolved, _ = expand_env_vars(v)
                resolved_headers[k] = resolved

        test_model = models[0]["id"] if models else "test"
        success, message = test_provider_connection(
            api_key,
            api_base_url,
            test_model,
            resolved_headers if resolved_headers else None,
        )

        if success:
            console.print(f"[green]{message}[/green]")
        else:
            console.print(f"[red]{message}[/red]")
            if not Confirm.ask("Continue anyway?", default=False):
                return False

    # Step 4: Select save location
    location = _select_location()

    # Step 5: Set as default?
    set_default = Confirm.ask("\nSet as default provider?", default=True)

    # Build and save config
    provider_config = _build_provider_config(
        provider_id,
        provider_name,
        api_base_url,
        api_key_config,
        models,
        headers,
    )

    saved_path = _save_provider_config(provider_id, provider_config, location, set_default)

    console.print(
        Panel.fit(
            f"[bold green]Provider configured![/bold green]\n\n"
            f"Saved to: [cyan]{saved_path}[/cyan]\n\n"
            f"Provider: [bold]{provider_name}[/bold]\n"
            f"Models: {len(models)}\n"
            f"Default: {'Yes' if set_default else 'No'}",
            title="Success",
        )
    )

    return True


def list_providers(settings) -> None:
    """Print configured providers."""
    console.print("\n[bold]Configured Providers:[/bold]")
    console.print("-" * 60)

    if not settings.providers.providers:
        console.print("  No providers configured")
        console.print("  Run 'flavia --setup-provider' to configure providers")
        return

    for provider_id, provider in settings.providers.providers.items():
        default_marker = ""
        if provider_id == settings.providers.default_provider_id:
            default_marker = " [DEFAULT]"

        console.print(f"\n  [bold]{provider.name}[/bold] ({provider_id}){default_marker}")
        console.print(f"    URL: {provider.api_base_url}")

        # Show API key status
        if provider.api_key:
            console.print(f"    API Key: [green]Configured[/green]", end="")
            if provider.api_key_env_var:
                console.print(f" [dim](from ${provider.api_key_env_var})[/dim]")
            else:
                console.print()
        else:
            console.print(f"    API Key: [red]Not set[/red]")

        # Show models
        console.print(f"    Models: {len(provider.models)}")
        for model in provider.models:
            default = " (default)" if model.default else ""
            console.print(f"      - {model.name}: {model.id}{default}")

    console.print()
