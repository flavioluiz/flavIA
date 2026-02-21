"""Tests for Telegram /agent and /agents command behavior."""

import asyncio
from types import SimpleNamespace

from flavia.config.bots import BotAccessConfig, BotConfig
from flavia.config.settings import Settings
from flavia.interfaces.telegram_interface import TelegramBot

# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------

class _DummyMessage:
    def __init__(self):
        self.replies: list[str] = []

    async def reply_text(self, text: str) -> None:
        self.replies.append(text)


class _DummyUpdate:
    def __init__(self, user_id: int = 123):
        self.effective_user = SimpleNamespace(
            id=user_id,
            username="test-user",
            full_name="Test User",
        )
        self.effective_chat = SimpleNamespace(id=456)
        self.message = _DummyMessage()


class _DummyContext:
    def __init__(self, args=None):
        self.args = args or []


class _DummyAgent:
    """Minimal agent stub — tracks whether it was discarded."""
    pass


def _make_bot(agents_config=None, bot_config=None) -> TelegramBot:
    bot = TelegramBot.__new__(TelegramBot)
    bot.settings = Settings(
        telegram_allow_all_users=True,
        agents_config=agents_config or {},
    )
    bot.bot_config = bot_config
    bot.agents = {}
    bot._user_agents = {}
    return bot


def _bot_config(allowed_agents=None, default_agent="main") -> BotConfig:
    return BotConfig(
        id="test",
        platform="telegram",
        token="tok",
        default_agent=default_agent,
        allowed_agents=allowed_agents,
        access=BotAccessConfig(allow_all=True),
    )


# ---------------------------------------------------------------------------
# /agents tests
# ---------------------------------------------------------------------------

def test_agents_command_empty_config():
    bot = _make_bot(agents_config={})
    update = _DummyUpdate()

    asyncio.run(bot._agents_command(update, context=None))

    assert len(update.message.replies) == 1
    assert "No agents configured" in update.message.replies[0]


def test_agents_command_lists_available():
    bot = _make_bot(agents_config={"main": {}, "researcher": {}})
    update = _DummyUpdate()

    asyncio.run(bot._agents_command(update, context=None))

    reply = update.message.replies[0]
    assert "main" in reply
    assert "researcher" in reply


def test_agents_command_filters_by_allowed_agents():
    bot = _make_bot(
        agents_config={"main": {}, "researcher": {}, "secret": {}},
        bot_config=_bot_config(allowed_agents=["main", "researcher"]),
    )
    update = _DummyUpdate()

    asyncio.run(bot._agents_command(update, context=None))

    reply = update.message.replies[0]
    assert "main" in reply
    assert "researcher" in reply
    assert "secret" not in reply


def test_agents_command_marks_active_agent():
    bot = _make_bot(agents_config={"main": {}, "researcher": {}})
    bot._user_agents[123] = "researcher"
    update = _DummyUpdate(user_id=123)

    asyncio.run(bot._agents_command(update, context=None))

    reply = update.message.replies[0]
    assert "researcher (active)" in reply
    assert "main (active)" not in reply


def test_agents_command_lists_subagents_from_main():
    bot = _make_bot(
        agents_config={
            "main": {
                "subagents": {
                    "ironic": {"context": "ironic style"},
                }
            }
        }
    )
    update = _DummyUpdate()

    asyncio.run(bot._agents_command(update, context=None))

    reply = update.message.replies[0]
    assert "main" in reply
    assert "ironic" in reply


def test_agents_command_filters_allowed_subagent():
    bot = _make_bot(
        agents_config={
            "main": {
                "subagents": {
                    "ironic": {"context": "ironic style"},
                }
            }
        },
        bot_config=_bot_config(allowed_agents=["ironic"]),
    )
    update = _DummyUpdate()

    asyncio.run(bot._agents_command(update, context=None))

    reply = update.message.replies[0]
    assert "ironic" in reply
    assert "main" not in reply


# ---------------------------------------------------------------------------
# /agent tests
# ---------------------------------------------------------------------------

def test_agent_command_no_args_shows_current():
    bot = _make_bot(agents_config={"main": {}})
    update = _DummyUpdate(user_id=123)
    ctx = _DummyContext(args=[])

    asyncio.run(bot._agent_command(update, ctx))

    reply = update.message.replies[0]
    assert "main" in reply


def test_agent_command_switches_successfully():
    bot = _make_bot(agents_config={"main": {}, "researcher": {}})
    bot.agents[123] = _DummyAgent()
    update = _DummyUpdate(user_id=123)
    ctx = _DummyContext(args=["researcher"])

    asyncio.run(bot._agent_command(update, ctx))

    assert bot._user_agents[123] == "researcher"
    assert 123 not in bot.agents  # old instance discarded
    reply = update.message.replies[0]
    assert "researcher" in reply
    assert "Switched" in reply


def test_agent_command_rejects_unknown_agent():
    bot = _make_bot(agents_config={"main": {}})
    update = _DummyUpdate(user_id=123)
    ctx = _DummyContext(args=["ghost"])

    asyncio.run(bot._agent_command(update, ctx))

    reply = update.message.replies[0]
    assert "Unknown agent" in reply
    assert "ghost" in reply


def test_agent_command_rejects_disallowed_agent():
    bot = _make_bot(
        agents_config={"main": {}, "researcher": {}},
        bot_config=_bot_config(allowed_agents=["main"]),
    )
    update = _DummyUpdate(user_id=123)
    ctx = _DummyContext(args=["researcher"])

    asyncio.run(bot._agent_command(update, ctx))

    reply = update.message.replies[0]
    assert "not allowed" in reply
    assert "researcher" in reply


def test_agent_command_already_current():
    bot = _make_bot(agents_config={"main": {}})
    update = _DummyUpdate(user_id=123)
    ctx = _DummyContext(args=["main"])

    asyncio.run(bot._agent_command(update, ctx))

    reply = update.message.replies[0]
    assert "Already using" in reply
    assert "main" in reply


def test_agent_command_switches_to_subagent():
    bot = _make_bot(
        agents_config={
            "main": {
                "subagents": {
                    "ironic": {"context": "ironic style"},
                }
            }
        }
    )
    update = _DummyUpdate(user_id=123)
    ctx = _DummyContext(args=["ironic"])

    asyncio.run(bot._agent_command(update, ctx))

    assert bot._user_agents[123] == "ironic"
    reply = update.message.replies[0]
    assert "Switched" in reply
    assert "ironic" in reply


def test_agent_switch_resets_conversation():
    """Switching agents should discard the existing RecursiveAgent instance."""
    bot = _make_bot(agents_config={"main": {}, "researcher": {}})
    old_agent = _DummyAgent()
    bot.agents[42] = old_agent
    update = _DummyUpdate(user_id=42)
    ctx = _DummyContext(args=["researcher"])

    asyncio.run(bot._agent_command(update, ctx))

    # Old agent instance gone; new one will be created on next message
    assert 42 not in bot.agents
    assert bot._user_agents[42] == "researcher"
