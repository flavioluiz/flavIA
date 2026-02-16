"""Regression tests for LLM summarization compatibility paths."""

import sys
from types import SimpleNamespace

from flavia.content.scanner import FileEntry
from flavia.content import summarizer as summarizer_module
from flavia.content.summarizer import summarize_file, summarize_file_with_quality


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


def test_summarize_file_handles_empty_response(monkeypatch, tmp_path):
    """Test handling when LLM returns empty/null content."""
    md_file = tmp_path / "doc.md"
    md_file.write_text("This is a document.", encoding="utf-8")
    entry = _build_entry("doc.md")

    class _FakeOpenAI:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(
                    create=lambda **_kwargs: SimpleNamespace(
                        choices=[SimpleNamespace(message=SimpleNamespace(content=None))]
                    )
                )
            )

    monkeypatch.setitem(sys.modules, "httpx", SimpleNamespace(Timeout=lambda *a, **kw: None))
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=_FakeOpenAI))

    result = summarize_file(
        entry=entry,
        base_dir=tmp_path,
        api_key="test-key",
        api_base_url="https://api.example.com/v1",
        model="test-model",
    )

    assert result is None


def test_summarize_file_retries_when_first_response_is_empty(monkeypatch, tmp_path):
    """If the first response is empty, summarizer should retry once."""
    md_file = tmp_path / "doc.md"
    md_file.write_text("This is a document.", encoding="utf-8")
    entry = _build_entry("doc.md")

    class _FakeOpenAI:
        def __init__(self, **kwargs):
            calls = {"count": 0}

            def _create(**_kwargs):
                calls["count"] += 1
                if calls["count"] == 1:
                    return SimpleNamespace(
                        choices=[
                            SimpleNamespace(
                                message=SimpleNamespace(content=None),
                                finish_reason="length",
                            )
                        ],
                        usage=SimpleNamespace(completion_tokens=200),
                    )
                return SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            message=SimpleNamespace(content="Generated summary"),
                            finish_reason="stop",
                        )
                    ],
                    usage=SimpleNamespace(completion_tokens=32),
                )

            self.chat = SimpleNamespace(
                completions=SimpleNamespace(create=_create)
            )

    monkeypatch.setitem(sys.modules, "httpx", SimpleNamespace(Timeout=lambda *a, **kw: None))
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=_FakeOpenAI))

    result = summarize_file(
        entry=entry,
        base_dir=tmp_path,
        api_key="test-key",
        api_base_url="https://api.example.com/v1",
        model="test-model",
    )

    assert result == "Generated summary"


def test_summarize_file_handles_structured_content_parts(monkeypatch, tmp_path):
    """Providers returning message.content as a list of parts should be supported."""
    md_file = tmp_path / "doc.md"
    md_file.write_text("This is a document.", encoding="utf-8")
    entry = _build_entry("doc.md")

    class _FakeOpenAI:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(
                    create=lambda **_kwargs: SimpleNamespace(
                        choices=[
                            SimpleNamespace(
                                message=SimpleNamespace(
                                    content=[
                                        {"type": "text", "text": "Part A"},
                                        {"type": "text", "text": "Part B"},
                                    ]
                                )
                            )
                        ]
                    )
                )
            )

    monkeypatch.setitem(sys.modules, "httpx", SimpleNamespace(Timeout=lambda *a, **kw: None))
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=_FakeOpenAI))

    result = summarize_file(
        entry=entry,
        base_dir=tmp_path,
        api_key="test-key",
        api_base_url="https://api.example.com/v1",
        model="test-model",
    )

    assert result == "Part A\nPart B"


def test_summarize_file_records_empty_after_retry_metadata(monkeypatch, tmp_path):
    md_file = tmp_path / "doc.md"
    md_file.write_text("This is a document.", encoding="utf-8")
    entry = _build_entry("doc.md")

    class _FakeOpenAI:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(
                    create=lambda **_kwargs: SimpleNamespace(
                        choices=[
                            SimpleNamespace(
                                message=SimpleNamespace(content=None),
                                finish_reason="length",
                            )
                        ],
                        usage=SimpleNamespace(completion_tokens=200),
                    )
                )
            )

    monkeypatch.setitem(sys.modules, "httpx", SimpleNamespace(Timeout=lambda *a, **kw: None))
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=_FakeOpenAI))

    result = summarize_file(
        entry=entry,
        base_dir=tmp_path,
        api_key="test-key",
        api_base_url="https://api.example.com/v1",
        model="test-model",
    )

    assert result is None
    info = summarizer_module.get_last_llm_call_info()
    assert info.get("status") == "empty_after_retry"
    assert info.get("first_finish_reason") == "length"
    assert info.get("retry_finish_reason") == "length"


