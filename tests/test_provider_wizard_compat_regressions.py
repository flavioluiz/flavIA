"""Regression tests for provider wizard OpenAI compatibility paths."""

import sys
from types import SimpleNamespace

import flavia.setup.provider_wizard as provider_wizard


def test_fetch_provider_models_fallback_preserves_headers(monkeypatch):
    openai_calls: list[dict] = []
    created_http_clients: list[object] = []

    class _FakeHttpClient:
        def __init__(self, timeout=None, headers=None):
            self.timeout = timeout
            self.headers = headers

    class _FakeHttpx:
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
            openai_calls.append(kwargs)
            if "http_client" not in kwargs:
                raise TypeError("Client.__init__() got an unexpected keyword argument 'proxies'")
            self.models = SimpleNamespace(
                list=lambda: SimpleNamespace(data=[SimpleNamespace(id="gpt-4o")])
            )

    monkeypatch.setattr("flavia.setup.provider_wizard.httpx", _FakeHttpx)
    monkeypatch.setattr("flavia.setup.provider_wizard.OpenAI", _FakeOpenAI)

    models, error = provider_wizard.fetch_provider_models(
        api_key="test-key",
        api_base_url="https://api.example.com/v1",
        headers={"X-Test-Header": "value"},
    )

    assert error is None
    assert [m["id"] for m in models] == ["gpt-4o"]
    assert len(openai_calls) == 2
    assert "default_headers" in openai_calls[0]
    assert "http_client" in openai_calls[1]
    assert created_http_clients[0].headers == {"X-Test-Header": "value"}


def test_test_provider_connection_fallback_preserves_headers(monkeypatch):
    openai_calls: list[dict] = []
    created_http_clients: list[object] = []

    class _FakeHttpClient:
        def __init__(self, timeout=None, headers=None):
            self.timeout = timeout
            self.headers = headers

    class _FakeHttpx:
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
            openai_calls.append(kwargs)
            if "http_client" not in kwargs:
                raise TypeError("Client.__init__() got an unexpected keyword argument 'proxies'")
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(
                    create=lambda **_kwargs: SimpleNamespace(
                        choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))]
                    )
                )
            )

    monkeypatch.setitem(sys.modules, "httpx", _FakeHttpx)
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=_FakeOpenAI))

    success, message = provider_wizard.test_provider_connection(
        api_key="test-key",
        api_base_url="https://api.example.com/v1",
        model_id="gpt-4o",
        headers={"X-Test-Header": "value"},
    )

    assert success is True
    assert "successful" in message.lower()
    assert len(openai_calls) == 2
    assert "default_headers" in openai_calls[0]
    assert "http_client" in openai_calls[1]
    assert created_http_clients[0].headers == {"X-Test-Header": "value"}
