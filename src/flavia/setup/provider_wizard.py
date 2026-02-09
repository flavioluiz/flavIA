"""Interactive provider configuration wizard for flavIA."""

import copy
import os
from pathlib import Path
from typing import Optional

import httpx
import yaml
from openai import OpenAI
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from flavia.config.loader import ensure_user_config
from flavia.config.providers import (
    ModelConfig as ProviderModelConfig,
    expand_env_vars,
)

console = Console()


def fetch_provider_models(
    api_key: str,
    api_base_url: str,
    headers: Optional[dict[str, str]] = None,
    timeout: float = 30.0,
) -> tuple[list[dict], Optional[str]]:
    """
    Fetch available models from a provider's /models endpoint.

    Args:
        api_key: API key for authentication
        api_base_url: Base URL of the API
        headers: Optional custom headers
        timeout: Request timeout in seconds

    Returns:
        Tuple of (models_list, error_message)
        models_list contains dicts with 'id' and 'name' keys
        error_message is None on success
    """
    try:
        kwargs: dict = {
            "api_key": api_key,
            "base_url": api_base_url,
            "timeout": httpx.Timeout(timeout, connect=10.0),
        }
        if headers:
            kwargs["default_headers"] = headers

        try:
            client = OpenAI(**kwargs)
        except TypeError as exc:
            if "unexpected keyword argument 'proxies'" not in str(exc):
                raise
            http_kwargs = {k: v for k, v in kwargs.items() if k != "default_headers"}
            client = OpenAI(**http_kwargs, http_client=httpx.Client(timeout=httpx.Timeout(timeout, connect=10.0)))

        response = client.models.list()

        models = []
        for model in response.data:
            model_id = model.id
            # Generate a friendly name from the ID
            name = _generate_model_name(model_id)
            models.append({"id": model_id, "name": name})

        # Sort by name for better display
        models.sort(key=lambda m: m["name"].lower())

        return models, None

    except Exception as e:
        return [], f"Failed to fetch models: {e}"


def _generate_model_name(model_id: str) -> str:
    """Generate a friendly display name from a model ID."""
    # Handle common ID formats like "hf:org/model-name" or "provider/model"
    name = model_id

    # Remove common prefixes
    if name.startswith("hf:"):
        name = name[3:]

    # Extract the model name part (after last /)
    if "/" in name:
        parts = name.split("/")
        name = parts[-1]  # Take the last part as the main name

    # Clean up common suffixes/patterns
    name = name.replace("-Instruct", "")
    name = name.replace("-instruct", "")

    return name

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

    # Ask first: use env var or enter key directly?
    if Confirm.ask(
        f"Use environment variable ${{{env_var}}}?",
        default=True,
    ):
        # User wants to use env var reference
        console.print(f"[dim]Set {env_var} in your shell before running flavIA[/dim]")
        console.print(f"[dim]Example: export {env_var}='your-api-key'[/dim]")

        # Still need the actual key for validation
        key_input = Prompt.ask("Enter the API key (for validation)", password=True)
        return key_input, f"${{{env_var}}}"
    else:
        # User wants to enter key directly (will be stored in config)
        console.print("[dim]The key will be stored directly in the config file[/dim]")
        key_input = Prompt.ask("API Key", password=True)
        return key_input, key_input


def _clone_models(models: list[dict]) -> list[dict]:
    """Clone model dictionaries to avoid mutating shared templates."""
    return [copy.deepcopy(m) for m in models]


def _provider_models_to_dicts(provider) -> list[dict]:
    """Convert provider models to wizard-friendly dict list."""
    converted: list[dict] = []
    for model in provider.models:
        normalized = _to_provider_model(model)
        item = {
            "id": normalized.id,
            "name": normalized.name,
        }
        if normalized.default:
            item["default"] = True
        if normalized.description:
            item["description"] = normalized.description
        converted.append(item)

    return converted


def _models_source_for_provider(provider_type: str, settings=None) -> list[dict]:
    """
    Resolve initial model list for provider wizard.

    Priority:
    1. Existing configured models for this provider (if available)
    2. Built-in template list
    """
    template_models = _clone_models(KNOWN_PROVIDERS[provider_type]["models"])
    if settings is None:
        return template_models

    existing_provider = settings.providers.get_provider(provider_type)
    if not existing_provider or not existing_provider.models:
        return template_models

    existing_models = _provider_models_to_dicts(existing_provider)
    if not existing_models:
        return template_models

    if not any(bool(m.get("default")) for m in existing_models):
        existing_models[0]["default"] = True
    return existing_models


