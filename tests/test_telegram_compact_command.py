"""Tests for Telegram /compact command behavior."""

import asyncio
from types import SimpleNamespace

from flavia.config.settings import Settings
from flavia.interfaces.telegram_interface import TelegramBot


class _DummyChat:
    def __init__(self):
        self.actions: list[str] = []

    async def send_action(self, action: str) -> None:
        self.actions.append(action)


class _DummyMessage:
    def __init__(self):
        self.replies: list[str] = []
        self.chat = _DummyChat()

    async def reply_text(self, text: str) -> None:
        self.replies.append(text)


class _DummyUpdate:
    def __init__(self, user_id: int = 123, chat_id: int = 456):
        self.effective_user = SimpleNamespace(
            id=user_id,
            username="test-user",
            full_name="Test User",
        )
        self.effective_chat = SimpleNamespace(id=chat_id)
        self.message = _DummyMessage()


class _CompactAgent:
    def __init__(self, summary: str = "summary"):
        self.last_prompt_tokens = 45_000
        self.max_context_tokens = 128_000
        self._summary = summary
        self.compaction_calls = 0

    @property
    def context_utilization(self) -> float:
        return self.last_prompt_tokens / self.max_context_tokens

    def compact_conversation(self, instructions=None) -> str:
        self.compaction_calls += 1
        if self._summary:
            self.last_prompt_tokens = 3_200
        return self._summary


def _make_bot() -> TelegramBot:
    bot = TelegramBot.__new__(TelegramBot)
    bot.settings = Settings(telegram_allow_all_users=True)
    bot.agents = {}
    return bot


def test_compact_command_without_active_conversation():
    bot = _make_bot()
    update = _DummyUpdate(user_id=42)

    asyncio.run(bot._compact_command(update, context=None))

    assert update.message.replies == ["No active conversation to compact."]
    assert update.message.chat.actions == []


def test_compact_command_reports_before_and_after_usage():
    bot = _make_bot()
    update = _DummyUpdate(user_id=42)
    agent = _CompactAgent(summary="Compacted summary")
    bot.agents[42] = agent

    asyncio.run(bot._compact_command(update, context=None))

    assert agent.compaction_calls == 1
    assert update.message.chat.actions == ["typing"]
    assert len(update.message.replies) == 1
    reply = update.message.replies[0]
    assert "Conversation compacted." in reply
    assert "Before: 45,000/128,000 (35%)" in reply
    assert "After: 3,200/128,000 (2.5%)" in reply
    assert "Summary:" in reply
    assert "Compacted summary" in reply


def test_compact_command_handles_empty_conversation():
    bot = _make_bot()
    update = _DummyUpdate(user_id=42)
    agent = _CompactAgent(summary="")
    bot.agents[42] = agent

    asyncio.run(bot._compact_command(update, context=None))

    assert agent.compaction_calls == 1
    assert update.message.chat.actions == ["typing"]
    assert update.message.replies == ["Nothing to compact (conversation is empty)."]
