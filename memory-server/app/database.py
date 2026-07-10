"""
MemoMCP 数据库模块

提供异步引擎、Session 工厂、建表初始化。
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class Base(DeclarativeBase):
    """SQLAlchemy 声明式基类。所有模型继承此类。"""

    pass


# 诊断日志：输出 DATABASE_URL 的主机和端口（不输出密码）
from urllib.parse import urlparse as _urlparse

_parsed = _urlparse(settings.database_url.replace("+asyncpg", ""))
_db_host = _parsed.hostname or "unknown"
_db_port = _parsed.port or 5432
logger.info("Database target: %s:%s", _db_host, _db_port)
if _db_host in ("localhost", "127.0.0.1"):
    logger.warning(
        "DATABASE_URL points to %s — in Docker Compose, use 'postgres' as host, "
        "not 'localhost'. Check your .env file.",
        _db_host,
    )


# 异步引擎：NullPool 避免连接绑定到特定事件循环（MCP stdio/http 模式兼容）
# connect_args ssl=False：Docker 内部网络通信不需要 SSL，避免 asyncpg 默认尝试 SSL 导致连接失败
engine = create_async_engine(
    settings.database_url,
    echo=(settings.log_level == "DEBUG"),
    pool_pre_ping=True,
    poolclass=NullPool,
    connect_args={"ssl": False},
)

# 异步 Session 工厂
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI / FastMCP 依赖注入：获取数据库 Session。

    用法::

        @app.get("/items")
        async def list_items(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """初始化数据库：创建表 + 特殊索引。带重试应对网络延迟。

    - 调用 Base.metadata.create_all 创建表（IF NOT EXISTS 语义）
    - 创建 HNSW 向量索引、GIN 全文检索索引等 init.sql 中的索引
    - 幂等：可安全重复调用
    """
    from app.models import Memory  # noqa: F401
    import asyncio as _asyncio

    max_retries = 5
    retry_delay = 3

    for attempt in range(max_retries):
        try:
            async with engine.begin() as conn:
                # 1. 确保扩展存在
                await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

                # 2. 创建所有表
                await conn.run_sync(Base.metadata.create_all)

                # 3. 创建 HNSW 向量索引（核心：近似最近邻）
                await conn.execute(
                    text(
                        """
                        CREATE INDEX IF NOT EXISTS idx_memories_embedding
                        ON memories USING hnsw (embedding vector_cosine_ops)
                        WITH (m = 16, ef_construction = 64)
                        """
                    )
                )

                # 4. 创建全文检索索引（Hybrid Search 用）
                await conn.execute(
                    text(
                        """
                        CREATE INDEX IF NOT EXISTS idx_memories_content_fts
                        ON memories USING gin (to_tsvector('english', content))
                        """
                    )
                )

                # 5. 标签 GIN 索引
                await conn.execute(
                    text(
                        """
                        CREATE INDEX IF NOT EXISTS idx_memories_tags
                        ON memories USING gin (tags)
                        """
                    )
                )

                # 6. metadata JSONB GIN 索引
                await conn.execute(
                    text(
                        """
                        CREATE INDEX IF NOT EXISTS idx_memories_metadata
                        ON memories USING gin (metadata)
                        """
                    )
                )

                # 7. updated_at 触发器
                await conn.execute(
                    text(
                        """
                        CREATE OR REPLACE FUNCTION update_updated_at_column()
                        RETURNS TRIGGER AS $$
                        BEGIN
                            NEW.updated_at = NOW();
                            RETURN NEW;
                        END;
                        $$ LANGUAGE plpgsql
                        """
                    )
                )
                await conn.execute(
                    text(
                        "DROP TRIGGER IF EXISTS trg_memories_updated_at ON memories"
                    )
                )
                await conn.execute(
                    text(
                        """
                        CREATE TRIGGER trg_memories_updated_at
                        BEFORE UPDATE ON memories
                        FOR EACH ROW
                        EXECUTE FUNCTION update_updated_at_column()
                        """
                    )
                )

            logger.info("Database initialized successfully")
            return

        except Exception as e:
            if attempt < max_retries - 1:
                # 诊断：尝试解析主机名
                import socket as _socket
                try:
                    addrs = _socket.getaddrinfo(_db_host, _db_port)
                    addr_str = ", ".join(f"{a[4][0]}:{a[4][1]}" for a in addrs)
                except Exception as dns_err:
                    addr_str = f"DNS FAILED: {dns_err}"
                logger.warning(
                    "Database init attempt %d/%d failed: %s — retrying in %ds... "
                    "(target=%s:%s, resolved=[%s])",
                    attempt + 1,
                    max_retries,
                    e,
                    retry_delay,
                    _db_host,
                    _db_port,
                    addr_str,
                )
                await _asyncio.sleep(retry_delay)
            else:
                logger.error("Database init failed after %d attempts: %s", max_retries, e)
                raise


async def close_db() -> None:
    """关闭数据库引擎，释放连接池。应用退出时调用。"""
    await engine.dispose()
    logger.info("Database engine disposed")
