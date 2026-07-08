"""
MemoMCP ORM 模型

使用 SQLAlchemy 2.x 声明式风格，定义 memories 表结构。
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Float,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import (
    ARRAY,
    JSONB,
    TIMESTAMP,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

from app.database import Base
from app.config import get_settings

settings = get_settings()


class MemoryType(str, enum.Enum):
    """记忆类型枚举。"""

    RULE = "rule"
    PREFERENCE = "preference"
    DECISION = "decision"
    ARCHITECTURE = "architecture"
    KNOWLEDGE = "knowledge"
    BUG = "bug"
    SOLUTION = "solution"
    SNIPPET = "snippet"
    TODO = "todo"
    API = "api"
    COMMAND = "command"
    EXPERIENCE = "experience"


class UTCDateTime(TypeDecorator):
    """始终以 UTC 存储的 TIMESTAMPTZ 类型装饰器。"""

    impl = TIMESTAMP(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):  # type: ignore[override]
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    def process_result_value(self, value, dialect):  # type: ignore[override]
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value


class Memory(Base):
    """长期记忆实体，对应 memories 表。"""

    __tablename__ = "memories"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
        server_default=func.gen_random_uuid(),
    )

    workspace_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="工作区隔离键",
    )

    memory_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="记忆类型",
    )

    title: Mapped[str | None] = mapped_column(
        String(256),
        nullable=True,
    )

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    summary: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    tags: Mapped[list[str]] = mapped_column(
        ARRAY(String),
        nullable=False,
        default=list,
        server_default="{}",
    )

    metadata_: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
        comment="扩展元数据",
    )

    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(settings.embedding_dimension),
        nullable=True,
        comment="内容向量",
    )

    importance: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.5,
        server_default="0.5",
    )

    source: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="manual",
        server_default="manual",
    )

    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    last_access_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    access_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    def __repr__(self) -> str:
        return (
            f"<Memory(id={self.id}, workspace={self.workspace_id}, "
            f"type={self.memory_type}, title={self.title!r})>"
        )
