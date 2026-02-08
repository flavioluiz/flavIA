"""Regression tests for chat message formatting and setup fallback."""

from pathlib import Path

from flavia.agent.base import BaseAgent
from flavia.agent.profile import AgentProfile
from flavia.config.settings import Settings
from flavia.setup_wizard import _run_basic_setup


class DummyAgent(BaseAgent):
    """Concrete agent used for BaseAgent method testing."""

    def run(self, user_message: str) -> str:
        return user_message


class _FakeFunction:
    def __init__(self, name: str, arguments: str):
        self.name = name
        self.arguments = arguments


class _FakeToolCall:
    def __init__(self, call_id: str, function: _FakeFunction):
        self.id = call_id
        self.function = function


class _FakeMessage:
    def __init__(self, content, tool_calls):
        self.content = content
        self.tool_calls = tool_calls


def _make_agent() -> DummyAgent:
    settings = Settings(
        api_key="test-key",
        api_base_url="https://api.synthetic.new/openai/v1",
    )
    profile = AgentProfile(context="test", base_dir=Path.cwd(), tools=[], subagents={})
    return DummyAgent(settings=settings, profile=profile)


def test_assistant_message_normalization_with_tool_calls():
    agent = _make_agent()
    message = _FakeMessage(
        content=None,
        tool_calls=[
            _FakeToolCall("call-1", _FakeFunction("list_files", '{"path":"."}')),
        ],
    )

    normalized = agent._assistant_message_to_dict(message)

    assert normalized == {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "id": "call-1",
                "type": "function",
                "function": {"name": "list_files", "arguments": '{"path":"."}'},
            }
        ],
    }


def test_basic_setup_succeeds_when_config_dir_already_exists(tmp_path):
    config_dir = tmp_path / ".flavia"
    config_dir.mkdir()

    success = _run_basic_setup(tmp_path, config_dir)

    assert success is True
    assert (config_dir / ".env").exists()
    assert (config_dir / "models.yaml").exists()
    assert (config_dir / "agents.yaml").exists()
    env_text = (config_dir / ".env").read_text(encoding="utf-8")
    assert "TELEGRAM_BOT_TOKEN" in env_text
    assert "TELEGRAM_ALLOWED_USER_IDS" in env_text
    assert "TELEGRAM_ALLOW_ALL_USERS" in env_text
