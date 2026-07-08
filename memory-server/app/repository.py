"""
MemoMCP 数据访问层

Repository Pattern：所有数据库操作集中在此，Service 层通过 Repository 访问数据。
向量搜索方法已预留，Phase 5 接入 Embedding 后启用。
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import and_, delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Memory

logger = logging.getLogger(__name__)


class MemoryRepository:
    """Memory 数据访问对象。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ============================================================
    # CRUD
    # ============================================================

    async def create(self, memory: Memory) -> Memory:
        """插入一条 Memory。"""
        self.session.add(memory)
        await self.session.flush()
        await self.session.refresh(memory)
        logger.debug("Created memory: %s", memory.id)
        return memory

    async def get_by_id(self, memory_id: UUID) -> Memory | None:
        """按 ID 查询单条，同时更新访问计数。"""
        stmt = select(Memory).where(Memory.id == memory_id)
        result = await self.session.execute(stmt)
        memory = result.scalar_one_or_none()
        if memory is not None:
            await self._touch_access(memory_id)
        return memory

    async def get_by_id_no_touch(self, memory_id: UUID) -> Memory | None:
        """按 ID 查询，不更新访问计数（内部使用）。"""
        stmt = select(Memory).where(Memory.id == memory_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update(self, memory_id: UUID, **fields) -> Memory | None:
        """部分更新。只更新传入的字段。"""
        # 处理 metadata -> metadata_ 映射
        if "metadata" in fields:
            fields["metadata_"] = fields.pop("metadata")

        if not fields:
            return await self.get_by_id_no_touch(memory_id)

        # 使用 ORM 方式更新
        memory = await self.get_by_id_no_touch(memory_id)
        if memory is None:
            return None

        for key, value in fields.items():
            setattr(memory, key, value)

        await self.session.flush()
        await self.session.refresh(memory)
        logger.debug("Updated memory: %s", memory_id)
        return memory

    async def delete(self, memory_id: UUID) -> bool:
        """按 ID 删除。"""
        stmt = delete(Memory).where(Memory.id == memory_id)
        result = await self.session.execute(stmt)
        await self.session.flush()
        deleted = result.rowcount > 0
        if deleted:
            logger.debug("Deleted memory: %s", memory_id)
        return deleted

    async def set_embedding(self, memory_id: UUID, embedding: list[float]) -> None:
        """设置向量（Phase 5 Embedding 接入后使用）。"""
        memory = await self.get_by_id_no_touch(memory_id)
        if memory is not None:
            memory.embedding = embedding
            await self.session.flush()

    # ============================================================
    # 列表查询
    # ============================================================

    async def list_by_workspace(
        self,
        workspace_id: str,
        memory_type: str | None = None,
        tags: list[str] | None = None,
        importance_min: float | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Memory]:
        """按工作区分页列表，支持过滤。"""
        conditions = [Memory.workspace_id == workspace_id]

        if memory_type is not None:
            conditions.append(Memory.memory_type == memory_type)
        if importance_min is not None:
            conditions.append(Memory.importance >= importance_min)
        if tags:
            # tags 数组重叠查询（OR 语义）
            conditions.append(Memory.tags.overlap(tags))

        stmt = (
            select(Memory)
            .where(and_(*conditions))
            .order_by(Memory.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    # ============================================================
    # 搜索
    # ============================================================

    async def search_keyword(
        self,
        workspace_id: str,
        query: str,
        memory_type: str | None = None,
        tags: list[str] | None = None,
        importance_min: float | None = None,
        top_k: int = 10,
    ) -> list[tuple[Memory, float]]:
        """关键词搜索（Phase 3）。

        将查询按空格分割为多个词，每个词用 ILIKE 匹配 title 或 content（OR 语义）。
        结合 ts_rank 全文检索排序 + importance 综合排序。
        返回 (memory, score) 列表。
        """
        conditions = [Memory.workspace_id == workspace_id]

        if memory_type is not None:
            conditions.append(Memory.memory_type == memory_type)
        if importance_min is not None:
            conditions.append(Memory.importance >= importance_min)
        if tags:
            conditions.append(Memory.tags.overlap(tags))

        # 将查询拆分为多个词，每个词 ILIKE 匹配（OR 语义）
        keywords = [w for w in query.split() if w]
        if not keywords:
            keywords = [query]

        keyword_conds = []
        for kw in keywords:
            pattern = f"%{kw}%"
            keyword_conds.append(Memory.title.ilike(pattern))
            keyword_conds.append(Memory.content.ilike(pattern))

        from sqlalchemy import or_

        conditions.append(or_(*keyword_conds))

        # 全文检索排序分数
        ts_query = func.plainto_tsquery("english", query)
        ts_score = func.ts_rank(
            func.to_tsvector("english", Memory.content), ts_query
        ).label("ts_score")

        stmt = (
            select(Memory, ts_score)
            .where(and_(*conditions))
            .order_by(text("ts_score DESC"), Memory.importance.desc())
            .limit(top_k)
        )
        result = await self.session.execute(stmt)

        results: list[tuple[Memory, float]] = []
        for row in result:
            memory = row[0]
            score = float(row[1]) if row[1] is not None else 0.0
            results.append((memory, score))
        return results

    async def search_vector(
        self,
        workspace_id: str,
        embedding: list[float],
        memory_type: str | None = None,
        tags: list[str] | None = None,
        importance_min: float | None = None,
        top_k: int = 10,
    ) -> list[tuple[Memory, float]]:
        """向量搜索（Phase 5 启用）。

        使用 pgvector 余弦距离 + HNSW 索引。
        返回 (memory, similarity) 列表，similarity 范围 0.0~1.0。
        """
        conditions = [Memory.workspace_id == workspace_id, Memory.embedding.isnot(None)]

        if memory_type is not None:
            conditions.append(Memory.memory_type == memory_type)
        if importance_min is not None:
            conditions.append(Memory.importance >= importance_min)
        if tags:
            conditions.append(Memory.tags.overlap(tags))

        # cosine_distance: 0=完全相同, 2=完全相反
        # similarity = 1 - cosine_distance
        distance = Memory.embedding.cosine_distance(embedding).label("distance")
        similarity = (1.0 - distance).label("similarity")

        stmt = (
            select(Memory, similarity)
            .where(and_(*conditions))
            .order_by(distance.asc())
            .limit(top_k)
        )
        result = await self.session.execute(stmt)

        results: list[tuple[Memory, float]] = []
        for row in result:
            memory = row[0]
            sim = float(row[1]) if row[1] is not None else 0.0
            results.append((memory, sim))
        return results

    # ============================================================
    # 统计
    # ============================================================

    async def count_by_workspace(self, workspace_id: str) -> int:
        """统计工作区内 Memory 总数。"""
        stmt = select(func.count()).select_from(Memory).where(
            Memory.workspace_id == workspace_id
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def count_all(self) -> int:
        """全局 Memory 总数。"""
        stmt = select(func.count()).select_from(Memory)
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def count_workspaces(self) -> int:
        """工作区总数。"""
        stmt = select(func.count(func.distinct(Memory.workspace_id)))
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def stats_by_type(self, workspace_id: str | None = None) -> dict[str, int]:
        """按类型统计。

        workspace_id 为 None 时统计全局。
        """
        stmt = select(Memory.memory_type, func.count()).group_by(Memory.memory_type)
        if workspace_id is not None:
            stmt = stmt.where(Memory.workspace_id == workspace_id)
        result = await self.session.execute(stmt)
        return {row[0]: row[1] for row in result}

    async def avg_importance(self, workspace_id: str) -> float:
        """工作区平均重要度。"""
        stmt = select(func.avg(Memory.importance)).where(
            Memory.workspace_id == workspace_id
        )
        result = await self.session.execute(stmt)
        val = result.scalar_one()
        return float(val) if val is not None else 0.0

    async def list_workspaces(self) -> list[str]:
        """列出所有工作区 ID。"""
        stmt = select(func.distinct(Memory.workspace_id))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    # ============================================================
    # 批量操作
    # ============================================================

    async def clear_workspace(self, workspace_id: str) -> int:
        """清空指定工作区，返回删除数量。"""
        # 先计数
        count = await self.count_by_workspace(workspace_id)
        if count == 0:
            return 0
        stmt = delete(Memory).where(Memory.workspace_id == workspace_id)
        await self.session.execute(stmt)
        await self.session.flush()
        logger.info("Cleared workspace %s: %d memories deleted", workspace_id, count)
        return count

    # ============================================================
    # 内部辅助
    # ============================================================

    async def _touch_access(self, memory_id: UUID) -> None:
        """更新访问计数和最近访问时间。"""
        stmt = text(
            "UPDATE memories SET access_count = access_count + 1, "
            "last_access_at = NOW() WHERE id = :id"
        )
        await self.session.execute(stmt, {"id": memory_id})
        await self.session.flush()
