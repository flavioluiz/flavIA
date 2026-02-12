"""Write confirmation mechanism for flavIA write tools.

Provides a confirmation gate that write tools must pass before executing
destructive operations. Supports three modes:

1. Auto-approve: all operations are approved without user interaction
2. Callback: a callable is invoked to ask the user for confirmation
3. Fail-safe: if neither is configured, operations are denied
"""

from inspect import Parameter, signature
from typing import Callable, Literal, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from flavia.tools.write.preview import OperationPreview


# Type alias for confirmation callbacks.
# Signature: (operation, path, details, preview) -> approved
# The preview parameter is optional for backward compatibility.
WriteConfirmationCallback = Callable[[str, str, str, Optional["OperationPreview"]], bool]


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
        self._callback_preview_mode: Literal["none", "positional", "keyword"] = "none"

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
            callback: A callable ``(operation, path, details, preview) -> bool``.
                      Return ``True`` to approve, ``False`` to deny.
                      Pass ``None`` to clear the callback.
        """
        self._callback = callback
        self._callback_preview_mode = self._detect_preview_mode(callback)

    @staticmethod
    def _detect_preview_mode(
        callback: Optional[WriteConfirmationCallback],
    ) -> Literal["none", "positional", "keyword"]:
        """Detect how a callback accepts preview data.

        Returns:
            - ``"positional"`` if callback accepts 4th positional arg.
            - ``"keyword"`` if callback accepts ``preview=...`` keyword.
            - ``"none"`` if callback appears to be legacy 3-arg signature.
        """
        if callback is None:
            return "none"

        try:
            sig = signature(callback)
        except (TypeError, ValueError):
            # If introspection is unavailable, default to legacy mode
            # to avoid accidentally retrying callbacks.
            return "none"

        # *args accepts preview positionally.
        if any(p.kind == Parameter.VAR_POSITIONAL for p in sig.parameters.values()):
            return "positional"

        positional_params = [
            p
            for p in sig.parameters.values()
            if p.kind in (Parameter.POSITIONAL_ONLY, Parameter.POSITIONAL_OR_KEYWORD)
        ]
        if len(positional_params) >= 4:
            return "positional"

        preview_param = sig.parameters.get("preview")
        if preview_param and preview_param.kind in (
            Parameter.POSITIONAL_OR_KEYWORD,
            Parameter.KEYWORD_ONLY,
        ):
            return "keyword"

        return "none"

    def confirm(
        self,
        operation: str,
        path: str,
        details: str = "",
        preview: Optional["OperationPreview"] = None,
    ) -> bool:
        """Request confirmation for a write operation.

        Args:
            operation: Short description of the operation
                       (e.g. ``"Write file"``, ``"Delete file"``).
            path: The target path being modified.
            details: Optional extra context shown to the user (e.g.
                     number of bytes, lines affected).
            preview: Optional detailed preview of the operation,
                     including diffs, content previews, etc.

        Returns:
            ``True`` if the operation is approved, ``False`` otherwise.
        """
        if self._auto_approve:
            return True

        if self._callback is not None:
            try:
                if self._callback_preview_mode == "positional":
                    return self._callback(operation, path, details, preview)
                if self._callback_preview_mode == "keyword":
                    return self._callback(operation, path, details, preview=preview)
                return self._callback(operation, path, details)  # type: ignore[call-arg]
            except Exception:
                # If the callback itself fails, deny the operation.
                return False

        # No auto-approve and no callback: fail-safe deny.
        return False
