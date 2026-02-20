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
        _FakeResponse(content="Resposta ainda sem consulta", tool_calls=None),
        _FakeResponse(content="Resposta ainda sem consulta", tool_calls=None),
        _FakeResponse(content="Resposta ainda sem consulta", tool_calls=None),
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

    assert "Unable to complete the answer because @file grounding was required" in result
    assert calls["count"] == 4
    assert any(
        "you must call search_chunks" in str(msg.get("content", ""))
        for msg in agent.messages
        if msg.get("role") == "user"
    )


def test_recursive_agent_propagates_search_chunks_missing_file_error(tmp_path: Path):
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
    agent.log = lambda _msg: None

    tool_call = SimpleNamespace(
        id="call-1",
        function=SimpleNamespace(
            name="search_chunks",
            arguments='{"query":"@arquivo_inexistente.pdf encontre os subitens"}',
        ),
    )
    responses = [_FakeResponse(content="", tool_calls=[tool_call])]

    def fake_call_llm(_messages):
        return responses.pop(0)

    def fake_assistant_to_dict(message):
        serialized_calls = []
        for tc in (message.tool_calls or []):
            serialized_calls.append(
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
            )
        msg = {"role": "assistant", "content": message.content or ""}
        if serialized_calls:
            msg["tool_calls"] = serialized_calls
        return msg

    agent._call_llm = fake_call_llm
    agent._assistant_message_to_dict = fake_assistant_to_dict
    agent._execute_tool = (
        lambda _name, _args: "No indexed documents match the @file references "
        "(unknown: @arquivo_inexistente.pdf). Ensure files are cataloged, converted, and indexed."
    )

    result = RecursiveAgent.run(agent, "@arquivo_inexistente.pdf encontre os subitens")
    assert result.startswith("No indexed documents match the @file references")


def test_recursive_agent_forces_exhaustive_mode_for_checklist_queries(tmp_path: Path):
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
    agent.log = lambda _msg: None

    tool_call = SimpleNamespace(
        id="call-1",
        function=SimpleNamespace(
            name="search_chunks",
            arguments='{"query":"@ficha.pdf procure todos os itens e subitens"}',
        ),
    )
    responses = [
        _FakeResponse(content="", tool_calls=[tool_call]),
        _FakeResponse(content="ok", tool_calls=None),
    ]
    captured_args = {}

    def fake_call_llm(_messages):
        return responses.pop(0)

    def fake_assistant_to_dict(message):
        serialized_calls = []
        for tc in (message.tool_calls or []):
            serialized_calls.append(
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
            )
        msg = {"role": "assistant", "content": message.content or ""}
        if serialized_calls:
            msg["tool_calls"] = serialized_calls
        return msg

    def fake_execute_tool(name, args):
        captured_args["name"] = name
        captured_args["args"] = dict(args)
        return "resultado grounded"

    agent._call_llm = fake_call_llm
    agent._assistant_message_to_dict = fake_assistant_to_dict
    agent._execute_tool = fake_execute_tool

    result = RecursiveAgent.run(agent, "@ficha.pdf procure todos os itens e subitens")
    assert result == "ok"
    assert captured_args["name"] == "search_chunks"
    assert captured_args["args"].get("retrieval_mode") == "exhaustive"


def test_recursive_agent_requires_cross_doc_mention_coverage_for_comparative_prompts(tmp_path: Path):
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
    agent.log = lambda _msg: None

    tool_call = SimpleNamespace(
        id="call-1",
        function=SimpleNamespace(
            name="search_chunks",
            arguments='{"query":"@esperado.pdf compare por subitem"}',
        ),
    )
    responses = [
        _FakeResponse(content="", tool_calls=[tool_call]),
        _FakeResponse(content="conclusão sem segunda fonte", tool_calls=None),
        _FakeResponse(content="conclusão sem segunda fonte", tool_calls=None),
        _FakeResponse(content="conclusão sem segunda fonte", tool_calls=None),
        _FakeResponse(content="conclusão sem segunda fonte", tool_calls=None),
    ]

    def fake_call_llm(_messages):
        return responses.pop(0)

    def fake_assistant_to_dict(message):
        serialized_calls = []
        for tc in (message.tool_calls or []):
            serialized_calls.append(
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
            )
        msg = {"role": "assistant", "content": message.content or ""}
        if serialized_calls:
            msg["tool_calls"] = serialized_calls
        return msg

    agent._call_llm = fake_call_llm
    agent._assistant_message_to_dict = fake_assistant_to_dict
    agent._execute_tool = lambda _name, _args: "resultado grounded"

    result = RecursiveAgent.run(agent, "@esperado.pdf @enviado.pdf compare por subitem")
    assert result.startswith("Unable to complete the answer because multi-file grounding was incomplete.")
    assert "@enviado.pdf" in result


