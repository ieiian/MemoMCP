"""
MemoMCP REST API 路由

提供 HTTP 接口用于调试、管理和测试。
MCP Tools（Phase 4）会复用 Service 层，与此 API 共享业务逻辑。
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas import (
    ClearWorkspaceRequest,
    DeleteResult,
    ExportResponse,
    GlobalStats,
    HealthResponse,
    ImportRequest,
    ImportResult,
    MemoryCreate,
    MemoryResponse,
    MemoryUpdate,
    SearchRequest,
    SearchResponse,
    WorkspaceStats,
)
from app.service import MemoryService

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================
# 依赖注入：获取 MemoryService
# ============================================================
async def get_service(
    db: AsyncSession = Depends(get_db),
) -> MemoryService:
    return MemoryService(db)


# ============================================================
# 系统接口
# ============================================================
@router.get("/health", response_model=HealthResponse, tags=["system"])
async def health_check(
    db: AsyncSession = Depends(get_db),
) -> HealthResponse:
    """健康检查：数据库连通性。"""
    from sqlalchemy import text

    try:
        await db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception as e:
        logger.error("Health check failed: %s", e)
        db_status = "error"

    return HealthResponse(
        status="ok" if db_status == "ok" else "degraded",
        database=db_status,
        version="0.1.0",
    )


@router.get("/version", tags=["system"])
async def version() -> dict:
    """版本信息。"""
    return {
        "name": "MemoMCP",
        "version": "0.1.0",
        "description": "Universal long-term memory service for AI coding tools",
    }


@router.get("/stats", response_model=GlobalStats, tags=["system"])
async def get_stats(
    service: MemoryService = Depends(get_service),
) -> GlobalStats:
    """全局统计。"""
    return await service.get_stats()


@router.get(
    "/stats/{workspace_id}",
    response_model=WorkspaceStats,
    tags=["system"],
)
async def get_workspace_stats(
    workspace_id: str,
    service: MemoryService = Depends(get_service),
) -> WorkspaceStats:
    """单个工作区统计。"""
    return await service.get_workspace_stats(workspace_id)


# ============================================================
# Memory CRUD
# ============================================================
@router.get(
    "/memories",
    response_model=list[MemoryResponse],
    tags=["memories"],
)
async def list_memories(
    workspace_id: str = Query(..., description="工作区 ID"),
    memory_type: str | None = Query(None, description="按类型过滤"),
    tags: str | None = Query(None, description="逗号分隔的标签"),
    importance_min: float | None = Query(None, ge=0.0, le=1.0),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    service: MemoryService = Depends(get_service),
) -> list[MemoryResponse]:
    """列表查询。"""
    tag_list = tags.split(",") if tags else None
    return await service.list_memories(
        workspace_id=workspace_id,
        memory_type=memory_type,
        tags=tag_list,
        importance_min=importance_min,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/memories",
    response_model=MemoryResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["memories"],
)
async def create_memory(
    data: MemoryCreate,
    service: MemoryService = Depends(get_service),
) -> MemoryResponse:
    """创建 Memory。"""
    return await service.create_memory(data)


@router.get(
    "/memories/{memory_id}",
    response_model=MemoryResponse,
    tags=["memories"],
)
async def get_memory(
    memory_id: UUID,
    service: MemoryService = Depends(get_service),
) -> MemoryResponse:
    """获取单条 Memory。"""
    result = await service.get_memory(memory_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Memory {memory_id} not found",
        )
    return result


@router.patch(
    "/memories/{memory_id}",
    response_model=MemoryResponse,
    tags=["memories"],
)
async def update_memory(
    memory_id: UUID,
    data: MemoryUpdate,
    service: MemoryService = Depends(get_service),
) -> MemoryResponse:
    """更新 Memory。"""
    result = await service.update_memory(memory_id, data)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Memory {memory_id} not found",
        )
    return result


@router.delete(
    "/memories/{memory_id}",
    response_model=DeleteResult,
    tags=["memories"],
)
async def delete_memory(
    memory_id: UUID,
    service: MemoryService = Depends(get_service),
) -> DeleteResult:
    """删除 Memory。"""
    deleted = await service.delete_memory(memory_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Memory {memory_id} not found",
        )
    return DeleteResult(deleted=1, message="Memory deleted")


# ============================================================
# 搜索
# ============================================================
@router.post(
    "/search",
    response_model=SearchResponse,
    tags=["search"],
)
async def search_memories(
    request: SearchRequest,
    service: MemoryService = Depends(get_service),
) -> SearchResponse:
    """搜索 Memory。Phase 3 为关键词搜索，Phase 5 升级为 Hybrid。"""
    return await service.search_memories(request)


# ============================================================
# 批量操作
# ============================================================
@router.delete(
    "/workspaces/{workspace_id}",
    response_model=DeleteResult,
    tags=["workspaces"],
)
async def clear_workspace(
    workspace_id: str,
    confirm: bool = Query(..., description="必须传 confirm=true"),
    service: MemoryService = Depends(get_service),
) -> DeleteResult:
    """清空工作区。"""
    if not confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="confirm=true is required to clear workspace",
        )
    count = await service.clear_workspace(workspace_id)
    return DeleteResult(
        deleted=count,
        message=f"Cleared {count} memories from workspace '{workspace_id}'",
    )


# ============================================================
# 导入导出
# ============================================================
@router.get(
    "/export",
    response_model=ExportResponse,
    tags=["backup"],
)
async def export_memories(
    workspace_id: str | None = Query(None, description="按工作区导出，留空导出全部"),
    service: MemoryService = Depends(get_service),
) -> ExportResponse:
    """导出记忆数据为 JSON（不含向量）。"""
    return await service.export_memories(workspace_id)


@router.post(
    "/import",
    response_model=ImportResult,
    tags=["backup"],
)
async def import_memories(
    data: ImportRequest,
    service: MemoryService = Depends(get_service),
) -> ImportResult:
    """从 JSON 批量导入记忆。"""
    return await service.import_memories(data)
