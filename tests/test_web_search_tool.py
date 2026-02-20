"""Tests for web_search tool and providers."""

from pathlib import Path
from types import SimpleNamespace

import httpx

from flavia.agent.context import AgentContext
from flavia.agent.profile import AgentPermissions
from flavia.tools import list_available_tools
from flavia.tools.research.search_providers.base import SearchResponse, SearchResult
from flavia.tools.research.search_providers.duckduckgo import DuckDuckGoSearchProvider
from flavia.tools.research.search_providers.google import GoogleSearchProvider
from flavia.tools.research.web_search import WebSearchTool


def _make_context(base_dir: Path) -> AgentContext:
    return AgentContext(
        agent_id="test",
        name="test",
        current_depth=0,
        max_depth=3,
        parent_id=None,
        base_dir=base_dir,
        available_tools=[],
        subagents={},
        model_id="test-model",
        messages=[],
        permissions=AgentPermissions(),
    )


def test_web_search_registered() -> None:
    assert "web_search" in list_available_tools()


def test_web_search_normalizes_provider_and_filters(tmp_path: Path, monkeypatch) -> None:
    tool = WebSearchTool()
    ctx = _make_context(tmp_path)
    captured: dict[str, object] = {}

    class _FakeProvider:
        def is_configured(self) -> bool:
            return True

        def search(self, query, num_results=10, region=None, time_range=None):
            captured["query"] = query
            captured["num_results"] = num_results
            captured["region"] = region
            captured["time_range"] = time_range
            return SearchResponse(
                query=query,
                provider="fake",
                results=[
                    SearchResult(
                        title="Result A",
                        url="https://example.com",
                        snippet="Snippet",
                        position=1,
                    )
                ],
                total_results=1,
            )

    def _fake_get_provider(name: str):
        captured["provider_name"] = name
        return _FakeProvider()

    monkeypatch.setattr("flavia.tools.research.web_search.get_provider", _fake_get_provider)

    output = tool.execute(
        {
            "query": "test query",
            "provider": " Google ",
            "region": "US",
            "time_range": "WEEK",
            "num_results": "3",
        },
        ctx,
    )

    assert captured["provider_name"] == "google"
    assert captured["query"] == "test query"
    assert captured["num_results"] == 3
    assert captured["region"] == "us"
    assert captured["time_range"] == "week"
    assert "Web Search Results" in output


def test_web_search_uses_normalized_provider_from_settings(tmp_path: Path, monkeypatch) -> None:
    tool = WebSearchTool()
    ctx = _make_context(tmp_path)
    calls: list[str] = []

    class _StubSettings:
        web_search_provider = " BING "

    def _fake_get_provider(name: str):
        calls.append(name)

        class _FakeProvider:
            def is_configured(self) -> bool:
                return True

            def search(self, query, num_results=10, region=None, time_range=None):
                return SearchResponse(
                    query=query,
                    provider=name,
                    results=[
                        SearchResult(
                            title="Result A",
                            url="https://example.com",
                            snippet="Snippet",
                            position=1,
                        )
                    ],
                    total_results=1,
                )

        return _FakeProvider()

    monkeypatch.setattr("flavia.config.get_settings", lambda: _StubSettings())
    monkeypatch.setattr("flavia.tools.research.web_search.get_provider", _fake_get_provider)

    output = tool.execute({"query": "x"}, ctx)

    assert calls
    assert calls[0] == "bing"
    assert "Web Search Results" in output
    assert "(bing)" in output


def test_web_search_fallback_returns_results_with_attempt_log(
    tmp_path: Path, monkeypatch
) -> None:
    tool = WebSearchTool()
    ctx = _make_context(tmp_path)

    class _DuckProvider:
        def is_configured(self) -> bool:
            return False

        def search(self, query, num_results=10, region=None, time_range=None):
            return SearchResponse(query=query, provider="duckduckgo", results=[])

    class _GoogleProvider:
        def is_configured(self) -> bool:
            return True

        def search(self, query, num_results=10, region=None, time_range=None):
            return SearchResponse(
                query=query,
                provider="google",
                results=[
                    SearchResult(
                        title="Result A",
                        url="https://example.com",
                        snippet="Snippet",
                        position=1,
                    )
                ],
                total_results=1,
            )

    def _fake_get_provider(name: str):
        if name == "duckduckgo":
            return _DuckProvider()
        if name == "google":
            return _GoogleProvider()
        return None

    monkeypatch.setattr("flavia.tools.research.web_search.get_provider", _fake_get_provider)
    output = tool.execute({"query": "fallback test", "provider": "duckduckgo"}, ctx)

    assert "**Web Search Results** (google)" in output
    assert "Provider fallback used" in output
    assert "duckduckgo-search is not installed" in output


def test_web_search_all_providers_unavailable_has_actionable_error(
    tmp_path: Path, monkeypatch
) -> None:
    tool = WebSearchTool()
    ctx = _make_context(tmp_path)

    class _UnconfiguredProvider:
        def is_configured(self) -> bool:
            return False

        def search(self, query, num_results=10, region=None, time_range=None):
            return SearchResponse(query=query, provider="none", results=[])

    monkeypatch.setattr(
        "flavia.tools.research.web_search.get_provider",
        lambda _name: _UnconfiguredProvider(),
    )

    output = tool.execute({"query": "who is x", "provider": "duckduckgo"}, ctx)

    assert "Error: web search unavailable" in output
    assert "Attempts:" in output
    assert "duckduckgo-search" in output
    assert "GOOGLE_SEARCH_API_KEY" in output
    assert "/settings web_search" in output


def test_google_search_error_does_not_expose_api_key(monkeypatch) -> None:
    provider = GoogleSearchProvider()
    secret_key = "secret-key-123"
    secret_cx = "secret-cx-987"

    class _StubSettings:
        google_search_api_key = secret_key
        google_search_cx = secret_cx

    def _fake_get(*_args, **_kwargs):
        req = httpx.Request(
            "GET",
            f"https://www.googleapis.com/customsearch/v1?key={secret_key}&cx={secret_cx}",
        )
        resp = httpx.Response(403, request=req)
        raise httpx.HTTPStatusError(
            f"Client error '403 Forbidden' for url '{req.url}'",
            request=req,
            response=resp,
        )

    monkeypatch.setattr("flavia.config.get_settings", lambda: _StubSettings())
    monkeypatch.setattr("flavia.tools.research.search_providers.google.httpx.get", _fake_get)

    response = provider.search("llm safety")

    assert response.results
    snippet = response.results[0].snippet
    assert "HTTP 403" in snippet
    assert secret_key not in snippet
    assert secret_cx not in snippet


def test_duckduckgo_rate_limit_returns_actionable_message(monkeypatch) -> None:
    provider = DuckDuckGoSearchProvider()

    class _FakeDDGS:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def text(self, *_args, **_kwargs):
            raise RuntimeError("https://html.duckduckgo.com/html 202 Ratelimit")

    monkeypatch.setitem(
        __import__("sys").modules,
        "duckduckgo_search",
        SimpleNamespace(DDGS=_FakeDDGS),
    )

    response = provider.search("OpenAI")

    assert response.error_message is not None
    assert "rate limited" in response.error_message.lower()
    assert response.results
    assert "rate limited" in response.results[0].snippet.lower()
