"""
管理页与文档页 Web 路由

提供统一风格的 HTML 页面：首页、管理台、Swagger UI、ReDoc。
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, Query
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.activity import tracker
from app.config import get_settings
from app.database import get_db
from app.embedding import get_embedding_provider
from app.schemas import SystemStatus

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(tags=["web"])

_STATIC_DIR = Path(__file__).parent / "static"

_NAV_ITEMS = (
    ("home", "/", "首页"),
    ("admin", "/admin", "管理"),
    ("docs", "/docs", "API 文档"),
    ("redoc", "/redoc", "ReDoc"),
)

_SWAGGER_UI_PARAMS = {
    "docExpansion": "list",
    "filter": True,
    "tryItOutEnabled": True,
    "displayRequestDuration": True,
    "syntaxHighlight.theme": "monokai",
}

# ReDoc 2 暗色主题（通过 web component theme 属性注入）
_REDOC_DARK_THEME = {
    "colors": {
        "primary": {"main": "#5b8def"},
        "text": {"primary": "#e8eaef", "secondary": "#b4bac8"},
        "border": {"dark": "#2a3142", "light": "#353d52"},
        "http": {
            "get": "#38bdf8",
            "post": "#34d399",
            "put": "#fbbf24",
            "delete": "#f87171",
            "patch": "#a78bfa",
            "basic": "#7a8499",
            "link": "#5b8def",
        },
    },
    "sidebar": {
        "backgroundColor": "#161b26",
        "textColor": "#b4bac8",
        "activeTextColor": "#e8eaef",
        "groupItems": {
            "activeBackgroundColor": "rgba(91, 141, 239, 0.12)",
            "activeTextColor": "#5b8def",
            "textTransform": "uppercase",
        },
    },
    "rightPanel": {"backgroundColor": "#0b0d12"},
    "codeBlock": {"backgroundColor": "#10141c"},
    "schema": {
        "linesColor": "#2a3142",
        "typeNameColor": "#5b8def",
        "typeTitleColor": "#e8eaef",
    },
    "typography": {
        "fontSize": "14px",
        "fontFamily": "Inter, -apple-system, BlinkMacSystemFont, sans-serif",
        "headings": {
            "fontFamily": "Inter, -apple-system, sans-serif",
            "fontWeight": "600",
        },
        "code": {
            "fontFamily": "JetBrains Mono, SF Mono, Monaco, Consolas, monospace",
            "fontSize": "13px",
        },
    },
}


def _site_header(active: str, extra: str = "") -> str:
    """生成统一站点导航栏。"""
    nav = "".join(
        f'<a href="{href}" class="{"active" if key == active else ""}">{label}</a>'
        for key, href, label in _NAV_ITEMS
    )
    extra_html = f'<div class="header-extra">{extra}</div>' if extra else ""
    return f"""<header class="site-header">
  <div class="header-inner">
    <a href="/" class="brand">
      <span class="brand-icon">M</span>
      <span class="brand-text">MemoMCP</span>
    </a>
    <nav class="site-nav">{nav}</nav>
    {extra_html}
  </div>
</header>"""


def _docs_intro(title: str, desc: str) -> str:
    """文档页顶部说明。"""
    return f"""<div class="docs-wrap">
  <div class="docs-intro">
    <h1 class="page-title">{title}</h1>
    <p class="page-desc">{desc}</p>
  </div>"""


def _inject_page_chrome(
    html: str,
    *,
    active: str,
    extra_css: list[str],
    intro: str = "",
    header_extra: str = "",
) -> str:
    """向 Swagger / ReDoc HTML 注入统一导航与样式。"""
    links = (
        '<link rel="icon" href="/static/favicon.svg" type="image/svg+xml">\n'
        '<link rel="stylesheet" href="/static/theme.css">\n'
    )
    for css in extra_css:
        links += f'<link rel="stylesheet" href="/static/{css}">\n'

    html = html.replace("</head>", links + "</head>", 1)
    chrome = _site_header(active, header_extra) + intro
    html = html.replace("<body>", f"<body>{chrome}", 1)
    if intro:
        html = html.replace("</body>", "</div></body>", 1)
    return html


# ============================================================
# 页面路由
# ============================================================
@router.get("/", include_in_schema=False)
async def home_page() -> FileResponse:
    """服务首页。"""
    return FileResponse(_STATIC_DIR / "home.html")


@router.get("/admin", include_in_schema=False)
async def admin_page() -> FileResponse:
    """管理台入口。"""
    return FileResponse(_STATIC_DIR / "index.html")


@router.get("/docs", include_in_schema=False)
async def swagger_ui() -> HTMLResponse:
    """自定义 Swagger UI 文档页。"""
    html = get_swagger_ui_html(
        openapi_url="/openapi.json",
        title="MemoMCP API",
        swagger_ui_parameters=_SWAGGER_UI_PARAMS,
    )
    content = _inject_page_chrome(
        html.body.decode(),
        active="docs",
        extra_css=["swagger.css"],
        intro=_docs_intro(
            "API 文档",
            "MemoMCP REST API 交互式参考，支持在线调试所有端点。",
        ),
    )
    return HTMLResponse(content)


@router.get("/redoc", include_in_schema=False)
async def redoc_ui() -> HTMLResponse:
    """自定义 ReDoc 文档页（注入暗色 theme）。"""
    theme_json = json.dumps(_REDOC_DARK_THEME, separators=(",", ":"))
    intro = _docs_intro(
        "ReDoc 文档",
        "MemoMCP REST API 结构化参考文档，适合阅读与分享。",
    )
    header = _site_header("redoc")
    content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>MemoMCP API — ReDoc</title>
  <link rel="icon" href="/static/favicon.svg" type="image/svg+xml">
  <link rel="stylesheet" href="/static/theme.css">
  <link rel="stylesheet" href="/static/redoc.css">
</head>
<body>
{header}
{intro}
  <redoc spec-url="/openapi.json" theme='{theme_json}'></redoc>
  <script src="https://cdn.jsdelivr.net/npm/redoc@2/bundles/redoc.standalone.js"></script>
</div>
</body>
</html>"""
    return HTMLResponse(content)


# ============================================================
# 管理 API
# ============================================================
@router.get("/admin/system", response_model=SystemStatus)
async def system_status(
    db: AsyncSession = Depends(get_db),
) -> SystemStatus:
    """系统运行状态。"""
    try:
        await db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception as e:
        logger.error("DB check failed: %s", e)
        db_status = "error"

    embedding = get_embedding_provider()
    embedding_name = (
        f"{settings.embedding_provider}/{settings.embedding_model}"
        if embedding
        else None
    )

    return SystemStatus(
        version="0.1.0",
        rest_api="running",
        database=db_status,
        embedding_provider=embedding_name,
        ai_memory_manager=settings.ai_memory_manager,
        mcp_transport=settings.mcp_transport,
        activity=tracker.get_status(),
    )


@router.get("/admin/activity")
async def get_activity(
    limit: int = Query(50, ge=1, le=200),
) -> dict:
    """获取最近调用活动。"""
    return {"events": tracker.get_recent(limit)}


@router.get("/admin/activity/stream")
async def activity_stream() -> StreamingResponse:
    """SSE 实时活动流。"""

    async def generate():
        queue = await tracker.subscribe()
        try:
            for event in reversed(tracker.get_recent(10)):
                yield f"data: {json.dumps(event)}\n\n"
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield f"data: {json.dumps(event.to_dict())}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            tracker.unsubscribe(queue)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
