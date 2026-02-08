#!/usr/bin/env python3
"""
flavIA CLI entry point.

Usage:
    flavia                  # Interactive CLI
    flavia --init           # Initialize local config with setup wizard
    flavia --telegram       # Telegram bot mode
    flavia --list-models    # List available models
    flavia --list-tools     # List available tools
"""

import argparse
import sys
from pathlib import Path

from flavia.config import load_settings, Settings
from flavia import tools as _  # Register tools
from flavia.venv_bootstrap import ensure_project_venv_and_reexec


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        prog="flavia",
        description="flavIA - AI Agent with modular tools",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Init command
    parser.add_argument(
        "--init",
        action="store_true",
        help="Initialize local configuration with setup wizard",
    )

    # Mode selection
    parser.add_argument(
        "--telegram",
        action="store_true",
        help="Run as Telegram bot instead of CLI",
    )

    # Model selection
    parser.add_argument(
        "-m", "--model",
        type=str,
        help="Model to use (index, model ID, or provider:model_id format)",
    )

    # Options
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose output",
    )

    parser.add_argument(
        "-d", "--depth",
        type=int,
        help="Maximum agent recursion depth",
    )

    parser.add_argument(
        "-p", "--path",
        type=str,
        help="Base directory for file operations (default: current directory)",
    )

    # Info commands
    parser.add_argument(
        "--list-models",
        action="store_true",
        help="List available models and exit",
    )

    parser.add_argument(
        "--list-tools",
        action="store_true",
        help="List available tools and exit",
    )

    parser.add_argument(
        "--list-providers",
        action="store_true",
        help="List configured providers and exit",
    )

    parser.add_argument(
        "--setup-provider",
        action="store_true",
        help="Run the interactive provider configuration wizard",
    )

    parser.add_argument(
        "--test-provider",
        type=str,
        metavar="PROVIDER_ID",
        nargs="?",
        const="",  # Empty string means test default provider
        help="Test connection to a provider (default: test default provider)",
    )

    parser.add_argument(
        "--config",
        action="store_true",
        help="Show configuration locations and exit",
    )

    parser.add_argument(
        "--version",
        action="store_true",
        help="Show version and exit",
    )

    return parser.parse_args()


def apply_args_to_settings(args: argparse.Namespace, settings: Settings) -> Settings:
    """Apply command line arguments to settings."""
    if args.verbose:
        settings.verbose = True

    if args.model is not None:
        try:
            index = int(args.model)
            model = settings.get_model_by_index(index)
            if model:
                settings.default_model = model.id
            else:
                print(f"Warning: Model index {index} not found, using default")
        except ValueError:
            settings.default_model = args.model

    if args.depth is not None:
        settings.max_depth = args.depth

    if args.path is not None:
        settings.base_dir = Path(args.path).resolve()

    return settings


def show_version() -> None:
    """Show version information."""
    from flavia import __version__
    print(f"flavIA version {__version__}")


def show_config_info(settings: Settings) -> None:
    """Show configuration locations and status."""
    print("\nConfiguration Locations:")
    print("-" * 60)

    local_dir = Path.cwd() / ".flavia"
    local_env = local_dir / ".env"
    print(f"\n[Local (current directory)]")
    print(f"  Directory: {local_dir}")
    print(f"  Exists: {'Yes' if local_dir.exists() else 'No (run flavia --init)'}")
    print(f"  .env: {'Found' if local_env.exists() else 'Not found'}")

    user_dir = Path.home() / ".config" / "flavia"
    print(f"\n[User (~/.config/flavia/)]")
    print(f"  Directory: {user_dir}")
    print(f"  Exists: {'Yes' if user_dir.exists() else 'No'}")

    print(f"\n[Active Settings]")
    print(f"  API Base URL: {settings.api_base_url}")
    print(f"  Default Model: {settings.default_model}")
    print(f"  Base Directory: {settings.base_dir}")
    print(f"  Max Depth: {settings.max_depth}")
    print(f"  Models Loaded: {len(settings.models)}")
    print(f"  Agents Config: {'Yes' if settings.agents_config else 'No'}")


