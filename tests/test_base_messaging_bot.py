"""Unit tests for BaseMessagingBot shared behaviors."""

from flavia.config.bots import BotConfig
from flavia.config.settings import Settings
from flavia.interfaces.base_bot import BaseMessagingBot


class _DummyBot(BaseMessagingBot):
    @property
    def platform_name(self) -> str:
        return "dummy"

    @property
    def max_message_length(self) -> int:
        return 5

    def run(self) -> None:
        return None

    def _send_message(self, user_id, message: str) -> None:
        _ = (user_id, message)

    def _send_file(self, user_id, file_action) -> None:
        _ = (user_id, file_action)


def _make_bot() -> _DummyBot:
    settings = Settings(
        agents_config={
            "main": {"model": "synthetic:hf:moonshotai/Kimi-K2.5"},
            "researcher": {"model": "synthetic:hf:moonshotai/Kimi-K2.5"},
        }
    )
    return _DummyBot(
        settings=settings,
        bot_config=BotConfig(
            id="dummy-bot",
            platform="telegram",
            token="tok",
            allowed_agents=["main", "researcher"],
        ),
    )


def test_chunk_text_uses_platform_limit():
    bot = _make_bot()
    assert bot._chunk_text("abcdefghij") == ["abcde", "fghij"]


def test_handle_default_commands_agents_and_switch():
    bot = _make_bot()
    user_id = 42

    listed = bot._handle_default_command("agents", user_id)
    assert listed is not None
    assert "- main (active)" in listed
    assert "- researcher" in listed

    switched = bot._handle_default_command("agent", user_id, "researcher")
    assert switched == "Switched to agent 'researcher'. Conversation has been reset."

    current = bot._handle_default_command("agent", user_id)
    assert current == "Current agent: researcher"


def test_log_event_falls_back_when_logger_attr_missing():
    bot = _DummyBot.__new__(_DummyBot)
    bot.settings = Settings()
    bot.bot_config = BotConfig(id="dummy-bot", platform="telegram", token="tok")
    bot.agents = {}
    bot._user_agents = {}

    # Regression guard: _log_event must not crash when tests instantiate via __new__.
    bot._log_event(user_id=1, action="smoke")
