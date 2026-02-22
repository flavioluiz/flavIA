"""Tests for Task 10.1 — Structured Agent Responses (context-based approach)."""

from unittest.mock import MagicMock

from flavia.agent import SendFileAction as AgentSendFileAction
from flavia.agent.context import AgentContext, SendFileAction
from flavia.config.bots import BotConfig
from flavia.config.settings import Settings
from flavia.interfaces import SendFileAction as InterfacesSendFileAction
from flavia.interfaces.base_bot import BaseMessagingBot, BotResponse
from flavia.interfaces.base_bot import SendFileAction as BaseBotSendFileAction


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _DummyBot(BaseMessagingBot):
    @property
    def platform_name(self) -> str:
        return "dummy"

    @property
    def max_message_length(self) -> int:
        return 4096

    def run(self) -> None:
        return None

    def _send_message(self, user_id, message: str) -> None:
        pass

    def _send_file(self, user_id, file_action) -> None:
        pass


def _make_bot() -> _DummyBot:
    settings = Settings(
        agents_config={"main": {"model": "synthetic:hf:moonshotai/Kimi-K2.5"}}
    )
    return _DummyBot(
        settings=settings,
        bot_config=BotConfig(id="dummy-bot", platform="telegram", token="tok"),
    )


# ---------------------------------------------------------------------------
# 1. SendFileAction importable from agent layer
# ---------------------------------------------------------------------------


def test_send_file_action_importable_from_agent_layer():
    action = SendFileAction(path="/tmp/report.pdf", filename="report.pdf", caption="Here")
    assert action.path == "/tmp/report.pdf"
    assert action.filename == "report.pdf"
    assert action.caption == "Here"


def test_send_file_action_importable_from_agent_package():
    action = AgentSendFileAction(path="/tmp/x.txt", filename="x.txt")
    assert action.caption == ""


# ---------------------------------------------------------------------------
# 2. AgentContext.pending_actions defaults to empty list
# ---------------------------------------------------------------------------


def test_agent_context_pending_actions_default_empty():
    ctx = AgentContext()
    assert ctx.pending_actions == []


# ---------------------------------------------------------------------------
# 3. Child context gets independent pending_actions
# ---------------------------------------------------------------------------


def test_agent_context_child_gets_independent_pending_actions():
    from flavia.agent import AgentProfile

    parent_ctx = AgentContext()
    parent_ctx.pending_actions.append(
        SendFileAction(path="/tmp/p.pdf", filename="p.pdf")
    )

    profile = AgentProfile(
        context="",
        model="synthetic:test",
        base_dir=parent_ctx.base_dir,
        tools=[],
        subagents={},
        name="child",
    )
    child_ctx = parent_ctx.create_child_context("child-1", profile)

    assert child_ctx.pending_actions == []
    assert len(parent_ctx.pending_actions) == 1


# ---------------------------------------------------------------------------
# 4. _process_agent_response reads pending_actions from context
# ---------------------------------------------------------------------------


def test_process_agent_response_reads_pending_actions():
    bot = _make_bot()

    mock_agent = MagicMock()
    action = SendFileAction(path="/tmp/report.pdf", filename="report.pdf", caption="Done")
    mock_agent.context.pending_actions = [action]

    bot.agents[42] = mock_agent

    result = bot._process_agent_response(42, "Here is your report.")

    assert isinstance(result, BotResponse)
    assert result.text == "Here is your report."
    assert len(result.actions) == 1
    assert result.actions[0].path == "/tmp/report.pdf"
    assert result.actions[0].filename == "report.pdf"
    assert result.actions[0].caption == "Done"


# ---------------------------------------------------------------------------
# 5. _process_agent_response returns empty actions when none queued
# ---------------------------------------------------------------------------


def test_process_agent_response_empty_when_no_actions():
    bot = _make_bot()

    mock_agent = MagicMock()
    mock_agent.context.pending_actions = []
    bot.agents[1] = mock_agent

    result = bot._process_agent_response(1, "Hello!")

    assert result.text == "Hello!"
    assert result.actions == []
    assert not result.has_actions


def test_process_agent_response_no_agent_returns_empty_actions():
    bot = _make_bot()
    result = bot._process_agent_response(999, "No agent here.")
    assert result.text == "No agent here."
    assert result.actions == []


# ---------------------------------------------------------------------------
# 6. _process_agent_response copies actions (context reset doesn't affect result)
# ---------------------------------------------------------------------------


def test_process_agent_response_copies_actions():
    bot = _make_bot()

    mock_agent = MagicMock()
    action = SendFileAction(path="/tmp/f.pdf", filename="f.pdf")
    mock_agent.context.pending_actions = [action]
    bot.agents[7] = mock_agent

    result = bot._process_agent_response(7, "File ready.")

    # Simulate what run() does: clear pending_actions
    mock_agent.context.pending_actions.clear()

    # result.actions should still have the action
    assert len(result.actions) == 1
    assert result.actions[0].filename == "f.pdf"


# ---------------------------------------------------------------------------
# 7. Backward compat: SendFileAction is the same class from all import paths
# ---------------------------------------------------------------------------


def test_backward_compat_send_file_action_from_interfaces():
    assert InterfacesSendFileAction is SendFileAction
    assert BaseBotSendFileAction is SendFileAction
    assert AgentSendFileAction is SendFileAction
