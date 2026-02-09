"""Interactive provider configuration wizard for flavIA."""

import copy
import os
from pathlib import Path
from typing import Any, Optional

import httpx
import yaml
from openai import OpenAI
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from flavia.config.providers import (
    ModelConfig as ProviderModelConfig,
    expand_env_vars,
)
from flavia.setup.prompt_utils import safe_confirm, safe_prompt

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


def _guess_api_key_env_var(provider_id: str) -> str:
    """Guess API key environment variable for a provider ID."""
    clean = "".join(c if c.isalnum() else "_" for c in provider_id).upper()
    return f"{clean}_API_KEY"


def _collect_provider_choices(settings=None) -> list[dict[str, str]]:
    """Build provider choices including configured providers from merged settings."""
    choices: list[dict[str, str]] = []
    configured_ids = set(settings.providers.providers.keys()) if settings else set()

    for provider_id, template in KNOWN_PROVIDERS.items():
        status = " (configured)" if provider_id in configured_ids else ""
        choices.append(
            {
                "kind": "known",
                "provider_id": provider_id,
                "name": f"{template['name']}{status}",
                "description": template["api_base_url"],
            }
        )

    if settings:
        for provider_id, provider in settings.providers.providers.items():
            if provider_id in KNOWN_PROVIDERS:
                continue
            choices.append(
                {
                    "kind": "existing",
                    "provider_id": provider_id,
                    "name": f"{provider.name} (configured)",
                    "description": provider.api_base_url,
                }
            )

    choices.append(
        {
            "kind": "custom",
            "provider_id": "custom",
            "name": "Custom Provider",
            "description": "Configure a custom OpenAI-compatible provider",
        }
    )

    return choices


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

        # Add timeout to avoid hanging indefinitely
        kwargs["timeout"] = httpx.Timeout(30.0, connect=10.0)

        try:
            client = OpenAI(**kwargs)
        except TypeError as exc:
            if "unexpected keyword argument 'proxies'" not in str(exc):
                raise
            # Compatibility fallback for environments where OpenAI SDK and httpx versions mismatch.
            http_kwargs = {k: v for k, v in kwargs.items() if k != "default_headers"}
            client = OpenAI(**http_kwargs, http_client=httpx.Client(timeout=httpx.Timeout(30.0, connect=10.0)))

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


def _select_provider_type(settings=None) -> Optional[dict[str, str]]:
    """Ask user to select provider source/type."""
    console.print("\n[bold]Select a provider:[/bold]")

    table = Table(show_header=False, box=None, padding=(0, 2))
    choices = _collect_provider_choices(settings=settings)
    for i, choice in enumerate(choices, 1):
        table.add_row(
            f"  [{i}]",
            f"[bold]{choice['name']}[/bold]",
            f"[dim]{choice['description']}[/dim]",
        )
    console.print(table)

    choice = safe_prompt("\nEnter number", default="1")

    try:
        index = int(choice) - 1
        if 0 <= index < len(choices):
            return choices[index]
    except ValueError:
        pass

    console.print("[red]Invalid choice[/red]")
    return None


def _headers_for_known_provider(provider_id: str, settings=None) -> Optional[dict[str, str]]:
    """Resolve headers for a known provider while preserving template placeholders."""
    template_headers = copy.deepcopy(KNOWN_PROVIDERS[provider_id].get("headers"))
    if settings is None:
        return template_headers

    existing_provider = settings.providers.get_provider(provider_id)
    if not existing_provider or not existing_provider.headers:
        return template_headers

    existing_headers = copy.deepcopy(existing_provider.headers)
    if template_headers and all(str(v) == "" for v in existing_headers.values()):
        return template_headers
    return existing_headers


def _load_settings_for_target_dir(target_dir: Path):
    """Load settings as if current working directory were target_dir."""
    from flavia.config import load_settings

    current_dir = Path.cwd().resolve()
    resolved_target = target_dir.resolve()
    if current_dir == resolved_target:
        return load_settings()

    os.chdir(resolved_target)
    try:
        return load_settings()
    finally:
        os.chdir(current_dir)


