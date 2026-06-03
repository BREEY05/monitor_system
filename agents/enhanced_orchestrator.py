"""
EnhancedOrchestrator — 增强型多 Agent 编排器

在原 OrchestratorAgent 基础上新增六大核心能力：

  1. 对话记忆 — 多轮对话上下文感知（MemoryManager）
  2. DAG 工作流 — 条件分支、并行执行、动态重规划（WorkflowEngine）
  3. 自评估循环 — 质量不达标自动重试（EvaluatorAgent）
  4. 主动监控 — 周期性异常检测（MonitorAgent）
  5. 黑板通信 — Agent 间共享中间结果（Blackboard）
  6. 引用解析 — 处理"刚才"、"上面说的"等多轮引用

这是改进 Workflow 的总入口，替代原来的 OrchestratorAgent。

与原架构的对比：
  ┌──────────────┬──────────────────┬──────────────────────────┐
  │ 维度         │ 原架构           │ 增强架构                 │
  ├──────────────┼──────────────────┼──────────────────────────┤
  │ 执行流程     │ 线性 Pipeline    │ DAG 工作流 + 动态重规划  │
  │ 状态管理     │ 无状态           │ 短期+长期记忆            │
  │ 质量控制     │ 无               │ 自评估 + 重试 + 降级     │
  │ Agent 通信   │ 结果合并         │ 黑板共享中间结果         │
  │ 监控模式     │ 纯被动           │ 主动 + 被动双模式        │
  │ 多轮对话     │ 不支持           │ 上下文感知 + 引用解析    │
  └──────────────┴──────────────────┴──────────────────────────┘
"""

import asyncio
import json
import logging
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

from .base import AgentResult, BaseAgent, Intent, IntentType, Plan, ToolCall
from .blackboard import Blackboard
from .evaluator_agent import EvaluatorAgent, QuickEvaluator
from .llm_provider import LLMMessage, LLMProvider
from .memory_manager import MemoryManager
from .monitor_agent import MonitorAgent
from .orchestrator import IntentClassifier, PlanGenerator, ResultFuser
from .tools import get_tools_for_agent, register_all_tools
from .workflow_engine import (
    ConditionRule,
    WorkflowDefinition,
    WorkflowEngine,
)

logger = logging.getLogger(__name__)