def _select_models(
    available_models: list[dict],
    api_key: Optional[str] = None,
    api_base_url: Optional[str] = None,
    headers: Optional[dict[str, str]] = None,
) -> list[dict]:
    """Let user select which models to enable."""
    console.print("\n[bold]Select models to enable:[/bold]")

    table = Table(show_header=False, box=None, padding=(0, 2))
    for i, model in enumerate(available_models, 1):
        default_marker = " [default]" if model.get("default") else ""
        table.add_row(f"  [{i}]", f"{model['name']}{default_marker}", f"[dim]{model['id']}[/dim]")
    console.print(table)
    console.print("  [a] All models")
    if api_key and api_base_url:
        console.print("  [f] Fetch models from provider API")
    console.print("  [+] Add custom model")

    choice = Prompt.ask(
        "\nEnter numbers separated by comma, 'a' for all, 'f' to fetch, or '+' to add",
        default="a",
    )

    if choice.lower() == "a":
        return available_models

    if choice.lower() == "f" and api_key and api_base_url:
        return _fetch_and_select_models(api_key, api_base_url, headers, available_models)

    if choice == "+":
        custom = _add_custom_model()
        if custom:
            return available_models + [custom]
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


def _fetch_and_select_models(
    api_key: str,
    api_base_url: str,
    headers: Optional[dict[str, str]],
    fallback_models: list[dict],
) -> list[dict]:
    """Fetch models from provider and let user select."""
    console.print("\n[dim]Fetching models from provider...[/dim]")

    # Resolve headers if present
    resolved_headers = {}
    if headers:
        for k, v in headers.items():
            resolved, _ = expand_env_vars(v)
            resolved_headers[k] = resolved

    models, error = fetch_provider_models(
        api_key,
        api_base_url,
        resolved_headers if resolved_headers else None,
    )

    if error:
        console.print(f"[red]{error}[/red]")
        console.print("[yellow]Using default model list instead.[/yellow]")
        return fallback_models

    if not models:
        console.print("[yellow]No models returned from provider.[/yellow]")
        return fallback_models

    console.print(f"[green]Found {len(models)} models![/green]")

    # Display fetched models and let user select
    console.print("\n[bold]Available models from provider:[/bold]")

    # Show in pages if too many
    page_size = 20
    if len(models) > page_size:
        console.print(f"[dim](Showing first {page_size} of {len(models)} models)[/dim]")
        displayed_models = models[:page_size]
    else:
        displayed_models = models

    table = Table(show_header=False, box=None, padding=(0, 2))
    for i, model in enumerate(displayed_models, 1):
        table.add_row(f"  [{i}]", f"{model['name']}", f"[dim]{model['id']}[/dim]")
    console.print(table)
    console.print("  [a] All displayed models")
    console.print("  [s] Search by name")
    if len(models) > page_size:
        console.print("  [m] Show more models")

    choice = Prompt.ask(
        "\nEnter numbers separated by comma, 'a' for all, 's' to search, or 'm' for more",
        default="a",
    )

    if choice.lower() == "a":
        selected = displayed_models
    elif choice.lower() == "s":
        selected = _search_models(models)
    elif choice.lower() == "m" and len(models) > page_size:
        # Show all models
        return _select_from_full_list(models)
    else:
        selected = []
        for part in choice.split(","):
            try:
                index = int(part.strip()) - 1
                if 0 <= index < len(displayed_models):
                    selected.append(displayed_models[index])
            except ValueError:
                continue

    if not selected:
        console.print("[yellow]No models selected, using defaults.[/yellow]")
        return fallback_models

    # Mark first selected as default
    selected[0]["default"] = True
    return selected


