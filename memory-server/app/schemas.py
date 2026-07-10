"""
MemoMCP Pydantic 模型

定义请求/响应的数据结构，供 REST API 和 MCP Tools 共用。
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models import MemoryType


# ============================================================
# 基础响应
# ============================================================
class MemoryResponse(BaseModel):
    """Memory 完整响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: str
    memory_type: str
    title: str | None = None
    content: str
    summary: str | None = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    importance: float
    source: str
    created_at: datetime
    updated_at: datetime
    last_access_at: datetime
    access_count: int


class SearchResult(BaseModel):
    """单条搜索结果，带相关性分数。"""

    memory: MemoryResponse
    score: float = Field(description="综合相关性分数 0.0~1.0")


# ============================================================
# 创建
# ============================================================
class MemoryCreate(BaseModel):
    """创建 Memory 请求。"""

    workspace_id: str = Field(..., min_length=1, max_length=64, description="工作区 ID")
    memory_type: MemoryType = Field(..., description="记忆类型")
    title: str | None = Field(default=None, max_length=256)
    content: str = Field(..., min_length=1, description="记忆内容")
    summary: str | None = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    importance: float = Field(default=0.5, ge=0.0, le=1.0, description="重要度")
    source: str = Field(default="manual", max_length=64)


# ============================================================
# 更新
# ============================================================
class MemoryUpdate(BaseModel):
    """更新 Memory 请求，所有字段可选。"""

    memory_type: MemoryType | None = None
    title: str | None = Field(default=None, max_length=256)
    content: str | None = None
    summary: str | None = None
    tags: list[str] | None = None
    metadata: dict | None = None
    importance: float | None = Field(default=None, ge=0.0, le=1.0)


# ============================================================
# 搜索
# ============================================================
class SearchRequest(BaseModel):
    """搜索请求。"""

    workspace_id: str = Field(..., min_length=1, description="工作区 ID")
    query: str = Field(..., min_length=1, description="搜索关键词")
    memory_type: MemoryType | None = Field(default=None, description="按类型过滤")
    tags: list[str] | None = Field(default=None, description="按标签过滤（OR 语义）")
    importance_min: float | None = Field(
        default=None, ge=0.0, le=1.0, description="最低重要度"
    )
    top_k: int = Field(default=10, ge=1, le=100, description="返回数量")


class SearchResponse(BaseModel):
    """搜索响应。"""

    results: list[SearchResult]
    total: int


# ============================================================
# 统计
# ============================================================
class WorkspaceStats(BaseModel):
    """工作区统计。"""

    workspace_id: str
    total_memories: int
    by_type: dict[str, int] = Field(default_factory=dict)
    avg_importance: float = 0.0


class GlobalStats(BaseModel):
    """全局统计。"""

    total_memories: int
    total_workspaces: int
    by_type: dict[str, int] = Field(default_factory=dict)
    workspaces: list[WorkspaceStats] = Field(default_factory=list)


# ============================================================
# 通用
# ============================================================
class ClearWorkspaceRequest(BaseModel):
    """清空工作区请求。"""

    workspace_id: str = Field(..., min_length=1)
    confirm: bool = Field(..., description="必须为 true 才执行")


class DeleteResult(BaseModel):
    """删除/清空结果。"""

    deleted: int
    message: str = ""


class HealthResponse(BaseModel):
    """健康检查响应。"""

    status: str = "ok"
    database: str = "unknown"
    version: str = ""


# ============================================================
# 导入导出
# ============================================================
class MemoryExportItem(BaseModel):
    """导出单条记忆（不含向量）。"""

    workspace_id: str
    memory_type: str
    title: str | None = None
    content: str
    summary: str | None = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    importance: float = 0.5
    source: str = "manual"
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ExportResponse(BaseModel):
    """导出响应。"""

    version: str = "0.1.0"
    exported_at: datetime
    workspace_id: str | None = None
    total: int
    memories: list[MemoryExportItem]


class ImportRequest(BaseModel):
    """导入请求。"""

    memories: list[MemoryExportItem] = Field(..., min_length=1)
    skip_existing: bool = Field(
        default=False,
        description="按 workspace_id + content 去重跳过已存在记录",
    )


class ImportResult(BaseModel):
    """导入结果。"""

    imported: int
    skipped: int
    failed: int
    errors: list[str] = Field(default_factory=list)


# ============================================================
# 系统状态
# ============================================================
class SystemStatus(BaseModel):
    """系统运行状态。"""

    version: str
    rest_api: str
    database: str
    embedding_provider: str | None
    ai_memory_manager: bool
    mcp_transport: str
    activity: dict = Field(default_factory=dict)
