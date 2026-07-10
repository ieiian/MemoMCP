"""
调用活动追踪

记录 MCP 工具与 REST API 的调用事件，供管理页实时展示。
使用内存环形缓冲区，不持久化。
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class ActivityEvent:
    """单条调用活动记录。"""

    timestamp: str
    source: str  # "mcp" | "rest"
    action: str
    status: str  # "ok" | "error"
    duration_ms: float
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        """转为可序列化字典。"""
        return asdict(self)


@dataclass
class ActivityTracker:
    """全局活动追踪器（进程内单例）。"""

    max_size: int = 200
    _events: deque[ActivityEvent] = field(default_factory=deque)
    _subscribers: list[asyncio.Queue[ActivityEvent]] = field(default_factory=list)
    _active_mcp: int = 0
    _active_rest: int = 0
    _last_mcp_at: str | None = None
    _total_mcp: int = 0
    _total_rest: int = 0
    _started_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def __post_init__(self) -> None:
        self._events = deque(maxlen=self.max_size)

    def record(
        self,
        source: str,
        action: str,
        status: str,
        duration_ms: float,
        detail: str = "",
    ) -> ActivityEvent:
        """记录一次调用并通知订阅者。"""
        event = ActivityEvent(
            timestamp=datetime.now(timezone.utc).isoformat(),
            source=source,
            action=action,
            status=status,
            duration_ms=round(duration_ms, 1),
            detail=detail,
        )
        self._events.appendleft(event)

        if source == "mcp":
            self._last_mcp_at = event.timestamp
            self._total_mcp += 1
        else:
            self._total_rest += 1

        for queue in self._subscribers:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass

        return event

    def begin(self, source: str) -> None:
        """标记调用开始。"""
        if source == "mcp":
            self._active_mcp += 1
        else:
            self._active_rest += 1

    def end(self, source: str) -> None:
        """标记调用结束。"""
        if source == "mcp":
            self._active_mcp = max(0, self._active_mcp - 1)
        else:
            self._active_rest = max(0, self._active_rest - 1)

    def get_recent(self, limit: int = 50) -> list[dict[str, Any]]:
        """获取最近的活动记录。"""
        return [e.to_dict() for e in list(self._events)[:limit]]

    def get_status(self) -> dict[str, Any]:
        """获取运行状态摘要。"""
        return {
            "started_at": self._started_at,
            "active_mcp_calls": self._active_mcp,
            "active_rest_calls": self._active_rest,
            "last_mcp_at": self._last_mcp_at,
            "total_mcp_calls": self._total_mcp,
            "total_rest_calls": self._total_rest,
            "mcp_likely_running": self._last_mcp_at is not None
            and self._active_mcp > 0,
        }

    async def subscribe(self) -> asyncio.Queue[ActivityEvent]:
        """订阅实时事件流。"""
        queue: asyncio.Queue[ActivityEvent] = asyncio.Queue(maxsize=50)
        self._subscribers.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[ActivityEvent]) -> None:
        """取消订阅。"""
        if queue in self._subscribers:
            self._subscribers.remove(queue)


# 全局单例
tracker = ActivityTracker()


class ActivityContext:
    """上下文管理器，自动记录调用耗时与状态。"""

    def __init__(
        self,
        source: str,
        action: str,
        detail: str = "",
    ) -> None:
        self.source = source
        self.action = action
        self.detail = detail
        self._start = 0.0
        self._status = "ok"
        self._detail = detail

    def set_error(self, detail: str) -> None:
        """标记调用失败。"""
        self._status = "error"
        self._detail = detail

    def __enter__(self) -> ActivityContext:
        self._start = time.perf_counter()
        tracker.begin(self.source)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        duration_ms = (time.perf_counter() - self._start) * 1000
        if exc_type is not None:
            self._status = "error"
            if not self._detail:
                self._detail = str(exc_val) if exc_val else exc_type.__name__
        tracker.record(
            source=self.source,
            action=self.action,
            status=self._status,
            duration_ms=duration_ms,
            detail=self._detail,
        )
        tracker.end(self.source)


async def track_async(
    source: str,
    action: str,
    coro,
    detail: str = "",
):
    """异步调用包装，自动记录活动。"""
    tracker.begin(source)
    start = time.perf_counter()
    status = "ok"
    result_detail = detail
    try:
        return await coro
    except Exception as e:
        status = "error"
        result_detail = str(e)
        raise
    finally:
        duration_ms = (time.perf_counter() - start) * 1000
        tracker.record(source, action, status, duration_ms, result_detail)
        tracker.end(source)
