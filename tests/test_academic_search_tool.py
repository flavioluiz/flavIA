"""Tests for academic search tools and providers."""

import logging
from pathlib import Path

import httpx

from flavia.agent.context import AgentContext
from flavia.agent.profile import AgentPermissions
from flavia.tools import list_available_tools
from flavia.tools.research.academic_providers.base import (
    AcademicSearchResponse,
    CitationResponse,
    PaperDetail,
    PaperDetailResponse,
    PaperResult,
)
from flavia.tools.research.academic_search import (
    FindSimilarPapersTool,
    GetCitationsTool,
    GetPaperDetailsTool,
    GetReferencesTool,
    SearchPapersTool,
)


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


def _fake_paper(position: int = 1, title: str = "Test Paper") -> PaperResult:
    return PaperResult(
        title=title,
        authors=["Author A", "Author B"],
        year=2024,
        venue="Test Journal",
        doi="10.1234/test",
        abstract="This is a test abstract.",
        citation_count=42,
        open_access=True,
        open_access_url="https://example.com/paper.pdf",
        external_ids={"openalex": "W123", "doi": "10.1234/test"},
        position=position,
    )


def _fake_paper_detail() -> PaperDetail:
    return PaperDetail(
        title="Test Paper",
        authors=["Author A", "Author B"],
        year=2024,
        venue="Test Journal",
        doi="10.1234/test",
        abstract="Full abstract text here.",
        citation_count=42,
        open_access=True,
        open_access_url="https://example.com/paper.pdf",
        external_ids={"openalex": "W123"},
        author_affiliations=["MIT", "Stanford"],
        references_count=30,
        related_works=["W456", "W789"],
        pdf_urls=["https://example.com/paper.pdf"],
        tldr="A short summary.",
        topics=["Computer Science", "NLP"],
    )


# --- Tool registration tests ---


def test_all_academic_tools_registered() -> None:
    tools = list_available_tools()
    assert "search_papers" in tools
    assert "get_paper_details" in tools
    assert "get_citations" in tools
    assert "get_references" in tools
    assert "find_similar_papers" in tools


# --- SearchPapersTool tests ---


def test_search_papers_normalizes_provider_and_filters(
    tmp_path: Path, monkeypatch
) -> None:
    tool = SearchPapersTool()
    ctx = _make_context(tmp_path)
    captured: dict[str, object] = {}

    class _FakeProvider:
        name = "fake"

        def is_configured(self) -> bool:
            return True

        def search(self, query, num_results=10, year_range=None, fields=None, sort_by="relevance"):
            captured["query"] = query
            captured["num_results"] = num_results
            captured["year_range"] = year_range
            captured["fields"] = fields
            captured["sort_by"] = sort_by
            return AcademicSearchResponse(
                query=query,
                provider="fake",
                results=[_fake_paper()],
                total_results=1,
            )

    def _fake_get_provider(name: str):
        captured["provider_name"] = name
        return _FakeProvider()

    monkeypatch.setattr(
        "flavia.tools.research.academic_search.get_academic_provider",
        _fake_get_provider,
    )

    output = tool.execute(
        {
            "query": "attention mechanisms",
            "provider": " OpenAlex ",
            "year_range": "2020-2024",
            "fields": "computer science",
            "sort_by": "CITATIONS",
            "num_results": "5",
        },
        ctx,
    )

    assert captured["provider_name"] == "openalex"
    assert captured["query"] == "attention mechanisms"
    assert captured["num_results"] == 5
    assert captured["year_range"] == (2020, 2024)
    assert captured["fields"] == "computer science"
    assert captured["sort_by"] == "citations"
    assert "Academic Search Results" in output


def test_search_papers_uses_provider_from_settings(
    tmp_path: Path, monkeypatch
) -> None:
    tool = SearchPapersTool()
    ctx = _make_context(tmp_path)
    calls: list[str] = []

    class _StubSettings:
        academic_search_provider = " semantic_scholar "

    class _FakeProvider:
        name = "fake"

        def __init__(self, pname):
            self.pname = pname

        def is_configured(self) -> bool:
            return True

        def search(self, query, num_results=10, year_range=None, fields=None, sort_by="relevance"):
            return AcademicSearchResponse(
                query=query,
                provider=self.pname,
                results=[_fake_paper()],
                total_results=1,
            )

    def _fake_get_provider(name: str):
        calls.append(name)
        return _FakeProvider(name)

    monkeypatch.setattr("flavia.config.get_settings", lambda: _StubSettings())
    monkeypatch.setattr(
        "flavia.tools.research.academic_search.get_academic_provider",
        _fake_get_provider,
    )

    output = tool.execute({"query": "test"}, ctx)

    assert calls
    assert calls[0] == "semantic_scholar"
    assert "Academic Search Results" in output
    assert "(semantic_scholar)" in output


