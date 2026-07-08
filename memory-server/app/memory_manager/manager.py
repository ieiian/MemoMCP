"""
AI Memory Manager

可选的 AI 治理层，在 AI_MEMORY_MANAGER=true 时启用。
负责：判断价值、生成标题、自动分类、总结、分析、合并。
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.embedding import get_embedding_provider
from app.embedding.base import EmbeddingProvider
from app.llm.base import LLMProvider
from app.memory_manager import prompts
from app.models import Memory
from app.repository import MemoryRepository
from app.service import _text_to_embed

logger = logging.getLogger(__name__)


class MemoryManager:
    """AI Memory Manager。

    通过 LLM Provider 实现记忆的自动治理。
    每个请求实例化一个 manager（持有 session）。
    """

    def __init__(
        self,
        session: AsyncSession,
        llm_provider: LLMProvider,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self.session = session
        self.llm = llm_provider
        self.embedding_provider = embedding_provider
        self.repo = MemoryRepository(session)

    # ============================================================
    # 单条记忆治理（save 路径增强）
    # ============================================================

    async def should_save(self, content: str) -> dict:
        """判断内容是否值得长期保存。

        Returns:
            {"should_save": bool, "reason": str, "suggested_importance": float}
        """
        messages = [
            {
                "role": "user",
                "content": prompts.SHOULD_SAVE.format(content=content[:2000]),
            }
        ]
        try:
            result = await self.llm.chat_json(messages, temperature=0.1)
            return {
                "should_save": bool(result.get("should_save", True)),
                "reason": result.get("reason", ""),
                "suggested_importance": float(
                    result.get("suggested_importance", 0.5)
                ),
            }
        except Exception as e:
            logger.warning("should_save LLM call failed: %s", e)
            return {"should_save": True, "reason": "LLM unavailable, defaulting to save", "suggested_importance": 0.5}

    async def generate_title(self, content: str) -> str:
        """自动生成标题。"""
        messages = [
            {
                "role": "user",
                "content": prompts.GENERATE_TITLE.format(content=content[:2000]),
            }
        ]
        try:
            result = await self.llm.chat_json(messages, temperature=0.2)
            return result.get("title", "")[:256]
        except Exception as e:
            logger.warning("generate_title LLM call failed: %s", e)
            return ""

    async def classify_type(self, content: str) -> str:
        """自动分类 memory_type。"""
        messages = [
            {
                "role": "user",
                "content": prompts.CLASSIFY_TYPE.format(content=content[:2000]),
            }
        ]
        try:
            result = await self.llm.chat_json(messages, temperature=0.1)
            mem_type = result.get("memory_type", "knowledge")
            # 验证类型合法
            from app.models import MemoryType

            return MemoryType(mem_type).value
        except Exception as e:
            logger.warning("classify_type LLM call failed: %s", e)
            return "knowledge"

    async def summarize(self, content: str) -> str:
        """总结记忆内容。"""
        messages = [
            {
                "role": "user",
                "content": prompts.SUMMARIZE.format(content=content[:4000]),
            }
        ]
        try:
            result = await self.llm.chat_json(messages, temperature=0.2)
            return result.get("summary", "")
        except Exception as e:
            logger.warning("summarize LLM call failed: %s", e)
            return ""

    # ============================================================
    # MCP AI 工具支持
    # ============================================================

    async def analyze(self, memory_id: UUID) -> dict:
        """分析单条记忆，给出建议（不自动修改）。

        对应 MCP Tool: analyze_memory
        """
        memory = await self.repo.get_by_id_no_touch(memory_id)
        if memory is None:
            return {"error": f"Memory {memory_id} not found"}

        messages = [
            {
                "role": "user",
                "content": prompts.ANALYZE.format(
                    title=memory.title or "(no title)",
                    memory_type=memory.memory_type,
                    content=memory.content[:2000],
                    importance=memory.importance,
                ),
            }
        ]
        try:
            result = await self.llm.chat_json(messages, temperature=0.2)
            return {
                "memory_id": str(memory_id),
                "current_importance": memory.importance,
                "current_type": memory.memory_type,
                "suggested_importance": result.get("suggested_importance"),
                "suggested_type": result.get("suggested_type"),
                "summary": result.get("summary"),
                "suggestions": result.get("suggestions"),
            }
        except Exception as e:
            logger.warning("analyze LLM call failed: %s", e)
            return {"error": f"LLM analysis failed: {e}", "memory_id": str(memory_id)}

    async def summarize_workspace(
        self, workspace_id: str, limit: int = 20
    ) -> dict:
        """批量总结工作区记忆。

        对应 MCP Tool: summarize_memory
        """
        memories = await self.repo.list_by_workspace(
            workspace_id=workspace_id, limit=limit
        )
        if not memories:
            return {
                "workspace_id": workspace_id,
                "summary": "No memories found in this workspace.",
                "key_themes": [],
                "review_needed": [],
            }

        # 构造记忆列表（标题 + 类型 + 内容摘要）
        memory_list = "\n".join(
            f"- {m.title or '(no title)'} [{m.memory_type}]: {m.content[:100]}..."
            for m in memories
        )

        messages = [
            {
                "role": "user",
                "content": prompts.SUMMARIZE_WORKSPACE.format(
                    workspace_id=workspace_id,
                    count=len(memories),
                    memory_list=memory_list[:4000],
                ),
            }
        ]
        try:
            result = await self.llm.chat_json(messages, temperature=0.3)
            return {
                "workspace_id": workspace_id,
                "memory_count": len(memories),
                "summary": result.get("summary", ""),
                "key_themes": result.get("key_themes", []),
                "review_needed": result.get("review_needed", []),
            }
        except Exception as e:
            logger.warning("summarize_workspace LLM call failed: %s", e)
            return {
                "workspace_id": workspace_id,
                "error": f"LLM summarization failed: {e}",
                "memory_count": len(memories),
            }

    async def merge(self, memory_ids: list[UUID]) -> dict:
        """合并多条相似记忆为一条。

        对应 MCP Tool: merge_memory

        流程:
        1. 获取所有记忆
        2. LLM 生成合并内容
        3. 创建新 Memory（保留第一个的 workspace_id）
        4. 生成 embedding
        5. 删除旧记忆
        """
        if len(memory_ids) < 2:
            return {"error": "At least 2 memories are required to merge"}

        # 获取所有记忆
        memories: list[Memory] = []
        for mid in memory_ids:
            m = await self.repo.get_by_id_no_touch(mid)
            if m is None:
                return {"error": f"Memory {mid} not found"}
            memories.append(m)

        # 检查是否在同一 workspace
        workspace_ids = {m.workspace_id for m in memories}
        if len(workspace_ids) > 1:
            return {"error": "Cannot merge memories from different workspaces"}

        workspace_id = memories[0].workspace_id

        # 构造合并 prompt
        memories_text = "\n\n".join(
            f"Memory {i+1}:\n  Title: {m.title or '(no title)'}\n"
            f"  Type: {m.memory_type}\n  Content: {m.content[:500]}"
            for i, m in enumerate(memories)
        )

        messages = [
            {
                "role": "user",
                "content": prompts.MERGE.format(memories=memories_text),
            }
        ]

        try:
            result = await self.llm.chat_json(messages, temperature=0.3)
        except Exception as e:
            logger.warning("merge LLM call failed: %s", e)
            return {"error": f"LLM merge failed: {e}"}

        # 创建合并后的新 Memory
        merged_memory = Memory(
            workspace_id=workspace_id,
            memory_type=result.get("merged_type", memories[0].memory_type),
            title=result.get("merged_title", "")[:256],
            content=result.get("merged_content", ""),
            summary=result.get("merge_notes", ""),
            tags=list(set(tag for m in memories for tag in (m.tags or []))),
            metadata_={"merged_from": [str(mid) for mid in memory_ids]},
            importance=float(result.get("merged_importance", 0.7)),
            source="ai-merge",
        )

        # 生成 embedding
        if self.embedding_provider is not None:
            try:
                merged_memory.embedding = await self.embedding_provider.embed(
                    _text_to_embed(merged_memory)
                )
            except Exception as e:
                logger.warning("Failed to generate embedding for merged memory: %s", e)

        # 保存新记忆
        merged_memory = await self.repo.create(merged_memory)

        # 删除旧记忆
        deleted_ids = []
        for mid in memory_ids:
            await self.repo.delete(mid)
            deleted_ids.append(str(mid))

        await self.session.commit()

        logger.info(
            "Merged %d memories into %s in workspace %s",
            len(memory_ids),
            merged_memory.id,
            workspace_id,
        )

        return {
            "merged_memory_id": str(merged_memory.id),
            "merged_title": merged_memory.title,
            "merged_type": merged_memory.memory_type,
            "deleted_ids": deleted_ids,
            "merge_notes": result.get("merge_notes", ""),
        }
