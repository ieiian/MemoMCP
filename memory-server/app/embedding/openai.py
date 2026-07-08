"""
OpenAI Embedding Provider

使用 OpenAI text-embedding-3-small/large 模型。
API: https://api.openai.com/v1/embeddings
"""

from __future__ import annotations

import logging

import httpx

from app.embedding.base import EmbeddingError, EmbeddingProvider

logger = logging.getLogger(__name__)

_OPENAI_BASE_URL = "https://api.openai.com/v1"
_OPENAI_DEFAULT_MODEL = "text-embedding-3-small"
_OPENAI_DEFAULT_DIMENSION = 1536


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """OpenAI 官方 Embedding 提供者。"""

    def __init__(
        self,
        api_key: str,
        model: str = _OPENAI_DEFAULT_MODEL,
        dimension: int = _OPENAI_DEFAULT_DIMENSION,
        base_url: str = _OPENAI_BASE_URL,
        timeout: float = 30.0,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._dimension = dimension
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers={"Authorization": f"Bearer {api_key}"},
        )

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def provider_name(self) -> str:
        return f"openai ({self._model})"

    async def embed(self, text: str) -> list[float]:
        """单条文本转向量。"""
        payload = {"model": self._model, "input": text}

        try:
            resp = await self._client.post(
                f"{self._base_url}/embeddings", json=payload
            )
            resp.raise_for_status()
            data = resp.json()
            embedding = data.get("data", [{}])[0].get("embedding")
            if not embedding:
                raise EmbeddingError(f"OpenAI returned empty embedding: {data}")
            return embedding
        except httpx.HTTPStatusError as e:
            raise EmbeddingError(
                f"OpenAI API error {e.response.status_code}: {e.response.text}"
            ) from e
        except httpx.RequestError as e:
            raise EmbeddingError(f"OpenAI request failed: {e}") from e

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """批量文本转向量。OpenAI API 原生支持 input 为数组。"""
        payload = {"model": self._model, "input": texts}

        try:
            resp = await self._client.post(
                f"{self._base_url}/embeddings", json=payload
            )
            resp.raise_for_status()
            data = resp.json()
            return [d.get("embedding", []) for d in data.get("data", [])]
        except httpx.HTTPStatusError as e:
            raise EmbeddingError(
                f"OpenAI batch API error {e.response.status_code}: {e.response.text}"
            ) from e
        except httpx.RequestError as e:
            raise EmbeddingError(f"OpenAI batch request failed: {e}") from e

    async def close(self) -> None:
        """关闭 HTTP 客户端。"""
        await self._client.aclose()
