"""
MemoMCP 配置模块

所有配置通过 .env 环境变量驱动，使用 Pydantic Settings 进行类型校验。
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置，从环境变量 / .env 文件加载。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ===== 运行模式 =====
    ai_memory_manager: bool = Field(
        default=False,
        description="true 启用 AI Memory Manager 模式",
    )

    # ===== LLM Provider =====
    llm_provider: Literal["gemini", "openai", "compatible"] = Field(
        default="gemini",
        description="LLM 提供者（仅 AI 模式需要）",
    )
    llm_model: str = Field(
        default="gemini-2.0-flash",
        description="LLM 模型名",
    )
    gemini_api_key: str = Field(default="", description="Google Gemini API Key")
    openai_api_key: str = Field(default="", description="OpenAI API Key")
    openai_base_url: str = Field(
        default="",
        description="OpenAI Compatible 端点 URL（compatible 模式必填）",
    )

    # ===== Embedding Provider =====
    embedding_provider: Literal["gemini", "openai", "compatible"] = Field(
        default="gemini",
        description="Embedding 提供者",
    )
    embedding_model: str = Field(
        default="text-embedding-3-small",
        description="Embedding 模型名",
    )
    embedding_dimension: int = Field(
        default=1536,
        description="向量维度（必须与数据库 init.sql 一致）",
    )

    # ===== 数据库 =====
    database_url: str = Field(
        default="postgresql+asyncpg://memomcp:memomcp@localhost:5432/memomcp",
        description="异步数据库连接字符串",
    )

    # ===== MCP 传输 =====
    mcp_transport: Literal["stdio", "sse"] = Field(
        default="stdio",
        description="MCP 传输协议",
    )

    # ===== REST API =====
    rest_host: str = Field(default="0.0.0.0", description="REST API 监听地址")
    rest_port: int = Field(default=8000, description="REST API 监听端口")

    # ===== 日志 =====
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO",
        description="日志级别",
    )


@lru_cache
def get_settings() -> Settings:
    """获取全局配置单例（缓存）。"""
    return Settings()
