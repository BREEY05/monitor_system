"""
Agent 基类与数据模型

定义 Intent（意图）、ToolCall（工具调用）、AgentResult（执行结果）
等核心数据结构，以及 BaseAgent 抽象基类。
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ==================== 意图分类 ====================

class IntentType(str, Enum):
    """系统支持的意图类型。"""
    SENSOR_QUERY   = "sensor_query"       # 查询实时传感器数据
    HISTORY_QUERY  = "history_query"      # 查询历史数据趋势
    ALARM_QUERY    = "alarm_query"        # 查询报警与异常
    ALARM_HANDLE   = "alarm_handle"       # 处理/确认报警
    KNOWLEDGE      = "knowledge"          # RAG 知识库检索
    SEARCH         = "search"             # 联网搜索
    DEVICE_MANAGE  = "device_manage"      # 设备管理（列表/3D 模型/地图）
    SYSTEM_CONFIG  = "system_config"      # 系统配置（阈值/模型/飞书）
    CHITCHAT       = "chitchat"           # 闲聊/问候
    COMPLEX        = "complex"            # 复杂多步任务


# ==================== 数据模型 ====================

@dataclass
class Intent:
    """意图分类结果。"""
    type: IntentType
    confidence: float = 1.0
    reasoning: str = ""
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Plan:
    """执行计划：由 Orchestrator 根据意图生成。"""
    intents: List[Intent]
    agent_sequence: List[str] = field(default_factory=list)   # Agent 名称执行顺序
    parallel: bool = False                                     # 是否可并行执行
    reasoning: str = ""


@dataclass
class ToolCall:
    """工具调用记录。"""
    tool_name: str
    params: Dict[str, Any]
    result: Any = None
    success: bool = True
    error: str = ""


@dataclass
class AgentResult:
    """单个 Agent 的执行结果。"""
    agent_name: str
    content: str = ""                                          # 文本结果
    data: Dict[str, Any] = field(default_factory=dict)        # 结构化数据
    tool_calls: List[ToolCall] = field(default_factory=list)  # 工具调用记录
    success: bool = True
    error: str = ""
    latency_ms: float = 0.0


# ==================== Agent 基类 ====================

class BaseAgent(ABC):
    """所有子 Agent 的抽象基类。"""

    name: str = "base"
    description: str = ""

    def __init__(self, llm, tools: Optional[Dict[str, Callable]] = None):
        """
        Args:
            llm:   LLMProvider 实例
            tools: 可用工具字典 {tool_name: callable}
        """
        self.llm = llm
        self.tools = tools or {}

    @abstractmethod
    def system_prompt(self) -> str:
        """返回该 Agent 的系统提示词。"""
        ...

    @abstractmethod
    async def execute(
        self,
        message: str,
        intent: Intent,
        context: Dict[str, Any],
    ) -> AgentResult:
        """
        执行 Agent 任务。

        Args:
            message: 用户原始消息
            intent:  分类后的意图
            context: 当前上下文（传感器数据、对话历史等）

        Returns:
            AgentResult 包含文本回复和结构化数据
        """
        ...

    def get_tool_descriptions(self) -> List[Dict[str, str]]:
        """返回该 Agent 可用的工具描述列表（用于系统提示词）。"""
        return [
            {"name": name, "description": fn.__doc__ or ""}
            for name, fn in self.tools.items()
        ]

    def call_tool(self, tool_name: str, **kwargs) -> Any:
        """调用指定工具。"""
        if tool_name not in self.tools:
            raise ValueError(f"工具 '{tool_name}' 不可用")
        return self.tools[tool_name](**kwargs)

    def build_messages(self, user_message: str, context: str = "") -> list:
        """构建 LLM 消息列表。"""
        from .llm_provider import LLMMessage
        messages = [LLMMessage(role="system", content=self.system_prompt())]
        if context:
            messages.append(LLMMessage(role="system", content=f"当前上下文：{context}"))
        messages.append(LLMMessage(role="user", content=user_message))
        return messages
