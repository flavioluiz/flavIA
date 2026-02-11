"""Write confirmation mechanism for flavIA write tools.

Provides a confirmation gate that write tools must pass before executing
destructive operations. Supports three modes:

1. Auto-approve: all operations are approved without user interaction
2. Callback: a callable is invoked to ask the user for confirmation
3. Fail-safe: if neither is configured, operations are denied
"""

from typing import Callable, Optional


# Type alias for confirmation callbacks.
# Signature: (operation, path, details) -> approved
WriteConfirmationCallback = Callable[[str, str, str], bool]


class WriteConfirmation:
    """Manages write operation confirmations.

    Write tools call :meth:`confirm` before executing any destructive
    operation.  The confirmation can be auto-approved (for batch/CI
    workflows) or delegated to a user-facing callback (CLI prompt,
    Telegram inline keyboard, etc.).

    If neither auto-approve nor a callback is configured, confirmation
    is **denied** by default (fail-safe).
    """

    def __init__(self) -> None:
        self._auto_approve: bool = False
        self._callback: Optional[WriteConfirmationCallback] = None

    @property
    def auto_approve(self) -> bool:
        """Whether all write operations are automatically approved."""
        return self._auto_approve

    def set_auto_approve(self, value: bool) -> None:
        """Enable or disable automatic approval of all write operations."""
        self._auto_approve = value

    def set_callback(self, callback: Optional[WriteConfirmationCallback]) -> None:
        """Set the confirmation callback.

        Args:
            callback: A callable ``(operation, path, details) -> bool``.
                      Return ``True`` to approve, ``False`` to deny.
                      Pass ``None`` to clear the callback.
        """
        self._callback = callback

    def confirm(self, operation: str, path: str, details: str = "") -> bool:
        """Request confirmation for a write operation.

        Args:
            operation: Short description of the operation
                       (e.g. ``"Write file"``, ``"Delete file"``).
            path: The target path being modified.
            details: Optional extra context shown to the user (e.g.
                     number of bytes, lines affected).

        Returns:
            ``True`` if the operation is approved, ``False`` otherwise.
        """
        if self._auto_approve:
            return True

        if self._callback is not None:
            try:
                return self._callback(operation, path, details)
            except Exception:
                # If the callback itself fails, deny the operation.
                return False

        # No auto-approve and no callback: fail-safe deny.
        return False