def test_search_papers_fallback_returns_results_with_attempt_log(
    tmp_path: Path, monkeypatch
) -> None:
    tool = SearchPapersTool()
    ctx = _make_context(tmp_path)

    class _FailingProvider:
        name = "openalex"

        def is_configured(self) -> bool:
            return True

        def search(self, query, num_results=10, year_range=None, fields=None, sort_by="relevance"):
            return AcademicSearchResponse(
                query=query,
                provider="openalex",
                error_message="OpenAlex search failed (HTTP 503).",
            )

    class _WorkingProvider:
        name = "semantic_scholar"

        def is_configured(self) -> bool:
            return True

        def search(self, query, num_results=10, year_range=None, fields=None, sort_by="relevance"):
            return AcademicSearchResponse(
                query=query,
                provider="semantic_scholar",
                results=[_fake_paper()],
                total_results=1,
            )

    def _fake_get_provider(name: str):
        if name == "openalex":
            return _FailingProvider()
        if name == "semantic_scholar":
            return _WorkingProvider()
        return None

    monkeypatch.setattr(
        "flavia.tools.research.academic_search.get_academic_provider",
        _fake_get_provider,
    )

    output = tool.execute({"query": "fallback test", "provider": "openalex"}, ctx)

    assert "**Academic Search Results** (semantic_scholar)" in output
    assert "Provider fallback used" in output
    assert "HTTP 503" in output


def test_search_papers_all_providers_unavailable_has_actionable_error(
    tmp_path: Path, monkeypatch
) -> None:
    tool = SearchPapersTool()
    ctx = _make_context(tmp_path)

    class _FailingProvider:
        name = "fail"

        def is_configured(self) -> bool:
            return True

        def search(self, query, num_results=10, year_range=None, fields=None, sort_by="relevance"):
            return AcademicSearchResponse(
                query=query,
                provider="fail",
                error_message="API error.",
            )

    monkeypatch.setattr(
        "flavia.tools.research.academic_search.get_academic_provider",
        lambda _name: _FailingProvider(),
    )

    output = tool.execute({"query": "who is x", "provider": "openalex"}, ctx)

    assert "Error: academic search unavailable" in output
    assert "Attempts:" in output
    assert "OpenAlex requires no API key" in output
    assert "SEMANTIC_SCHOLAR_API_KEY" in output


def test_search_papers_empty_query_returns_error(tmp_path: Path) -> None:
    tool = SearchPapersTool()
    ctx = _make_context(tmp_path)

    output = tool.execute({"query": "  "}, ctx)
    assert "Error: search query is required" in output


def test_search_papers_invalid_sort_returns_error(tmp_path: Path) -> None:
    tool = SearchPapersTool()
    ctx = _make_context(tmp_path)

    output = tool.execute({"query": "test", "sort_by": "invalid"}, ctx)
    assert "Error: invalid sort_by" in output


# --- GetPaperDetailsTool tests ---


def test_get_paper_details_formats_output(tmp_path: Path, monkeypatch) -> None:
    tool = GetPaperDetailsTool()
    ctx = _make_context(tmp_path)

    class _FakeProvider:
        name = "openalex"

        def is_configured(self) -> bool:
            return True

        def get_details(self, paper_id):
            return PaperDetailResponse(
                paper=_fake_paper_detail(),
                provider="openalex",
            )

    monkeypatch.setattr(
        "flavia.tools.research.academic_search.get_academic_provider",
        lambda _name: _FakeProvider(),
    )

    output = tool.execute({"paper_id": "10.1234/test"}, ctx)

    assert "# Test Paper" in output
    assert "Author A" in output
    assert "Author B" in output
    assert "MIT" in output
    assert "DOI:** 10.1234/test" in output
    assert "Citations:** 42" in output
    assert "TL;DR:** A short summary." in output
    assert "Computer Science" in output


