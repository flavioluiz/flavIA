"""Settings management for flavIA."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml
from dotenv import load_dotenv

from .loader import get_config_paths, ConfigPaths
from .providers import (
    ProviderConfig,
    ProviderRegistry,
    load_providers_from_file,
    create_fallback_provider,
    merge_providers,
)


@dataclass
class ModelConfig:
    """Configuration for a single model."""

    id: str
    name: str
    description: str = ""
    default: bool = False


@dataclass
class Settings:
    """Application settings loaded from environment and config files."""

    # API settings
    api_key: str = ""
    api_base_url: str = "https://api.synthetic.new/openai/v1"

    # Paths
    base_dir: Path = field(default_factory=Path.cwd)
    config_paths: Optional[ConfigPaths] = None

    # Agent defaults
    default_model: str = "hf:moonshotai/Kimi-K2.5"
    summary_model: Optional[str] = None  # Optional override used for catalog summaries
    image_vision_model: Optional[str] = None  # Vision-capable model for image analysis
    max_depth: int = 3
    compact_threshold: float = 0.9
    compact_threshold_configured: bool = False
    parallel_workers: int = 4
    subagents_enabled: bool = True
    active_agent: Optional[str] = None  # None means "main"; can be a subagent name

    # Telegram settings
    telegram_token: str = ""
    telegram_allowed_users: list[int] = field(default_factory=list)
    telegram_allow_all_users: bool = False
    telegram_whitelist_configured: bool = False

    # Runtime
    verbose: bool = False
    dry_run: bool = False
    rag_debug: bool = False

    # RAG/retrieval tuning
    rag_catalog_router_k: int = 20
    rag_vector_k: int = 15
    rag_fts_k: int = 15
    rag_rrf_k: int = 60
    rag_max_chunks_per_doc: int = 3
    rag_chunk_min_tokens: int = 300
    rag_chunk_max_tokens: int = 800
    rag_video_window_seconds: int = 60
    rag_expand_video_temporal: bool = True

    # Status display settings (-1 = unlimited)
    status_max_tasks_main: int = -1
    status_max_tasks_subagent: int = -1

    # Timeouts and limits
    max_iterations: int = 20  # Max tool call iterations per agent turn
    llm_request_timeout: int = 600  # LLM request timeout in seconds
    llm_connect_timeout: int = 10  # LLM connection timeout in seconds
    image_max_size_mb: int = 20  # Max image size for vision analysis
    summary_max_length: int = 3000  # Max length for catalog summaries

    # Display settings
    show_token_usage: bool = True  # Show token usage after responses
    color_theme: str = "default"  # Color theme: default, light, minimal
    timestamp_format: str = "iso"  # Timestamp format: iso, relative, local
    log_level: str = "warning"  # Log level: debug, info, warning, error

    # Web search settings
    web_search_provider: str = "duckduckgo"
    google_search_api_key: str = ""
    google_search_cx: str = ""
    brave_search_api_key: str = ""
    bing_search_api_key: str = ""

    # Content processing settings
    ocr_min_chars_per_page: int = 50  # Minimum characters per page for OCR
    transcription_timeout: int = 600  # Timeout for transcription in seconds
    embedder_batch_size: int = 64  # Batch size for embedding
    latex_timeout: int = 120  # Timeout for LaTeX compilation in seconds

    # Loaded configs
    models: list[ModelConfig] = field(default_factory=list)
    agents_config: dict[str, Any] = field(default_factory=dict)

    # Provider registry (new multi-provider system)
    providers: ProviderRegistry = field(default_factory=ProviderRegistry)

    def get_model_by_index(self, index: int) -> Optional[ModelConfig]:
        """Get model by index."""
        if 0 <= index < len(self.models):
            return self.models[index]
        return None

    def get_model_by_id(self, model_id: str) -> Optional[ModelConfig]:
        """Get model by ID."""
        for model in self.models:
            if model.id == model_id:
                return model
        return None

    def get_default_model(self) -> Optional[ModelConfig]:
        """Get the default model."""
        for model in self.models:
            if model.default:
                return model
        return self.models[0] if self.models else None

    def resolve_model(self, model_ref: str | int) -> str:
        """Resolve model reference (index or ID) to model ID."""
        if isinstance(model_ref, int):
            model = self.get_model_by_index(model_ref)
            return model.id if model else self.default_model
        return model_ref

    def resolve_model_with_provider(
        self, model_ref: str | int
    ) -> tuple[Optional[ProviderConfig], str]:
        """
        Resolve model reference to provider and model ID.

        Args:
            model_ref: Model reference (index, model_id, or provider:model_id)

        Returns:
            Tuple of (ProviderConfig, model_id). Provider may be None if using
            legacy config without providers.yaml.
        """
        # Try provider registry first
        if self.providers.providers:
            provider, model = self.providers.resolve_model(model_ref)
            if model:
                return provider, model.id
            # Model not found in registry, fall back
            if provider:
                return provider, self.resolve_model(model_ref)

        # Fall back to legacy resolution
        return None, self.resolve_model(model_ref)


def load_models(models_file: Optional[Path]) -> list[ModelConfig]:
    """Load models from YAML file."""
    if not models_file or not models_file.exists():
        return []

    try:
        with open(models_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        models = []
        for m in data.get("models", []):
            models.append(
                ModelConfig(
                    id=m["id"],
                    name=m.get("name", m["id"]),
                    description=m.get("description", ""),
                    default=m.get("default", False),
                )
            )
        return models
    except Exception:
        return []


def load_agents_config(agents_file: Optional[Path]) -> dict[str, Any]:
    """Load agents configuration from YAML file."""
    if not agents_file or not agents_file.exists():
        return {}

    try:
        with open(agents_file, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def load_providers(paths: ConfigPaths) -> ProviderRegistry:
    """
    Load providers from all config locations and merge them.

    Priority (later takes precedence):
    1. Package defaults
    2. User config
    3. Local config
    """
    registries: list[ProviderRegistry] = []

    # Load from package defaults
    if paths.package_dir:
        package_providers = paths.package_dir / "providers.yaml"
        if package_providers.exists():
            registries.append(load_providers_from_file(package_providers))

    # Load from user config
    if paths.user_dir:
        user_providers = paths.user_dir / "providers.yaml"
        if user_providers.exists():
            registries.append(load_providers_from_file(user_providers))

    # Load from local config (highest priority)
    if paths.local_dir:
        local_providers = paths.local_dir / "providers.yaml"
        if local_providers.exists():
            registries.append(load_providers_from_file(local_providers))

    if not registries:
        return ProviderRegistry()

    return merge_providers(*registries)


def load_settings() -> Settings:
    """
    Load settings from all configuration sources.

    Priority (highest to lowest):
    1. Environment variables (including from .env files)
    2. Local .flavia/ directory
    3. User ~/.config/flavia/ directory
    4. Package defaults
    """
    # Discover config paths
    paths = get_config_paths()

    # Load .env file (local takes priority)
    if paths.env_file:
        load_dotenv(paths.env_file, override=True)

    # Parse Telegram access controls
    allow_all_raw = os.getenv("TELEGRAM_ALLOW_ALL_USERS", "").strip().lower()
    allow_all_users = allow_all_raw in {"1", "true", "yes", "y", "on"}

    allowed_users_env = os.getenv("TELEGRAM_ALLOWED_USER_IDS")
    allowed_users_str = (allowed_users_env or "").strip()
    whitelist_configured = bool(allowed_users_str)
    allowed_users = []
    if allowed_users_str.lower() in {"*", "all", "public"}:
        allow_all_users = True
        whitelist_configured = False
    elif allowed_users_str:
        for uid in allowed_users_str.split(","):
            uid = uid.strip()
            if not uid:
                continue
            try:
                allowed_users.append(int(uid))
            except ValueError:
                continue

    # Load providers from providers.yaml (new multi-provider system)
    providers = load_providers(paths)

    # Get API settings - prefer from providers if available
    api_key = os.getenv("SYNTHETIC_API_KEY", "")
    api_base_url = os.getenv("API_BASE_URL", "https://api.synthetic.new/openai/v1")
    default_model = os.getenv("DEFAULT_MODEL", "hf:moonshotai/Kimi-K2.5")
    summary_model = os.getenv("SUMMARY_MODEL", "").strip() or None
    image_vision_model = os.getenv("IMAGE_VISION_MODEL", "").strip() or None
    compact_threshold, compact_threshold_configured = _load_compact_threshold_from_env()
    rag_debug = _load_bool_env("RAG_DEBUG", default=False)

    # If no providers loaded but we have env vars, create fallback provider
    if not providers.providers and api_key:
        fallback = create_fallback_provider(api_key, api_base_url, default_model)
        providers = ProviderRegistry(
            providers={"default": fallback},
            default_provider_id="default",
        )

    # Use provider's API settings if available
    default_provider = providers.get_default_provider()
    if default_provider and default_provider.api_key:
        api_key = default_provider.api_key
        api_base_url = default_provider.api_base_url

    # Build settings
    settings = Settings(
        api_key=api_key,
        api_base_url=api_base_url,
        base_dir=Path.cwd(),  # Always use current directory as base
        config_paths=paths,
        default_model=default_model,
        summary_model=summary_model,
        image_vision_model=image_vision_model,
        max_depth=int(os.getenv("AGENT_MAX_DEPTH", "3")),
        compact_threshold=compact_threshold,
        compact_threshold_configured=compact_threshold_configured,
        parallel_workers=int(os.getenv("AGENT_PARALLEL_WORKERS", "4")),
        telegram_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
        telegram_allowed_users=allowed_users,
        telegram_allow_all_users=allow_all_users,
        telegram_whitelist_configured=whitelist_configured,
        providers=providers,
        status_max_tasks_main=int(os.getenv("STATUS_MAX_TASKS_MAIN", "-1")),
        status_max_tasks_subagent=int(os.getenv("STATUS_MAX_TASKS_SUBAGENT", "-1")),
        rag_debug=rag_debug,
        rag_catalog_router_k=_load_int_env(
            "RAG_CATALOG_ROUTER_K", default=20, minimum=0, maximum=500
        ),
        rag_vector_k=_load_int_env("RAG_VECTOR_K", default=15, minimum=0, maximum=500),
        rag_fts_k=_load_int_env("RAG_FTS_K", default=15, minimum=0, maximum=500),
        rag_rrf_k=_load_int_env("RAG_RRF_K", default=60, minimum=1, maximum=1000),
        rag_max_chunks_per_doc=_load_int_env(
            "RAG_MAX_CHUNKS_PER_DOC", default=3, minimum=1, maximum=50
        ),
        rag_chunk_min_tokens=_load_int_env(
            "RAG_CHUNK_MIN_TOKENS", default=300, minimum=50, maximum=2000
        ),
        rag_chunk_max_tokens=_load_int_env(
            "RAG_CHUNK_MAX_TOKENS", default=800, minimum=100, maximum=4000
        ),
        rag_video_window_seconds=_load_int_env(
            "RAG_VIDEO_WINDOW_SECONDS", default=60, minimum=5, maximum=600
        ),
        rag_expand_video_temporal=_load_bool_env("RAG_EXPAND_VIDEO_TEMPORAL", default=True),
        # Timeouts and limits
        max_iterations=_load_int_env("MAX_ITERATIONS", default=20, minimum=1, maximum=100),
        llm_request_timeout=_load_int_env(
            "LLM_REQUEST_TIMEOUT", default=600, minimum=30, maximum=1800
        ),
        llm_connect_timeout=_load_int_env(
            "LLM_CONNECT_TIMEOUT", default=10, minimum=5, maximum=120
        ),
        image_max_size_mb=_load_int_env("IMAGE_MAX_SIZE_MB", default=20, minimum=1, maximum=100),
        summary_max_length=_load_int_env(
            "SUMMARY_MAX_LENGTH", default=3000, minimum=500, maximum=10000
        ),
        # Display settings
        show_token_usage=_load_bool_env("SHOW_TOKEN_USAGE", default=True),
        color_theme=os.getenv("COLOR_THEME", "default"),
        timestamp_format=os.getenv("TIMESTAMP_FORMAT", "iso"),
        log_level=os.getenv("LOG_LEVEL", "warning"),
        # Web search settings
        web_search_provider=os.getenv("WEB_SEARCH_PROVIDER", "duckduckgo"),
        google_search_api_key=os.getenv("GOOGLE_SEARCH_API_KEY", ""),
        google_search_cx=os.getenv("GOOGLE_SEARCH_CX", ""),
        brave_search_api_key=os.getenv("BRAVE_SEARCH_API_KEY", ""),
        bing_search_api_key=os.getenv("BING_SEARCH_API_KEY", ""),
        # Content processing settings
        ocr_min_chars_per_page=_load_int_env(
            "OCR_MIN_CHARS_PER_PAGE", default=50, minimum=1, maximum=1000
        ),
        transcription_timeout=_load_int_env(
            "TRANSCRIPTION_TIMEOUT", default=600, minimum=60, maximum=3600
        ),
        embedder_batch_size=_load_int_env(
            "EMBEDDER_BATCH_SIZE", default=64, minimum=1, maximum=256
        ),
        latex_timeout=_load_int_env("LATEX_TIMEOUT", default=120, minimum=30, maximum=600),
    )

    # Load models and agents config
    settings.models = load_models(paths.models_file)
    settings.agents_config = load_agents_config(paths.agents_file)

    # If no models loaded, use defaults
    if not settings.models:
        settings.models = [
            ModelConfig(
                id="hf:moonshotai/Kimi-K2.5",
                name="Kimi-K2.5",
                default=True,
            )
        ]

    return settings


def _load_compact_threshold_from_env() -> tuple[float, bool]:
    """Load global compact threshold from environment.

    Uses ``AGENT_COMPACT_THRESHOLD`` when valid, otherwise returns default (0.9).
    """
    raw = os.getenv("AGENT_COMPACT_THRESHOLD", "").strip()
    if not raw:
        return 0.9, False

    try:
        threshold = float(raw)
    except ValueError:
        return 0.9, False

    if 0.0 <= threshold <= 1.0:
        return threshold, True
    return 0.9, False


def _load_bool_env(name: str, default: bool) -> bool:
    """Parse a boolean environment variable."""
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    if raw in {"1", "true", "yes", "y", "on"}:
        return True
    if raw in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _load_int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    """Parse bounded integer env var with fallback to default."""
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    if value < minimum or value > maximum:
        return default
    return value


# Global settings instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get or create global settings instance."""
    global _settings
    if _settings is None:
        _settings = load_settings()
    return _settings


def reset_settings() -> None:
    """Reset global settings (useful for testing or directory change)."""
    global _settings
    _settings = None
