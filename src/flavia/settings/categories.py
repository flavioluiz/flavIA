"""Settings categories and definitions.

This module defines all configurable settings organized into categories,
with metadata for validation, display, and persistence.
"""

from dataclasses import dataclass, field
from typing import Any, Literal, Optional


SettingType = Literal["string", "int", "float", "bool", "choice"]


@dataclass
class SettingDefinition:
    """Definition of a single configurable setting."""

    # Environment variable name
    env_var: str

    # Display name for UI
    display_name: str

    # Help text describing the setting
    description: str

    # Value type for validation
    setting_type: SettingType

    # Default value
    default: Any

    # For numeric types: optional range constraints
    min_value: Optional[float] = None
    max_value: Optional[float] = None

    # For choice type: valid options
    choices: Optional[list[str]] = None

    # Whether to mask the value in display (for API keys)
    masked: bool = False


@dataclass
class SettingsCategory:
    """A category grouping related settings."""

    # Category identifier
    id: str

    # Display name
    name: str

    # Settings in this category
    settings: list[SettingDefinition] = field(default_factory=list)


# =============================================================================
# Settings Definitions by Category
# =============================================================================

MODEL_SETTINGS = SettingsCategory(
    id="models",
    name="Model Settings",
    settings=[
        SettingDefinition(
            env_var="DEFAULT_MODEL",
            display_name="Default Model",
            description="The default LLM model for conversations",
            setting_type="string",
            default="hf:moonshotai/Kimi-K2.5",
        ),
        SettingDefinition(
            env_var="SUMMARY_MODEL",
            display_name="Summary Model",
            description="Model for generating summaries (uses default if empty)",
            setting_type="string",
            default="",
        ),
        SettingDefinition(
            env_var="IMAGE_VISION_MODEL",
            display_name="Vision Model",
            description="Vision-capable model for image analysis",
            setting_type="string",
            default="synthetic:hf:moonshotai/Kimi-K2.5",
        ),
    ],
)

API_KEYS = SettingsCategory(
    id="api_keys",
    name="API Keys",
    settings=[
        SettingDefinition(
            env_var="MISTRAL_API_KEY",
            display_name="Mistral API Key",
            description="API key for Mistral provider",
            setting_type="string",
            default="",
            masked=True,
        ),
        SettingDefinition(
            env_var="SYNTHETIC_API_KEY",
            display_name="Synthetic API Key",
            description="API key for Synthetic provider",
            setting_type="string",
            default="",
            masked=True,
        ),
    ],
)

AGENT_PARAMETERS = SettingsCategory(
    id="agent",
    name="Agent Parameters",
    settings=[
        SettingDefinition(
            env_var="AGENT_COMPACT_THRESHOLD",
            display_name="Compact Threshold",
            description="Context utilization that triggers compaction warning",
            setting_type="float",
            default=0.9,
            min_value=0.0,
            max_value=1.0,
        ),
        SettingDefinition(
            env_var="AGENT_PARALLEL_WORKERS",
            display_name="Parallel Workers",
            description="Maximum number of parallel sub-agents",
            setting_type="int",
            default=4,
            min_value=1,
            max_value=16,
        ),
        SettingDefinition(
            env_var="AGENT_MAX_DEPTH",
            display_name="Max Depth",
            description="Maximum recursion depth for sub-agents",
            setting_type="int",
            default=3,
            min_value=1,
            max_value=10,
        ),
        SettingDefinition(
            env_var="MAX_ITERATIONS",
            display_name="Max Iterations",
            description="Maximum tool call iterations per turn",
            setting_type="int",
            default=20,
            min_value=1,
            max_value=100,
        ),
    ],
)

