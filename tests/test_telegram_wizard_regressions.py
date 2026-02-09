"""Regression tests for Telegram setup wizard flows."""

from flavia.setup import telegram_wizard


def test_prompt_telegram_setup_handles_non_interactive_stdin(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    called = {"wizard": False}

    class _NonInteractiveStdin:
        def isatty(self) -> bool:
            return False

    def _run_wizard(*args, **kwargs):
        _ = args, kwargs
        called["wizard"] = True
        return True

    monkeypatch.setattr("flavia.setup.telegram_wizard.sys.stdin", _NonInteractiveStdin())
    monkeypatch.setattr("flavia.setup.telegram_wizard.run_telegram_wizard", _run_wizard)

    assert telegram_wizard.prompt_telegram_setup_if_needed() is False
    assert called["wizard"] is False


def test_run_telegram_wizard_returns_false_without_interactive_stdin(monkeypatch):
    class _NonInteractiveStdin:
        def isatty(self) -> bool:
            return False

    monkeypatch.setattr("flavia.setup.telegram_wizard.sys.stdin", _NonInteractiveStdin())

    assert telegram_wizard.run_telegram_wizard() is False


def test_test_bot_token_masks_token_in_connection_errors(monkeypatch):
    token = "123456:super-secret-token"

    class FakeHttpx:
        @staticmethod
        def get(url, timeout):  # pragma: no cover - interface shim
            raise RuntimeError(f"failed request to {url}")

    monkeypatch.setitem(__import__("sys").modules, "httpx", FakeHttpx)

    success, message = telegram_wizard.test_bot_token(token)

    assert success is False
    assert token not in message
    assert "***" in message
