"""
MemoryManager — 对话记忆管理器

为多 Agent 系统提供短期记忆（对话历史）和长期记忆（用户偏好、历史事件）。
解决原架构「无状态」的核心问题。

设计思路：
  短期记忆：维护滑动窗口式对话历史，注入到每次 Agent 调用的上下文中
  长期记忆：存储用户画像、常见查询模式、高频关注点
  会话摘要：对话超长时自动调用 LLM 生成摘要，压缩上下文

学术价值：
  对话记忆是 Agent 系统的核心能力之一，
  基于滑动窗口 + 自动摘要的混合记忆管理方案可作为论文的一个创新点。
"""

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ConversationTurn:
    """单轮对话记录。"""
    role: str              # "user" | "assistant" | "system"
    content: str
    timestamp: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    # metadata 可存储：intents, agent_used, tool_calls, latency 等


@dataclass
class UserProfile:
    """用户画像（长期记忆）。"""
    user_id: str = "default"
    query_count: int = 0
    top_intents: Dict[str, int] = field(default_factory=dict)      # 高频意图
    top_entities: Dict[str, int] = field(default_factory=dict)     # 高频实体
    preferred_detail_level: str = "normal"                          # brief/normal/detailed
    last_active: float = 0.0
    notes: List[str] = field(default_factory=list)                 # 用户特殊偏好


