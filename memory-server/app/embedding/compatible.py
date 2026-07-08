"""
OpenAI Compatible Embedding Provider

支持任何兼容 OpenAI API 格式的 Embedding 端点：
- OpenRouter
- DeepSeek
- Moonshot
- MiniMax
- Ollama (OpenAI Compatible)
- vLLM
- LocalAI

用法：设置 OPENAI_BASE_URL 指向兼容端点，例如:
  OPENAI_BASE_URL=http://localhost:11434/v1  (Ollama)
  OPENAI_BASE_URL=https://openrouter.ai/api/v1
"""

from __future__ import annotations

import logging

from app.embedding.openai import OpenAIEmbeddingProvider

logger = logging.getLogger(__name__)


class OpenAICompatibleEmbeddingProvider(OpenAIEmbeddingProvider):
    """OpenAI 兼容 Embedding 提供者。

    继承 OpenAIEmbeddingProvider，复用相同的 API 调用逻辑，
    仅 base_url 指向第三方端点。
    """

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str = "text-embedding-3-small",
        dimension: int = 1536,
        timeout: float = 30.0,
    ) -> None:
        if not base_url:
            raise ValueError("base_url is required for compatible provider")

        super().__init__(
            api_key=api_key or "dummy",  # 某些本地服务不需要 key
            model=model,
            dimension=dimension,
            base_url=base_url,
            timeout=timeout,
        )

    @property
    def provider_name(self) -> str:
        return f"compatible ({self._model} @ {self._base_url})"