def test_get_paper_details_empty_id_returns_error(tmp_path: Path) -> None:
    tool = GetPaperDetailsTool()
    ctx = _make_context(tmp_path)

    output = tool.execute({"paper_id": ""}, ctx)
    assert "Error: paper_id is required" in output


def test_get_paper_details_detects_openalex_id(tmp_path: Path, monkeypatch) -> None:
    tool = GetPaperDetailsTool()
    ctx = _make_context(tmp_path)
    captured_providers: list[str] = []

    class _FakeProvider:
        def __init__(self, name):
            self.name = name

        def is_configured(self) -> bool:
            return True

        def get_details(self, paper_id):
            return PaperDetailResponse(
                paper=_fake_paper_detail(),
                provider=self.name,
            )

    def _fake_get_provider(name: str):
        captured_providers.append(name)
        return _FakeProvider(name)

    monkeypatch.setattr(
        "flavia.tools.research.academic_search.get_academic_provider",
        _fake_get_provider,
    )

    tool.execute({"paper_id": "W1234567890"}, ctx)

    # OpenAlex ID should route to openalex first
    assert captured_providers[0] == "openalex"


# --- GetCitationsTool tests ---


def test_get_citations_formats_output(tmp_path: Path, monkeypatch) -> None:
    tool = GetCitationsTool()
    ctx = _make_context(tmp_path)

    class _FakeProvider:
        name = "openalex"

        def is_configured(self) -> bool:
            return True

        def get_citations(self, paper_id, num_results=10, sort_by="relevance"):
            return CitationResponse(
                paper_id=paper_id,
                citations=[_fake_paper(1, "Citing Paper A"), _fake_paper(2, "Citing Paper B")],
                provider="openalex",
                total_results=100,
            )

    monkeypatch.setattr(
        "flavia.tools.research.academic_search.get_academic_provider",
        lambda _name: _FakeProvider(),
    )

    output = tool.execute({"paper_id": "10.1234/test", "num_results": 2}, ctx)

    assert "Citations of 10.1234/test" in output
    assert "Citing Paper A" in output
    assert "Citing Paper B" in output
    assert "100" in output


# --- GetReferencesTool tests ---


def test_get_references_formats_output(tmp_path: Path, monkeypatch) -> None:
    tool = GetReferencesTool()
    ctx = _make_context(tmp_path)

    class _FakeProvider:
        name = "openalex"

        def is_configured(self) -> bool:
            return True

        def get_references(self, paper_id, num_results=10):
            return CitationResponse(
                paper_id=paper_id,
                citations=[_fake_paper(1, "Referenced Paper")],
                provider="openalex",
                total_results=30,
            )

    monkeypatch.setattr(
        "flavia.tools.research.academic_search.get_academic_provider",
        lambda _name: _FakeProvider(),
    )

    output = tool.execute({"paper_id": "W123"}, ctx)

    assert "References of W123" in output
    assert "Referenced Paper" in output


# --- FindSimilarPapersTool tests ---


def test_find_similar_papers_formats_output(tmp_path: Path, monkeypatch) -> None:
    tool = FindSimilarPapersTool()
    ctx = _make_context(tmp_path)

    class _FakeProvider:
        name = "semantic_scholar"

        def is_configured(self) -> bool:
            return True

        def find_similar(self, paper_id, num_results=10):
            return AcademicSearchResponse(
                query=f"similar to {paper_id}",
                results=[_fake_paper(1, "Similar Paper")],
                provider="semantic_scholar",
            )

    monkeypatch.setattr(
        "flavia.tools.research.academic_search.get_academic_provider",
        lambda _name: _FakeProvider(),
    )

    output = tool.execute({"paper_id": "10.1234/test"}, ctx)

    assert "Papers Similar to 10.1234/test" in output
    assert "Similar Paper" in output


# --- Provider-level tests ---


def test_openalex_http_error_logs_diagnostics(monkeypatch, caplog) -> None:
    from flavia.tools.research.academic_providers.openalex import OpenAlexProvider

    provider = OpenAlexProvider()

    def _fake_get(*_args, **_kwargs):
        req = httpx.Request("GET", "https://api.openalex.org/works")
        resp = httpx.Response(503, request=req)
        raise httpx.HTTPStatusError("503 Service Unavailable", request=req, response=resp)

    monkeypatch.setattr(
        "flavia.tools.research.academic_providers.openalex.httpx.get", _fake_get
    )

    caplog.set_level(
        logging.WARNING, logger="flavia.tools.research.academic_providers.openalex"
    )
    response = provider.search("test query")

    assert response.error_message is not None
    assert "HTTP 503" in response.error_message

    messages = [record.getMessage() for record in caplog.records]
    assert any("OpenAlex search HTTP error" in msg for msg in messages)
    assert any("status=503" in msg for msg in messages)