class MemoryManager:
    """
    对话记忆管理器 — 短期记忆 + 长期记忆 + 自动摘要。

    用法示例:
        memory = MemoryManager(max_turns=20, llm=llm_provider)

        # 记录对话
        memory.add_user_message("温度多少？")
        memory.add_assistant_message("当前温度 28.5°C，湿度 65%。")

        # 获取上下文（注入到 Agent 调用中）
        context = memory.get_context_string(max_tokens=500)

        # 长期记忆
        memory.update_user_profile(intents=["sensor_query"], entities=["温度"])
    """

    def __init__(
        self,
        max_turns: int = 20,
        summary_threshold: int = 15,
        llm=None,
    ):
        """
        Args:
            max_turns:           短期记忆最大对话轮数
            summary_threshold:   触发自动摘要的对话长度阈值
            llm:                 LLMProvider 实例（用于自动生成摘要）
        """
        self.max_turns = max_turns
        self.summary_threshold = summary_threshold
        self.llm = llm

        # 短期记忆：对话历史（双端队列，自动丢弃最旧的）
        self._history: deque = deque(maxlen=max_turns * 2)  # user+assistant 各一条

        # 对话摘要（当历史被截断时保存压缩上下文）
        self._summaries: List[str] = []

        # 长期记忆：用户画像
        self._user_profile = UserProfile()

        # 当前会话 ID
        self._session_id: str = ""

        # 最近一次对话的 Agent 执行元数据
        self._last_execution_meta: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    # 短期记忆：对话历史
    # ------------------------------------------------------------------
    def add_turn(self, role: str, content: str, metadata: Optional[Dict] = None) -> None:
        """添加一轮对话。"""
        turn = ConversationTurn(
            role=role,
            content=content,
            timestamp=time.time(),
            metadata=metadata or {},
        )
        self._history.append(turn)

        # 检查是否需要自动摘要
        if len(self._history) >= self.summary_threshold * 2 and self.llm:
            self._auto_summarize()

    def add_user_message(self, message: str, metadata: Optional[Dict] = None) -> None:
        """记录用户消息。"""
        self.add_turn("user", message, metadata)

    def add_assistant_message(self, message: str, metadata: Optional[Dict] = None) -> None:
        """记录助手回复。"""
        self.add_turn("assistant", message, metadata)
        self._user_profile.query_count += 1
        self._user_profile.last_active = time.time()

    def get_recent_turns(self, n: int = 10) -> List[ConversationTurn]:
        """获取最近 n 轮对话。"""
        return list(self._history)[-n * 2:]  # n 轮 = n * 2 条

    def get_context_string(self, max_turns: int = 8) -> str:
        """
        生成可注入到 Agent 系统提示词中的上下文字符串。

        包含：历史摘要（如有）+ 最近对话 + 用户画像摘要
        """
        parts = []

        # 1. 历史摘要
        if self._summaries:
            latest_summary = self._summaries[-1]
            parts.append(f"[历史对话摘要]\n{latest_summary}")

        # 2. 最近对话
        recent = self.get_recent_turns(max_turns)
        if recent:
            lines = []
            for turn in recent:
                role_label = "用户" if turn.role == "user" else "助手"
                # 截断过长的内容
                content = turn.content[:200] + "..." if len(turn.content) > 200 else turn.content
                lines.append(f"{role_label}: {content}")
            parts.append("[最近对话]\n" + "\n".join(lines))

        # 3. 用户画像（简化版）
        if self._user_profile.query_count > 3:
            top_intents = sorted(
                self._user_profile.top_intents.items(),
                key=lambda x: x[1], reverse=True
            )[:3]
            if top_intents:
                intent_str = ", ".join(f"{k}({v}次)" for k, v in top_intents)
                parts.append(f"[用户偏好] 高频查询: {intent_str}")

        return "\n\n".join(parts) if parts else ""

    # ------------------------------------------------------------------
    # 自动摘要
    # ------------------------------------------------------------------
    def _auto_summarize(self) -> None:
        """当对话历史过长时，自动生成摘要压缩上下文。"""
        if not self.llm:
            return

        # 取出较早的一半对话用于摘要
        mid = len(self._history) // 2
        old_turns = list(self._history)[:mid]

        if not old_turns:
            return

        conversation_text = "\n".join(
            f"{'用户' if t.role == 'user' else '助手'}: {t.content[:150]}"
            for t in old_turns
        )

        summary_prompt = (
            "请用 2-3 句话概括以下对话的核心内容和结论：\n\n"
            f"{conversation_text}"
        )

        try:
            from .llm_provider import LLMMessage
            messages = [LLMMessage(role="user", content=summary_prompt)]
            resp = self.llm.chat(messages, temperature=0.1)
            if resp.content:
                self._summaries.append(resp.content)
                # 只保留最近 3 个摘要
                self._summaries = self._summaries[-3:]
                logger.info(f"对话摘要生成成功: {resp.content[:80]}...")

                # 清除已摘要的对话
                for _ in range(mid):
                    if self._history:
                        self._history.popleft()
        except Exception as e:
            logger.warning(f"对话摘要生成失败: {e}")

    # ------------------------------------------------------------------
    # 长期记忆：用户画像
    # ------------------------------------------------------------------
    def update_user_profile(
        self,
        intents: Optional[List[str]] = None,
        entities: Optional[List[str]] = None,
    ) -> None:
        """根据本次对话更新用户画像。"""
        if intents:
            for intent in intents:
                self._user_profile.top_intents[intent] = (
                    self._user_profile.top_intents.get(intent, 0) + 1
                )
        if entities:
            for entity in entities:
                self._user_profile.top_entities[entity] = (
                    self._user_profile.top_entities.get(entity, 0) + 1
                )

    def get_user_profile(self) -> Dict[str, Any]:
        """获取用户画像。"""
        return {
            "query_count": self._user_profile.query_count,
            "top_intents": dict(
                sorted(self._user_profile.top_intents.items(), key=lambda x: x[1], reverse=True)[:5]
            ),
            "top_entities": dict(
                sorted(self._user_profile.top_entities.items(), key=lambda x: x[1], reverse=True)[:5]
            ),
            "preferred_detail_level": self._user_profile.preferred_detail_level,
            "notes": self._user_profile.notes,
        }

    # ------------------------------------------------------------------
    # 执行元数据（最近一次 Agent 执行信息）
    # ------------------------------------------------------------------
    def set_execution_meta(self, meta: Dict[str, Any]) -> None:
        """记录最近一次 Agent 执行的元数据。"""
        self._last_execution_meta = meta

    def get_execution_meta(self) -> Dict[str, Any]:
        """获取最近一次执行元数据。"""
        return self._last_execution_meta

    # ------------------------------------------------------------------
    # 引用解析（处理"刚才"、"上面说的"等引用）
    # ------------------------------------------------------------------
    def resolve_reference(self, message: str) -> Optional[Dict[str, Any]]:
        """
        尝试解析消息中的引用关系。

        例如用户说"刚才那个报警能详细分析一下吗"，
        此方法会从历史对话中提取上一次涉及报警的执行上下文。

        Returns:
            引用的上下文字典，或 None（无引用/无法解析）
        """
        reference_keywords = ["刚才", "上面", "之前", "那个", "这个", "上次"]
        has_reference = any(kw in message for kw in reference_keywords)

        if not has_reference:
            return None

        # 查找最近一次有实质内容的 Agent 执行
        meta = self._last_execution_meta
        if meta and meta.get("intents"):
            return {
                "previous_intents": meta.get("intents", []),
                "previous_agents": meta.get("agents_used", []),
                "previous_reply": meta.get("reply_summary", ""),
                "previous_data": meta.get("data_snapshot", {}),
            }

        return None

    # ------------------------------------------------------------------
    # Session 管理
    # ------------------------------------------------------------------
    def start_session(self, session_id: str) -> None:
        """开始新会话。"""
        self._session_id = session_id
        logger.info(f"Memory session started: {session_id}")

    def end_session(self) -> Dict[str, Any]:
        """结束会话，返回会话统计。"""
        stats = {
            "session_id": self._session_id,
            "turns": len(self._history),
            "summaries": len(self._summaries),
            "profile": self.get_user_profile(),
        }
        self._session_id = ""
        return stats

    def __repr__(self) -> str:
        return (
            f"MemoryManager(turns={len(self._history)}, "
            f"summaries={len(self._summaries)}, "
            f"queries={self._user_profile.query_count})"
        )
