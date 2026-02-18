"""Settings management module for flavIA.

Provides configuration persistence, validation, and category definitions
for the interactive /settings command.
"""

from .categories import (
    SETTINGS_CATEGORIES,
    SettingDefinition,
    SettingsCategory,
    get_all_settings,
    get_category_by_id,
    get_setting_by_env_var,
)
from .persistence import (
    SettingSource,
    get_global_env_path,
    get_local_env_path,
    get_setting_source,
    global_env_exists,
    local_env_exists,
    remove_from_env_file,
    write_to_env_file,
)
from .validators import (
    ValidationResult,
    format_bool_for_env,
    format_value_for_env,
    validate_bool,
    validate_choice,
    validate_float,
    validate_int,
    validate_string,
)

__all__ = [
    # Categories
    "SETTINGS_CATEGORIES",
    "SettingDefinition",
    "SettingsCategory",
    "get_all_settings",
    "get_category_by_id",
    "get_setting_by_env_var",
    # Persistence
    "SettingSource",
    "get_global_env_path",
    "get_local_env_path",
    "get_setting_source",
    "global_env_exists",
    "local_env_exists",
    "remove_from_env_file",
    "write_to_env_file",
    # Validators
    "ValidationResult",
    "format_bool_for_env",
    "format_value_for_env",
    "validate_bool",
    "validate_choice",
    "validate_float",
    "validate_int",
    "validate_string",
]