def _search_models(models: list[dict]) -> list[dict]:
    """Search and select models by name."""
    query = Prompt.ask("Search for model (partial name)").lower()

    matches = [m for m in models if query in m["name"].lower() or query in m["id"].lower()]

    if not matches:
        console.print("[yellow]No matches found.[/yellow]")
        return []

    console.print(f"\n[bold]Found {len(matches)} matching models:[/bold]")
    table = Table(show_header=False, box=None, padding=(0, 2))
    for i, model in enumerate(matches[:20], 1):
        table.add_row(f"  [{i}]", f"{model['name']}", f"[dim]{model['id']}[/dim]")
    console.print(table)
    if len(matches) > 20:
        console.print(f"[dim](Showing first 20 of {len(matches)} matches)[/dim]")

    choice = Prompt.ask(
        "Enter numbers to select (comma-separated), or 'a' for all matches",
        default="a",
    )

    if choice.lower() == "a":
        return matches

    selected = []
    for part in choice.split(","):
        try:
            index = int(part.strip()) - 1
            if 0 <= index < len(matches):
                selected.append(matches[index])
        except ValueError:
            continue

    return selected


def _select_from_full_list(models: list[dict]) -> list[dict]:
    """Display and select from full model list."""
    console.print(f"\n[bold]All {len(models)} available models:[/bold]")

    table = Table(show_header=False, box=None, padding=(0, 2))
    for i, model in enumerate(models, 1):
        table.add_row(f"  [{i}]", f"{model['name']}", f"[dim]{model['id']}[/dim]")
    console.print(table)

    choice = Prompt.ask(
        "Enter numbers to select (comma-separated)",
        default="1",
    )

    selected = []
    for part in choice.split(","):
        try:
            index = int(part.strip()) - 1
            if 0 <= index < len(models):
                selected.append(models[index])
        except ValueError:
            continue

    return selected if selected else [models[0]]


def _add_custom_model() -> Optional[dict]:
    """Prompt user to add a custom model."""
    console.print("\n[bold]Add custom model:[/bold]")

    model_id = Prompt.ask("Model ID (as used in API calls)")
    if not model_id:
        return None

    model_name = Prompt.ask("Display name", default=_generate_model_name(model_id))
    is_default = Confirm.ask("Set as default?", default=False)

    return {"id": model_id, "name": model_name, "default": is_default}


def _to_provider_model(model: object) -> ProviderModelConfig:
    """Normalize model input into ProviderModelConfig."""
    if isinstance(model, ProviderModelConfig):
        return model

    if isinstance(model, dict):
        model_id = str(model.get("id", "")).strip()
        if not model_id:
            raise ValueError("Model id is required")
        return ProviderModelConfig(
            id=model_id,
            name=model.get("name", model_id),
            max_tokens=int(model.get("max_tokens", 128000)),
            default=bool(model.get("default", False)),
            description=model.get("description", ""),
        )

    model_id = str(getattr(model, "id", "")).strip()
    if not model_id:
        raise ValueError("Model id is required")

    return ProviderModelConfig(
        id=model_id,
        name=getattr(model, "name", model_id),
        max_tokens=int(getattr(model, "max_tokens", 128000)),
        default=bool(getattr(model, "default", False)),
        description=getattr(model, "description", ""),
    )


def _normalize_provider_models(provider) -> None:
    """Ensure provider.models only contains ProviderModelConfig values."""
    normalized: list[ProviderModelConfig] = []
    for model in provider.models:
        try:
            normalized.append(_to_provider_model(model))
        except Exception:
            continue
    provider.models = normalized


def _ensure_single_default(models: list[ProviderModelConfig]) -> None:
    """Keep exactly one default model when models are present."""
    if not models:
        return

    default_indexes = [idx for idx, model in enumerate(models) if model.default]
    if not default_indexes:
        models[0].default = True
        return

    default_index = default_indexes[0]
    for idx, model in enumerate(models):
        model.default = idx == default_index


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
    target_dir: Optional[Path] = None,
) -> Path:
    """Save provider configuration to file."""
    if location == "global":
        config_dir = ensure_user_config()
    else:
        base_dir = target_dir if target_dir is not None else Path.cwd()
        config_dir = base_dir / ".flavia"
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
        yaml.dump(
            existing_data,
            f,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )

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
    from flavia.config import load_settings
    settings = load_settings()

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

        initial_models = _models_source_for_provider(provider_type, settings=settings)
        if len(initial_models) != len(template["models"]):
            console.print(
                f"[dim]Using {len(initial_models)} model(s) already configured for {provider_name}.[/dim]"
            )

        # Select models (pass API info for optional model fetching)
        models = _select_models(
            initial_models,
            api_key=api_key,
            api_base_url=api_base_url,
            headers=headers,
        )

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

    saved_path = _save_provider_config(
        provider_id,
        provider_config,
        location,
        set_default,
        target_dir=target_dir,
    )

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


