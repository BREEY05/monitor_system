"""
工业环境监控系统 — 多 Agent 协作框架 (v2 增强版)

改进架构概览：
    用户消息
      │
      ▼
┌──────────────────────────────────────────────────┐
│          EnhancedOrchestrator (增强编排器)         │
├──────────────────────────────────────────────────┤
│  ┌──────────┐  ┌──────────┐  ┌───────────────┐   │
│  │ Memory   │  │ Intent   │  │ Plan          │   │
│  │ Manager  │  │Classifier│  │ Generator     │   │
│  │ (记忆)   │  │ (意图)   │  │ (计划+重规划) │   │
│  └────┬─────┘  └────┬─────┘  └──────┬────────┘   │
│       │              │               │             │
│       ▼              ▼               ▼             │
│  ┌─────────────────────────────────────────────┐   │
│  │         DAG Workflow Engine (工作流引擎)      │   │
│  │   条件分支 · 并行执行 · 动态重试 · 质量门控  │   │
│  └────────────────────┬────────────────────────┘   │
│                       │                            │
│    ┌──────┬───────┬───┴───┬────────┬──────────┐    │
│    ▼      ▼       ▼       ▼        ▼          ▼    │
│ ┌──────┐┌────┐┌──────┐┌─────┐┌──────┐┌───────┐   │
│ │Sensor││Know││Search││Alarm││Device││Monitor│   │
│ │Agent ││led ││Agent ││Agent││Agent ││Agent  │   │
│ └──┬───┘└─┬──┘└──┬───┘└──┬──┘└──┬───┘└───┬───┘   │
│    │      │      │       │      │         │        │
│    └──────┴──────┴───────┴──────┴─────────┘        │
│                     │                              │
│     ┌───────────────┼────────────────┐             │
│     ▼               ▼                ▼             │
│ ┌────────┐   ┌───────────┐   ┌───────────┐        │
│ │Blackbd │   │ Evaluator │   │  Result   │        │
│ │(黑板)  │   │ Agent     │   │  Fuser    │        │
│ │共享状态│   │ (自评估)  │   │ (融合)    │        │
│ └────────┘   └───────────┘   └───────────┘        │
└──────────────────────────────────────────────────┘
                     │
     ┌───────────────┼───────────────┐
     ▼               ▼               ▼
┌─────────┐   ┌──────────┐   ┌──────────┐
│ SQLite  │   │  Ollama  │   │Raspberry │
│   DB    │   │   LLM    │   │  Pi 传感器│
└─────────┘   └──────────┘   └──────────┘

快速使用（原架构 API 不变）：
    from agents import create_orchestrator
    orchestrator = create_orchestrator(backend="ollama", model="qwen3.5:0.8b")
    result = await orchestrator.handle_message("当前温度多少？")

快速使用（增强架构）：
    from agents import create_enhanced_orchestrator
    orch = create_enhanced_orchestrator(backend="ollama", model="qwen3.5:0.8b")
    result = await orch.handle_message("当前温度多少？")
    # 支持多轮对话
    result = await orch.handle_message("刚才那个数据正常吗？")
    # 主动监控
    alerts = await orch.run_proactive_check()
"""

from .llm_provider import LLMProvider, LLMMessage, LLMResponse
from .base import (
    BaseAgent, IntentType, Intent, Plan, ToolCall, AgentResult,
)
from .orchestrator import OrchestratorAgent
from .sensor_agent import SensorAgent
from .knowledge_agent import KnowledgeAgent
from .search_agent import SearchAgent
from .alarm_agent import AlarmAgent
from .device_agent import DeviceAgent
from .tools import register_all_tools, TOOL_REGISTRY, TOOL_SCHEMAS

# ---- 增强架构模块 (v2) ----
from .blackboard import Blackboard
from .memory_manager import MemoryManager
from .workflow_engine import WorkflowEngine, WorkflowDefinition, WorkflowNode
from .evaluator_agent import EvaluatorAgent, QuickEvaluator
from .monitor_agent import MonitorAgent, StatisticalDetector
from .enhanced_orchestrator import EnhancedOrchestrator


