"""Regression tests for Telegram setup wizard flows."""

from flavia.setup import telegram_wizard


def test_prompt_telegram_setup_handles_non_interactive_stdin(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setattr(
        "flavia.setup.telegram_wizard.safe_confirm",
        lambda *args, **kwargs: (_ for _ in ()).throw(EOFError()),
    )

    assert telegram_wizard.prompt_telegram_setup_if_needed() is False


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