def test_semantic_scholar_network_error_logs_diagnostics(monkeypatch, caplog) -> None:
    from flavia.tools.research.academic_providers.semantic_scholar import (
        SemanticScholarProvider,
    )

    provider = SemanticScholarProvider()

    def _fake_get(*_args, **_kwargs):
        req = httpx.Request(
            "GET", "https://api.semanticscholar.org/graph/v1/paper/search"
        )
        raise httpx.ConnectError("dns failure", request=req)

    monkeypatch.setattr(
        "flavia.tools.research.academic_providers.semantic_scholar.httpx.get",
        _fake_get,
    )

    caplog.set_level(
        logging.WARNING,
        logger="flavia.tools.research.academic_providers.semantic_scholar",
    )
    response = provider.search("test query")

    assert response.error_message is not None
    assert "network error" in response.error_message

    messages = [record.getMessage() for record in caplog.records]
    assert any("Semantic Scholar search network error" in msg for msg in messages)
    assert any("ConnectError" in msg for msg in messages)


def test_semantic_scholar_api_key_not_leaked_in_error(monkeypatch) -> None:
    from flavia.tools.research.academic_providers.semantic_scholar import (
        SemanticScholarProvider,
    )

    provider = SemanticScholarProvider()
    secret_key = "secret-s2-key-12345"

    class _StubSettings:
        semantic_scholar_api_key = secret_key

    def _fake_get(*_args, **_kwargs):
        req = httpx.Request(
            "GET", "https://api.semanticscholar.org/graph/v1/paper/search"
        )
        resp = httpx.Response(429, request=req)
        raise httpx.HTTPStatusError("429 Too Many Requests", request=req, response=resp)

    monkeypatch.setattr("flavia.config.get_settings", lambda: _StubSettings())
    monkeypatch.setattr(
        "flavia.tools.research.academic_providers.semantic_scholar.httpx.get",
        _fake_get,
    )

    response = provider.search("test query")

    assert response.error_message is not None
    assert secret_key not in response.error_message
    assert "HTTP 429" in response.error_message


def test_openalex_abstract_reconstruction() -> None:
    from flavia.tools.research.academic_providers.openalex import _reconstruct_abstract

    inverted_index = {
        "We": [0],
        "propose": [1],
        "a": [2],
        "new": [3],
        "method": [4],
    }
    result = _reconstruct_abstract(inverted_index)
    assert result == "We propose a new method"


def test_openalex_abstract_reconstruction_empty() -> None:
    from flavia.tools.research.academic_providers.openalex import _reconstruct_abstract

    assert _reconstruct_abstract(None) == ""
    assert _reconstruct_abstract({}) == ""


def test_year_range_parsing() -> None:
    from flavia.tools.research.academic_search import _parse_year_range

    assert _parse_year_range("2020-2024") == (2020, 2024)
    assert _parse_year_range("2023") == (2023, 2023)
    assert _parse_year_range("") is None
    assert _parse_year_range(None) is None
    assert _parse_year_range("invalid") is None


def test_response_formatting_includes_paper_metadata(
    tmp_path: Path, monkeypatch
) -> None:
    tool = SearchPapersTool()
    ctx = _make_context(tmp_path)

    paper = _fake_paper()

    class _FakeProvider:
        name = "openalex"

        def is_configured(self) -> bool:
            return True

        def search(self, query, num_results=10, year_range=None, fields=None, sort_by="relevance"):
            return AcademicSearchResponse(
                query=query,
                provider="openalex",
                results=[paper],
                total_results=1,
            )

    monkeypatch.setattr(
        "flavia.tools.research.academic_search.get_academic_provider",
        lambda _name: _FakeProvider(),
    )

    output = tool.execute({"query": "test"}, ctx)

    assert "Test Paper" in output
    assert "Author A" in output
    assert "DOI: 10.1234/test" in output
    assert "Citations: 42" in output
    assert "Open Access" in output
    assert "test abstract" in output