def test_summarize_file_handles_empty_choices(monkeypatch, tmp_path):
    """Test handling when LLM returns empty choices list."""
    md_file = tmp_path / "doc.md"
    md_file.write_text("This is a document.", encoding="utf-8")
    entry = _build_entry("doc.md")

    class _FakeOpenAI:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(create=lambda **_kwargs: SimpleNamespace(choices=[]))
            )

    monkeypatch.setitem(sys.modules, "httpx", SimpleNamespace(Timeout=lambda *a, **kw: None))
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=_FakeOpenAI))

    result = summarize_file(
        entry=entry,
        base_dir=tmp_path,
        api_key="test-key",
        api_base_url="https://api.example.com/v1",
        model="test-model",
    )

    assert result is None


def test_summarize_file_with_quality_parses_quality(monkeypatch, tmp_path):
    md_file = tmp_path / "doc.md"
    md_file.write_text("This is a document.", encoding="utf-8")
    entry = _build_entry("doc.md")

    monkeypatch.setattr(
        summarizer_module,
        "_call_llm",
        lambda *args, **kwargs: "Concise summary.\ngood",
    )

    summary, quality = summarize_file_with_quality(
        entry=entry,
        base_dir=tmp_path,
        api_key="test-key",
        api_base_url="https://api.example.com/v1",
        model="test-model",
    )

    assert summary == "Concise summary."
    assert quality == "good"


def test_summarize_file_with_quality_allows_missing_quality(monkeypatch, tmp_path):
    md_file = tmp_path / "doc.md"
    md_file.write_text("This is a document.", encoding="utf-8")
    entry = _build_entry("doc.md")

    monkeypatch.setattr(
        summarizer_module,
        "_call_llm",
        lambda *args, **kwargs: "Concise summary only.",
    )

    summary, quality = summarize_file_with_quality(
        entry=entry,
        base_dir=tmp_path,
        api_key="test-key",
        api_base_url="https://api.example.com/v1",
        model="test-model",
    )

    assert summary == "Concise summary only."
    assert quality is None


def test_summarize_file_with_quality_parses_quality_with_prefix(monkeypatch, tmp_path):
    md_file = tmp_path / "doc.md"
    md_file.write_text("This is a document.", encoding="utf-8")
    entry = _build_entry("doc.md")

    monkeypatch.setattr(
        summarizer_module,
        "_call_llm",
        lambda *args, **kwargs: "Line one summary.\nLine two summary.\nQuality: partial",
    )

    summary, quality = summarize_file_with_quality(
        entry=entry,
        base_dir=tmp_path,
        api_key="test-key",
        api_base_url="https://api.example.com/v1",
        model="test-model",
    )

    assert summary == "Line one summary. Line two summary."
    assert quality == "partial"