def manage_provider_models(settings, provider_id: Optional[str] = None) -> bool:
    """
    Manage models for a configured provider.

    Args:
        settings: Current settings
        provider_id: Provider ID to manage (prompts if not provided)

    Returns:
        True if changes were saved
    """
    if not settings.providers.providers:
        console.print("[yellow]No providers configured.[/yellow]")
        console.print("Run 'flavia --setup-provider' to configure a provider first.")
        return False

    # Select provider if not specified
    if not provider_id:
        provider_id = _select_existing_provider(settings)
        if not provider_id:
            return False

    provider = settings.providers.get_provider(provider_id)
    if not provider:
        console.print(f"[red]Provider '{provider_id}' not found.[/red]")
        return False

    _normalize_provider_models(provider)
    _ensure_single_default(provider.models)

    console.print(
        Panel.fit(
            f"[bold blue]Manage Models[/bold blue]\n\n"
            f"Provider: [bold]{provider.name}[/bold] ({provider_id})\n"
            f"Models: {len(provider.models)}",
            title="Model Management",
        )
    )

    while True:
        # Show current models
        console.print("\n[bold]Current models:[/bold]")
        table = Table(show_header=False, box=None, padding=(0, 2))
        for i, model in enumerate(provider.models, 1):
            default_marker = " [default]" if model.default else ""
            table.add_row(f"  [{i}]", f"{model.name}{default_marker}", f"[dim]{model.id}[/dim]")
        console.print(table)

        # Menu options
        console.print("\n[bold]Actions:[/bold]")
        console.print("  [a] Add model")
        console.print("  [f] Fetch models from provider API")
        console.print("  [r] Remove model(s)")
        console.print("  [d] Set default model")
        console.print("  [s] Save and exit")
        console.print("  [q] Quit without saving")

        choice = Prompt.ask("\nChoice", default="s").lower()

        if choice == "a":
            custom = _add_custom_model()
            if custom:
                model = _to_provider_model(custom)
                if model.default:
                    for existing in provider.models:
                        existing.default = False
                provider.models.append(model)
                _ensure_single_default(provider.models)
                console.print(f"[green]Added model: {custom['name']}[/green]")

        elif choice == "f":
            if not provider.api_key:
                console.print("[red]API key not configured for this provider.[/red]")
                continue

            new_models = _fetch_models_for_provider(provider)
            if new_models:
                # Ask how to handle
                console.print(f"\n[green]Found {len(new_models)} models.[/green]")
                action = Prompt.ask(
                    "How to handle?",
                    choices=["replace", "merge", "cancel"],
                    default="merge",
                )
                if action == "replace":
                    provider.models = [_to_provider_model(m) for m in new_models]
                    _ensure_single_default(provider.models)
                elif action == "merge":
                    existing_ids = {m.id for m in provider.models}
                    added = 0
                    for m in new_models:
                        if m["id"] not in existing_ids:
                            provider.models.append(_to_provider_model(m))
                            added += 1
                    _ensure_single_default(provider.models)
                    console.print(f"[green]Added {added} new models.[/green]")

        elif choice == "r":
            indices = Prompt.ask("Enter model numbers to remove (comma-separated)")
            removed = []
            for part in indices.split(","):
                try:
                    index = int(part.strip()) - 1
                    if 0 <= index < len(provider.models):
                        removed.append(provider.models[index])
                except ValueError:
                    continue
            for model in removed:
                provider.models.remove(model)
                console.print(f"[yellow]Removed: {model.name}[/yellow]")
            _ensure_single_default(provider.models)

        elif choice == "d":
            index_str = Prompt.ask("Enter model number to set as default")
            try:
                index = int(index_str) - 1
                if 0 <= index < len(provider.models):
                    for m in provider.models:
                        m.default = False
                    provider.models[index].default = True
                    console.print(f"[green]Default set to: {provider.models[index].name}[/green]")
            except ValueError:
                console.print("[red]Invalid number.[/red]")

        elif choice == "s":
            # Save changes
            return _save_provider_changes(settings, provider_id, provider)

        elif choice == "q":
            console.print("[yellow]Changes discarded.[/yellow]")
            return False


