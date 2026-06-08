from __future__ import annotations

import httpx
import numpy as np


class OpenAIEmbedder:
    """Embedder via OpenAI-compatible /embeddings endpoint (e.g. polza.ai)."""

    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        model: str,
        normalize: bool = True,
        timeout: float = 30.0,
    ) -> None:
        self.model_name = f"openai:{model}"
        self.model = model
        self._normalize = normalize
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            headers={"Authorization": f"Bearer {token}"},
        )
        self._dim: int | None = None

    def encode(
        self,
        texts: str | list[str],
        batch_size: int = 32,
        normalize: bool | None = None,
    ) -> np.ndarray:
        if isinstance(texts, str):
            texts = [texts]
        if not texts:
            return np.zeros((0, self._dim or 0), dtype=np.float32)

        all_vecs: list[np.ndarray] = []
        for start in range(0, len(texts), batch_size):
            chunk = texts[start : start + batch_size]
            resp = self._client.post(
                "/embeddings",
                json={"input": chunk, "model": self.model},
            )
            resp.raise_for_status()
            data = resp.json()["data"]
            vecs = np.array([item["embedding"] for item in data], dtype=np.float32)
            all_vecs.append(vecs)

        result = np.vstack(all_vecs) if len(all_vecs) > 1 else all_vecs[0]
        if self._dim is None and result.size:
            self._dim = int(result.shape[-1])

        do_normalize = self._normalize if normalize is None else normalize
        if do_normalize:
            norms = np.linalg.norm(result, axis=1, keepdims=True)
            result = result / np.where(norms == 0, 1, norms)

        return result

    def encode_single(self, text: str) -> np.ndarray:
        result: np.ndarray = self.encode([text])[0]
        return result

    @property
    def embedding_dim(self) -> int:
        if self._dim is None:
            self.encode_single("dim probe")
        assert self._dim is not None
        return self._dim
