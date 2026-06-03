"""
Orchestrator — 多 Agent 协作编排器

核心组件，负责：
1. 意图分类（基于 LLM 的零样本分类）
2. 执行计划生成（单 Agent 调度 / 多 Agent 并行协作）
3. 子 Agent 调度与结果融合
4. 流式输出管理

这是论文的核心创新点所在。
"""

import asyncio
import json
import logging
import time
from typing import Any, Callable, Dict, List, Optional

from .base import AgentResult, BaseAgent, Intent, IntentType, Plan, ToolCall
from .llm_provider import LLMMessage, LLMProvider
from .tools import get_tools_for_agent, register_all_tools

logger = logging.getLogger(__name__)


# ==================== 意图分类 Prompt ====================

INTENT_CLASSIFICATION_PROMPT = """你是一个意图分类器。分析用户的消息，判断其意图类型。

可选意图类型：
- sensor_query:   查询实时传感器数据（温度、湿度、气压、振动、当前数据、现在多少度）
- history_query:  查询历史数据趋势（历史、趋势、变化、最近一周/一天、过去）
- alarm_query:    查询报警与异常（报警、告警、异常、故障、报警记录）
- alarm_handle:   处理/确认报警（处理报警、确认、标记已处理）
- knowledge:      知识库/文档检索（资料、文档、知识库、手册、规范、制度、说明书）
- search:         联网搜索（搜索、联网、网上查、最新新闻、今天、latest）
- device_manage:  设备管理（设备列表、有哪些设备、设备位置、3D模型、地图）
- system_config:  系统配置（阈值设置、修改配置、模型切换、飞书配置）
- chitchat:       闲聊/问候（你好、hello、谢谢、再见、在吗）
- complex:        复杂多步任务（同时涉及多个意图，如"查报警并分析趋势"）

输出 JSON 格式（只输出 JSON，不要其他文字）：
```json
{
    "intents": [
        {"type": "意图类型", "confidence": 0.0-1.0, "reasoning": "判断依据"}
    ],
    "needs_multiple_agents": true/false,
    "explanation": "整体分析说明"
}
```

注意：
- 可以有多个意图，按置信度降序排列
- "查报警并看趋势" → [alarm_query, history_query], needs_multiple_agents=true
- "温度多少" → [sensor_query]
- "知识库中关于安全的文档" → [knowledge]（不要误判为 search）"""


# ==================== 意图分类器 ====================

class IntentClassifier:
    """基于 LLM 的意图分类器。"""

    def __init__(self, llm: LLMProvider):
        self.llm = llm
        # 关键词快速分类表（用于小模型降级场景）
        self._keyword_map = {
            IntentType.ALARM_QUERY:   ["报警", "告警", "异常", "故障", "危险", "超标", "预警"],
            IntentType.ALARM_HANDLE:  ["处理报警", "确认报警", "标记", "已处理", "消除报警"],
            IntentType.SENSOR_QUERY:  ["温度", "湿度", "气压", "振动", "当前", "现在", "实时", "传感器", "读数", "多少度"],
            IntentType.HISTORY_QUERY: ["历史", "趋势", "变化", "过去", "一周", "一天", "hour", "day", "week", "trend"],
            IntentType.KNOWLEDGE:     ["资料", "文档", "知识库", "手册", "规范", "制度", "说明书", "检索"],
            IntentType.SEARCH:        ["搜索", "联网", "网上", "新闻", "最新", "search", "online", "web"],
            IntentType.DEVICE_MANAGE: ["设备", "列表", "位置", "地图", "3D", "模型", "注册"],
            IntentType.SYSTEM_CONFIG: ["阈值", "配置", "设置", "修改", "切换模型"],
            IntentType.CHITCHAT:      ["你好", "您好", "hello", "hi", "嗨", "谢谢", "再见", "在吗", "在不在"],
        }

    def classify_fast(self, message: str) -> List[Intent]:
        """基于关键词的快速意图分类（不依赖 LLM）。"""
        text = message.lower()
        scores: Dict[IntentType, float] = {}
        for intent_type, keywords in self._keyword_map.items():
            hits = 0
            for kw in keywords:
                if kw in text:
                    # 多字关键词权重更高（"报警" > "最近"）
                    hits += 1.5 if len(kw) >= 2 else 1.0
            if hits > 0:
                scores[intent_type] = min(hits * 0.25 + 0.3, 1.0)
        if not scores:
            return [Intent(type=IntentType.CHITCHAT, confidence=0.5, reasoning="未匹配关键词")]
        sorted_intents = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [
            Intent(type=it, confidence=sc, reasoning="关键词匹配")
            for it, sc in sorted_intents[:3]
        ]

    async def classify(self, message: str) -> List[Intent]:
        """基于 LLM 的意图分类。"""
        messages = [
            LLMMessage(role="system", content=INTENT_CLASSIFICATION_PROMPT),
            LLMMessage(role="user", content=f"用户消息：{message}"),
        ]
        try:
            result = self.llm.chat_json(messages)
            if not result or "intents" not in result:
                return self.classify_fast(message)

            intents = []
            for item in result["intents"]:
                try:
                    it = IntentType(item["type"])
                except ValueError:
                    continue
                intents.append(Intent(
                    type=it,
                    confidence=item.get("confidence", 0.8),
                    reasoning=item.get("reasoning", ""),
                ))
            return intents or self.classify_fast(message)

        except Exception as e:
            logger.warning(f"LLM 意图分类失败，降级为关键词分类: {e}")
            return self.classify_fast(message)


