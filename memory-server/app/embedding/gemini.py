"""
Google Gemini Embedding Provider

使用 Gemini text-embedding-004 模型，输出 768 维向量。
API: https://generativelanguage.googleapis.com/v1beta/models/{model}:embedContent
"""

from __future__ import annotations

import logging

import httpx

from app.embedding.base import EmbeddingError, EmbeddingProvider

logger = logging.getLogger(__name__)

_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
_GEMINI_DEFAULT_MODEL = "text-embedding-004"
_GEMINI_DEFAULT_DIMENSION = 768


class GeminiEmbeddingProvider(EmbeddingProvider):
    """Google Gemini Embedding 提供者。"""

    def __init__(
        self,
        api_key: str,
        model: str = _GEMINI_DEFAULT_MODEL,
        dimension: int = _GEMINI_DEFAULT_DIMENSION,
        timeout: float = 30.0,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._dimension = dimension
        self._timeout = timeout
        self._client = httpx.AsyncClient(timeout=timeout)

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def provider_name(self) -> str:
        return f"gemini ({self._model})"

    async def embed(self, text: str) -> list[float]:
        """单条文本转向量。"""
        url = f"{_GEMINI_BASE_URL}/models/{self._model}:embedContent"
        payload = {
            "content": {"parts": [{"text": text}]},
            "taskType": "RETRIEVAL_DOCUMENT",
        }

        try:
            resp = await self._client.post(
                url, json=payload, params={"key": self._api_key}
            )
            resp.raise_for_status()
            data = resp.json()
            embedding = data.get("embedding", {}).get("values")
            if not embedding:
                raise EmbeddingError(
                    f"Gemini returned empty embedding: {data}"
                )
            return embedding
        except httpx.HTTPStatusError as e:
            raise EmbeddingError(
                f"Gemini API error {e.response.status_code}: {e.response.text}"
            ) from e
        except httpx.RequestError as e:
            raise EmbeddingError(f"Gemini request failed: {e}") from e

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """批量文本转向量。"""
        url = f"{_GEMINI_BASE_URL}/models/{self._model}:batchEmbedContents"
        requests = [
            {
                "model": f"models/{self._model}",
                "content": {"parts": [{"text": t}]},
                "taskType": "RETRIEVAL_DOCUMENT",
            }
            for t in texts
        ]
        payload = {"requests": requests}

        try:
            resp = await self._client.post(
                url, json=payload, params={"key": self._api_key}
            )
            resp.raise_for_status()
            data = resp.json()
            embeddings = data.get("embeddings", [])
            return [e.get("values", []) for e in embeddings]
        except httpx.HTTPStatusError as e:
            raise EmbeddingError(
                f"Gemini batch API error {e.response.status_code}: {e.response.text}"
            ) from e
        except httpx.RequestError as e:
            raise EmbeddingError(f"Gemini batch request failed: {e}") from e

    async def close(self) -> None:
        """关闭 HTTP 客户端。"""
        await self._client.aclose()
