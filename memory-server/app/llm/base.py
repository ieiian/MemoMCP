"""
LLM Provider 抽象基类

所有 LLM 提供者必须实现此接口。
支持 gemini / openai / compatible 三种实现。
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class LLMProvider(ABC):
    """LLM 提供者抽象基类。

    实现者需提供:
    - model: 当前模型名
    - chat(): 普通对话，返回文本
    - chat_json(): 结构化输出，返回 JSON dict
    """

    @property
    @abstractmethod
    def model(self) -> str:
        """当前模型名。"""
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """提供者名称。"""
        ...

    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        temperature: float = 0.3,
        max_tokens: int | None = None,
    ) -> str:
        """普通对话，返回文本。

        Args:
            messages: 消息列表 [{"role": "system/user/assistant", "content": "..."}]
            temperature: 生成温度
            max_tokens: 最大输出 token 数

        Returns:
            LLM 生成的文本

        Raises:
            LLMError: 调用失败
        """
        ...

    @abstractmethod
    async def chat_json(
        self,
        messages: list[dict],
        temperature: float = 0.3,
        max_tokens: int | None = None,
    ) -> dict:
        """结构化输出，返回 JSON dict。

        在 prompt 中要求返回 JSON，provider 会配置相应的 JSON 输出模式。

        Args:
            messages: 消息列表
            temperature: 生成温度
            max_tokens: 最大输出 token 数

        Returns:
            解析后的 JSON dict

        Raises:
            LLMError: 调用失败或 JSON 解析失败
        """
        ...

    async def health_check(self) -> bool:
        """健康检查。"""
        try:
            result = await self.chat(
                [{"role": "user", "content": "Reply with: OK"}],
                temperature=0.0,
                max_tokens=10,
            )
            return bool(result)
        except Exception as e:
            logger.warning("LLM health check failed: %s", e)
            return False


class LLMError(Exception):
    """LLM 调用异常。"""

    pass