RAG_PARAMETERS = SettingsCategory(
    id="rag",
    name="RAG Parameters",
    settings=[
        SettingDefinition(
            env_var="RAG_CATALOG_ROUTER_K",
            display_name="Catalog Router K",
            description="Number of candidates for catalog routing",
            setting_type="int",
            default=20,
            min_value=0,
            max_value=500,
        ),
        SettingDefinition(
            env_var="RAG_VECTOR_K",
            display_name="Vector K",
            description="Number of vector search results",
            setting_type="int",
            default=15,
            min_value=0,
            max_value=500,
        ),
        SettingDefinition(
            env_var="RAG_FTS_K",
            display_name="FTS K",
            description="Number of full-text search results",
            setting_type="int",
            default=15,
            min_value=0,
            max_value=500,
        ),
        SettingDefinition(
            env_var="RAG_RRF_K",
            display_name="RRF K",
            description="Reciprocal Rank Fusion constant",
            setting_type="int",
            default=60,
            min_value=1,
            max_value=1000,
        ),
        SettingDefinition(
            env_var="RAG_MAX_CHUNKS_PER_DOC",
            display_name="Max Chunks/Doc",
            description="Maximum chunks returned per document",
            setting_type="int",
            default=3,
            min_value=1,
            max_value=50,
        ),
        SettingDefinition(
            env_var="RAG_CHUNK_MIN_TOKENS",
            display_name="Chunk Min Tokens",
            description="Minimum tokens per chunk",
            setting_type="int",
            default=300,
            min_value=50,
            max_value=2000,
        ),
        SettingDefinition(
            env_var="RAG_CHUNK_MAX_TOKENS",
            display_name="Chunk Max Tokens",
            description="Maximum tokens per chunk",
            setting_type="int",
            default=800,
            min_value=100,
            max_value=4000,
        ),
        SettingDefinition(
            env_var="RAG_DEBUG",
            display_name="Debug Mode",
            description="Enable RAG diagnostics capture",
            setting_type="bool",
            default=False,
        ),
        SettingDefinition(
            env_var="RAG_VIDEO_WINDOW_SECONDS",
            display_name="Video Window (s)",
            description="Temporal window for video retrieval in seconds",
            setting_type="int",
            default=60,
            min_value=5,
            max_value=600,
        ),
        SettingDefinition(
            env_var="RAG_EXPAND_VIDEO_TEMPORAL",
            display_name="Expand Video Temporal",
            description="Enable temporal expansion for video retrieval",
            setting_type="bool",
            default=True,
        ),
    ],
)

VISUAL_DISPLAY = SettingsCategory(
    id="display",
    name="Visual/Display",
    settings=[
        SettingDefinition(
            env_var="NO_COLOR",
            display_name="Disable Colors",
            description="Disable colored output",
            setting_type="bool",
            default=False,
        ),
        SettingDefinition(
            env_var="SHOW_TOKEN_USAGE",
            display_name="Show Token Usage",
            description="Display token usage after responses",
            setting_type="bool",
            default=True,
        ),
        SettingDefinition(
            env_var="STATUS_MAX_TASKS_MAIN",
            display_name="Status Max Tasks (Main)",
            description="Max tasks shown in main agent status (-1 = unlimited)",
            setting_type="int",
            default=-1,
            min_value=-1,
            max_value=100,
        ),
        SettingDefinition(
            env_var="STATUS_MAX_TASKS_SUBAGENT",
            display_name="Status Max Tasks (Sub)",
            description="Max tasks shown in sub-agent status (-1 = unlimited)",
            setting_type="int",
            default=-1,
            min_value=-1,
            max_value=100,
        ),
    ],
)

TIMEOUTS_LIMITS = SettingsCategory(
    id="timeouts",
    name="Timeouts & Limits",
    settings=[
        SettingDefinition(
            env_var="LLM_REQUEST_TIMEOUT",
            display_name="LLM Request Timeout",
            description="Request timeout for LLM calls (seconds)",
            setting_type="int",
            default=600,
            min_value=30,
            max_value=1800,
        ),
        SettingDefinition(
            env_var="LLM_CONNECT_TIMEOUT",
            display_name="Connection Timeout",
            description="Connection timeout for LLM calls (seconds)",
            setting_type="int",
            default=10,
            min_value=5,
            max_value=120,
        ),
        SettingDefinition(
            env_var="IMAGE_MAX_SIZE_MB",
            display_name="Image Max Size (MB)",
            description="Maximum image file size for vision analysis",
            setting_type="int",
            default=20,
            min_value=1,
            max_value=100,
        ),
        SettingDefinition(
            env_var="SUMMARY_MAX_LENGTH",
            display_name="Summary Max Length",
            description="Maximum character length for catalog summaries",
            setting_type="int",
            default=3000,
            min_value=500,
            max_value=10000,
        ),
    ],
)

# All categories in display order
SETTINGS_CATEGORIES: list[SettingsCategory] = [
    MODEL_SETTINGS,
    API_KEYS,
    AGENT_PARAMETERS,
    RAG_PARAMETERS,
    VISUAL_DISPLAY,
    TIMEOUTS_LIMITS,
]


def get_category_by_id(category_id: str) -> Optional[SettingsCategory]:
    """Get a category by its ID."""
    for category in SETTINGS_CATEGORIES:
        if category.id == category_id:
            return category
    return None


def get_setting_by_env_var(env_var: str) -> Optional[SettingDefinition]:
    """Find a setting definition by its environment variable name."""
    for category in SETTINGS_CATEGORIES:
        for setting in category.settings:
            if setting.env_var == env_var:
                return setting
    return None


def get_all_settings() -> list[SettingDefinition]:
    """Get all setting definitions across all categories."""
    result: list[SettingDefinition] = []
    for category in SETTINGS_CATEGORIES:
        result.extend(category.settings)
    return result
