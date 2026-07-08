"""
Embedding Provider 抽象基类

所有 Embedding 提供者必须实现此接口。
支持 gemini / openai / compatible 三种实现。
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class EmbeddingProvider(ABC):
    """Embedding 提供者抽象基类。

    实现者需提供:
    - dimension: 向量维度
    - embed(): 单条文本转向量
    - embed_batch(): 批量转向量
    """

    @property
    @abstractmethod
    def dimension(self) -> int:
        """向量维度。必须与数据库 vector 列维度一致。"""
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """提供者名称（用于日志和调试）。"""
        ...

    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        """将单条文本转为向量。

        Args:
            text: 输入文本

        Returns:
            浮点数列表，长度等于 dimension

        Raises:
            EmbeddingError: 向量生成失败
        """
        ...

    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """批量将文本转为向量。

        Args:
            texts: 输入文本列表

        Returns:
            向量列表，长度等于 len(texts)

        Raises:
            EmbeddingError: 向量生成失败
        """
        ...

    async def health_check(self) -> bool:
        """健康检查：尝试生成一条测试向量。

        Returns:
            True 如果服务可用
        """
        try:
            vec = await self.embed("health check")
            return len(vec) == self.dimension
        except Exception as e:
            logger.warning("Embedding health check failed: %s", e)
            return False


class EmbeddingError(Exception):
    """Embedding 生成异常。"""

    pass
