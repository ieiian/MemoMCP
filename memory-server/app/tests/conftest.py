"""
pytest 共享 fixture
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_factory, init_db
from app.models import Memory


@pytest.fixture(scope="session")
def event_loop():
    """session 级事件循环。"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_database():
    """session 开始时初始化数据库。"""
    await init_db()
    yield


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """每个测试一个独立 Session。"""
    async with async_session_factory() as session:
        # 测试前清理所有测试工作区数据
        await session.execute(
            text(
                "DELETE FROM memories WHERE workspace_id LIKE 'test-%' "
                "OR workspace_id LIKE 'svc-%' "
                "OR workspace_id LIKE 'tools-%' "
                "OR workspace_id LIKE 'stats-%' "
                "OR workspace_id LIKE 'ws-%' "
                "OR workspace_id LIKE 'error-%'"
            )
        )
        await session.commit()

        yield session

        # 测试后清理
        await session.execute(
            text(
                "DELETE FROM memories WHERE workspace_id LIKE 'test-%' "
                "OR workspace_id LIKE 'svc-%' "
                "OR workspace_id LIKE 'tools-%' "
                "OR workspace_id LIKE 'stats-%' "
                "OR workspace_id LIKE 'ws-%' "
                "OR workspace_id LIKE 'error-%'"
            )
        )
        await session.commit()
