from __future__ import annotations

import logging
from typing import Any

import httpx
from gigachat import GigaChat
from gigachat.models import Chat, Messages, MessagesRole
from gigachat.settings import AUTH_URL, BASE_URL

from backend.infrastructure.llm.prompt import build_v8_messages, split_fragments

logger = logging.getLogger(__name__)


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
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._timeout = timeout
        self._verify_ssl = verify_ssl
        self._access_token = self._get_access_token(credentials, verify_ssl)

    def _get_access_token(self, credentials: str, verify_ssl: bool) -> str | None:
        try:
            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
                "Authorization": f"Basic {credentials}",
            }
            with httpx.Client(verify=verify_ssl) as client:
                response = client.post(
                    AUTH_URL,
                    headers=headers,
                    data={"scope": "GIGACHAT_API_PERS"},
                    timeout=self._timeout,
                )
                if response.status_code == 200:
                    token_data: Any = response.json()
                    token = token_data.get("access_token")
                    if isinstance(token, str):
                        return token
        except Exception as e:
            logger.warning(f"Failed to get GigaChat access token: {e}")
        return None

    def is_available(self) -> bool:
        return self._access_token is not None

    async def describe(self, label: str, code: str, parent_chain: list[str]) -> list[str]:
        if not self._access_token:
            raise RuntimeError("GigaChat access token not available")

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
            access_token=self._access_token,
            base_url=BASE_URL,
            timeout=self._timeout,
            verify_ssl_certs=self._verify_ssl,
        ) as client:
            response = await client.achat(chat)
        raw: str = response.choices[0].message.content
        return split_fragments(raw)

    async def aclose(self) -> None:
        pass
