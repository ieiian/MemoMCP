"""
MemoMCP MCP Tools

通过 FastMCP 暴露 10 个 MCP 工具，供 Cursor / Claude Code / Cline 等
AI Coding 工具调用。所有工具复用 Service 层，与 REST API 共享业务逻辑。

通用工具（7 个）: save/search/update/delete/get/list/clear
AI 工具（3 个，需 AI_MEMORY_MANAGER=true）: analyze/summarize/merge
"""

from __future__ import annotations

import functools
import logging
from uuid import UUID

from fastmcp import FastMCP

from app.activity import track_async
from app.database import async_session_factory
from app.embedding import get_embedding_provider
from app.llm import get_llm_provider
from app.memory_manager.manager import MemoryManager
from app.models import MemoryType
from app.service import MemoryService

logger = logging.getLogger(__name__)

# ============================================================
# FastMCP 实例
# ============================================================
mcp = FastMCP(
    "MemoMCP",
    instructions=(
        "MemoMCP — Universal long-term memory service.\n"
        "Use save_memory to store rules, preferences, decisions, etc.\n"
        "Use search_memory to find relevant memories by keywords.\n"
        "All memories are isolated by workspace_id."
    ),
)


# ============================================================
# 辅助函数
# ============================================================
def _validate_memory_type(memory_type: str) -> str:
    """校验 memory_type 是否合法，返回小写值。"""
    try:
        return MemoryType(memory_type).value
    except ValueError:
        valid = ", ".join(t.value for t in MemoryType)
        raise ValueError(
            f"Invalid memory_type '{memory_type}'. Valid types: {valid}"
        )


def _validate_uuid(memory_id: str) -> UUID:
    """校验 UUID 格式。"""
    try:
        return UUID(memory_id)
    except ValueError:
        raise ValueError(f"Invalid UUID: '{memory_id}'")


def _get_mcp_client_ip() -> str:
    """尝试从 FastMCP 上下文获取客户端 IP。

    stdio 模式下无法获取 IP，返回 "local"。
    HTTP 模式下尝试从上下文中提取请求信息。
    """
    try:
        from fastmcp.server.context import get_context

        ctx = get_context()
        # FastMCP HTTP 模式下，上下文可能包含请求信息
        if hasattr(ctx, "request"):
            request = ctx.request
            if hasattr(request, "headers"):
                forwarded_for = request.headers.get("x-forwarded-for")
                if forwarded_for:
                    return forwarded_for.split(",")[0].strip()
                real_ip = request.headers.get("x-real-ip")
                if real_ip:
                    return real_ip.strip()
            if hasattr(request, "client") and request.client:
                return request.client.host
    except Exception:
        pass
    return "local"


def track_mcp(func):
    """MCP 工具调用追踪装饰器。"""

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        client_ip = _get_mcp_client_ip()
        return await track_async(
            "mcp", func.__name__, func(*args, **kwargs), client_ip=client_ip
        )

    return wrapper


# ============================================================
# 1. save_memory
# ============================================================
@mcp.tool
@track_mcp
async def save_memory(
    workspace_id: str,
    memory_type: str,
    content: str,
    title: str | None = None,
    tags: list[str] | None = None,
    importance: float = 0.5,
    source: str = "cursor",
) -> dict:
    """Save a memory to the specified workspace.

    Args:
        workspace_id: Workspace identifier (e.g. "project-a", "personal")
        memory_type: Type of memory. One of: rule, preference, decision,
                     architecture, knowledge, bug, solution, snippet,
                     todo, api, command, experience
        content: The memory content text
        title: Optional short title for the memory
        tags: Optional list of tags for categorization
        importance: Importance score 0.0-1.0 (default 0.5)
        source: Source identifier (e.g. "cursor", "claude", "manual")

    Returns:
        The saved memory object with id, workspace_id, content, etc.
    """
    from app.schemas import MemoryCreate

    mem_type = _validate_memory_type(memory_type)

    async with async_session_factory() as session:
        service = MemoryService(session)
        result = await service.create_memory(
            MemoryCreate(
                workspace_id=workspace_id,
                memory_type=mem_type,
                content=content,
                title=title,
                tags=tags or [],
                importance=importance,
                source=source,
            )
        )
        return result.model_dump(mode="json")


