"""
MemoMCP 配置模块

所有配置通过 .env 环境变量驱动，使用 Pydantic Settings 进行类型校验。
"""

from __future__ import annotations

import ipaddress
from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# RFC1918 私网段，"lan" 关键字展开为这三段
_LAN_CIDRS = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")


def _cidr_to_patterns(cidr: str) -> list[str]:
    """把 IPv4 CIDR 转成 FastMCP Host 守卫支持的 fnmatch 通配模式。

    整 octet 前缀直接转通配符（10.0.0.0/24 -> 10.0.0.*）；
    非整 octet 前缀枚举部分 octet 的取值（172.16.0.0/12 -> 172.16.* … 172.31.*）。
    """
    network = ipaddress.ip_network(cidr, strict=False)
    if network.version != 4:
        raise ValueError(
            f"不支持 IPv6 CIDR: '{cidr}'，请使用单个 IPv6 地址或通配符"
        )
    octets = [str(b) for b in network.network_address.packed]
    full, rem = divmod(network.prefixlen, 8)
    if rem == 0:
        if full == 0:
            return ["*"]
        if full == 4:
            return [".".join(octets)]
        return [".".join(octets[:full]) + ".*"]
    block = 1 << (8 - rem)
    start = int(octets[full])
    suffix = ".*" if full < 3 else ""
    return [
        ".".join(octets[:full] + [str(v)]) + suffix
        for v in range(start, start + block)
    ]


def resolve_mcp_allowed_hosts(value: str) -> list[str]:
    """解析 MCP_ALLOWED_HOSTS 为 Host 白名单（fnmatch 模式列表）。

    逗号分隔，每项可以是：
    - lan / private / rfc1918：全部 RFC1918 私网（默认）
    - 单个 IP 或域名：10.0.0.4、mcp.example.com
    - IPv4 CIDR：10.0.0.0/24
    - 通配符：10.0.0.*、*.example.com
    - *：放行任意 Host（仅限可信反向代理场景）

    localhost / 127.0.0.1 / ::1 由 FastMCP 恒放行，无需配置。
    """
    patterns: list[str] = []
    for item in value.split(","):
        entry = item.strip()
        if not entry:
            continue
        if entry.lower() in ("lan", "private", "rfc1918"):
            for cidr in _LAN_CIDRS:
                patterns.extend(_cidr_to_patterns(cidr))
        elif "/" in entry:
            patterns.extend(_cidr_to_patterns(entry))
        else:
            patterns.append(entry)
    if not patterns:
        raise ValueError("MCP_ALLOWED_HOSTS 不能为空，例如 lan 或 10.0.0.4")
    return patterns


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
    mcp_transport: Literal["stdio", "http"] = Field(
        default="stdio",
        description="MCP 传输协议（实际启动方式由 --transport 参数决定）",
    )
    mcp_allowed_hosts: str = Field(
        default="lan",
        description=(
            "MCP HTTP 的 Host 白名单，逗号分隔：lan（默认，全部 RFC1918 私网）、"
            "单个 IP/域名、IPv4 CIDR（10.0.0.0/24）、通配符（10.0.0.*）、* 放行任意 Host"
        ),
    )

    # ===== REST API =====
    rest_host: str = Field(default="0.0.0.0", description="REST API 监听地址")
    rest_port: int = Field(default=8000, description="REST API 监听端口")

    # ===== 日志 =====
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO",
        description="日志级别",
    )

    # ===== 管理台 =====
    admin_password: str = Field(
        default="2026",
        description="管理台访问密码",
    )


@lru_cache
def get_settings() -> Settings:
    """获取全局配置单例（缓存）。"""
    return Settings()