def test_recursive_agent_treats_stem_mentions_as_covered_equivalents(tmp_path: Path):
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
    agent.log = lambda _msg: None

    tool_call_1 = SimpleNamespace(
        id="call-1",
        function=SimpleNamespace(
            name="search_chunks",
            arguments='{"query":"@esperado compare por subitem"}',
        ),
    )
    tool_call_2 = SimpleNamespace(
        id="call-2",
        function=SimpleNamespace(
            name="search_chunks",
            arguments='{"query":"@enviado compare por subitem"}',
        ),
    )
    responses = [
        _FakeResponse(content="", tool_calls=[tool_call_1]),
        _FakeResponse(content="", tool_calls=[tool_call_2]),
        _FakeResponse(content="análise final [1]", tool_calls=None),
    ]

    def fake_call_llm(_messages):
        return responses.pop(0)

    def fake_assistant_to_dict(message):
        serialized_calls = []
        for tc in (message.tool_calls or []):
            serialized_calls.append(
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
            )
        msg = {"role": "assistant", "content": message.content or ""}
        if serialized_calls:
            msg["tool_calls"] = serialized_calls
        return msg

    agent._call_llm = fake_call_llm
    agent._assistant_message_to_dict = fake_assistant_to_dict
    agent._execute_tool = lambda _name, _args: "resultado grounded"

    result = RecursiveAgent.run(agent, "@esperado.pdf @enviado.pdf compare por subitem")
    assert result == "análise final [1]"


def test_recursive_agent_enforces_cited_two_stage_output_for_comparative_prompts(tmp_path: Path):
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
    agent.log = lambda _msg: None

    tool_call = SimpleNamespace(
        id="call-1",
        function=SimpleNamespace(
            name="search_chunks",
            arguments='{"query":"@esperado.pdf @enviado.pdf compare por subitem"}',
        ),
    )
    responses = [
        _FakeResponse(content="", tool_calls=[tool_call]),
        _FakeResponse(content="análise sem citação", tool_calls=None),
        _FakeResponse(content="Matriz [1]\nConclusão [2]", tool_calls=None),
    ]

    def fake_call_llm(_messages):
        return responses.pop(0)

    def fake_assistant_to_dict(message):
        serialized_calls = []
        for tc in (message.tool_calls or []):
            serialized_calls.append(
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
            )
        msg = {"role": "assistant", "content": message.content or ""}
        if serialized_calls:
            msg["tool_calls"] = serialized_calls
        return msg

    agent._call_llm = fake_call_llm
    agent._assistant_message_to_dict = fake_assistant_to_dict
    agent._execute_tool = lambda _name, _args: "resultado grounded"

    result = RecursiveAgent.run(agent, "@esperado.pdf @enviado.pdf compare por subitem")
    assert result == "Matriz [1]\nConclusão [2]"
    assert any(
        "answer in two stages" in str(msg.get("content", ""))
        for msg in agent.messages
        if msg.get("role") == "user"
    )


def test_recursive_agent_canonicalizes_mistyped_extension_in_search_chunks_query(tmp_path: Path):
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
    agent.log = lambda _msg: None

    tool_call = SimpleNamespace(
        id="call-1",
        function=SimpleNamespace(
            name="search_chunks",
            arguments='{"query":"@relatorio_dados_enviados_coleta_full.php pontos fracos"}',
        ),
    )
    responses = [
        _FakeResponse(content="", tool_calls=[tool_call]),
        _FakeResponse(content="ok", tool_calls=None),
    ]
    captured_args = {}

    def fake_call_llm(_messages):
        return responses.pop(0)

    def fake_assistant_to_dict(message):
        serialized_calls = []
        for tc in (message.tool_calls or []):
            serialized_calls.append(
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
            )
        msg = {"role": "assistant", "content": message.content or ""}
        if serialized_calls:
            msg["tool_calls"] = serialized_calls
        return msg

    def fake_execute_tool(name, args):
        captured_args["name"] = name
        captured_args["args"] = dict(args)
        return "resultado grounded"

    agent._call_llm = fake_call_llm
    agent._assistant_message_to_dict = fake_assistant_to_dict
    agent._execute_tool = fake_execute_tool

    result = RecursiveAgent.run(agent, "@relatorio_dados_enviados_coleta_full.pdf pontos fracos")
    assert result == "ok"
    assert captured_args["name"] == "search_chunks"
    assert "@relatorio_dados_enviados_coleta_full.pdf" in captured_args["args"]["query"]
    assert ".php" not in captured_args["args"]["query"]


def test_recursive_agent_appends_web_search_unavailable_error_without_interrupting():
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
        function=SimpleNamespace(name="web_search", arguments='{"query":"OpenAI"}'),
    )

    # The agent should continue one more LLM turn for conversational flow,
    # while preserving and appending detailed web_search diagnostics.
    responses = [
        _FakeResponse(content="", tool_calls=[tool_call]),
        _FakeResponse(content="Não consegui buscar agora, mas posso tentar de novo.", tool_calls=None),
    ]
    calls = {"count": 0}

    def fake_call_llm(_messages):
        calls["count"] += 1
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
    agent._execute_tool = lambda _name, _args: (
        "Error: web search unavailable for query: OpenAI\n\n"
        "Attempts:\n"
        "- `duckduckgo`: duckduckgo-search is not installed in the current Python environment."
    )

    result = RecursiveAgent.run(agent, "busque OpenAI")

    assert "Não consegui buscar agora" in result
    assert "Error: web search unavailable for query: OpenAI" in result
    assert "Attempts:" in result
    assert calls["count"] == 2