# ============================================================
# 2. search_memory
# ============================================================
@mcp.tool
@track_mcp
async def search_memory(
    workspace_id: str,
    query: str,
    memory_type: str | None = None,
    tags: list[str] | None = None,
    importance_min: float | None = None,
    top_k: int = 10,
) -> dict:
    """Search memories by keywords in a workspace.

    Uses keyword matching (ILIKE) with full-text search ranking.
    Vector search will be added in Phase 5 for hybrid search.

    Args:
        workspace_id: Workspace to search in
        query: Search keywords (space-separated terms are OR-matched)
        memory_type: Optional filter by memory type
        tags: Optional filter by tags (OR semantics)
        importance_min: Optional minimum importance threshold (0.0-1.0)
        top_k: Maximum number of results (default 10, max 100)

    Returns:
        Search results with memory objects and relevance scores.
    """
    from app.schemas import SearchRequest

    mem_type = _validate_memory_type(memory_type) if memory_type else None

    async with async_session_factory() as session:
        service = MemoryService(session)
        result = await service.search_memories(
            SearchRequest(
                workspace_id=workspace_id,
                query=query,
                memory_type=mem_type,
                tags=tags,
                importance_min=importance_min,
                top_k=min(top_k, 100),
            )
        )
        return result.model_dump(mode="json")


# ============================================================
# 3. update_memory
# ============================================================
@mcp.tool
@track_mcp
async def update_memory(
    memory_id: str,
    title: str | None = None,
    content: str | None = None,
    summary: str | None = None,
    tags: list[str] | None = None,
    metadata: dict | None = None,
    importance: float | None = None,
    memory_type: str | None = None,
) -> dict:
    """Update an existing memory. Only provided fields are updated.

    Args:
        memory_id: UUID of the memory to update
        title: New title (optional)
        content: New content (optional)
        summary: New summary (optional)
        tags: New list of tags (optional)
        metadata: New metadata dict (optional)
        importance: New importance 0.0-1.0 (optional)
        memory_type: New memory type (optional)

    Returns:
        The updated memory object, or error if not found.
    """
    from app.schemas import MemoryUpdate

    uid = _validate_uuid(memory_id)
    mem_type = _validate_memory_type(memory_type) if memory_type else None

    # 构造更新数据，只包含传入的字段
    update_data = {}
    if title is not None:
        update_data["title"] = title
    if content is not None:
        update_data["content"] = content
    if summary is not None:
        update_data["summary"] = summary
    if tags is not None:
        update_data["tags"] = tags
    if metadata is not None:
        update_data["metadata"] = metadata
    if importance is not None:
        update_data["importance"] = importance
    if mem_type is not None:
        update_data["memory_type"] = mem_type

    if not update_data:
        return {"error": "No fields provided to update"}

    async with async_session_factory() as session:
        service = MemoryService(session)
        result = await service.update_memory(
            uid, MemoryUpdate(**update_data)
        )
        if result is None:
            return {"error": f"Memory {memory_id} not found"}
        return result.model_dump(mode="json")


# ============================================================
# 4. delete_memory
# ============================================================
@mcp.tool
@track_mcp
async def delete_memory(memory_id: str) -> dict:
    """Delete a memory by its ID.

    Args:
        memory_id: UUID of the memory to delete

    Returns:
        Confirmation of deletion or error if not found.
    """
    uid = _validate_uuid(memory_id)

    async with async_session_factory() as session:
        service = MemoryService(session)
        deleted = await service.delete_memory(uid)
        if not deleted:
            return {"error": f"Memory {memory_id} not found"}
        return {"deleted": True, "memory_id": memory_id}


# ============================================================
# 5. get_memory
# ============================================================
@mcp.tool
@track_mcp
async def get_memory(memory_id: str) -> dict:
    """Get a single memory by its ID.

    Also increments the access count and updates last_access_at.

    Args:
        memory_id: UUID of the memory

    Returns:
        The memory object, or error if not found.
    """
    uid = _validate_uuid(memory_id)

    async with async_session_factory() as session:
        service = MemoryService(session)
        result = await service.get_memory(uid)
        if result is None:
            return {"error": f"Memory {memory_id} not found"}
        return result.model_dump(mode="json")


