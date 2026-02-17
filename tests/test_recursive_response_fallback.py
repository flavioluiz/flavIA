"""Tests for RecursiveAgent response fallback behavior."""

from pathlib import Path
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


def test_recursive_agent_max_iterations_message_includes_limit():
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
        function=SimpleNamespace(name="list_files", arguments='{"path":"."}'),
    )

    def fake_call_llm(_messages):
        return _FakeResponse(content="", tool_calls=[tool_call])

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
    agent._execute_tool = lambda _name, _args: "ok"

    response = RecursiveAgent.run(agent, "continue", max_iterations=2)

    assert response == RecursiveAgent.format_max_iterations_message(2)


def test_recursive_agent_can_continue_after_max_iterations_without_new_user_message():
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
        function=SimpleNamespace(name="list_files", arguments='{"path":"."}'),
    )
    responses = [
        _FakeResponse(content="", tool_calls=[tool_call]),
        _FakeResponse(content="Final answer", tool_calls=None),
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
    agent._execute_tool = lambda _name, _args: "ok"

    first = RecursiveAgent.run(agent, "continue", max_iterations=1)
    assert RecursiveAgent.extract_max_iterations_limit(first) == 1

    second = RecursiveAgent.run(
        agent,
        "",
        max_iterations=1,
        continue_from_current=True,
    )

    assert second == "Final answer"
    assert len([m for m in agent.messages if m.get("role") == "user"]) == 1


def test_recursive_agent_enforces_search_chunks_before_final_response_for_mentions(tmp_path: Path):
    agent = RecursiveAgent.__new__(RecursiveAgent)
    agent.messages = []
    index_dir = tmp_path / ".index"
    index_dir.mkdir()
    (index_dir / "index.db").write_text("", encoding="utf-8")
    agent.context = AgentContext(
        agent_id="main",
        current_depth=0,
        max_depth=3,
        base_dir=tmp_path,
        available_tools=["search_chunks"],
    )
    agent.status_callback = None
    agent.compaction_warning_pending = False
    agent.compaction_warning_prompt_tokens = 0
    agent.last_prompt_tokens = 0
    agent.max_context_tokens = 128_000
    agent.profile = SimpleNamespace(compact_threshold=0.9)

    responses = [
        _FakeResponse(content="Resposta sem consulta", tool_calls=None),
        _FakeResponse(content="Resposta após grounding", tool_calls=None),
    ]
    calls = {"count": 0}

    def fake_call_llm(_messages):
        calls["count"] += 1
        return responses.pop(0)

    def fake_assistant_to_dict(message):
        return {"role": "assistant", "content": message.content or ""}

    agent._call_llm = fake_call_llm
    agent._assistant_message_to_dict = fake_assistant_to_dict

    result = RecursiveAgent.run(agent, "@ficha.pdf quais são os pontos fracos?")

    assert result == "Resposta após grounding"
    assert calls["count"] == 2
    assert any(
        "Before answering, call search_chunks" in str(msg.get("content", ""))
        for msg in agent.messages
        if msg.get("role") == "user"
    )