def _select_existing_provider(settings) -> Optional[str]:
    """Let user select from existing providers."""
    providers = list(settings.providers.providers.keys())

    console.print("\n[bold]Select provider to manage:[/bold]")
    table = Table(show_header=False, box=None, padding=(0, 2))
    for i, pid in enumerate(providers, 1):
        provider = settings.providers.providers[pid]
        table.add_row(f"  [{i}]", f"[bold]{provider.name}[/bold]", f"[dim]{pid}[/dim]")
    console.print(table)

    choice = Prompt.ask("Enter number")
    try:
        index = int(choice) - 1
        if 0 <= index < len(providers):
            return providers[index]
    except ValueError:
        pass

    console.print("[red]Invalid choice.[/red]")
    return None


def _fetch_models_for_provider(provider) -> list[dict]:
    """Fetch models from a provider."""
    console.print("\n[dim]Fetching models from provider...[/dim]")

    # Resolve headers if present
    resolved_headers = {}
    if provider.headers:
        for k, v in provider.headers.items():
            resolved, _ = expand_env_vars(v)
            resolved_headers[k] = resolved

    models, error = fetch_provider_models(
        provider.api_key,
        provider.api_base_url,
        resolved_headers if resolved_headers else None,
    )

    if error:
        console.print(f"[red]{error}[/red]")
        return []

    if not models:
        console.print("[yellow]No models returned from provider.[/yellow]")
        return []

    console.print(f"[green]Found {len(models)} models![/green]")

    # Let user select from fetched models
    console.print("\n[bold]Available models:[/bold]")
    displayed = models[:30]  # Limit display
    if len(models) > 30:
        console.print(f"[dim](Showing first 30 of {len(models)} models)[/dim]")

    table = Table(show_header=False, box=None, padding=(0, 2))
    for i, model in enumerate(displayed, 1):
        table.add_row(f"  [{i}]", f"{model['name']}", f"[dim]{model['id']}[/dim]")
    console.print(table)
    console.print("  [a] All displayed")
    console.print("  [s] Search")

    choice = Prompt.ask("Select models (numbers/a/s)", default="a").lower()

    if choice == "a":
        selected = displayed
    elif choice == "s":
        selected = _search_models(models)
    else:
        selected = []
        for part in choice.split(","):
            try:
                index = int(part.strip()) - 1
                if 0 <= index < len(displayed):
                    selected.append(displayed[index])
            except ValueError:
                continue

    # Mark first as default
    if selected:
        selected[0]["default"] = True

    return selected


def _save_provider_changes(settings, provider_id: str, provider) -> bool:
    """Save provider model changes to config file."""
    from flavia.config.loader import get_config_paths

    paths = get_config_paths()

    # Determine which file to update
    if paths.providers_file:
        providers_file = paths.providers_file
    elif paths.local_dir:
        providers_file = paths.local_dir / "providers.yaml"
    else:
        providers_file = ensure_user_config() / "providers.yaml"

    # Load existing config
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

    # Convert models to serializable format
    models_data = []
    for m in provider.models:
        model = _to_provider_model(m)
        model_dict = {"id": model.id, "name": model.name}
        if model.default:
            model_dict["default"] = True
        if model.max_tokens != 128000:
            model_dict["max_tokens"] = model.max_tokens
        if model.description:
            model_dict["description"] = model.description
        models_data.append(model_dict)

    # Update provider config
    if provider_id in existing_data["providers"]:
        existing_data["providers"][provider_id]["models"] = models_data
    else:
        # New provider - need full config
        existing_data["providers"][provider_id] = {
            "name": provider.name,
            "api_base_url": provider.api_base_url,
            "api_key": f"${{{provider.api_key_env_var}}}" if provider.api_key_env_var else provider.api_key,
            "models": models_data,
        }

    # Write back
    with open(providers_file, "w", encoding="utf-8") as f:
        yaml.dump(
            existing_data,
            f,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )

    console.print(f"\n[green]Changes saved to: {providers_file}[/green]")
    return True