# ============================================================
# 6. list_memory
# ============================================================
@mcp.tool
@track_mcp
async def list_memory(
    workspace_id: str,
    memory_type: str | None = None,
    tags: list[str] | None = None,
    importance_min: float | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """List memories in a workspace with optional filters.

    Args:
        workspace_id: Workspace to list from
        memory_type: Optional filter by type
        tags: Optional filter by tags (OR semantics)
        importance_min: Optional minimum importance (0.0-1.0)
        limit: Max results (default 50, max 200)
        offset: Pagination offset

    Returns:
        List of memory objects and total count.
    """
    mem_type = _validate_memory_type(memory_type) if memory_type else None

    async with async_session_factory() as session:
        service = MemoryService(session)
        memories = await service.list_memories(
            workspace_id=workspace_id,
            memory_type=mem_type,
            tags=tags,
            importance_min=importance_min,
            limit=min(limit, 200),
            offset=offset,
        )
        return {
            "memories": [m.model_dump(mode="json") for m in memories],
            "total": len(memories),
            "limit": min(limit, 200),
            "offset": offset,
        }


# ============================================================
# 7. clear_workspace
# ============================================================
@mcp.tool
@track_mcp
async def clear_workspace(workspace_id: str, confirm: bool = False) -> dict:
    """Delete ALL memories in a workspace. This is irreversible.

    Args:
        workspace_id: Workspace to clear
        confirm: Must be True to actually delete (safety check)

    Returns:
        Number of deleted memories, or error if not confirmed.
    """
    if not confirm:
        return {
            "error": "Confirmation required. Set confirm=true to proceed. "
            "This will permanently delete ALL memories in the workspace."
        }

    async with async_session_factory() as session:
        service = MemoryService(session)
        count = await service.clear_workspace(workspace_id)
        return {
            "deleted": count,
            "workspace_id": workspace_id,
            "message": f"Cleared {count} memories from workspace '{workspace_id}'",
        }


# ============================================================
# 8. analyze_memory (AI Manager 模式)
# ============================================================
@mcp.tool
@track_mcp
async def analyze_memory(memory_id: str) -> dict:
    """Analyze a memory and provide AI-powered recommendations.

    Requires AI_MEMORY_MANAGER=true and a configured LLM provider.

    Args:
        memory_id: UUID of the memory to analyze

    Returns:
        Suggested importance, type, summary, and improvement suggestions.
    """
    llm = get_llm_provider()
    if llm is None:
        return {
            "error": "AI Memory Manager is not enabled. "
            "Set AI_MEMORY_MANAGER=true and configure LLM_PROVIDER."
        }

    uid = _validate_uuid(memory_id)

    async with async_session_factory() as session:
        manager = MemoryManager(
            session=session,
            llm_provider=llm,
            embedding_provider=get_embedding_provider(),
        )
        result = await manager.analyze(uid)
        return result


# ============================================================
# 9. summarize_memory (AI Manager 模式)
# ============================================================
@mcp.tool
@track_mcp
async def summarize_memory(
    workspace_id: str,
    limit: int = 20,
) -> dict:
    """Summarize all memories in a workspace using AI.

    Requires AI_MEMORY_MANAGER=true and a configured LLM provider.

    Args:
        workspace_id: Workspace to summarize
        limit: Max memories to include (default 20)

    Returns:
        Overall summary, key themes, and items needing review.
    """
    llm = get_llm_provider()
    if llm is None:
        return {
            "error": "AI Memory Manager is not enabled. "
            "Set AI_MEMORY_MANAGER=true and configure LLM_PROVIDER."
        }

    async with async_session_factory() as session:
        manager = MemoryManager(
            session=session,
            llm_provider=llm,
            embedding_provider=get_embedding_provider(),
        )
        result = await manager.summarize_workspace(
            workspace_id=workspace_id, limit=min(limit, 50)
        )
        return result


# ============================================================
# 10. merge_memory (AI Manager 模式)
# ============================================================
@mcp.tool
@track_mcp
async def merge_memory(memory_ids: list[str]) -> dict:
    """Merge multiple similar memories into one using AI.

    Requires AI_MEMORY_MANAGER=true and a configured LLM provider.
    All memories must be in the same workspace.
    Original memories are deleted after merge.

    Args:
        memory_ids: List of memory UUIDs to merge (minimum 2)

    Returns:
        The new merged memory details and deleted memory IDs.
    """
    llm = get_llm_provider()
    if llm is None:
        return {
            "error": "AI Memory Manager is not enabled. "
            "Set AI_MEMORY_MANAGER=true and configure LLM_PROVIDER."
        }

    if len(memory_ids) < 2:
        return {"error": "At least 2 memory IDs are required to merge"}

    # 验证所有 UUID
    uids = [_validate_uuid(mid) for mid in memory_ids]

    async with async_session_factory() as session:
        manager = MemoryManager(
            session=session,
            llm_provider=llm,
            embedding_provider=get_embedding_provider(),
        )
        result = await manager.merge(uids)
        return result
