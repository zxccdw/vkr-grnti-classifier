from __future__ import annotations

from gigachat import GigaChat
from gigachat.models import Chat, Messages, MessagesRole
from gigachat.settings import AUTH_URL, BASE_URL

from backend.infrastructure.llm.prompt import build_v8_messages, split_fragments


class GigaChatProvider:
    def __init__(
        self,
        *,
        credentials: str,
        model: str = "GigaChat-Pro",
        temperature: float = 0.3,
        max_tokens: int = 512,
        timeout: float = 60.0,
        verify_ssl: bool = False,
    ) -> None:
        self.name = "gigachat"
        self._credentials = credentials
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._timeout = timeout
        self._verify_ssl = verify_ssl

    async def describe(self, label: str, code: str, parent_chain: list[str]) -> list[str]:
        messages = build_v8_messages(label=label, code=code, parent_chain=parent_chain)
        chat = Chat(
            model=self._model,
            messages=[
                Messages(role=MessagesRole(m["role"]), content=m["content"]) for m in messages
            ],
            temperature=self._temperature,
            max_tokens=self._max_tokens,
        )
        async with GigaChat(
            credentials=self._credentials,
            base_url=BASE_URL,
            auth_url=AUTH_URL,
            timeout=self._timeout,
            verify_ssl_certs=self._verify_ssl,
        ) as client:
            response = await client.achat(chat)
        raw: str = response.choices[0].message.content
        return split_fragments(raw)

    async def aclose(self) -> None:
        pass