def _get_api_key(provider_name: str, default_env_var: str = "") -> tuple[str, str]:
    """
    Get API key from user.

    Args:
        provider_name: Display name of the provider
        default_env_var: Suggested environment variable name (optional)

    Returns:
        Tuple of (api_key_value, api_key_config_string)
        The config string is either the literal value or ${ENV_VAR}
    """
    console.print(f"\n[bold]API Key for {provider_name}[/bold]")

    # Check if suggested env var is already set
    if default_env_var:
        existing = os.getenv(default_env_var, "")
        if existing:
            console.print(f"[green]Found existing {default_env_var} in environment[/green]")
            if safe_confirm(f"Use existing {default_env_var}?", default=True):
                return existing, f"${{{default_env_var}}}"

    # Ask if user wants to use an environment variable
    if safe_confirm("Store API key as environment variable reference?", default=True):
        # User wants to use env var reference
        env_var = safe_prompt(
            "Environment variable name",
            default=default_env_var or "API_KEY",
        )
        console.print(f"[dim]Set {env_var} in your shell before running flavIA[/dim]")
        console.print(f"[dim]Example: export {env_var}='your-api-key'[/dim]")

        # Still need the actual key for validation
        key_input = safe_prompt("Enter the API key (for validation)", password=True)
        return key_input, f"${{{env_var}}}"
    else:
        # User wants to enter key directly (will be stored in config)
        console.print("[yellow]The key will be stored directly in the config file[/yellow]")
        key_input = safe_prompt("API Key", password=True)
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
    console.print("  \\[a] All models")
    if api_key and api_base_url:
        console.print("  \\[f] Fetch models from provider API")
    console.print("  \\[+] Add custom model")

    choice = safe_prompt(
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
    console.print("  \\[a] All displayed models")
    console.print("  \\[s] Search by name")
    if len(models) > page_size:
        console.print("  \\[m] Show more models")

    choice = safe_prompt(
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
    query = safe_prompt("Search for model (partial name)").lower()

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

    choice = safe_prompt(
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

    choice = safe_prompt(
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

    model_id = safe_prompt("Model ID (as used in API calls)")
    if not model_id:
        return None

    model_name = safe_prompt("Display name", default=_generate_model_name(model_id))
    is_default = safe_confirm("Set as default?", default=False)

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


def _providers_file_for_location(location: str, target_dir: Optional[Path] = None) -> Path:
    """Resolve providers.yaml path for local/global location."""
    if location == "global":
        return Path.home() / ".config" / "flavia" / "providers.yaml"

    base_dir = target_dir.resolve() if target_dir is not None else Path.cwd()
    return base_dir / ".flavia" / "providers.yaml"


def _load_yaml_data(file_path: Path) -> dict[str, Any]:
    """Load YAML as dictionary, returning empty dict on failures."""
    if not file_path.exists():
        return {}

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            loaded = yaml.safe_load(f) or {}
    except Exception:
        return {}

    return loaded if isinstance(loaded, dict) else {}


def _extract_provider_from_file(file_path: Path, provider_id: str) -> Optional[dict[str, Any]]:
    """Extract raw provider config from a providers.yaml file."""
    data = _load_yaml_data(file_path)
    providers = data.get("providers")
    if not isinstance(providers, dict):
        return None
    provider_data = providers.get(provider_id)
    if not isinstance(provider_data, dict):
        return None
    return copy.deepcopy(provider_data)


def _select_location(
    provider_id: Optional[str] = None,
    target_dir: Optional[Path] = None,
    title: str = "Where to save provider configuration?",
) -> str:
    """Ask user where to save configuration, showing where provider already exists."""
    local_file = _providers_file_for_location("local", target_dir=target_dir)
    global_file = _providers_file_for_location("global")
    local_exists = bool(provider_id and _extract_provider_from_file(local_file, provider_id))
    global_exists = bool(provider_id and _extract_provider_from_file(global_file, provider_id))

    local_hint = "Project-specific"
    global_hint = "User-wide"
    if local_exists:
        local_hint += " [configured]"
    if global_exists:
        global_hint += " [configured]"

    console.print(f"\n[bold]{title}[/bold]")
    console.print(f"  [1] Local ({local_file}) - {local_hint}")
    console.print(f"  [2] Global ({global_file}) - {global_hint}")

    default_choice = "1"
    if global_exists and not local_exists:
        default_choice = "2"

    choice = safe_prompt("Enter number", default=default_choice)

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
    providers_file = _providers_file_for_location(location, target_dir=target_dir)
    providers_file.parent.mkdir(parents=True, exist_ok=True)

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
    target_dir = target_dir.resolve()
    settings = _load_settings_for_target_dir(target_dir)

    console.print(
        Panel.fit(
            "[bold blue]Provider Configuration Wizard[/bold blue]\n\n"
            "[dim]Configure LLM providers for flavIA[/dim]",
            title="Setup",
        )
    )

    # Step 1: Select provider type
    provider_selection = _select_provider_type(settings=settings)
    if not provider_selection:
        return False

    # Step 2: Get configuration based on provider type
    selection_kind = provider_selection["kind"]
    selected_provider_id = provider_selection["provider_id"]

    if selection_kind == "custom":
        # Custom provider
        provider_id = safe_prompt("\nProvider ID (short name)", default="custom")
        provider_name = safe_prompt("Provider display name", default="Custom Provider")
        api_base_url = safe_prompt(
            "API Base URL",
            default="https://api.example.com/v1",
        )
        api_key, api_key_config = _get_api_key(provider_name, _guess_api_key_env_var(provider_id))
        headers = None

        # Model configuration
        console.print("\n[bold]Model configuration[/bold]")
        console.print("  \\[1] Fetch available models from provider")
        console.print("  \\[2] Enter model name manually")

        model_choice = safe_prompt("Choice", default="1")

        if model_choice == "1" and api_key:
            # Try to fetch models from the provider
            fetched = _fetch_and_select_models(api_key, api_base_url, headers, [])
            if fetched:
                models = fetched
            else:
                console.print("[yellow]Could not fetch models. Please enter manually.[/yellow]")
                model_id = safe_prompt("Model ID", default="model-name")
                model_name = safe_prompt("Model display name", default=model_id)
                models = [{"id": model_id, "name": model_name, "default": True}]
        else:
            # Manual entry
            model_id = safe_prompt("Model ID", default="model-name")
            model_name = safe_prompt("Model display name", default=model_id)
            models = [{"id": model_id, "name": model_name, "default": True}]

    else:
        provider_id = selected_provider_id
        existing_provider = settings.providers.get_provider(provider_id)

        if selection_kind == "known":
            # Known provider template with existing values as defaults when available.
            template = KNOWN_PROVIDERS[provider_id]
            provider_name = existing_provider.name if existing_provider else template["name"]
            api_base_url = (
                existing_provider.api_base_url
                if existing_provider and existing_provider.api_base_url
                else template["api_base_url"]
            )
            default_env_var = (
                existing_provider.api_key_env_var
                if existing_provider and existing_provider.api_key_env_var
                else template["api_key_env"]
            )
            headers = _headers_for_known_provider(provider_id, settings=settings)

            api_key, api_key_config = _get_api_key(provider_name, default_env_var)

            initial_models = _models_source_for_provider(provider_id, settings=settings)
            if existing_provider:
                console.print(
                    f"[dim]Using {len(initial_models)} model(s) already configured for {provider_name}.[/dim]"
                )

            models = _select_models(
                initial_models,
                api_key=api_key,
                api_base_url=api_base_url,
                headers=headers,
            )
        else:
            # Existing configured provider (typically custom/non-template).
            if not existing_provider:
                console.print(f"[red]Provider '{provider_id}' is not available in current settings.[/red]")
                return False

            provider_name = safe_prompt("\nProvider display name", default=existing_provider.name)
            api_base_url = safe_prompt("API Base URL", default=existing_provider.api_base_url)
            default_env_var = existing_provider.api_key_env_var or _guess_api_key_env_var(provider_id)
            api_key, api_key_config = _get_api_key(provider_name, default_env_var)
            headers = copy.deepcopy(existing_provider.headers) if existing_provider.headers else None

            initial_models = _provider_models_to_dicts(existing_provider)
            if not initial_models:
                initial_models = [{"id": "model-name", "name": "model-name", "default": True}]
            if not any(bool(m.get("default")) for m in initial_models):
                initial_models[0]["default"] = True

            models = _select_models(
                initial_models,
                api_key=api_key,
                api_base_url=api_base_url,
                headers=headers,
            )

    # Step 3: Test connection (optional)
    if api_key and safe_confirm("\nTest connection?", default=True):
        test_model = models[0]["id"] if models else "test"
        console.print(f"[dim]Testing connection with model: [cyan]{test_model}[/cyan]...[/dim]")

        # Resolve headers if present
        resolved_headers = {}
        if headers:
            for k, v in headers.items():
                resolved, _ = expand_env_vars(v)
                resolved_headers[k] = resolved

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
            if not safe_confirm("Continue anyway?", default=False):
                return False

    # Step 4: Select save location
    location = _select_location(provider_id=provider_id, target_dir=target_dir)

    # Step 5: Choose default model for this provider
    default_model = next((m for m in models if m.get("default")), models[0] if models else None)
    if len(models) > 1:
        console.print("\n[bold]Default model for this provider:[/bold]")
        table = Table(show_header=False, box=None, padding=(0, 2))
        for i, model in enumerate(models, 1):
            marker = " [current default]" if model.get("default") else ""
            table.add_row(f"  [{i}]", f"{model['name']}{marker}", f"[dim]{model['id']}[/dim]")
        console.print(table)

        choice = safe_prompt(
            "Select default model",
            default="1",
        )
        try:
            index = int(choice) - 1
            if 0 <= index < len(models):
                # Clear old default and set new one
                for m in models:
                    m["default"] = False
                models[index]["default"] = True
                default_model = models[index]
                console.print(f"[green]Default model: {default_model['name']}[/green]")
        except ValueError:
            pass

    default_model_name = default_model["name"] if default_model else "unknown"

    # Step 6: Set as default provider+model for flavia?
    console.print(f"\n[dim]This will use [cyan]{provider_name}[/cyan] with model [cyan]{default_model_name}[/cyan] when running flavia.[/dim]")
    set_default = safe_confirm("Set as default?", default=True)

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
            f"Models: {len(models)} (default: {default_model_name})\n"
            f"Use by default: {'Yes' if set_default else 'No'}",
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
        console.print("  \\[a] Add model")
        console.print("  \\[f] Fetch models from provider API")
        console.print("  \\[r] Remove model(s)")
        console.print("  \\[d] Set default model")
        console.print("  \\[x] Delete this provider")
        console.print("  \\[s] Save and exit")
        console.print("  \\[q] Quit without saving")

        choice = safe_prompt("\nChoice", default="s").lower()

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
                action = safe_prompt(
                    "How to handle? (replace/merge/cancel)",
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
            indices = safe_prompt("Enter model numbers to remove (comma-separated)")
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
            index_str = safe_prompt("Enter model number to set as default")
            try:
                index = int(index_str) - 1
                if 0 <= index < len(provider.models):
                    for m in provider.models:
                        m.default = False
                    provider.models[index].default = True
                    console.print(f"[green]Default set to: {provider.models[index].name}[/green]")
            except ValueError:
                console.print("[red]Invalid number.[/red]")

        elif choice == "x":
            # Delete provider
            if safe_confirm(
                f"Delete provider '{provider.name}' completely?",
                default=False,
            ):
                return _delete_provider(settings, provider_id)

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

    choice = safe_prompt("Enter number")
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
    console.print("  \\[a] All displayed")
    console.print("  \\[s] Search")

    choice = safe_prompt("Select models (numbers/a/s)", default="a").lower()

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


def _find_provider_raw_config(provider_id: str) -> Optional[dict[str, Any]]:
    """Find raw provider config in local, global, or package providers.yaml."""
    from flavia.config.loader import get_config_paths

    paths = get_config_paths()
    candidates: list[Path] = []

    if paths.local_dir:
        candidates.append(paths.local_dir / "providers.yaml")
    if paths.user_dir:
        candidates.append(paths.user_dir / "providers.yaml")
    if paths.package_dir:
        candidates.append(paths.package_dir / "providers.yaml")

    seen: set[Path] = set()
    for file_path in candidates:
        resolved = file_path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        provider_data = _extract_provider_from_file(file_path, provider_id)
        if provider_data:
            return provider_data

    return None


def _build_api_key_reference(provider_id: str, provider, raw_provider: Optional[dict[str, Any]] = None) -> str:
    """Build safe api_key value without persisting resolved secret values."""
    if raw_provider:
        raw_key = raw_provider.get("api_key")
        if isinstance(raw_key, str) and raw_key:
            return raw_key

    if getattr(provider, "api_key_env_var", None):
        return f"${{{provider.api_key_env_var}}}"

    known = KNOWN_PROVIDERS.get(provider_id)
    if known and known.get("api_key_env"):
        return f"${{{known['api_key_env']}}}"

    return f"${{{_guess_api_key_env_var(provider_id)}}}"


def _delete_provider(settings, provider_id: str) -> bool:
    """Delete a provider from configuration."""
    _ = settings
    location = _select_location(
        provider_id=provider_id,
        title=f"Where should provider '{provider_id}' be deleted from?",
    )
    providers_file = _providers_file_for_location(location)

    if not providers_file.exists():
        console.print(f"[red]Config file not found: {providers_file}[/red]")
        return False

    console.print(f"[dim]Target file: {providers_file}[/dim]")
    if not safe_confirm(f"Delete provider '{provider_id}' from this file?", default=False):
        console.print("[yellow]Delete cancelled.[/yellow]")
        return False

    # Load existing config
    existing_data = _load_yaml_data(providers_file)
    providers = existing_data.get("providers", {})

    if provider_id not in providers:
        console.print(f"[yellow]Provider '{provider_id}' not found in {providers_file}[/yellow]")
        return False

    # Remove provider
    del providers[provider_id]

    # Clear default if it was this provider
    if existing_data.get("default_provider") == provider_id:
        if providers:
            # Set first remaining provider as default
            new_default = next(iter(providers.keys()))
            existing_data["default_provider"] = new_default
            console.print(f"[dim]New default provider: {new_default}[/dim]")
        else:
            del existing_data["default_provider"]

    # Write back
    with open(providers_file, "w", encoding="utf-8") as f:
        yaml.safe_dump(existing_data, f, sort_keys=False, allow_unicode=True)

    console.print(f"[green]Provider '{provider_id}' deleted from {providers_file}[/green]")
    return True


def _save_provider_changes(settings, provider_id: str, provider) -> bool:
    """Save provider model changes to config file."""
    _ = settings
    location = _select_location(
        provider_id=provider_id,
        title=f"Where should changes for provider '{provider_id}' be saved?",
    )
    providers_file = _providers_file_for_location(location)
    providers_file.parent.mkdir(parents=True, exist_ok=True)

    console.print(f"[dim]Target file: {providers_file}[/dim]")
    if not safe_confirm("Save changes to this file?", default=True):
        console.print("[yellow]Save cancelled.[/yellow]")
        return False

    # Load existing config
    existing_data = _load_yaml_data(providers_file)

    # Ensure providers dict exists
    providers = existing_data.get("providers")
    if not isinstance(providers, dict):
        providers = {}
        existing_data["providers"] = providers

    # Convert models to serializable format
    models_data: list[dict[str, Any]] = []
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
    existing_provider_data = providers.get(provider_id)
    if isinstance(existing_provider_data, dict):
        existing_provider_data["models"] = models_data
    else:
        raw_provider = _find_provider_raw_config(provider_id)
        new_provider: dict[str, Any] = copy.deepcopy(raw_provider) if raw_provider else {}

        if not new_provider:
            new_provider = {
                "name": provider.name,
                "api_base_url": provider.api_base_url,
            }
        else:
            if "name" not in new_provider:
                new_provider["name"] = provider.name
            if "api_base_url" not in new_provider:
                new_provider["api_base_url"] = provider.api_base_url

        if not new_provider.get("api_key"):
            new_provider["api_key"] = _build_api_key_reference(provider_id, provider, raw_provider=raw_provider)

        if "headers" not in new_provider and getattr(provider, "headers", None):
            template_headers = KNOWN_PROVIDERS.get(provider_id, {}).get("headers")
            new_provider["headers"] = (
                copy.deepcopy(template_headers) if template_headers else copy.deepcopy(provider.headers)
            )

        new_provider["models"] = models_data
        providers[provider_id] = new_provider

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
