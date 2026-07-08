"""
Google Gemini LLM Provider

使用 Gemini 2.x 系列模型。
API: https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent
"""

from __future__ import annotations

import json
import logging

import httpx

from app.llm.base import LLMError, LLMProvider

logger = logging.getLogger(__name__)

_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


class GeminiLLMProvider(LLMProvider):
    """Google Gemini LLM 提供者。"""

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.0-flash",
        timeout: float = 60.0,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._timeout = timeout
        self._client = httpx.AsyncClient(timeout=timeout)

    @property
    def model(self) -> str:
        return self._model

    @property
    def provider_name(self) -> str:
        return f"gemini ({self._model})"

    def _to_gemini_messages(self, messages: list[dict]) -> list[dict]:
        """将 OpenAI 格式消息转为 Gemini 格式。"""
        contents = []
        system_text = ""
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                system_text += content + "\n"
            elif role == "assistant":
                contents.append({"role": "model", "parts": [{"text": content}]})
            else:
                contents.append({"role": "user", "parts": [{"text": content}]})
        # Gemini 用 systemInstruction 字段处理 system 消息
        return contents, system_text.strip()

    async def chat(
        self,
        messages: list[dict],
        temperature: float = 0.3,
        max_tokens: int | None = None,
    ) -> str:
        """普通对话。"""
        contents, system_text = self._to_gemini_messages(messages)
        payload: dict = {
            "contents": contents,
            "generationConfig": {"temperature": temperature},
        }
        if system_text:
            payload["systemInstruction"] = {"parts": [{"text": system_text}]}
        if max_tokens:
            payload["generationConfig"]["maxOutputTokens"] = max_tokens

        url = f"{_GEMINI_BASE_URL}/models/{self._model}:generateContent"
        try:
            resp = await self._client.post(
                url, json=payload, params={"key": self._api_key}
            )
            resp.raise_for_status()
            data = resp.json()
            text = (
                data.get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [{}])[0]
                .get("text", "")
            )
            if not text:
                raise LLMError(f"Gemini returned empty response: {data}")
            return text.strip()
        except httpx.HTTPStatusError as e:
            raise LLMError(
                f"Gemini API error {e.response.status_code}: {e.response.text}"
            ) from e
        except httpx.RequestError as e:
            raise LLMError(f"Gemini request failed: {e}") from e

    async def chat_json(
        self,
        messages: list[dict],
        temperature: float = 0.3,
        max_tokens: int | None = None,
    ) -> dict:
        """结构化 JSON 输出。"""
        contents, system_text = self._to_gemini_messages(messages)
        payload: dict = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "responseMimeType": "application/json",
            },
        }
        if system_text:
            payload["systemInstruction"] = {"parts": [{"text": system_text}]}
        if max_tokens:
            payload["generationConfig"]["maxOutputTokens"] = max_tokens

        url = f"{_GEMINI_BASE_URL}/models/{self._model}:generateContent"
        try:
            resp = await self._client.post(
                url, json=payload, params={"key": self._api_key}
            )
            resp.raise_for_status()
            data = resp.json()
            text = (
                data.get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [{}])[0]
                .get("text", "")
            )
            if not text:
                raise LLMError(f"Gemini returned empty JSON response: {data}")
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise LLMError(f"Failed to parse Gemini JSON: {e}\nText: {text}") from e
        except httpx.HTTPStatusError as e:
            raise LLMError(
                f"Gemini API error {e.response.status_code}: {e.response.text}"
            ) from e
        except httpx.RequestError as e:
            raise LLMError(f"Gemini request failed: {e}") from e

    async def close(self) -> None:
        await self._client.aclose()
