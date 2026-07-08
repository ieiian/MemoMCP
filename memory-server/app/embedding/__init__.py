"""
Embedding Provider 工厂

根据 .env 配置自动创建对应的 EmbeddingProvider 实例。
如果 API Key 未配置，返回 None（回退到关键词搜索）。
"""

from __future__ import annotations

import logging

from app.config import get_settings
from app.embedding.base import EmbeddingProvider

logger = logging.getLogger(__name__)

_provider_instance: EmbeddingProvider | None = None
_provider_initialized: bool = False


def get_embedding_provider() -> EmbeddingProvider | None:
    """获取全局 Embedding Provider 单例。

    Returns:
        EmbeddingProvider 实例，或 None（未配置 API Key 时）
    """
    global _provider_instance, _provider_initialized

    if not _provider_initialized:
        _provider_instance = _create_provider()
        _provider_initialized = True
        if _provider_instance is not None:
            logger.info(
                "Embedding provider initialized: %s (dim=%d)",
                _provider_instance.provider_name,
                _provider_instance.dimension,
            )
        else:
            logger.info(
                "Embedding provider not configured, "
                "falling back to keyword search only"
            )

    return _provider_instance


def _create_provider() -> EmbeddingProvider | None:
    """根据配置创建 Embedding Provider。"""
    settings = get_settings()
    provider_type = settings.embedding_provider

    if provider_type == "gemini":
        if not settings.gemini_api_key:
            logger.warning(
                "EMBEDDING_PROVIDER=gemini but GEMINI_API_KEY is not set"
            )
            return None
        from app.embedding.gemini import GeminiEmbeddingProvider

        return GeminiEmbeddingProvider(
            api_key=settings.gemini_api_key,
            model=settings.embedding_model
            if settings.embedding_model != "text-embedding-3-small"
            else "text-embedding-004",
            dimension=settings.embedding_dimension,
        )

    elif provider_type == "openai":
        if not settings.openai_api_key:
            logger.warning(
                "EMBEDDING_PROVIDER=openai but OPENAI_API_KEY is not set"
            )
            return None
        from app.embedding.openai import OpenAIEmbeddingProvider

        return OpenAIEmbeddingProvider(
            api_key=settings.openai_api_key,
            model=settings.embedding_model,
            dimension=settings.embedding_dimension,
        )

    elif provider_type == "compatible":
        if not settings.openai_base_url:
            logger.warning(
                "EMBEDDING_PROVIDER=compatible but OPENAI_BASE_URL is not set"
            )
            return None
        from app.embedding.compatible import OpenAICompatibleEmbeddingProvider

        return OpenAICompatibleEmbeddingProvider(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            model=settings.embedding_model,
            dimension=settings.embedding_dimension,
        )

    else:
        logger.error("Unknown embedding provider: %s", provider_type)
        return None


def reset_embedding_provider() -> None:
    """重置 Provider 单例（测试用）。"""
    global _provider_instance, _provider_initialized
    _provider_instance = None
    _provider_initialized = False
