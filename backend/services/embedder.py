from __future__ import annotations

import httpx
import numpy as np


class TextEmbedder:
    """HTTP-клиент к TEI (HuggingFace text-embeddings-inference).

    Embeddings-сервис поднят как отдельный контейнер с готовой моделью BGE-M3;
    backend здесь только сериализует запросы и нормализует векторы.
    """

    def __init__(
        self,
        endpoint: str = "http://embeddings:80",
        normalize: bool = True,
        timeout: float = 30.0,
    ):
        self.endpoint = endpoint.rstrip("/")
        self.normalize = normalize
        self._client = httpx.Client(timeout=timeout)
        self._dim: int | None = None
        # Лёгкий маркер для health-эндпоинта.
        self.model = "tei:remote"

    def encode(
        self,
        texts: str | list[str],
        batch_size: int = 32,
        normalize: bool | None = None,
    ) -> np.ndarray:
        if isinstance(texts, str):
            texts = [texts]
        if not texts:
            return np.zeros((0, self.embedding_dim), dtype=np.float32)

        do_normalize = self.normalize if normalize is None else normalize

        all_vecs: list[np.ndarray] = []
        for start in range(0, len(texts), batch_size):
            chunk = texts[start : start + batch_size]
            resp = self._client.post(
                f"{self.endpoint}/embed",
                json={"inputs": chunk, "normalize": do_normalize},
            )
            resp.raise_for_status()
            vecs = np.asarray(resp.json(), dtype=np.float32)
            all_vecs.append(vecs)

        result = np.vstack(all_vecs) if len(all_vecs) > 1 else all_vecs[0]
        if self._dim is None and result.size:
            self._dim = int(result.shape[-1])
        return result

    def encode_single(self, text: str) -> np.ndarray:
        return self.encode([text])[0]

    @property
    def embedding_dim(self) -> int:
        if self._dim is None:
            _ = self.encode_single("dim probe")
        assert self._dim is not None
        return self._dim
