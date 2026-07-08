"""
MemoMCP 应用入口

支持两种启动模式：
1. REST API 模式（默认）：运行 FastAPI HTTP 服务，用于调试和管理
2. MCP 模式：运行 FastMCP 服务，供 Cursor / Claude Code 等 MCP Client 调用

用法：
  # REST API 模式（默认）
  python -m app.main

  # MCP stdio 模式（Cursor / Claude Code 调用）
  python -m app.main --mcp

  # MCP HTTP 模式（远程连接）
  python -m app.main --mcp --transport http --port 9000
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import router
from app.config import get_settings
from app.database import close_db, init_db

settings = get_settings()

# 日志配置（输出到 stderr，MCP stdio 模式下不污染 stdout）
_log_level_num = getattr(logging, settings.log_level.upper(), logging.INFO)
logging.basicConfig(
    level=_log_level_num,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)


# ============================================================
# FastAPI 应用（REST API 模式）
# ============================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时初始化数据库，关闭时释放连接。"""
    logger.info("Starting MemoMCP REST API server...")
    await init_db()
    logger.info("Database initialized")
    yield
    logger.info("Shutting down...")
    await close_db()


app = FastAPI(
    title="MemoMCP",
    description="Universal long-term memory service for AI coding tools",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(router, prefix="/api/v1")


@app.get("/", tags=["root"])
async def root() -> dict:
    return {
        "name": "MemoMCP",
        "version": "0.1.0",
        "docs": "/docs",
        "api": "/api/v1",
    }


# ============================================================
# MCP 模式启动
# ============================================================
def run_mcp(transport: str = "stdio", port: int = 8000) -> None:
    """启动 MCP 服务（FastMCP）。

    Args:
        transport: 传输方式 "stdio" 或 "http"
        port: HTTP 模式的监听端口
    """
    from app.tools import mcp

    # 先初始化数据库（async 操作）
    asyncio.run(init_db())
    logger.info("Starting MemoMCP MCP server (%s)...", transport)
    try:
        if transport == "http":
            mcp.run(transport="http", host="0.0.0.0", port=port)
        else:
            mcp.run(transport="stdio")
    finally:
        asyncio.run(close_db())


# ============================================================
# 主入口
# ============================================================
def main() -> None:
    """主入口：解析命令行参数，选择启动模式。"""
    parser = argparse.ArgumentParser(
        description="MemoMCP — Universal long-term memory service"
    )
    parser.add_argument(
        "--mcp",
        action="store_true",
        help="Run as MCP server (for Cursor / Claude Code integration)",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="stdio",
        help="MCP transport mode (default: stdio)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for HTTP transport or REST API (default: 8000)",
    )
    args = parser.parse_args()

    if args.mcp:
        run_mcp(transport=args.transport, port=args.port)
    else:
        # REST API 模式：用 uvicorn 启动
        import uvicorn

        uvicorn.run(
            app,
            host=settings.rest_host,
            port=args.port,
            log_level=settings.log_level.lower(),
        )


if __name__ == "__main__":
    main()