# ==================== 计划生成器 ====================

class PlanGenerator:
    """根据意图分类结果生成执行计划。"""

    # 意图 → Agent 名称映射
    INTENT_AGENT_MAP = {
        IntentType.SENSOR_QUERY:  "sensor",
        IntentType.HISTORY_QUERY: "sensor",
        IntentType.ALARM_QUERY:   "alarm",
        IntentType.ALARM_HANDLE:  "alarm",
        IntentType.KNOWLEDGE:     "knowledge",
        IntentType.SEARCH:        "search",
        IntentType.DEVICE_MANAGE: "device",
        IntentType.SYSTEM_CONFIG: "sensor",     # 配置类由通用 Agent 处理
        IntentType.CHITCHAT:      "chitchat",
        IntentType.COMPLEX:       "complex",
    }

    def generate(self, intents: List[Intent], message: str) -> Plan:
        """生成执行计划。"""
        if not intents:
            return Plan(
                intents=[], agent_sequence=["chitchat"], parallel=False,
                reasoning="无意图，默认闲聊"
            )

        # 单意图
        if len(intents) == 1 and intents[0].type != IntentType.COMPLEX:
            agent = self.INTENT_AGENT_MAP.get(intents[0].type, "sensor")
            return Plan(
                intents=intents,
                agent_sequence=[agent],
                parallel=False,
                reasoning=f"单意图 {intents[0].type.value} → {agent}",
            )

        # 多意图 / 复杂任务
        agents = []
        for intent in intents:
            if intent.confidence < 0.3:
                continue
            agent = self.INTENT_AGENT_MAP.get(intent.type, "")
            if agent and agent not in agents and agent != "chitchat":
                agents.append(agent)

        if not agents:
            agents = ["sensor"]

        # 判断是否可并行（互不依赖的 Agent 可以并行）
        parallel = len(agents) >= 2

        return Plan(
            intents=intents,
            agent_sequence=agents,
            parallel=parallel,
            reasoning=f"多意图协作: {', '.join(agents)}",
        )


# ==================== 结果融合器 ====================

class ResultFuser:
    """将多个 Agent 的结果融合为统一回复。"""

    def __init__(self, llm: LLMProvider):
        self.llm = llm

    async def fuse(
        self, message: str, results: List[AgentResult], plan: Plan
    ) -> str:
        """融合多个 Agent 的结果。"""
        if len(results) == 1:
            return results[0].content

        # 多 Agent 结果：用 LLM 融合
        result_texts = []
        for r in results:
            if r.content:
                result_texts.append(f"[{r.agent_name} Agent 的分析结果]\n{r.content}")

        combined = "\n\n".join(result_texts)

        fuse_prompt = f"""你是工业环境监控系统的 AI 助手。

以下多个专业分析模块分别给出了分析结果，请你综合这些信息，给用户一个统一、简洁、专业的回复。

用户问题：{message}

{combined}

输出规则：
- 综合各模块信息，不要分别罗列每个模块的回答
- 如果有矛盾信息，优先信任数据查询结果
- 简洁专业，用中文回复
- 不要提及"多个模块"、"Agent"等内部概念"""

        messages = [LLMMessage(role="system", content=fuse_prompt)]
        try:
            resp = self.llm.chat(messages, temperature=0.3)
            return resp.content
        except Exception as e:
            logger.error(f"结果融合 LLM 调用失败: {e}")
            # 降级：直接拼接
            parts = []
            for r in results:
                if r.content:
                    parts.append(r.content)
            return "\n\n---\n\n".join(parts)


# ==================== 编排器 ====================

