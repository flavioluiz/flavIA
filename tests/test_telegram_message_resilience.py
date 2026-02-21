"""Resilience tests for Telegram message handling under network hiccups."""

import asyncio
from types import SimpleNamespace

from flavia.config.settings import Settings
from flavia.interfaces.telegram_interface import TelegramBot


class _DummyChat:
    def __init__(self, fail_on_action: bool = False):
        self.fail_on_action = fail_on_action

    async def send_action(self, action: str) -> None:
        _ = action
        if self.fail_on_action:
            raise RuntimeError("transient telegram network error")


class _DummyMessage:
    def __init__(self, text: str, fail_on_action: bool = False):
        self.text = text
        self.replies: list[str] = []
        self.chat = _DummyChat(fail_on_action=fail_on_action)

    async def reply_text(self, text: str) -> None:
        self.replies.append(text)


class _DummyUpdate:
    def __init__(self, text: str, fail_on_action: bool = False):
        self.effective_user = SimpleNamespace(
            id=123,
            username="test-user",
            full_name="Test User",
        )
        self.effective_chat = SimpleNamespace(id=456)
        self.message = _DummyMessage(text=text, fail_on_action=fail_on_action)


class _DummyAgent:
    def __init__(self):
        self.last_prompt_tokens = 100
        self.max_context_tokens = 128_000
        self.needs_compaction = False
        self.compaction_warning_pending = False

    @property
    def context_utilization(self) -> float:
        return self.last_prompt_tokens / self.max_context_tokens

    def run(self, message: str) -> str:
        return f"echo:{message}"


def _make_bot() -> TelegramBot:
    bot = TelegramBot.__new__(TelegramBot)
    bot.settings = Settings(telegram_allow_all_users=True)
    bot.bot_config = None
    bot.agents = {}
    bot._user_agents = {}
    return bot


def test_handle_message_continues_when_typing_indicator_fails():
    bot = _make_bot()
    agent = _DummyAgent()
    bot._get_or_create_agent = lambda user_id: agent  # type: ignore[assignment]
    update = _DummyUpdate(text="ola", fail_on_action=True)

    asyncio.run(bot._handle_message(update, context=None))

    assert update.message.replies
    assert "echo:ola" in update.message.replies[0]
