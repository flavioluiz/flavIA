"""Tests for the WriteConfirmation mechanism."""

import pytest

from flavia.tools.write_confirmation import WriteConfirmation
from flavia.tools.write.preview import OperationPreview


class TestWriteConfirmation:
    def test_default_denies(self):
        """Without auto-approve or callback, confirm() returns False."""
        wc = WriteConfirmation()
        assert wc.confirm("Write file", "/tmp/x", "") is False

    def test_auto_approve_allows(self):
        wc = WriteConfirmation()
        wc.set_auto_approve(True)
        assert wc.confirm("Write file", "/tmp/x", "100 bytes") is True

    def test_auto_approve_disable(self):
        wc = WriteConfirmation()
        wc.set_auto_approve(True)
        assert wc.confirm("Write", "/tmp/x", "") is True
        wc.set_auto_approve(False)
        assert wc.confirm("Write", "/tmp/x", "") is False

    def test_callback_approve(self):
        calls = []

        def cb(op, path, details):
            calls.append((op, path, details))
            return True

        wc = WriteConfirmation()
        wc.set_callback(cb)
        assert wc.confirm("Delete file", "/path/f.txt", "42 bytes") is True
        assert len(calls) == 1
        assert calls[0] == ("Delete file", "/path/f.txt", "42 bytes")

    def test_callback_deny(self):
        wc = WriteConfirmation()
        wc.set_callback(lambda op, path, det: False)
        assert wc.confirm("Edit", "/f.txt", "") is False

    def test_callback_exception_denies(self):
        """If callback raises, confirm() returns False (fail-safe)."""

        def bad_callback(op, path, det):
            raise RuntimeError("boom")

        wc = WriteConfirmation()
        wc.set_callback(bad_callback)
        assert wc.confirm("Write", "/f.txt", "") is False

    def test_auto_approve_takes_precedence_over_callback(self):
        """Auto-approve bypasses the callback entirely."""
        wc = WriteConfirmation()
        wc.set_auto_approve(True)
        wc.set_callback(lambda op, path, det: False)
        assert wc.confirm("Write", "/f.txt", "") is True

    def test_clear_callback(self):
        wc = WriteConfirmation()
        wc.set_callback(lambda op, path, det: True)
        assert wc.confirm("Write", "/f.txt", "") is True
        wc.set_callback(None)
        # With no callback and no auto-approve, should deny.
        assert wc.confirm("Write", "/f.txt", "") is False

    def test_auto_approve_property(self):
        wc = WriteConfirmation()
        assert wc.auto_approve is False
        wc.set_auto_approve(True)
        assert wc.auto_approve is True


class TestWriteConfirmationWithPreview:
    """Tests for preview parameter support."""

    def test_callback_receives_preview(self):
        """Callback should receive the preview parameter."""
        received_preview = []

        def cb(op, path, details, preview=None):
            received_preview.append(preview)
            return True

        preview = OperationPreview(
            operation="write",
            path="/tmp/test.txt",
            content_preview="hello",
            content_bytes=5,
        )

        wc = WriteConfirmation()
        wc.set_callback(cb)
        assert wc.confirm("Write file", "/tmp/test.txt", "5 bytes", preview=preview)
        assert len(received_preview) == 1
        assert received_preview[0] is preview

    def test_callback_with_preview_none(self):
        """Callback should work when preview is None."""
        received_preview = []

        def cb(op, path, details, preview=None):
            received_preview.append(preview)
            return True

        wc = WriteConfirmation()
        wc.set_callback(cb)
        assert wc.confirm("Write file", "/tmp/test.txt", "5 bytes")
        assert len(received_preview) == 1
        assert received_preview[0] is None

    def test_backward_compatible_callback(self):
        """Old-style callbacks without preview parameter should still work."""
        calls = []

        def old_callback(op, path, details):
            calls.append((op, path, details))
            return True

        preview = OperationPreview(
            operation="edit",
            path="/tmp/test.txt",
            diff="--- a/test.txt\n+++ b/test.txt\n",
        )

        wc = WriteConfirmation()
        wc.set_callback(old_callback)
        # This should work via backward compatibility
        assert wc.confirm("Edit file", "/tmp/test.txt", "replacing", preview=preview)
        assert len(calls) == 1
        assert calls[0] == ("Edit file", "/tmp/test.txt", "replacing")

    def test_auto_approve_ignores_preview(self):
        """Auto-approve should work regardless of preview."""
        preview = OperationPreview(
            operation="delete",
            path="/tmp/test.txt",
            file_size=100,
        )

        wc = WriteConfirmation()
        wc.set_auto_approve(True)
        assert wc.confirm("Delete file", "/tmp/test.txt", "100 bytes", preview=preview)

    def test_callback_exception_with_preview_denies(self):
        """If callback raises with preview, operation is denied."""

        def bad_callback(op, path, details, preview=None):
            raise RuntimeError("boom")

        preview = OperationPreview(operation="write", path="/tmp/x")

        wc = WriteConfirmation()
        wc.set_callback(bad_callback)
        assert wc.confirm("Write", "/f.txt", "", preview=preview) is False
