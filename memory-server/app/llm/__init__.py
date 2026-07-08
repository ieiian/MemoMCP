"""
LLM Provider 工厂

根据 .env 配置自动创建对应的 LLMProvider 实例。
仅在 AI_MEMORY_MANAGER=true 时需要。
如果 API Key 未配置，返回 None（Passive 模式）。
"""

from __future__ import annotations

import logging

from app.config import get_settings
from app.llm.base import LLMProvider

logger = logging.getLogger(__name__)

_provider_instance: LLMProvider | None = None
_provider_initialized: bool = False


def get_llm_provider() -> LLMProvider | None:
    """获取全局 LLM Provider 单例。

    Returns:
        LLMProvider 实例，或 None（未启用 AI Manager 或未配置 API Key）
    """
    global _provider_instance, _provider_initialized

    if not _provider_initialized:
        _provider_instance = _create_provider()
        _provider_initialized = True
        if _provider_instance is not None:
            logger.info(
                "LLM provider initialized: %s (model=%s)",
                _provider_instance.provider_name,
                _provider_instance.model,
            )
        else:
            logger.info("LLM provider not configured (AI Manager mode disabled)")

    return _provider_instance


def _create_provider() -> LLMProvider | None:
    """根据配置创建 LLM Provider。"""
    settings = get_settings()

    # AI Memory Manager 未启用
    if not settings.ai_memory_manager:
        return None

    provider_type = settings.llm_provider

    if provider_type == "gemini":
        if not settings.gemini_api_key:
            logger.warning("LLM_PROVIDER=gemini but GEMINI_API_KEY is not set")
            return None
        from app.llm.gemini import GeminiLLMProvider

        return GeminiLLMProvider(
            api_key=settings.gemini_api_key,
            model=settings.llm_model,
        )

    elif provider_type == "openai":
        if not settings.openai_api_key:
            logger.warning("LLM_PROVIDER=openai but OPENAI_API_KEY is not set")
            return None
        from app.llm.openai import OpenAILLMProvider

        return OpenAILLMProvider(
            api_key=settings.openai_api_key,
            model=settings.llm_model,
        )

    elif provider_type == "compatible":
        if not settings.openai_base_url:
            logger.warning(
                "LLM_PROVIDER=compatible but OPENAI_BASE_URL is not set"
            )
            return None
        from app.llm.compatible import OpenAICompatibleLLMProvider

        return OpenAICompatibleLLMProvider(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            model=settings.llm_model,
        )

    else:
        logger.error("Unknown LLM provider: %s", provider_type)
        return None


def reset_llm_provider() -> None:
    """重置 Provider 单例（测试用）。"""
    global _provider_instance, _provider_initialized
    _provider_instance = None
    _provider_initialized = False
