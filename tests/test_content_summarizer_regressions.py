"""Regression tests for LLM summarization compatibility paths."""

import sys
from types import SimpleNamespace

from flavia.content.scanner import FileEntry
from flavia.content.summarizer import summarize_file


def _build_entry(path: str) -> FileEntry:
    return FileEntry(
        path=path,
        name=path,
        extension=".md",
        file_type="text",
        category="markdown",
        size_bytes=10,
        created_at="2026-01-01T00:00:00+00:00",
        modified_at="2026-01-01T00:00:00+00:00",
        indexed_at="2026-01-01T00:00:00+00:00",
        checksum_sha256="abc",
    )


def test_summarize_file_uses_openai_compat_fallback_for_httpx_proxy_error(monkeypatch, tmp_path):
    md_file = tmp_path / "doc.md"
    md_file.write_text("This is a short document about testing.", encoding="utf-8")
    entry = _build_entry("doc.md")

    calls: list[dict] = []
    created_http_clients: list[object] = []

    class _FakeHttpClient:
        def __init__(self, timeout=None, headers=None):
            self.timeout = timeout
            self.headers = headers

    class _FakeHttpxModule:
        @staticmethod
        def Timeout(*args, **kwargs):
            return {"args": args, "kwargs": kwargs}

        @staticmethod
        def Client(timeout=None, headers=None):
            client = _FakeHttpClient(timeout=timeout, headers=headers)
            created_http_clients.append(client)
            return client

    class _FakeOpenAI:
        def __init__(self, **kwargs):
            calls.append(kwargs)
            if "http_client" not in kwargs:
                raise TypeError("Client.__init__() got an unexpected keyword argument 'proxies'")
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(
                    create=lambda **_kwargs: SimpleNamespace(
                        choices=[SimpleNamespace(message=SimpleNamespace(content="Generated summary"))]
                    )
                )
            )

    monkeypatch.setitem(sys.modules, "httpx", _FakeHttpxModule)
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=_FakeOpenAI))

    result = summarize_file(
        entry=entry,
        base_dir=tmp_path,
        api_key="test-key",
        api_base_url="https://api.example.com/v1",
        model="test-model",
        headers={"X-Test-Header": "value"},
    )

    assert result == "Generated summary"
    assert len(calls) == 2
    assert "default_headers" in calls[0]
    assert "http_client" in calls[1]
    assert created_http_clients[0].headers == {"X-Test-Header": "value"}
