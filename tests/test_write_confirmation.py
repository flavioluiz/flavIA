"""Tests for the WriteConfirmation mechanism."""

import pytest

from flavia.tools.write_confirmation import WriteConfirmation


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
