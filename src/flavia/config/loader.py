"""Configuration file discovery and initialization."""

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Package defaults directory
PACKAGE_DIR = Path(__file__).parent.parent
DEFAULTS_DIR = PACKAGE_DIR / "defaults"


@dataclass
class ConfigPaths:
    """Discovered configuration paths."""

    # Directories
    local_dir: Optional[Path] = None  # .flavia/ in current directory
    user_dir: Optional[Path] = None  # ~/.config/flavia/
    package_dir: Path = DEFAULTS_DIR  # Package defaults

    # Specific files (resolved from directories)
    env_file: Optional[Path] = None
    models_file: Optional[Path] = None
    agents_file: Optional[Path] = None
    providers_file: Optional[Path] = None
    bots_file: Optional[Path] = None

    def __post_init__(self):
        """Resolve file paths from directories."""
        # Priority: local > user > package
        self.env_file = self._find_file(".env")
        self.models_file = self._find_file("models.yaml")
        self.agents_file = self._find_file("agents.yaml")
        self.providers_file = self._find_file("providers.yaml")
        self.bots_file = self._find_file("bots.yaml")

    def _find_file(self, filename: str) -> Optional[Path]:
        """Find a config file in priority order."""
        # Check local .flavia/ directory
        if self.local_dir:
            local_file = self.local_dir / filename
            if local_file.exists():
                return local_file

        # Check user directory
        if self.user_dir:
            user_file = self.user_dir / filename
            if user_file.exists():
                return user_file

        # Check package defaults
        if self.package_dir:
            package_file = self.package_dir / filename
            if package_file.exists():
                return package_file

        return None


def get_config_paths() -> ConfigPaths:
    """
    Discover configuration paths.

    Priority order (highest to lowest):
    1. .flavia/ in current directory
    2. ~/.config/flavia/
    3. Package defaults

    Returns:
        ConfigPaths with discovered locations
    """
    # Local directory
    local_dir = Path.cwd() / ".flavia"
    local_dir = local_dir if local_dir.exists() else None

    # User directory
    user_dir = Path.home() / ".config" / "flavia"
    user_dir = user_dir if user_dir.exists() else None

    return ConfigPaths(
        local_dir=local_dir,
        user_dir=user_dir,
        package_dir=DEFAULTS_DIR,
    )


