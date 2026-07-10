"""
MemoMCP 服务层

业务逻辑编排层。Repository 负责数据访问，Service 负责业务规则。
Phase 5：集成 Embedding Provider，save 时生成向量，search 时 Hybrid Search。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.embedding import get_embedding_provider
from app.embedding.base import EmbeddingProvider
from app.llm import get_llm_provider
from app.llm.base import LLMProvider
from app.models import Memory, MemoryType
from app.repository import MemoryRepository
from app.schemas import (
    ExportResponse,
    GlobalStats,
    ImportRequest,
    ImportResult,
    MemoryCreate,
    MemoryExportItem,
    MemoryResponse,
    MemoryUpdate,
    SearchRequest,
    SearchResponse,
    SearchResult,
    WorkspaceStats,
)

logger = logging.getLogger(__name__)


def _to_response(memory: Memory) -> MemoryResponse:
    """ORM 对象转响应模型，处理 metadata_ -> metadata 映射。"""
    return MemoryResponse(
        id=memory.id,
        workspace_id=memory.workspace_id,
        memory_type=memory.memory_type,
        title=memory.title,
        content=memory.content,
        summary=memory.summary,
        tags=memory.tags or [],
        metadata=memory.metadata_ or {},
        importance=memory.importance,
        source=memory.source,
        created_at=memory.created_at,
        updated_at=memory.updated_at,
        last_access_at=memory.last_access_at,
        access_count=memory.access_count,
    )


def _text_to_embed(memory: Memory) -> str:
    """构造用于生成向量的文本（title + content）。"""
    parts = []
    if memory.title:
        parts.append(memory.title)
    if memory.content:
        parts.append(memory.content)
    return "\n".join(parts)


class MemoryService:
    """Memory 业务服务。

    通过构造函数注入 session，每个请求实例化一个 service。
    Embedding Provider 和 LLM Provider 从全局单例获取。
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = MemoryRepository(session)
        self.embedding_provider: EmbeddingProvider | None = get_embedding_provider()
        self.llm_provider = get_llm_provider()

    def _get_memory_manager(self):
        """获取 MemoryManager（仅 AI Manager 模式可用时）。

        使用延迟导入避免循环依赖（manager.py 导入 service._text_to_embed）。
        """
        if self.llm_provider is None:
            return None
        from app.memory_manager.manager import MemoryManager

        return MemoryManager(
            session=self.session,
            llm_provider=self.llm_provider,
            embedding_provider=self.embedding_provider,
        )

    # ============================================================
    # CRUD
    # ============================================================

    async def create_memory(self, data: MemoryCreate) -> MemoryResponse:
        """创建 Memory。

        - 如果 Embedding Provider 可用，自动生成向量。
        - 如果 AI Memory Manager 可用，自动生成标题和摘要。
        - 所有 AI 调用失败不阻塞保存。
        """
        memory = Memory(
            workspace_id=data.workspace_id,
            memory_type=data.memory_type.value,
            title=data.title,
            content=data.content,
            summary=data.summary,
            tags=data.tags,
            metadata_=data.metadata,
            importance=data.importance,
            source=data.source,
        )

        # AI Memory Manager 增强（可选）
        manager = self._get_memory_manager()
        if manager is not None:
            # 自动生成标题（如果未提供）
            if not memory.title:
                try:
                    memory.title = await manager.generate_title(data.content)
                except Exception as e:
                    logger.warning("AI title generation failed: %s", e)

            # 自动生成摘要（如果内容较长且未提供摘要）
            if not memory.summary and len(data.content) > 500:
                try:
                    memory.summary = await manager.summarize(data.content)
                except Exception as e:
                    logger.warning("AI summary generation failed: %s", e)

        # 生成 embedding
        if self.embedding_provider is not None:
            try:
                memory.embedding = await self.embedding_provider.embed(
                    _text_to_embed(memory)
                )
            except Exception as e:
                logger.warning("Failed to generate embedding for new memory: %s", e)

        memory = await self.repo.create(memory)
        await self.session.commit()
        logger.info(
            "Created memory %s in workspace %s", memory.id, memory.workspace_id
        )
        return _to_response(memory)

    async def get_memory(self, memory_id: UUID) -> MemoryResponse | None:
        """获取单条 Memory。"""
        memory = await self.repo.get_by_id(memory_id)
        if memory is None:
            return None
        await self.session.commit()
        return _to_response(memory)

    async def update_memory(
        self, memory_id: UUID, data: MemoryUpdate
    ) -> MemoryResponse | None:
        """更新 Memory。

        如果 content 变更且 Embedding Provider 可用，重新生成向量。
        """
        fields = data.model_dump(exclude_unset=True, exclude_none=True)
        if not fields:
            memory = await self.repo.get_by_id_no_touch(memory_id)
            if memory is None:
                return None
            return _to_response(memory)

        memory = await self.repo.update(memory_id, **fields)
        if memory is None:
            return None

        # content 变更时重新生成 embedding
        if "content" in fields and self.embedding_provider is not None:
            try:
                new_embedding = await self.embedding_provider.embed(
                    _text_to_embed(memory)
                )
                await self.repo.set_embedding(memory_id, new_embedding)
                await self.session.flush()
            except Exception as e:
                logger.warning(
                    "Failed to regenerate embedding for %s: %s", memory_id, e
                )

        await self.session.commit()
        logger.info("Updated memory %s", memory_id)
        return _to_response(memory)

    async def delete_memory(self, memory_id: UUID) -> bool:
        """删除 Memory。"""
        deleted = await self.repo.delete(memory_id)
        if deleted:
            await self.session.commit()
        return deleted

    async def list_memories(
        self,
        workspace_id: str,
        memory_type: str | None = None,
        tags: list[str] | None = None,
        importance_min: float | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[MemoryResponse]:
        """列表查询。"""
        memories = await self.repo.list_by_workspace(
            workspace_id=workspace_id,
            memory_type=memory_type,
            tags=tags,
            importance_min=importance_min,
            limit=limit,
            offset=offset,
        )
        return [_to_response(m) for m in memories]

    # ============================================================
    # 搜索
    # ============================================================

    async def search_memories(
        self, request: SearchRequest
    ) -> SearchResponse:
        """搜索 Memory。

        - Embedding Provider 可用时：Hybrid Search（向量 + 关键词 + RRF 融合）
        - Embedding Provider 不可用时：关键词搜索回退
        """
        mem_type = request.memory_type.value if request.memory_type else None

        # 尝试 Hybrid Search
        if self.embedding_provider is not None:
            try:
                results = await self._hybrid_search(request, mem_type)
            except Exception as e:
                logger.warning(
                    "Hybrid search failed, falling back to keyword: %s", e
                )
                results = await self._keyword_search(request, mem_type)
        else:
            # 关键词搜索回退
            results = await self._keyword_search(request, mem_type)

        search_results = [
            SearchResult(memory=_to_response(mem), score=score)
            for mem, score in results
        ]
        return SearchResponse(results=search_results, total=len(search_results))

    async def _keyword_search(
        self, request: SearchRequest, mem_type: str | None
    ) -> list[tuple[Memory, float]]:
        """关键词搜索。"""
        return await self.repo.search_keyword(
            workspace_id=request.workspace_id,
            query=request.query,
            memory_type=mem_type,
            tags=request.tags,
            importance_min=request.importance_min,
            top_k=request.top_k,
        )

    async def _hybrid_search(
        self, request: SearchRequest, mem_type: str | None
    ) -> list[tuple[Memory, float]]:
        """Hybrid Search：向量搜索 + 关键词搜索 + RRF 融合。"""
        # 1. 查询向量化
        query_embedding = await self.embedding_provider.embed(request.query)

        # 2. 并行执行向量搜索和关键词搜索
        #    取 top_k * 2 扩大召回，RRF 后截断到 top_k
        fetch_k = request.top_k * 2

        vector_results = await self.repo.search_vector(
            workspace_id=request.workspace_id,
            embedding=query_embedding,
            memory_type=mem_type,
            tags=request.tags,
            importance_min=request.importance_min,
            top_k=fetch_k,
        )
        keyword_results = await self.repo.search_keyword(
            workspace_id=request.workspace_id,
            query=request.query,
            memory_type=mem_type,
            tags=request.tags,
            importance_min=request.importance_min,
            top_k=fetch_k,
        )

        # 3. RRF 融合
        merged = self._rrf_merge(
            vector_results, keyword_results, request.top_k
        )
        return merged

    @staticmethod
    def _rrf_merge(
        vector_results: list[tuple[Memory, float]],
        keyword_results: list[tuple[Memory, float]],
        top_k: int,
        k: int = 60,
    ) -> list[tuple[Memory, float]]:
        """RRF (Reciprocal Rank Fusion) 融合两路搜索结果。

        公式: score = sum( 1 / (k + rank_i) )

        Args:
            vector_results: 向量搜索结果 (memory, similarity)
            keyword_results: 关键词搜索结果 (memory, ts_score)
            top_k: 最终返回数量
            k: RRF 常数（默认 60，标准值）

        Returns:
            融合后的 (memory, rrf_score) 列表
        """
        scores: dict[UUID, tuple[Memory, float]] = {}

        # 向量搜索结果贡献
        for rank, (memory, _) in enumerate(vector_results):
            rrf_score = 1.0 / (k + rank + 1)
            if memory.id in scores:
                scores[memory.id] = (memory, scores[memory.id][1] + rrf_score)
            else:
                scores[memory.id] = (memory, rrf_score)

        # 关键词搜索结果贡献
        for rank, (memory, _) in enumerate(keyword_results):
            rrf_score = 1.0 / (k + rank + 1)
            if memory.id in scores:
                scores[memory.id] = (memory, scores[memory.id][1] + rrf_score)
            else:
                scores[memory.id] = (memory, rrf_score)

        # 按 RRF score 降序排序
        merged = sorted(scores.values(), key=lambda x: x[1], reverse=True)
        return merged[:top_k]

    # ============================================================
    # 批量操作
    # ============================================================

    async def clear_workspace(self, workspace_id: str) -> int:
        """清空工作区，返回删除数量。"""
        count = await self.repo.clear_workspace(workspace_id)
        if count > 0:
            await self.session.commit()
        return count

    # ============================================================
    # 统计
    # ============================================================

    async def get_stats(self) -> GlobalStats:
        """获取全局统计。"""
        total = await self.repo.count_all()
        workspace_count = await self.repo.count_workspaces()
        by_type = await self.repo.stats_by_type()

        workspace_ids = await self.repo.list_workspaces()
        workspace_stats: list[WorkspaceStats] = []
        for ws_id in workspace_ids:
            ws_total = await self.repo.count_by_workspace(ws_id)
            ws_by_type = await self.repo.stats_by_type(ws_id)
            ws_avg = await self.repo.avg_importance(ws_id)
            workspace_stats.append(
                WorkspaceStats(
                    workspace_id=ws_id,
                    total_memories=ws_total,
                    by_type=ws_by_type,
                    avg_importance=round(ws_avg, 3),
                )
            )

        return GlobalStats(
            total_memories=total,
            total_workspaces=workspace_count,
            by_type=by_type,
            workspaces=workspace_stats,
        )

    async def get_workspace_stats(self, workspace_id: str) -> WorkspaceStats:
        """获取单个工作区统计。"""
        total = await self.repo.count_by_workspace(workspace_id)
        by_type = await self.repo.stats_by_type(workspace_id)
        avg = await self.repo.avg_importance(workspace_id)
        return WorkspaceStats(
            workspace_id=workspace_id,
            total_memories=total,
            by_type=by_type,
            avg_importance=round(avg, 3),
        )

    # ============================================================
    # 导入导出
    # ============================================================

    async def export_memories(
        self,
        workspace_id: str | None = None,
    ) -> ExportResponse:
        """导出记忆数据（不含向量）。"""
        memories = await self.repo.list_all(workspace_id)
        items = [
            MemoryExportItem(
                workspace_id=m.workspace_id,
                memory_type=m.memory_type,
                title=m.title,
                content=m.content,
                summary=m.summary,
                tags=m.tags or [],
                metadata=m.metadata_ or {},
                importance=m.importance,
                source=m.source,
                created_at=m.created_at,
                updated_at=m.updated_at,
            )
            for m in memories
        ]
        return ExportResponse(
            exported_at=datetime.now(timezone.utc),
            workspace_id=workspace_id,
            total=len(items),
            memories=items,
        )

    async def import_memories(self, request: ImportRequest) -> ImportResult:
        """批量导入记忆，导入时重新生成向量。"""
        imported = 0
        skipped = 0
        failed = 0
        errors: list[str] = []

        for idx, item in enumerate(request.memories):
            try:
                if request.skip_existing and await self.repo.exists_by_content(
                    item.workspace_id, item.content
                ):
                    skipped += 1
                    continue

                mem_type = MemoryType(item.memory_type)
                await self.create_memory(
                    MemoryCreate(
                        workspace_id=item.workspace_id,
                        memory_type=mem_type,
                        title=item.title,
                        content=item.content,
                        summary=item.summary,
                        tags=item.tags,
                        metadata=item.metadata,
                        importance=item.importance,
                        source=item.source,
                    )
                )
                imported += 1
            except Exception as e:
                failed += 1
                errors.append(f"第 {idx + 1} 条: {e}")
                logger.warning("Import failed at index %d: %s", idx, e)

        return ImportResult(
            imported=imported,
            skipped=skipped,
            failed=failed,
            errors=errors[:20],
        )
