"""
OpenAI LLM Provider

使用 OpenAI GPT 系列模型。
API: https://api.openai.com/v1/chat/completions
"""

from __future__ import annotations

import json
import logging

import httpx

from app.llm.base import LLMError, LLMProvider

logger = logging.getLogger(__name__)

_OPENAI_BASE_URL = "https://api.openai.com/v1"


class OpenAILLMProvider(LLMProvider):
    """OpenAI 官方 LLM 提供者。"""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        base_url: str = _OPENAI_BASE_URL,
        timeout: float = 60.0,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers={"Authorization": f"Bearer {api_key}"},
        )

    @property
    def model(self) -> str:
        return self._model

    @property
    def provider_name(self) -> str:
        return f"openai ({self._model})"

    async def chat(
        self,
        messages: list[dict],
        temperature: float = 0.3,
        max_tokens: int | None = None,
    ) -> str:
        """普通对话。"""
        payload: dict = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens

        try:
            resp = await self._client.post(
                f"{self._base_url}/chat/completions", json=payload
            )
            resp.raise_for_status()
            data = resp.json()
            text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            if not text:
                raise LLMError(f"OpenAI returned empty response: {data}")
            return text.strip()
        except httpx.HTTPStatusError as e:
            raise LLMError(
                f"OpenAI API error {e.response.status_code}: {e.response.text}"
            ) from e
        except httpx.RequestError as e:
            raise LLMError(f"OpenAI request failed: {e}") from e

    async def chat_json(
        self,
        messages: list[dict],
        temperature: float = 0.3,
        max_tokens: int | None = None,
    ) -> dict:
        """结构化 JSON 输出。"""
        payload: dict = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens

        try:
            resp = await self._client.post(
                f"{self._base_url}/chat/completions", json=payload
            )
            resp.raise_for_status()
            data = resp.json()
            text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            if not text:
                raise LLMError(f"OpenAI returned empty JSON response: {data}")
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise LLMError(f"Failed to parse OpenAI JSON: {e}\nText: {text}") from e
        except httpx.HTTPStatusError as e:
            raise LLMError(
                f"OpenAI API error {e.response.status_code}: {e.response.text}"
            ) from e
        except httpx.RequestError as e:
            raise LLMError(f"OpenAI request failed: {e}") from e

    async def close(self) -> None:
        await self._client.aclose()