def init_local_config(target_dir: Optional[Path] = None) -> bool:
    """
    Initialize local configuration in the specified or current directory.

    Creates .flavia/ directory with template configuration files.

    Args:
        target_dir: Directory to initialize (default: current directory)

    Returns:
        True if successful
    """
    if target_dir is None:
        target_dir = Path.cwd()

    config_dir = target_dir / ".flavia"

    # Check if already exists
    if config_dir.exists():
        print(f"Configuration already exists at {config_dir}")
        print("Delete it first if you want to reinitialize.")
        return False

    print(f"Initializing flavIA configuration in {config_dir}")

    try:
        # Create directory
        config_dir.mkdir(parents=True)

        # Create .env file (API keys are commented out to avoid overriding existing config)
        env_content = """\
# flavIA Local Configuration
# This file contains sensitive settings - do not commit to git!
# Uncomment and set values if not already configured elsewhere
# (e.g., in ~/.config/flavia/.env or environment variables)

# API Configuration
# SYNTHETIC_API_KEY=your_api_key_here
# API_BASE_URL=https://api.synthetic.new/openai/v1

# Agent defaults
# DEFAULT_MODEL=hf:moonshotai/Kimi-K2.5
# SUMMARY_MODEL=hf:moonshotai/Kimi-K2-Instruct-0905
# AGENT_MAX_DEPTH=3
# AGENT_PARALLEL_WORKERS=4

# Image analysis model (vision-capable)
# IMAGE_VISION_MODEL=synthetic:hf:moonshotai/Kimi-K2.5

# Academic search settings
# ACADEMIC_SEARCH_PROVIDER=openalex
# SEMANTIC_SCHOLAR_API_KEY=
# OPENALEX_EMAIL=your@email.com

# Telegram (only needed for flavia --telegram)
# TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
# Restrict bot access to specific Telegram user IDs (comma-separated)
# TELEGRAM_ALLOWED_USER_IDS=123456789
# Public mode without whitelist (optional)
# TELEGRAM_ALLOW_ALL_USERS=true
"""
        (config_dir / ".env").write_text(env_content)

        # Create models.yaml
        models_content = """\
# Available models for this project
# Reference by index (0, 1, 2...) or full ID

models:
  - id: "hf:moonshotai/Kimi-K2.5"
    name: "Kimi-K2.5"
    default: true
    description: "Moonshot AI Kimi K2.5"

  - id: "hf:zai-org/GLM-4.7"
    name: "GLM-4.7"
    description: "Zhipu AI GLM-4.7"

  - id: "hf:MiniMaxAI/MiniMax-M2.1"
    name: "MiniMax-M2.1"

  - id: "hf:moonshotai/Kimi-K2-Thinking"
    name: "Kimi-K2-Thinking"
    description: "With reasoning capability"
"""
        (config_dir / "models.yaml").write_text(models_content)

        # Create agents.yaml
        agents_content = """\
# Agent configuration for this project
# The 'main' agent is used by default

main:
  context: |
    You are a helpful assistant that can read and analyze files.
    You are working in the directory: {base_dir}
    Always be concise and precise in your responses.
    Use catalog-first workflow: summarize/query the catalog before reading many files.

  # Model to use (index or full ID)
  # model: 0

  # Context compaction threshold (0.0 to 1.0)
  # Triggers a compaction warning when context usage reaches this level
  # compact_threshold: 0.9

  # Access permissions (optional - defaults to full base_dir access)
  # permissions:
  #   read:
  #     - "."              # Relative to base_dir
  #     - "./docs"         # Subfolders
  #     - "/etc/configs"   # Absolute paths (outside project)
  #   write:
  #     - "./output"       # Write access (also grants read)
  #
  # Converted-content access policy:
  # strict: block direct .converted reads (RAG only)
  # hybrid: require search_chunks first, then allow direct fallback reads
  # open: allow direct .converted reads without RAG-first gating
  # converted_access_mode: hybrid
  #
  # Legacy compatibility (deprecated):
  # allow_converted_read: true   # maps to converted_access_mode: open

  # Tools available to this agent
  # Keep write-capable tools (write_*, compile_latex, refresh_catalog,
  # conversion/fetch tools) disabled unless
  # permissions.write is explicitly configured for this agent.
  tools:
    - read_file
    - list_files
    - search_files
    - get_file_info
    - query_catalog
    - search_chunks
    - get_catalog_summary
    - analyze_image
    - web_search
    - search_papers
    - compact_context
    - spawn_agent
    - spawn_predefined_agent

  # Predefined sub-agents for spawn_predefined_agent
  subagents:
    researcher:
      context: |
        You are a research specialist.
        Search thoroughly and report findings accurately.
        Start with catalog queries to shortlist relevant files.
      # Inherits permissions from parent if not specified
      tools:
        - read_file
        - list_files
        - search_files
        - query_catalog
        - web_search
        - search_papers

    summarizer:
      context: |
        You are a summarization specialist.
        Create clear, concise summaries.
        Use the catalog to find the most relevant files before reading.
      tools:
        - read_file
        - query_catalog
"""
        (config_dir / "agents.yaml").write_text(agents_content)

        # Create bots.yaml (commented-out example; empty bots falls back to env vars)
        bots_content = """\
# flavIA Bot Configuration
# Uncomment and edit to enable YAML-based bot config.
# Token secrets stay in .env; structural config lives here.
#
# Schema:
#   bots:
#     <bot-id>:
#       platform: telegram
#       token: "${TELEGRAM_BOT_TOKEN}"
#       default_agent: main
#       allowed_agents: [main, researcher]  # or "all" (default)
#       access:
#         allowed_users: [123456789]
#         allow_all: false
#
# Example (uncomment to activate):
# bots:
#   default:
#     platform: telegram
#     token: "${TELEGRAM_BOT_TOKEN}"
#     default_agent: main
#     allowed_agents: all
#     access:
#       allowed_users: []
#       allow_all: false

# Empty registry — falls back to TELEGRAM_BOT_TOKEN env var
bots: {}
"""
        (config_dir / "bots.yaml").write_text(bots_content)

        # Create .gitignore for the config dir
        gitignore_content = """\
# Ignore sensitive files
.env
*.env.local

# File backups created by write tools
file_backups/
"""
        (config_dir / ".gitignore").write_text(gitignore_content)

        print(f"\nCreated configuration files:")
        print(f"  {config_dir}/.env          - API keys and settings")
        print(f"  {config_dir}/models.yaml   - Available models")
        print(f"  {config_dir}/agents.yaml   - Agent definitions")
        print(f"  {config_dir}/bots.yaml     - Telegram/bot configuration")
        print(f"\nNext steps:")
        print(f"  1. Edit {config_dir}/.env and add your API key")
        print(f"  2. Run 'flavia' to start the CLI")
        print(f"\nTip: Add '.flavia/.env' to your project's .gitignore")

        return True

    except Exception as e:
        print(f"Error creating configuration: {e}")
        # Cleanup on failure
        if config_dir.exists():
            shutil.rmtree(config_dir)
        return False


def ensure_user_config() -> Path:
    """
    Ensure user config directory exists.

    Returns:
        Path to user config directory
    """
    user_dir = Path.home() / ".config" / "flavia"
    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir
