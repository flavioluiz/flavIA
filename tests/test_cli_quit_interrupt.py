"""Tests for CLI exit behavior after interrupted agent execution."""

import threading

from flavia.config.settings import Settings
from flavia.interfaces import cli_interface


class _DummyAgent:
    provider = None
    model_id = "dummy-model"

    def run(self, _user_message: str) -> str:
        return "ok"


def test_cli_quit_exits_after_keyboard_interrupt_during_agent_run(monkeypatch, tmp_path):
    """CLI should exit cleanly on /quit after an interrupted agent run."""
    settings = Settings(base_dir=tmp_path)
    input_iter = iter(["run a complex task", "/quit"])
    printed: list[str] = []
    run_calls: list[bool] = []

    monkeypatch.setattr(cli_interface, "print_welcome", lambda _settings: None)
    monkeypatch.setattr(cli_interface, "_configure_prompt_history", lambda _history_file: False)
    monkeypatch.setattr(cli_interface, "_print_active_model_hint", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        cli_interface,
        "_read_user_input",
        lambda _history_enabled, _active_agent=None: next(input_iter),
    )
    monkeypatch.setattr(cli_interface, "create_agent_from_settings", lambda _settings: _DummyAgent())
    monkeypatch.setattr(cli_interface, "_append_prompt_history", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli_interface, "_append_chat_log", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        cli_interface.console,
        "print",
        lambda *args, **_kwargs: printed.append(" ".join(str(a) for a in args)),
    )

    def _fake_run_agent_with_feedback(*_args, **_kwargs):
        run_calls.append(True)
        raise KeyboardInterrupt()

    monkeypatch.setattr(cli_interface, "_run_agent_with_feedback", _fake_run_agent_with_feedback)

    thread = threading.Thread(target=cli_interface.run_cli, args=(settings,), daemon=True)
    thread.start()
    thread.join(timeout=2.0)

    assert not thread.is_alive()
    assert run_calls == [True]
    assert any("Goodbye!" in line for line in printed)
