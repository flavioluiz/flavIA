"""Tests for RecursiveAgent response fallback behavior."""

from types import SimpleNamespace

from flavia.agent.context import AgentContext
from flavia.agent.recursive import RecursiveAgent


class _FakeResponse:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


def test_recursive_agent_returns_fallback_when_assistant_content_is_empty():
    agent = RecursiveAgent.__new__(RecursiveAgent)
    agent.messages = []
    agent.context = AgentContext(agent_id="main", current_depth=0, max_depth=3)
    agent.status_callback = None
    agent.compaction_warning_pending = False
    agent.compaction_warning_prompt_tokens = 0
    agent.last_prompt_tokens = 0
    agent.max_context_tokens = 128_000
    agent.profile = SimpleNamespace(compact_threshold=0.9)

    def fake_call_llm(messages):
        return _FakeResponse(content=None, tool_calls=None)

    def fake_assistant_to_dict(message):
        return {"role": "assistant", "content": ""}

    agent._call_llm = fake_call_llm
    agent._assistant_message_to_dict = fake_assistant_to_dict

    response = RecursiveAgent.run(agent, "Pergunta teste")

    assert response == "I could not produce a textual response. Please try rephrasing your question."
