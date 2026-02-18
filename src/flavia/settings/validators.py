"""Input validators for settings values.

Provides validation functions for different setting types with
clear error messages.
"""

from dataclasses import dataclass
from typing import Any, Optional, Sequence


@dataclass
class ValidationResult:
    """Result of a validation check."""

    valid: bool
    value: Any = None
    error: Optional[str] = None


def validate_int(
    value: str,
    min_value: Optional[int] = None,
    max_value: Optional[int] = None,
) -> ValidationResult:
    """Validate an integer value with optional range.

    Args:
        value: The input string to validate.
        min_value: Minimum allowed value (inclusive).
        max_value: Maximum allowed value (inclusive).

    Returns:
        ValidationResult with parsed int if valid, error message otherwise.
    """
    value = value.strip()
    if not value:
        return ValidationResult(valid=False, error="Value cannot be empty")

    try:
        parsed = int(value)
    except ValueError:
        return ValidationResult(valid=False, error=f"'{value}' is not a valid integer")

    if min_value is not None and parsed < min_value:
        return ValidationResult(
            valid=False,
            error=f"Value must be at least {min_value} (got {parsed})"
        )

    if max_value is not None and parsed > max_value:
        return ValidationResult(
            valid=False,
            error=f"Value must be at most {max_value} (got {parsed})"
        )

    return ValidationResult(valid=True, value=parsed)


def validate_float(
    value: str,
    min_value: Optional[float] = None,
    max_value: Optional[float] = None,
) -> ValidationResult:
    """Validate a float value with optional range.

    Args:
        value: The input string to validate.
        min_value: Minimum allowed value (inclusive).
        max_value: Maximum allowed value (inclusive).

    Returns:
        ValidationResult with parsed float if valid, error message otherwise.
    """
    value = value.strip()
    if not value:
        return ValidationResult(valid=False, error="Value cannot be empty")

    try:
        parsed = float(value)
    except ValueError:
        return ValidationResult(valid=False, error=f"'{value}' is not a valid number")

    if min_value is not None and parsed < min_value:
        return ValidationResult(
            valid=False,
            error=f"Value must be at least {min_value} (got {parsed})"
        )

    if max_value is not None and parsed > max_value:
        return ValidationResult(
            valid=False,
            error=f"Value must be at most {max_value} (got {parsed})"
        )

    return ValidationResult(valid=True, value=parsed)


def validate_bool(value: str) -> ValidationResult:
    """Validate a boolean value.

    Accepts: true, false, yes, no, 1, 0, on, off (case-insensitive).

    Args:
        value: The input string to validate.

    Returns:
        ValidationResult with parsed bool if valid, error message otherwise.
    """
    value = value.strip().lower()
    if not value:
        return ValidationResult(valid=False, error="Value cannot be empty")

    if value in ("true", "yes", "1", "on", "y"):
        return ValidationResult(valid=True, value=True)

    if value in ("false", "no", "0", "off", "n"):
        return ValidationResult(valid=True, value=False)

    return ValidationResult(
        valid=False,
        error=f"'{value}' is not a valid boolean (use true/false, yes/no, 1/0, on/off)"
    )


def validate_choice(value: str, choices: Sequence[str]) -> ValidationResult:
    """Validate a choice from a list of valid options.

    Args:
        value: The input string to validate.
        choices: List of valid choices.

    Returns:
        ValidationResult with the matching choice if valid, error message otherwise.
    """
    value = value.strip()
    if not value:
        return ValidationResult(valid=False, error="Value cannot be empty")

    # Case-insensitive matching
    value_lower = value.lower()
    for choice in choices:
        if choice.lower() == value_lower:
            return ValidationResult(valid=True, value=choice)

    choices_str = ", ".join(choices)
    return ValidationResult(
        valid=False,
        error=f"'{value}' is not a valid choice. Options: {choices_str}"
    )


def validate_string(
    value: str,
    min_length: Optional[int] = None,
    max_length: Optional[int] = None,
    allow_empty: bool = True,
) -> ValidationResult:
    """Validate a string value with optional length constraints.

    Args:
        value: The input string to validate.
        min_length: Minimum string length.
        max_length: Maximum string length.
        allow_empty: Whether empty strings are allowed.

    Returns:
        ValidationResult with the string if valid, error message otherwise.
    """
    if not allow_empty and not value:
        return ValidationResult(valid=False, error="Value cannot be empty")

    if min_length is not None and len(value) < min_length:
        return ValidationResult(
            valid=False,
            error=f"Value must be at least {min_length} characters"
        )

    if max_length is not None and len(value) > max_length:
        return ValidationResult(
            valid=False,
            error=f"Value must be at most {max_length} characters"
        )

    return ValidationResult(valid=True, value=value)


def format_bool_for_env(value: bool) -> str:
    """Format a boolean value for .env file."""
    return "true" if value else "false"


def format_value_for_env(value: Any, setting_type: str) -> str:
    """Format a value for .env file based on its type.

    Args:
        value: The value to format.
        setting_type: One of "string", "int", "float", "bool", "choice".

    Returns:
        String representation suitable for .env file.
    """
    if setting_type == "bool":
        return format_bool_for_env(value)
    return str(value)
