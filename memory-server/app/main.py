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
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.activity import tracker
from app.api import router
from app.config import get_settings
from app.database import close_db, init_db
from app.web import router as admin_router

settings = get_settings()

# 日志配置（输出到 stderr，MCP stdio 模式下不污染 stdout）
_log_level_num = getattr(logging, settings.log_level.upper(), logging.INFO)
_log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
logging.basicConfig(
    level=_log_level_num,
    format=_log_format,
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

# uvicorn 日志配置（让 access log 也带日期时间）
UVICORN_LOG_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": _log_format,
        },
    },
    "handlers": {
        "default": {
            "formatter": "default",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stderr",
        },
    },
    "loggers": {
        "": {"handlers": ["default"], "level": settings.log_level.upper()},
        "uvicorn": {"handlers": ["default"], "level": "INFO", "propagate": False},
        "uvicorn.access": {"handlers": ["default"], "level": "INFO", "propagate": False},
        "uvicorn.error": {"handlers": ["default"], "level": "INFO", "propagate": False},
    },
}


# ============================================================
# 活动追踪中间件
# ============================================================
class ActivityMiddleware(BaseHTTPMiddleware):
    """记录 REST API 调用活动。"""

    @staticmethod
    def _get_client_ip(request: Request) -> str:
        """从请求中提取客户端 IP 地址。

        优先级：X-Forwarded-For > X-Real-IP > request.client.host
        """
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip.strip()
        if request.client:
            return request.client.host
        return "unknown"

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        skip = (
            path.startswith("/admin/activity/stream")
            or path in ("/admin", "/", "/redoc", "/deploy")
            or path.startswith("/static")
            or path.startswith("/docs")
            or path.startswith("/openapi")
        )
        if not path.startswith("/api/v1") or skip:
            return await call_next(request)

        action = f"{request.method} {path}"
        client_ip = self._get_client_ip(request)
        tracker.begin("rest")
        start = time.perf_counter()
        status = "ok"
        detail = ""
        try:
            response = await call_next(request)
            if response.status_code >= 400:
                status = "error"
                detail = f"HTTP {response.status_code}"
            return response
        except Exception as e:
            status = "error"
            detail = str(e)
            raise
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            tracker.record(
                "rest", action, status, duration_ms, detail, client_ip
            )
            tracker.end("rest")


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
    docs_url=None,
    redoc_url=None,
)

_STATIC_DIR = Path(__file__).parent / "static"

app.add_middleware(ActivityMiddleware)
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")
app.include_router(router, prefix="/api/v1")
app.include_router(admin_router)


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
            log_config=UVICORN_LOG_CONFIG,
        )


if __name__ == "__main__":
    main()
