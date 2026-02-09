"""Tests for CLI wait feedback helpers."""

from flavia.interfaces.cli_interface import (
    LOADING_DOTS,
    LOADING_MESSAGES,
    _build_loading_line,
    _choose_loading_message,
)


def test_build_loading_line_cycles_dot_frames():
    message = "Mensagem de teste"
    for i, dots in enumerate(LOADING_DOTS):
        assert _build_loading_line(message, i).endswith(f"{message} {dots}")


def test_choose_loading_message_avoids_immediate_repeat(monkeypatch):
    if len(LOADING_MESSAGES) < 2:
        return

    current = LOADING_MESSAGES[0]
    monkeypatch.setattr(
        "flavia.interfaces.cli_interface.random.choice",
        lambda candidates: candidates[0],
    )

    selected = _choose_loading_message(current)
    assert selected != current