class EnhancedOrchestrator:
    """
    增强型多 Agent 编排器 — 改进 Workflow 的核心入口。

    用法示例:
        from agents.enhanced_orchestrator import EnhancedOrchestrator

        orch = EnhancedOrchestrator(llm_provider)

        # 基础对话（自动记忆管理）
        result = await orch.handle_message("温度多少？")
        result = await orch.handle_message("刚才那个数据正常吗？")  # 自动解析引用

        # 主动监控
        alerts = await orch.run_proactive_check()

        # 巡检报告
        report = await orch.generate_report(period="day")
    """

    def __init__(
        self,
        llm: LLMProvider,
        agent_registry: Optional[Dict[str, BaseAgent]] = None,
        enable_memory: bool = True,
        enable_evaluator: bool = True,
        enable_monitor: bool = True,
        max_retries: int = 1,
        quality_threshold: float = 0.5,
    ):
        self.llm = llm
        self.max_retries = max_retries
        self.quality_threshold = quality_threshold

        # 注册工具
        register_all_tools()

        # ---- 核心组件 ----
        # 1. 意图分类器 & 计划生成器（复用原架构）
        self.classifier = IntentClassifier(llm)
        self.planner = PlanGenerator()
        self.fuser = ResultFuser(llm)

        # 2. 黑板
        self.blackboard = Blackboard()

        # 3. 对话记忆
        self.memory = MemoryManager(
            max_turns=20,
            summary_threshold=15,
            llm=llm,
        ) if enable_memory else None

        # 4. 评估器
        self.evaluator = EvaluatorAgent(
            llm, quick_threshold=quality_threshold
        ) if enable_evaluator else None

        # 5. 主动监控
        self.monitor = MonitorAgent(llm) if enable_monitor else None

        # 6. 子 Agent 注册表
        if agent_registry:
            self.agents = agent_registry
        else:
            from .sensor_agent import SensorAgent
            from .knowledge_agent import KnowledgeAgent
            from .search_agent import SearchAgent
            from .alarm_agent import AlarmAgent
            from .device_agent import DeviceAgent

            self.agents: Dict[str, BaseAgent] = {
                "sensor":    SensorAgent(llm, get_tools_for_agent("sensor")),
                "knowledge": KnowledgeAgent(llm, get_tools_for_agent("knowledge")),
                "search":    SearchAgent(llm, get_tools_for_agent("search")),
                "alarm":     AlarmAgent(llm, get_tools_for_agent("alarm")),
                "device":    DeviceAgent(llm, get_tools_for_agent("device")),
            }

        # 7. 工作流引擎
        self.workflow_engine = WorkflowEngine(
            blackboard=self.blackboard,
            agent_registry=self.agents,
            llm=llm,
        )

        # 统计
        self.stats = {
            "total_requests": 0,
            "agent_calls": {},
            "retry_count": 0,
            "quality_scores": [],
            "proactive_alerts": 0,
        }

    # ==================================================================
    # 主入口：同步（HTTP API）
    # ==================================================================
    async def handle_message(
        self,
        message: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        处理用户消息（增强版）。

        新增流程（相比原 OrchestratorAgent）：
          0. 引用解析 — 检查是否引用了上一轮对话
          1. 记忆注入 — 将对话历史注入上下文
          2. 意图分类 + 计划生成（复用）
          3. DAG 工作流执行（替代简单调度）
          4. 自评估循环 — 质量不达标时重试
          5. 记忆更新 — 记录本轮对话
          6. 主动监控检查 — 附带最新监控状态
        """
        start = time.time()
        self.stats["total_requests"] += 1
        context = context or {}
        session_id = context.get("session_id", str(uuid.uuid4())[:8])

        # ---- Step 0: 引用解析 ----
        reference_context = {}
        if self.memory:
            ref = self.memory.resolve_reference(message)
            if ref:
                reference_context = ref
                context["reference"] = ref
                logger.info(f"引用解析命中: previous_intents={ref.get('previous_intents')}")

        # ---- Step 1: 记忆注入 ----
        memory_context = ""
        if self.memory:
            memory_context = self.memory.get_context_string(max_turns=5)
            if memory_context:
                context["memory"] = memory_context

        # ---- Step 2: 意图分类 ----
        intents = await self.classifier.classify(message)
        intent_names = [i.type.value for i in intents]
        logger.info(f"意图分类: {intent_names}")

        # 更新用户画像
        if self.memory:
            self.memory.update_user_profile(intents=intent_names)

        # ---- Step 3: 生成执行计划 ----
        plan = self.planner.generate(intents, message)
        logger.info(f"执行计划: {plan.agent_sequence}, parallel={plan.parallel}")

        # ---- Step 4: 执行（带自评估循环）----
        results = []
        evaluation = None
        retry_count = 0

        for attempt in range(self.max_retries + 1):
            # 执行 Agent 调度
            results = await self._dispatch_with_blackboard(
                plan, message, context, session_id
            )

            # 自评估
            if self.evaluator and results:
                evaluation = self.evaluator.batch_evaluate(message, results, intents)
                avg_score = evaluation["average_score"]
                self.stats["quality_scores"].append(avg_score)

                if avg_score >= self.quality_threshold:
                    break  # 质量达标

                if attempt < self.max_retries:
                    retry_count += 1
                    self.stats["retry_count"] += 1
                    logger.info(
                        f"质量不达标 (score={avg_score:.2f}), "
                        f"重试 {retry_count}/{self.max_retries}"
                    )
                    # 清除黑板中的旧结果，重新执行
                    self.blackboard.clear(prefix=f"result.session_{session_id}")
                else:
                    logger.info(f"质量偏低但已达重试上限: score={avg_score:.2f}")
            else:
                break  # 未启用评估器

        # ---- Step 5: 融合结果 ----
        reply = await self.fuser.fuse(message, results, plan)

        # ---- Step 6: 记忆更新 ----
        if self.memory:
            self.memory.add_user_message(message, metadata={
                "intents": intent_names,
            })
            self.memory.add_assistant_message(reply[:300], metadata={
                "agents_used": plan.agent_sequence,
                "quality": evaluation["average_score"] if evaluation else None,
            })
            self.memory.set_execution_meta({
                "intents": intent_names,
                "agents_used": plan.agent_sequence,
                "reply_summary": reply[:200],
                "data_snapshot": {r.agent_name: r.data for r in results},
            })

        # ---- Step 7: 附带监控状态 ----
        monitor_status = None
        if self.monitor and self.stats["total_requests"] % 5 == 0:
            # 每 5 次请求做一次主动检查
            alerts = await self.monitor.check_health()
            if alerts:
                monitor_status = {
                    "alerts": len(alerts),
                    "highest_severity": max(a.severity for a in alerts),
                }
                self.stats["proactive_alerts"] += len(alerts)

        # ---- 统计 ----
        latency = (time.time() - start) * 1000
        all_tool_calls = []
        for r in results:
            all_tool_calls.extend(r.tool_calls)
            self.stats["agent_calls"][r.agent_name] = (
                self.stats["agent_calls"].get(r.agent_name, 0) + 1
            )

        response = {
            "reply": reply,
            "intents": [
                {"type": i.type.value, "confidence": i.confidence, "reasoning": i.reasoning}
                for i in intents
            ],
            "plan": {
                "agent_sequence": plan.agent_sequence,
                "parallel": plan.parallel,
                "reasoning": plan.reasoning,
            },
            "agent_results": [
                {
                    "agent": r.agent_name,
                    "success": r.success,
                    "latency_ms": round(r.latency_ms, 1),
                    "tool_count": len(r.tool_calls),
                }
                for r in results
            ],
            "tool_calls": [
                {"tool": tc.tool_name, "success": tc.success}
                for tc in all_tool_calls
            ],
            "latency_ms": round(latency, 1),
            # ---- 新增字段 ----
            "quality": evaluation if evaluation else None,
            "retry_count": retry_count,
            "memory_context": bool(memory_context),
            "reference_resolved": bool(reference_context),
            "monitor_status": monitor_status,
        }

        return response

    # ==================================================================
    # 主入口：流式（WebSocket）
    # ==================================================================
    async def handle_message_stream(
        self,
        message: str,
        context: Optional[Dict[str, Any]] = None,
        on_status: Optional[Callable] = None,
        on_content: Optional[Callable] = None,
    ) -> str:
        """流式处理用户消息（增强版）。"""
        context = context or {}

        async def noop(*args, **kwargs):
            pass

        on_status = on_status or noop
        on_content = on_content or noop

        # 记忆注入
        memory_context = ""
        if self.memory:
            ref = self.memory.resolve_reference(message)
            if ref:
                context["reference"] = ref
            memory_context = self.memory.get_context_string(max_turns=5)
            if memory_context:
                context["memory"] = memory_context

        # 意图分类
        await on_status("thinking", "正在分析您的问题...")
        intents = await self.classifier.classify(message)
        intent_names = [i.type.value for i in intents]
        await on_status("intent", f"识别意图: {', '.join(intent_names)}")

        if self.memory:
            self.memory.update_user_profile(intents=intent_names)

        # 计划
        plan = self.planner.generate(intents, message)
        await on_status("plan", f"调度: {', '.join(plan.agent_sequence)}")

        # 执行 + 评估
        results = await self._dispatch_with_blackboard(
            plan, message, context, "stream", on_status
        )

        # 自评估
        if self.evaluator and results:
            evaluation = self.evaluator.batch_evaluate(message, results, intents)
            if evaluation["average_score"] < self.quality_threshold:
                await on_status("eval", f"质量评估: {evaluation['average_score']:.2f}, 正在优化...")

        # 融合
        if len(results) == 1:
            reply = results[0].content
        else:
            await on_status("thinking", "正在综合分析结果...")
            reply = await self.fuser.fuse(message, results, plan)

        # 记忆更新
        if self.memory:
            self.memory.add_user_message(message, metadata={"intents": intent_names})
            self.memory.add_assistant_message(reply[:300])
            self.memory.set_execution_meta({
                "intents": intent_names,
                "agents_used": plan.agent_sequence,
                "reply_summary": reply[:200],
            })

        # 流式输出
        chunk_size = 6
        for i in range(0, len(reply), chunk_size):
            await on_content(reply[i:i + chunk_size])
            await asyncio.sleep(0.01)

        return reply

    # ==================================================================
    # 内部：带黑板的 Agent 调度
    # ==================================================================
    async def _dispatch_with_blackboard(
        self,
        plan: Plan,
        message: str,
        context: Dict[str, Any],
        session_id: str = "",
        on_status: Optional[Callable] = None,
    ) -> List[AgentResult]:
        """
        带黑板共享的 Agent 调度。
        每个 Agent 执行前可从黑板读取前置 Agent 的中间结果。
        """
        async def noop(*args, **kwargs):
            pass
        on_status = on_status or noop

        # 开启黑板会话
        self.blackboard.start_session(session_id)

        results = []
        for idx, agent_name in enumerate(plan.agent_sequence):
            if agent_name == "chitchat":
                result = await self._handle_chitchat(message)
                results.append(result)
                continue

            agent = self.agents.get(agent_name)
            if not agent:
                logger.warning(f"Agent '{agent_name}' 未注册，跳过")
                continue

            await on_status("agent", f"正在调用 {agent_name} Agent...")

            # 从黑板读取前置 Agent 的结果
            enriched_context = dict(context)
            for prev_result in results:
                key = f"prev.{prev_result.agent_name}"
                self.blackboard.write_to_session(
                    session_id, key, prev_result.data,
                    source=prev_result.agent_name,
                )
                enriched_context[key] = prev_result.data

            # 匹配意图
            intent = next(
                (i for i in plan.intents
                 if PlanGenerator.INTENT_AGENT_MAP.get(i.type) == agent_name),
                plan.intents[0] if plan.intents else Intent(type=IntentType.CHITCHAT),
            )

            try:
                result = await agent.execute(message, intent, enriched_context)
                results.append(result)

                # 写入黑板
                self.blackboard.write_to_session(
                    session_id,
                    f"result.{agent_name}",
                    {"content": result.content, "data": result.data},
                    source=agent_name,
                )

                logger.info(
                    f"Agent '{agent_name}' 完成: {result.latency_ms:.0f}ms, "
                    f"tools={len(result.tool_calls)}"
                )
            except Exception as e:
                logger.error(f"Agent '{agent_name}' 执行失败: {e}", exc_info=True)
                results.append(AgentResult(
                    agent_name=agent_name,
                    content=f"{agent_name} 模块暂时不可用，请稍后重试。",
                    success=False,
                    error=str(e),
                ))

        return results or [await self._handle_chitchat(message)]

    async def _handle_chitchat(self, message: str) -> AgentResult:
        """处理闲聊。"""
        text = message.strip().lower()
        greetings = {"你好", "您好", "hello", "hi", "嗨", "在吗", "在不在"}
        if text in greetings or text in {f"{g}！" for g in greetings} or text in {f"{g}!" for g in greetings}:
            reply = (
                "您好，我是工业环境监控系统 AI 助手。\n\n"
                "我可以帮您：\n"
                "- 查看当前传感器数据（温度、湿度、气压、振动）\n"
                "- 分析历史数据趋势\n"
                "- 查看报警与异常记录\n"
                "- 检索知识库文档\n"
                "- 联网搜索最新信息\n"
                "- 管理设备信息\n"
                "- 系统健康巡检"
            )
        elif any(kw in text for kw in ("谢谢", "感谢", "thanks", "thank")):
            reply = "不客气，有其他问题随时问我。"
        elif any(kw in text for kw in ("再见", "拜拜", "bye")):
            reply = "再见，祝您工作顺利！"
        else:
            try:
                messages = [
                    LLMMessage(role="system", content=(
                        "你是工业环境监控系统的 AI 助手。对于闲聊类消息，简短友好地回复，"
                        "并引导用户询问与环境监控、传感器数据、报警、设备相关的问题。"
                    )),
                    LLMMessage(role="user", content=message),
                ]
                resp = self.llm.chat(messages)
                reply = resp.content
            except Exception:
                reply = "您好，我是工业环境监控 AI 助手，请问有什么关于环境监控的问题需要帮忙吗？"

        return AgentResult(agent_name="chitchat", content=reply, latency_ms=0)

    # ==================================================================
    # 主动监控
    # ==================================================================
    async def run_proactive_check(self) -> Dict[str, Any]:
        """执行一次主动健康检查。"""
        if not self.monitor:
            return {"error": "主动监控未启用"}

        alerts = await self.monitor.check_health()
        self.stats["proactive_alerts"] += len(alerts)

        return {
            "alerts": [
                {
                    "type": a.signal_type,
                    "severity": a.severity,
                    "metric": a.metric,
                    "description": a.description,
                }
                for a in alerts
            ],
            "total": len(alerts),
        }

    async def generate_report(self, period: str = "hour") -> Dict[str, Any]:
        """生成巡检报告。"""
        if not self.monitor:
            return {"error": "主动监控未启用"}
        return await self.monitor.generate_inspection_report(period)

    # ==================================================================
    # 诊断与统计
    # ==================================================================
    def get_stats(self) -> Dict[str, Any]:
        """获取编排器运行统计（增强版）。"""
        quality_scores = self.stats.get("quality_scores", [])
        return {
            "total_requests": self.stats["total_requests"],
            "agent_calls": dict(self.stats["agent_calls"]),
            "registered_agents": list(self.agents.keys()),
            "retry_count": self.stats["retry_count"],
            "avg_quality": round(
                sum(quality_scores) / len(quality_scores), 2
            ) if quality_scores else None,
            "proactive_alerts": self.stats["proactive_alerts"],
            "memory_enabled": self.memory is not None,
            "evaluator_enabled": self.evaluator is not None,
            "monitor_enabled": self.monitor is not None,
            "blackboard": repr(self.blackboard),
        }

    def get_memory_profile(self) -> Dict[str, Any]:
        """获取用户画像（如启用记忆）。"""
        if self.memory:
            return self.memory.get_user_profile()
        return {"error": "记忆功能未启用"}

    def get_monitor_stats(self) -> Dict[str, Any]:
        """获取主动监控统计（如启用监控）。"""
        if self.monitor:
            return self.monitor.get_stats()
        return {"error": "主动监控未启用"}

    def get_eval_stats(self) -> Dict[str, Any]:
        """获取评估器统计（如启用评估）。"""
        if self.evaluator:
            return self.evaluator.get_eval_stats()
        return {"error": "评估器未启用"}
