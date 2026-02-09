"""Tests for project-local CLI prompt/chat history helpers."""

import json

from flavia.interfaces import cli_interface


def test_history_paths_create_project_local_files_dir(tmp_path):
    prompt_file, chat_file = cli_interface._history_paths(tmp_path)

    assert prompt_file == tmp_path / ".flavia" / ".prompt_history"
    assert chat_file == tmp_path / ".flavia" / "chat_history.jsonl"
    assert (tmp_path / ".flavia").exists()


def test_append_chat_log_preserves_unicode(tmp_path):
    log_file = tmp_path / ".flavia" / "chat_history.jsonl"
    log_file.parent.mkdir(parents=True, exist_ok=True)

    cli_interface._append_chat_log(
        log_file,
        "user",
        "Você está comparando pós-graduação?",
        model_ref="openai:gpt-4o",
    )

    line = log_file.read_text(encoding="utf-8").strip()
    entry = json.loads(line)

    assert entry["role"] == "user"
    assert entry["model"] == "openai:gpt-4o"
    assert "Você" in entry["content"]
    assert "\\u00ea" not in line


def test_append_prompt_history_skips_duplicate_last_entry(monkeypatch, tmp_path):
    history_file = tmp_path / ".flavia" / ".prompt_history"
    history_file.parent.mkdir(parents=True, exist_ok=True)
    events = {"added": [], "written": 0}

    class FakeReadline:
        def get_current_history_length(self):
            return 1

        def get_history_item(self, index):
            _ = index
            return "repeat me"

        def add_history(self, text):
            events["added"].append(text)

        def write_history_file(self, path):
            _ = path
            events["written"] += 1

    monkeypatch.setattr(cli_interface, "_readline", FakeReadline())

    cli_interface._append_prompt_history("repeat me", history_file, history_enabled=True)
    assert events["added"] == []
    assert events["written"] == 0

    cli_interface._append_prompt_history("new query", history_file, history_enabled=True)
    assert events["added"] == ["new query"]
    assert events["written"] == 1
