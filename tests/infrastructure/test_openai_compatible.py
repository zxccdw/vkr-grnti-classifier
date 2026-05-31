from __future__ import annotations

import json

import httpx
import pytest

from backend.infrastructure.llm.openai_compatible import OpenAICompatibleProvider


def _provider(transport: httpx.MockTransport) -> OpenAICompatibleProvider:
    p = OpenAICompatibleProvider(
        name="gigachat",
        base_url="http://llm.example/v1",
        token="secret",
        model="GigaChat-Pro",
    )
    p._client = httpx.AsyncClient(
        base_url="http://llm.example/v1",
        headers={"Authorization": "Bearer secret"},
        transport=transport,
    )
    return p


async def test_describe_splits_fragments_from_chat_completion_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "first fragment\nsecond fragment\n\nthird"}}]
            },
        )

    provider = _provider(httpx.MockTransport(handler))
    result = await provider.describe("Геномика", "34.15.23", ["ГРНТИ", "Био"])
    assert result == ["first fragment", "second fragment", "third"]


async def test_describe_sends_authorization_header_and_payload() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "x"}}]},
        )

    provider = _provider(httpx.MockTransport(handler))
    await provider.describe("X", "34.15.99", ["A", "B"])

    assert captured["url"].endswith("/chat/completions")
    assert captured["auth"] == "Bearer secret"
    body = captured["body"]
    assert body["model"] == "GigaChat-Pro"
    assert body["temperature"] == 0.3
    assert isinstance(body["messages"], list) and len(body["messages"]) == 2
    assert body["messages"][0]["role"] == "system"
    assert "X" in body["messages"][1]["content"]
    assert "34.15.99" in body["messages"][1]["content"]


async def test_describe_propagates_http_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    provider = _provider(httpx.MockTransport(handler))
    with pytest.raises(httpx.HTTPStatusError):
        await provider.describe("X", "0", ["A"])


async def test_describe_drops_blank_lines() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "  \n  \n  one  \n   \n  two  \n  "}}]},
        )

    provider = _provider(httpx.MockTransport(handler))
    result = await provider.describe("X", "0", ["A"])
    assert result == ["one", "two"]
