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


def test_recursive_agent_appends_write_error_summary_when_all_writes_fail():
    agent = RecursiveAgent.__new__(RecursiveAgent)
    agent.messages = []
    agent.context = AgentContext(agent_id="main", current_depth=0, max_depth=3)
    agent.status_callback = None
    agent.compaction_warning_pending = False
    agent.compaction_warning_prompt_tokens = 0
    agent.last_prompt_tokens = 0
    agent.max_context_tokens = 128_000
    agent.profile = SimpleNamespace(compact_threshold=0.9)
    agent.log = lambda _msg: None

    tool_call = SimpleNamespace(
        id="call-1",
        function=SimpleNamespace(name="write_file", arguments='{"path":"x.txt","content":"x"}'),
    )
    responses = [
        _FakeResponse(content="", tool_calls=[tool_call]),
        _FakeResponse(content="Arquivo gravado com sucesso.", tool_calls=None),
    ]

    def fake_call_llm(_messages):
        return responses.pop(0)

    def fake_assistant_to_dict(message):
        tool_calls = message.tool_calls or []
        serialized_calls = []
        for tc in tool_calls:
            serialized_calls.append(
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
            )
        msg = {"role": "assistant", "content": message.content or ""}
        if serialized_calls:
            msg["tool_calls"] = serialized_calls
        return msg

    agent._call_llm = fake_call_llm
    agent._assistant_message_to_dict = fake_assistant_to_dict
    agent._execute_tool = lambda _name, _args: "Error: Write access denied - no write permissions configured"

    response = RecursiveAgent.run(agent, "Crie um arquivo")

    assert "Arquivo gravado com sucesso." in response
    assert "Write operations were not applied due to errors" in response
    assert "write_file: Error: Write access denied" in response