def create_orchestrator(
    backend: str = "ollama",
    base_url: str = "http://localhost:11434",
    model: str = "qwen3.5:0.8b",
    api_key: str = "",
    temperature: float = 0.2,
    top_p: float = 0.8,
    timeout: int = 120,
) -> OrchestratorAgent:
    """
    创建并初始化多 Agent 编排器（原架构）。

    Args:
        backend:     "ollama" 或 "openai"
        base_url:    LLM 服务地址
        model:       模型名称
        api_key:     API 密钥（云端 API 时需要）
        temperature: 温度参数
        top_p:       top_p 参数
        timeout:     超时时间（秒）

    Returns:
        初始化好的 OrchestratorAgent 实例
    """
    llm = LLMProvider(
        backend=backend,
        base_url=base_url,
        model=model,
        api_key=api_key,
        temperature=temperature,
        top_p=top_p,
        timeout=timeout,
    )
    register_all_tools()
    return OrchestratorAgent(llm)


def create_enhanced_orchestrator(
    backend: str = "ollama",
    base_url: str = "http://localhost:11434",
    model: str = "qwen3.5:0.8b",
    api_key: str = "",
    temperature: float = 0.2,
    top_p: float = 0.8,
    timeout: int = 120,
    enable_memory: bool = True,
    enable_evaluator: bool = True,
    enable_monitor: bool = True,
    max_retries: int = 1,
    quality_threshold: float = 0.5,
) -> EnhancedOrchestrator:
    """
    创建增强型多 Agent 编排器（改进架构 v2）。

    在原架构基础上新增：
    - 对话记忆（多轮上下文感知）
    - DAG 工作流（条件分支、并行、重试）
    - 自评估循环（质量不达标自动重试）
    - 主动监控（周期性异常检测）
    - 黑板通信（Agent 间共享中间结果）

    Args:
        backend:            "ollama" 或 "openai"
        base_url:           LLM 服务地址
        model:              模型名称
        api_key:            API 密钥
        temperature:        温度参数
        top_p:              top_p 参数
        timeout:            超时时间（秒）
        enable_memory:      是否启用对话记忆
        enable_evaluator:   是否启用自评估
        enable_monitor:     是否启用主动监控
        max_retries:        最大重试次数
        quality_threshold:  质量阈值（低于此值触发重试）

    Returns:
        初始化好的 EnhancedOrchestrator 实例
    """
    llm = LLMProvider(
        backend=backend,
        base_url=base_url,
        model=model,
        api_key=api_key,
        temperature=temperature,
        top_p=top_p,
        timeout=timeout,
    )
    register_all_tools()
    return EnhancedOrchestrator(
        llm=llm,
        enable_memory=enable_memory,
        enable_evaluator=enable_evaluator,
        enable_monitor=enable_monitor,
        max_retries=max_retries,
        quality_threshold=quality_threshold,
    )


__all__ = [
    # LLM
    "LLMProvider", "LLMMessage", "LLMResponse",
    # 基础模型
    "BaseAgent", "IntentType", "Intent", "Plan", "ToolCall", "AgentResult",
    # 原架构
    "OrchestratorAgent",
    "SensorAgent", "KnowledgeAgent", "SearchAgent", "AlarmAgent", "DeviceAgent",
    "create_orchestrator",
    # 增强架构 (v2)
    "Blackboard", "MemoryManager",
    "WorkflowEngine", "WorkflowDefinition", "WorkflowNode",
    "EvaluatorAgent", "QuickEvaluator",
    "MonitorAgent", "StatisticalDetector",
    "EnhancedOrchestrator",
    "create_enhanced_orchestrator",
    # 工具
    "register_all_tools", "TOOL_REGISTRY", "TOOL_SCHEMAS",
]
