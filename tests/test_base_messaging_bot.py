"""Unit tests for BaseMessagingBot shared behaviors."""

import asyncio

from flavia.config.bots import BotConfig
from flavia.config.settings import Settings
from flavia.interfaces.base_bot import BaseMessagingBot, BotResponse, SendFileAction


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


def test_handle_default_command_compact_reports_distinct_before_after_values():
    class _CompactAgent:
        def __init__(self):
            self.last_prompt_tokens = 900
            self.max_context_tokens = 1000

        @property
        def context_utilization(self) -> float:
            return self.last_prompt_tokens / self.max_context_tokens

        def compact_conversation(self) -> str:
            self.last_prompt_tokens = 200
            return "compact-summary"

    bot = _make_bot()
    user_id = 777
    bot.agents[user_id] = _CompactAgent()

    reply = bot._handle_default_command("compact", user_id)

    assert reply is not None
    assert "Before: 900/1,000 (90%)" in reply
    assert "After: 200/1,000 (20.0%)" in reply


def test_send_response_supports_async_platform_senders():
    class _AsyncDummyBot(_DummyBot):
        def __init__(self, settings, bot_config):
            super().__init__(settings, bot_config)
            self.sent_messages: list[str] = []
            self.sent_files: list[str] = []

        async def _send_message(self, user_id, message: str) -> None:
            _ = user_id
            self.sent_messages.append(message)

        async def _send_file(self, user_id, file_action) -> None:
            _ = user_id
            self.sent_files.append(file_action.filename)

    bot = _AsyncDummyBot(
        settings=Settings(),
        bot_config=BotConfig(id="dummy-bot", platform="telegram", token="tok"),
    )
    response = BotResponse(
        text="abcdefghij",
        actions=[SendFileAction(path="/tmp/report.txt", filename="report.txt")],
    )

    asyncio.run(bot._send_response(1, response))

    assert bot.sent_messages == ["abcde", "fghij"]
    assert bot.sent_files == ["report.txt"]


def test_send_response_skips_files_when_message_send_fails():
    class _FailingMessageBot(_DummyBot):
        def __init__(self, settings, bot_config):
            super().__init__(settings, bot_config)
            self.sent_files: list[str] = []

        async def _send_message(self, user_id, message: str) -> None:
            _ = (user_id, message)
            raise RuntimeError("simulated message send failure")

        async def _send_file(self, user_id, file_action) -> None:
            _ = user_id
            self.sent_files.append(file_action.filename)

    bot = _FailingMessageBot(
        settings=Settings(),
        bot_config=BotConfig(id="dummy-bot", platform="telegram", token="tok"),
    )
    response = BotResponse(
        text="hello",
        actions=[SendFileAction(path="/tmp/report.txt", filename="report.txt")],
    )

    asyncio.run(bot._send_response(1, response))

    assert bot.sent_files == []
