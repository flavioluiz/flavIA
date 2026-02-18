"""Tests for /settings interactive command helpers."""

from flavia.interfaces import settings_command
from flavia.settings.categories import SettingDefinition
from flavia.settings.persistence import SettingSource


class _DummyConsole:
    def __init__(self):
        self.printed: list[str] = []

    def print(self, *args, **kwargs):
        self.printed.append(" ".join(str(a) for a in args))


def test_edit_masked_setting_does_not_echo_secret(monkeypatch, tmp_path):
    setting = SettingDefinition(
        env_var="SYNTHETIC_API_KEY",
        display_name="Synthetic API Key",
        description="API key for provider",
        setting_type="string",
        default="",
        masked=True,
    )

    prompts = iter(["super-secret-token", "1"])
    monkeypatch.setattr(settings_command, "safe_prompt", lambda *_a, **_k: next(prompts))
    monkeypatch.setattr(
        settings_command,
        "get_setting_source",
        lambda *_a, **_k: SettingSource(value="", source="default"),
    )
    monkeypatch.setattr(settings_command, "get_local_env_path", lambda: tmp_path / ".flavia" / ".env")

    writes: dict[str, str] = {}

    def _fake_write_to_env_file(_env_file, env_var, value):
        writes["env_var"] = env_var
        writes["value"] = value
        return True

    monkeypatch.setattr(settings_command, "write_to_env_file", _fake_write_to_env_file)

    console = _DummyConsole()
    changed = settings_command._edit_setting(console, setting)

    assert changed is True
    assert writes == {"env_var": "SYNTHETIC_API_KEY", "value": "super-secret-token"}

    output = "\n".join(console.printed)
    assert "super-secret-token" not in output
    assert "SYNTHETIC_API_KEY=" in output
    assert "*" in output
