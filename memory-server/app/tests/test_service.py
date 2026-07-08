"""
Service 层测试

测试 MemoryService 的业务逻辑，包括 RRF 融合。
"""

from __future__ import annotations

import pytest
from uuid import uuid4

from app.models import Memory, MemoryType
from app.schemas import MemoryCreate, SearchRequest
from app.service import MemoryService


@pytest.mark.asyncio
async def test_create_memory(db_session):
    """创建 Memory（Passive 模式，无 embedding）。"""
    service = MemoryService(db_session)
    result = await service.create_memory(
        MemoryCreate(
            workspace_id="svc-test",
            memory_type=MemoryType.RULE,
            content="Use pnpm for package management",
            title="Package Manager",
            tags=["tooling"],
            importance=0.8,
        )
    )
    assert result.id is not None
    assert result.title == "Package Manager"
    assert result.workspace_id == "svc-test"


@pytest.mark.asyncio
async def test_search_memories_keyword(db_session):
    """关键词搜索（无 embedding provider 回退）。"""
    service = MemoryService(db_session)
    await service.create_memory(
        MemoryCreate(
            workspace_id="svc-search",
            memory_type=MemoryType.KNOWLEDGE,
            content="Docker Compose is a tool for defining multi-container applications",
            title="Docker Compose",
        )
    )
    await service.create_memory(
        MemoryCreate(
            workspace_id="svc-search",
            memory_type=MemoryType.KNOWLEDGE,
            content="Kubernetes orchestrates containerized applications",
            title="Kubernetes",
        )
    )

    results = await service.search_memories(
        SearchRequest(workspace_id="svc-search", query="Docker container")
    )
    assert results.total >= 1
    assert any("Docker" in r.memory.title for r in results.results)


def test_rrf_merge():
    """RRF 融合逻辑（单元测试，不需要数据库）。"""
    m1 = Memory(id=uuid4(), workspace_id="t", memory_type="rule", content="A")
    m2 = Memory(id=uuid4(), workspace_id="t", memory_type="rule", content="B")
    m3 = Memory(id=uuid4(), workspace_id="t", memory_type="rule", content="C")

    vector_results = [(m1, 0.95), (m2, 0.85), (m3, 0.75)]
    keyword_results = [(m2, 0.06), (m3, 0.04), (m1, 0.02)]

    merged = MemoryService._rrf_merge(vector_results, keyword_results, top_k=3)

    # m2 在两路搜索中排名都靠前，应该排第一
    assert merged[0][0].id == m2.id
    assert len(merged) == 3


def test_rrf_merge_dedup():
    """RRF 融合去重。"""
    m1 = Memory(id=uuid4(), workspace_id="t", memory_type="rule", content="A")

    # 同一条记忆在两路结果中
    vector_results = [(m1, 0.95)]
    keyword_results = [(m1, 0.06)]

    merged = MemoryService._rrf_merge(vector_results, keyword_results, top_k=5)
    assert len(merged) == 1  # 不应该重复


@pytest.mark.asyncio
async def test_get_stats(db_session):
    """全局统计。"""
    service = MemoryService(db_session)
    await service.create_memory(
        MemoryCreate(
            workspace_id="stats-ws",
            memory_type=MemoryType.RULE,
            content="Rule 1",
            importance=0.8,
        )
    )
    await service.create_memory(
        MemoryCreate(
            workspace_id="stats-ws",
            memory_type=MemoryType.PREFERENCE,
            content="Preference 1",
            importance=0.6,
        )
    )

    stats = await service.get_stats()
    assert stats.total_memories >= 2
    assert stats.total_workspaces >= 1


@pytest.mark.asyncio
async def test_update_memory(db_session):
    """更新 Memory。"""
    service = MemoryService(db_session)
    created = await service.create_memory(
        MemoryCreate(
            workspace_id="svc-update",
            memory_type=MemoryType.RULE,
            content="Original content",
            importance=0.5,
        )
    )

    from app.schemas import MemoryUpdate

    updated = await service.update_memory(
        created.id,
        MemoryUpdate(content="Updated content", importance=0.9),
    )
    assert updated.content == "Updated content"
    assert updated.importance == 0.9
