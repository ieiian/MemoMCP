"""
Repository 层测试

测试 MemoryRepository 的 CRUD、搜索、统计功能。
"""

from __future__ import annotations

import pytest
from uuid import uuid4

from app.models import Memory
from app.repository import MemoryRepository


@pytest.mark.asyncio
async def test_create_and_get(db_session):
    """创建并获取 Memory。"""
    repo = MemoryRepository(db_session)
    memory = Memory(
        workspace_id="test-repo",
        memory_type="rule",
        title="Test Rule",
        content="Always use type hints",
        tags=["python"],
        importance=0.8,
    )
    created = await repo.create(memory)
    await db_session.commit()

    assert created.id is not None
    assert created.title == "Test Rule"

    fetched = await repo.get_by_id_no_touch(created.id)
    assert fetched is not None
    assert fetched.content == "Always use type hints"


@pytest.mark.asyncio
async def test_update(db_session):
    """更新 Memory。"""
    repo = MemoryRepository(db_session)
    memory = Memory(
        workspace_id="test-repo",
        memory_type="rule",
        content="Original",
        importance=0.5,
    )
    created = await repo.create(memory)
    await db_session.commit()

    updated = await repo.update(created.id, content="Updated", importance=0.9)
    await db_session.commit()

    assert updated.content == "Updated"
    assert updated.importance == 0.9


@pytest.mark.asyncio
async def test_delete(db_session):
    """删除 Memory。"""
    repo = MemoryRepository(db_session)
    memory = Memory(
        workspace_id="test-repo",
        memory_type="rule",
        content="To be deleted",
    )
    created = await repo.create(memory)
    await db_session.commit()

    deleted = await repo.delete(created.id)
    await db_session.commit()
    assert deleted is True

    fetched = await repo.get_by_id_no_touch(created.id)
    assert fetched is None


@pytest.mark.asyncio
async def test_list_by_workspace(db_session):
    """按工作区列表查询。"""
    repo = MemoryRepository(db_session)
    for i in range(3):
        await repo.create(
            Memory(
                workspace_id="test-list",
                memory_type="rule" if i < 2 else "preference",
                content=f"Content {i}",
            )
        )
    await db_session.commit()

    all_items = await repo.list_by_workspace("test-list")
    assert len(all_items) == 3

    rules = await repo.list_by_workspace("test-list", memory_type="rule")
    assert len(rules) == 2


@pytest.mark.asyncio
async def test_search_keyword(db_session):
    """关键词搜索。"""
    repo = MemoryRepository(db_session)
    await repo.create(
        Memory(
            workspace_id="test-search",
            memory_type="knowledge",
            title="FastMCP Guide",
            content="FastMCP is a framework for MCP servers",
        )
    )
    await repo.create(
        Memory(
            workspace_id="test-search",
            memory_type="knowledge",
            title="pgvector",
            content="Vector search for PostgreSQL",
        )
    )
    await db_session.commit()

    results = await repo.search_keyword("test-search", "FastMCP")
    assert len(results) == 1
    assert results[0][0].title == "FastMCP Guide"


@pytest.mark.asyncio
async def test_workspace_isolation(db_session):
    """工作区隔离。"""
    repo = MemoryRepository(db_session)
    await repo.create(
        Memory(
            workspace_id="ws-a",
            memory_type="rule",
            content="Rule in workspace A",
        )
    )
    await repo.create(
        Memory(
            workspace_id="ws-b",
            memory_type="rule",
            content="Rule in workspace B",
        )
    )
    await db_session.commit()

    results_a = await repo.search_keyword("ws-a", "Rule")
    results_b = await repo.search_keyword("ws-b", "Rule")

    assert len(results_a) == 1
    assert len(results_b) == 1
    assert results_a[0][0].workspace_id == "ws-a"
    assert results_b[0][0].workspace_id == "ws-b"


@pytest.mark.asyncio
async def test_stats(db_session):
    """统计功能。"""
    repo = MemoryRepository(db_session)
    for t in ["rule", "rule", "preference"]:
        await repo.create(
            Memory(
                workspace_id="test-stats",
                memory_type=t,
                content=f"Content for {t}",
            )
        )
    await db_session.commit()

    count = await repo.count_by_workspace("test-stats")
    assert count == 3

    by_type = await repo.stats_by_type("test-stats")
    assert by_type["rule"] == 2
    assert by_type["preference"] == 1


@pytest.mark.asyncio
async def test_clear_workspace(db_session):
    """清空工作区。"""
    repo = MemoryRepository(db_session)
    for i in range(5):
        await repo.create(
            Memory(
                workspace_id="test-clear",
                memory_type="rule",
                content=f"Item {i}",
            )
        )
    await db_session.commit()

    count = await repo.clear_workspace("test-clear")
    await db_session.commit()
    assert count == 5

    remaining = await repo.count_by_workspace("test-clear")
    assert remaining == 0