def list_models(settings: Settings) -> None:
    """Print available models."""
    print("\nAvailable Models:")
    print("-" * 60)

    # Show models from providers if available
    if settings.providers.providers:
        index = 0
        for provider in settings.providers.providers.values():
            print(f"\n  [{provider.name}]")
            for model in provider.models:
                default = " [DEFAULT]" if model.default else ""
                print(f"    {index}: {model.name}{default}")
                print(f"       ID: {provider.id}:{model.id}")
                if model.description:
                    print(f"       {model.description}")
                index += 1
        print()
        return

    # Fall back to legacy models list
    if not settings.models:
        print("  No models configured")
        print("  Add models to .flavia/models.yaml or ~/.config/flavia/models.yaml")
        return

    for i, model in enumerate(settings.models):
        default = " [DEFAULT]" if model.default else ""
        print(f"  {i}: {model.name}{default}")
        print(f"     ID: {model.id}")
        if model.description:
            print(f"     {model.description}")
        print()


def list_tools_info() -> None:
    """Print available tools."""
    from flavia.tools import get_registry

    registry = get_registry()
    all_tools = registry.get_all()

    print("\nAvailable Tools:")
    print("-" * 60)

    categories: dict[str, list] = {}
    for tool in all_tools.values():
        # Skip setup tools in normal listing
        if tool.category == "setup":
            continue
        cat = tool.category
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(tool)

    for category, tool_list in sorted(categories.items()):
        print(f"\n[{category.upper()}]")
        for tool in tool_list:
            print(f"  {tool.name}")
            print(f"    {tool.description}")


def list_providers(settings: Settings) -> None:
    """Print configured providers."""
    from flavia.setup.provider_wizard import list_providers as _list_providers
    _list_providers(settings)


def test_provider_cli(settings: Settings, provider_id: str) -> int:
    """Test connection to a provider."""
    from flavia.setup.provider_wizard import test_provider_connection

    # Get provider to test
    if provider_id:
        provider = settings.providers.get_provider(provider_id)
        if not provider:
            print(f"Error: Provider '{provider_id}' not found")
            print("\nAvailable providers:")
            for pid in settings.providers.providers:
                print(f"  - {pid}")
            return 1
    else:
        provider = settings.providers.get_default_provider()
        if not provider:
            print("Error: No default provider configured")
            print("Run 'flavia --setup-provider' to configure providers")
            return 1

    print(f"\nTesting provider: {provider.name} ({provider.id})")
    print(f"  URL: {provider.api_base_url}")

    if not provider.api_key:
        print(f"\nError: API key not configured for {provider.name}")
        if provider.api_key_env_var:
            print(f"Set the {provider.api_key_env_var} environment variable")
        return 1

    # Get a model to test with
    model = provider.get_default_model()
    if not model:
        print("Error: No models configured for this provider")
        return 1

    print(f"  Model: {model.id}")
    print("\nConnecting...")

    success, message = test_provider_connection(
        provider.api_key,
        provider.api_base_url,
        model.id,
        provider.headers if provider.headers else None,
    )

    if success:
        print(f"\n[SUCCESS] {message}")
        return 0
    else:
        print(f"\n[FAILED] {message}")
        return 1


def main() -> int:
    """Main entry point."""
    ensure_project_venv_and_reexec(sys.argv[1:])

    args = parse_args()

    # Version
    if args.version:
        show_version()
        return 0

    # Init command - use setup wizard
    if args.init:
        from flavia.setup_wizard import run_setup_wizard
        success = run_setup_wizard()
        return 0 if success else 1

    # Setup provider wizard
    if args.setup_provider:
        from flavia.setup.provider_wizard import run_provider_wizard
        success = run_provider_wizard()
        return 0 if success else 1

    # Load settings
    settings = load_settings()
    settings = apply_args_to_settings(args, settings)

    # Config info
    if args.config:
        show_config_info(settings)
        return 0

    # Info commands
    if args.list_models:
        list_models(settings)
        return 0

    if args.list_tools:
        list_tools_info()
        return 0

    if args.list_providers:
        list_providers(settings)
        return 0

    if args.test_provider is not None:
        return test_provider_cli(settings, args.test_provider)

    # Check API key
    if not settings.api_key:
        print("Error: API key not configured")
        print("\nTo configure, either:")
        print("  1. Run 'flavia --init' and edit .flavia/.env")
        print("  2. Create ~/.config/flavia/.env")
        print("  3. Set SYNTHETIC_API_KEY environment variable")
        return 1

    # Run appropriate interface
    if args.telegram:
        from flavia.interfaces import run_telegram_bot
        run_telegram_bot(settings)
    else:
        from flavia.interfaces import run_cli
        run_cli(settings)

    return 0


if __name__ == "__main__":
    sys.exit(main())
