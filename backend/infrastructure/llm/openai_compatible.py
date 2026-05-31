from __future__ import annotations

import httpx

from backend.infrastructure.llm.prompt import build_v8_messages, split_fragments


class OpenAICompatibleProvider:
    def __init__(
        self,
        *,
        name: str,
        base_url: str,
        token: str,
        model: str,
        temperature: float = 0.3,
        max_tokens: int = 512,
        timeout: float = 60.0,
        verify_ssl: bool = True,
    ) -> None:
        self.name = name
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            verify=verify_ssl,
            headers={"Authorization": f"Bearer {token}"},
        )
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens

    async def describe(self, label: str, code: str, parent_chain: list[str]) -> list[str]:
        payload = {
            "model": self._model,
            "messages": build_v8_messages(label=label, code=code, parent_chain=parent_chain),
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
        }
        response = await self._client.post("/chat/completions", json=payload)
        response.raise_for_status()
        data = response.json()
        raw = data["choices"][0]["message"]["content"]
        return split_fragments(raw)

    async def aclose(self) -> None:
        await self._client.aclose()
