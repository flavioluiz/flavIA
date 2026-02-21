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


def test_token_env_var_for_bot_name_supports_multiple_bots():
    assert telegram_wizard._token_env_var_for_bot_name("default") == "TELEGRAM_BOT_TOKEN"
    assert (
        telegram_wizard._token_env_var_for_bot_name("ironic-bot")
        == "TELEGRAM_BOT_TOKEN_IRONIC_BOT"
    )
    assert (
        telegram_wizard._token_env_var_for_bot_name("Research Bot 2")
        == "TELEGRAM_BOT_TOKEN_RESEARCH_BOT_2"
    )


def test_write_bots_yaml_uses_bot_specific_token_env_var(tmp_path):
    cfg = tmp_path / ".flavia"
    cfg.mkdir(parents=True, exist_ok=True)

    bots_path = telegram_wizard._write_bots_yaml(
        cfg,
        bot_name="ironic-bot",
        token_env_var="TELEGRAM_BOT_TOKEN_IRONIC_BOT",
        user_ids=[123],
        allow_all=False,
    )
    content = bots_path.read_text(encoding="utf-8")

    assert "${TELEGRAM_BOT_TOKEN_IRONIC_BOT}" in content
    assert "ironic-bot:" in content


def test_update_env_file_preserves_existing_other_bot_tokens(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("TELEGRAM_BOT_TOKEN=old-default\n", encoding="utf-8")

    telegram_wizard._update_env_file(
        env_path,
        {
            "TELEGRAM_BOT_TOKEN_IRONIC_BOT": "new-ironic-token",
        },
    )
    content = env_path.read_text(encoding="utf-8")

    assert "TELEGRAM_BOT_TOKEN=old-default" in content
    assert "TELEGRAM_BOT_TOKEN_IRONIC_BOT=new-ironic-token" in content
