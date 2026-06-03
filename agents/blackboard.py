"""
Blackboard — 共享状态黑板

所有 Agent 通过黑板共享中间结果和上下文信息，
替代原来各 Agent 独立工作、最后合并结果的粗粒度协作模式。

核心概念：
  - 黑板是一个全局可读写的结构化状态存储
  - 每个 Agent 执行前从黑板读取上下文（前置 Agent 的产出）
  - 每个 Agent 执行后将结果写入黑板（供后续 Agent 使用）
  - 支持命名空间隔离（session 级别）和过期清理

这是改进 Workflow 的核心通信机制。
"""

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class BlackboardEntry:
    """黑板中的一条记录。"""
    key: str
    value: Any
    source_agent: str          # 写入该条目的 Agent 名称
    timestamp: float = 0.0     # 写入时间
    confidence: float = 1.0    # 置信度（由 EvaluatorAgent 设置）
    tags: Set[str] = field(default_factory=set)

    def is_expired(self, ttl_seconds: float = 300) -> bool:
        """检查条目是否过期。"""
        return (time.time() - self.timestamp) > ttl_seconds


class Blackboard:
    """
    共享状态黑板 — Agent 间的通信中介。

    用法示例:
        bb = Blackboard()
        bb.write("sensor.current", {"temperature": 28.5}, source="sensor")
        bb.write("sensor.trend", {"trend": "rising"}, source="sensor")

        # 后续 Agent 可以读取前置 Agent 的结果
        sensor_data = bb.read("sensor.current")
        all_sensor = bb.read_prefix("sensor.")
    """

    def __init__(self):
        self._entries: Dict[str, BlackboardEntry] = {}
        self._history: List[Dict[str, Any]] = []    # 操作日志
        self._sessions: Dict[str, set] = defaultdict(set)  # session → keys

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------
    def write(
        self,
        key: str,
        value: Any,
        source: str = "system",
        confidence: float = 1.0,
        tags: Optional[Set[str]] = None,
    ) -> None:
        """向黑板写入一条数据。"""
        entry = BlackboardEntry(
            key=key,
            value=value,
            source_agent=source,
            timestamp=time.time(),
            confidence=confidence,
            tags=tags or set(),
        )
        self._entries[key] = entry
        self._history.append({
            "action": "write",
            "key": key,
            "source": source,
            "timestamp": entry.timestamp,
        })
        logger.debug(f"Blackboard.write: {key} = {str(value)[:100]}... (by {source})")

    # ------------------------------------------------------------------
    # 读取
    # ------------------------------------------------------------------
    def read(self, key: str, default: Any = None) -> Any:
        """读取指定 key 的值。"""
        entry = self._entries.get(key)
        if entry is None or entry.is_expired():
            return default
        return entry.value

    def read_entry(self, key: str) -> Optional[BlackboardEntry]:
        """读取完整的 BlackboardEntry（含元信息）。"""
        entry = self._entries.get(key)
        if entry and not entry.is_expired():
            return entry
        return None

    def read_prefix(self, prefix: str) -> Dict[str, Any]:
        """读取所有以 prefix 开头的键值对。"""
        result = {}
        for key, entry in self._entries.items():
            if key.startswith(prefix) and not entry.is_expired():
                result[key] = entry.value
        return result

    def read_by_source(self, source: str) -> Dict[str, Any]:
        """读取指定 Agent 写入的所有数据。"""
        result = {}
        for key, entry in self._entries.items():
            if entry.source_agent == source and not entry.is_expired():
                result[key] = entry.value
        return result

    def read_by_tags(self, tags: Set[str]) -> Dict[str, Any]:
        """读取包含指定标签的所有数据。"""
        result = {}
        for key, entry in self._entries.items():
            if tags & entry.tags and not entry.is_expired():
                result[key] = entry.value
        return result

    # ------------------------------------------------------------------
    # 查询与统计
    # ------------------------------------------------------------------
    def keys(self, prefix: str = "") -> List[str]:
        """列出所有未过期的 key。"""
        return [
            k for k, e in self._entries.items()
            if k.startswith(prefix) and not e.is_expired()
        ]

    def snapshot(self) -> Dict[str, Any]:
        """获取黑板当前状态的完整快照。"""
        return {
            k: {
                "value": e.value,
                "source": e.source_agent,
                "confidence": e.confidence,
                "age_seconds": round(time.time() - e.timestamp, 1),
            }
            for k, e in self._entries.items()
            if not e.is_expired()
        }

    def get_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """获取最近的操作日志。"""
        return self._history[-limit:]

    # ------------------------------------------------------------------
    # 清理
    # ------------------------------------------------------------------
    def clear(self, prefix: str = "") -> int:
        """清除指定前缀的条目，返回清除数量。"""
        to_remove = [k for k in self._entries if k.startswith(prefix)]
        for k in to_remove:
            del self._entries[k]
        return len(to_remove)

    def cleanup_expired(self) -> int:
        """清理所有过期条目。"""
        to_remove = [k for k, e in self._entries.items() if e.is_expired()]
        for k in to_remove:
            del self._entries[k]
        return len(to_remove)

    # ------------------------------------------------------------------
    # Session 管理
    # ------------------------------------------------------------------
    def start_session(self, session_id: str) -> None:
        """开始一个新的工作流会话。"""
        self._sessions[session_id] = set()
        logger.debug(f"Blackboard session started: {session_id}")

    def write_to_session(self, session_id: str, key: str, value: Any, **kwargs) -> None:
        """写入数据并关联到指定会话。"""
        self.write(key, value, **kwargs)
        self._sessions.setdefault(session_id, set()).add(key)

    def clear_session(self, session_id: str) -> int:
        """清除指定会话的所有数据。"""
        keys = self._sessions.pop(session_id, set())
        count = 0
        for key in keys:
            if key in self._entries:
                del self._entries[key]
                count += 1
        return count

    def __repr__(self) -> str:
        active = [k for k, e in self._entries.items() if not e.is_expired()]
        return f"Blackboard(entries={len(active)}, sessions={len(self._sessions)})"