def test_summarize_file_uses_custom_timeouts(monkeypatch, tmp_path):
    """Test that custom timeout values are passed correctly."""
    md_file = tmp_path / "doc.md"
    md_file.write_text("Short doc", encoding="utf-8")
    entry = _build_entry("doc.md")

    timeout_calls = []

    class _FakeHttpxModule:
        @staticmethod
        def Timeout(*args, **kwargs):
            timeout_calls.append({"args": args, "kwargs": kwargs})
            return {"args": args, "kwargs": kwargs}

    class _FakeOpenAI:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(
                    create=lambda **_kwargs: SimpleNamespace(
                        choices=[SimpleNamespace(message=SimpleNamespace(content="Summary"))]
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
        timeout=60.0,
        connect_timeout=20.0,
    )

    assert result == "Summary"
    assert len(timeout_calls) == 1
    assert timeout_calls[0]["args"] == (60.0,)
    assert timeout_calls[0]["kwargs"]["connect"] == 20.0


def test_summarize_file_handles_openai_api_status_error(monkeypatch, tmp_path, caplog):
    """OpenAI APIStatusError should be handled as a warning and return None."""
    md_file = tmp_path / "doc.md"
    md_file.write_text("This is a document.", encoding="utf-8")
    entry = _build_entry("doc.md")

    class _FakeAPIConnectionError(Exception):
        pass

    class _FakeAPITimeoutError(Exception):
        pass

    class _FakeAPIStatusError(Exception):
        def __init__(self, status_code):
            super().__init__(f"status={status_code}")
            self.status_code = status_code

    class _FakeOpenAI:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(
                    create=lambda **_kwargs: (_ for _ in ()).throw(_FakeAPIStatusError(429))
                )
            )

    class _FakeHttpxModule:
        class TimeoutException(Exception):
            pass

        class ConnectTimeout(TimeoutException):
            pass

        class HTTPStatusError(Exception):
            pass

        @staticmethod
        def Timeout(*args, **kwargs):
            return None

    monkeypatch.setitem(sys.modules, "httpx", _FakeHttpxModule)
    monkeypatch.setitem(
        sys.modules,
        "openai",
        SimpleNamespace(
            OpenAI=_FakeOpenAI,
            APIConnectionError=_FakeAPIConnectionError,
            APITimeoutError=_FakeAPITimeoutError,
            APIStatusError=_FakeAPIStatusError,
        ),
    )

    with caplog.at_level("WARNING"):
        result = summarize_file(
            entry=entry,
            base_dir=tmp_path,
            api_key="test-key",
            api_base_url="https://api.example.com/v1",
            model="test-model",
        )

    assert result is None
    assert "LLM OpenAI API error for model test-model: status=429" in caplog.text


def test_summarize_file_handles_openai_timeout_error(monkeypatch, tmp_path, caplog):
    """OpenAI APITimeoutError should be handled as warning and return None."""
    md_file = tmp_path / "doc.md"
    md_file.write_text("This is a document.", encoding="utf-8")
    entry = _build_entry("doc.md")

    class _FakeAPIConnectionError(Exception):
        pass

    class _FakeAPITimeoutError(Exception):
        pass

    class _FakeAPIStatusError(Exception):
        pass

    class _FakeOpenAI:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(
                    create=lambda **_kwargs: (_ for _ in ()).throw(_FakeAPITimeoutError("timeout"))
                )
            )

    class _FakeHttpxModule:
        class TimeoutException(Exception):
            pass

        class ConnectTimeout(TimeoutException):
            pass

        class HTTPStatusError(Exception):
            pass

        @staticmethod
        def Timeout(*args, **kwargs):
            return None

    monkeypatch.setitem(sys.modules, "httpx", _FakeHttpxModule)
    monkeypatch.setitem(
        sys.modules,
        "openai",
        SimpleNamespace(
            OpenAI=_FakeOpenAI,
            APIConnectionError=_FakeAPIConnectionError,
            APITimeoutError=_FakeAPITimeoutError,
            APIStatusError=_FakeAPIStatusError,
        ),
    )

    with caplog.at_level("WARNING"):
        result = summarize_file(
            entry=entry,
            base_dir=tmp_path,
            api_key="test-key",
            api_base_url="https://api.example.com/v1",
            model="test-model",
        )

    assert result is None
    assert "LLM OpenAI timeout/connection error for model test-model: timeout" in caplog.text


def test_summarize_file_rejects_path_traversal_from_converted_to(tmp_path, caplog):
    """Converted path must not escape the project base directory."""
    outside_file = tmp_path.parent / "outside.md"
    outside_file.write_text("sensitive content", encoding="utf-8")

    entry = _build_entry("paper.pdf")
    entry.converted_to = "../outside.md"

    with caplog.at_level("WARNING"):
        result = summarize_file(
            entry=entry,
            base_dir=tmp_path,
            api_key="test-key",
            api_base_url="https://api.example.com/v1",
            model="test-model",
        )

    assert result is None
    assert "Skipping summary for path outside base_dir: ../outside.md" in caplog.text
