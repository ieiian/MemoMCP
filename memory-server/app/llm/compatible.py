"""
OpenAI Compatible LLM Provider

支持任何兼容 OpenAI API 格式的 LLM 端点：
- OpenRouter
- DeepSeek
- Moonshot
- MiniMax
- Ollama (OpenAI Compatible)
- vLLM
- LocalAI

用法：设置 OPENAI_BASE_URL 指向兼容端点。
"""

from __future__ import annotations

import logging

from app.llm.openai import OpenAILLMProvider

logger = logging.getLogger(__name__)


class OpenAICompatibleLLMProvider(OpenAILLMProvider):
    """OpenAI 兼容 LLM 提供者。

    继承 OpenAILLMProvider，复用相同的 API 调用逻辑。
    如果端点不支持 response_format，chat_json 会在 prompt 中要求 JSON。
    """

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str = "gpt-4o-mini",
        timeout: float = 60.0,
    ) -> None:
        if not base_url:
            raise ValueError("base_url is required for compatible provider")

        super().__init__(
            api_key=api_key or "dummy",
            model=model,
            base_url=base_url,
            timeout=timeout,
        )

    @property
    def provider_name(self) -> str:
        return f"compatible ({self._model} @ {self._base_url})"

    async def chat_json(
        self,
        messages: list[dict],
        temperature: float = 0.3,
        max_tokens: int | None = None,
    ) -> dict:
        """结构化 JSON 输出。

        先尝试 response_format，如果端点不支持则回退到纯 prompt 方式。
        """
        import json

        payload: dict = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens

        # 尝试 response_format（部分兼容端点支持）
        try:
            payload["response_format"] = {"type": "json_object"}
            resp = await self._client.post(
                f"{self._base_url}/chat/completions", json=payload
            )
            if resp.status_code == 400:
                # 不支持 response_format，去掉重试
                payload.pop("response_format", None)
                resp = await self._client.post(
                    f"{self._base_url}/chat/completions", json=payload
                )
            resp.raise_for_status()
        except Exception:
            # 网络错误等，直接抛出
            raise

        from app.llm.base import LLMError

        data = resp.json()
        text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        if not text:
            raise LLMError(f"Compatible LLM returned empty response: {data}")

        # 尝试解析 JSON（兼容可能返回 markdown 代码块的情况）
        text = text.strip()
        if text.startswith("```"):
            # 去掉 markdown 代码块
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise LLMError(f"Failed to parse JSON: {e}\nText: {text}") from e