class OrchestratorAgent:
    """多 Agent 协作编排器 — 系统的入口 Agent。"""

    def __init__(self, llm: LLMProvider, agent_registry: Optional[Dict[str, BaseAgent]] = None):
        self.llm = llm
        self.classifier = IntentClassifier(llm)
        self.planner = PlanGenerator()
        self.fuser = ResultFuser(llm)

        # 注册工具
        register_all_tools()

        # 初始化子 Agent
        if agent_registry:
            self.agents = agent_registry
        else:
            from .sensor_agent import SensorAgent
            from .knowledge_agent import KnowledgeAgent
            from .search_agent import SearchAgent
            from .alarm_agent import AlarmAgent
            from .device_agent import DeviceAgent

            self.agents: Dict[str, BaseAgent] = {
                "sensor":   SensorAgent(llm, get_tools_for_agent("sensor")),
                "knowledge": KnowledgeAgent(llm, get_tools_for_agent("knowledge")),
                "search":   SearchAgent(llm, get_tools_for_agent("search")),
                "alarm":    AlarmAgent(llm, get_tools_for_agent("alarm")),
                "device":   DeviceAgent(llm, get_tools_for_agent("device")),
            }

        # 执行统计
        self.stats = {"total_requests": 0, "agent_calls": {}, "avg_latency_ms": 0}

    # ------------------------------------------------------------------
    # 主入口：同步（用于 HTTP API）
    # ------------------------------------------------------------------
    async def handle_message(
        self,
        message: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        处理用户消息，返回结构化结果。

        Returns:
            {
                "reply": "最终回复文本",
                "intents": [...],
                "plan": {...},
                "agent_results": [...],
                "latency_ms": 总延迟,
                "tool_calls": [...],
            }
        """
        start = time.time()
        self.stats["total_requests"] += 1
        context = context or {}

        # 1. 意图分类
        intents = await self.classifier.classify(message)
        logger.info(f"意图分类: {[i.type.value for i in intents]}")

        # 2. 生成执行计划
        plan = self.planner.generate(intents, message)
        logger.info(f"执行计划: agents={plan.agent_sequence}, parallel={plan.parallel}")

        # 3. 调度子 Agent
        results = await self._dispatch(plan, message, context)

        # 4. 融合结果
        reply = await self.fuser.fuse(message, results, plan)

        # 5. 统计
        latency = (time.time() - start) * 1000
        all_tool_calls = []
        for r in results:
            all_tool_calls.extend(r.tool_calls)
            self.stats["agent_calls"][r.agent_name] = (
                self.stats["agent_calls"].get(r.agent_name, 0) + 1
            )

        return {
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
        }

    # ------------------------------------------------------------------
    # 主入口：流式（用于 WebSocket）
    # ------------------------------------------------------------------
    async def handle_message_stream(
        self,
        message: str,
        context: Optional[Dict[str, Any]] = None,
        on_status: Optional[Callable] = None,
        on_content: Optional[Callable] = None,
    ) -> str:
        """
        流式处理用户消息。通过回调函数输出中间状态和最终内容。

        Args:
            on_status:  async fn(status_type, data) — 状态更新
            on_content: async fn(text_chunk)         — 流式文本输出
        """
        context = context or {}

        async def noop(*args, **kwargs):
            pass

        on_status = on_status or noop
        on_content = on_content or noop

        # 1. 意图分类
        await on_status("thinking", "正在分析您的问题...")
        intents = await self.classifier.classify(message)
        intent_names = [i.type.value for i in intents]
        await on_status("intent", f"识别意图: {', '.join(intent_names)}")

        # 2. 生成计划
        plan = self.planner.generate(intents, message)
        await on_status("plan", f"调度: {', '.join(plan.agent_sequence)}")

        # 3. 调度 Agent
        results = await self._dispatch(plan, message, context, on_status)

        # 4. 融合
        if len(results) == 1:
            reply = results[0].content
        else:
            await on_status("thinking", "正在综合分析结果...")
            reply = await self.fuser.fuse(message, results, plan)

        # 5. 流式输出
        chunk_size = 6
        for i in range(0, len(reply), chunk_size):
            await on_content(reply[i:i + chunk_size])
            await asyncio.sleep(0.01)

        return reply

    # ------------------------------------------------------------------
    # 内部：Agent 调度
    # ------------------------------------------------------------------
    async def _dispatch(
        self,
        plan: Plan,
        message: str,
        context: Dict[str, Any],
        on_status: Optional[Callable] = None,
    ) -> List[AgentResult]:
        """根据计划调度子 Agent 执行。"""

        async def noop(*args, **kwargs):
            pass

        on_status = on_status or noop

        results = []
        for agent_name in plan.agent_sequence:
            if agent_name == "chitchat":
                # 闲聊直接处理，不调度子 Agent
                results.append(await self._handle_chitchat(message))
                continue

            agent = self.agents.get(agent_name)
            if not agent:
                logger.warning(f"Agent '{agent_name}' 未注册，跳过")
                continue

            await on_status("agent", f"正在调用 {agent_name} Agent...")

            # 找到对应的意图
            intent = next(
                (i for i in plan.intents
                 if PlanGenerator.INTENT_AGENT_MAP.get(i.type) == agent_name),
                plan.intents[0] if plan.intents else Intent(type=IntentType.CHITCHAT),
            )

            try:
                result = await agent.execute(message, intent, context)
                results.append(result)
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
        """处理闲聊类消息。"""
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
                "- 管理设备信息"
            )
        elif any(kw in text for kw in ("谢谢", "感谢", "thanks", "thank")):
            reply = "不客气，有其他问题随时问我。"
        elif any(kw in text for kw in ("再见", "拜拜", "bye")):
            reply = "再见，祝您工作顺利！"
        else:
            # 通用闲聊：用 LLM 回复
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

        return AgentResult(
            agent_name="chitchat",
            content=reply,
            latency_ms=0,
        )

    # ------------------------------------------------------------------
    # 统计与诊断
    # ------------------------------------------------------------------
    def get_stats(self) -> Dict[str, Any]:
        """返回编排器运行统计。"""
        return {
            "total_requests": self.stats["total_requests"],
            "agent_calls": dict(self.stats["agent_calls"]),
            "registered_agents": list(self.agents.keys()),
        }
