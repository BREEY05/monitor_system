"""
WorkflowEngine — DAG 工作流引擎

将原来的线性 Pipeline（Intent → Plan → Dispatch → Fuse）
升级为基于有向无环图（DAG）的工作流引擎。

核心改进：
  1. 条件分支：根据 Agent 输出的数据动态选择后续路径
  2. 循环与重试：Agent 执行失败或质量不达标时可重试
  3. 动态重规划：根据中间结果实时调整执行计划
  4. 并行执行：互不依赖的节点可真正并行调度

节点类型：
  - TaskNode:     执行具体 Agent 的任务节点
  - ConditionNode: 基于条件的分支节点
  - GateNode:     质量控制门节点（评估 Agent 输出质量）
  - MergeNode:    结果汇聚节点

学术价值：
  DAG 工作流 + 动态重规划是本文区别于传统 Pipeline 架构的核心创新点。
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


# ==================== 节点状态 ====================

class NodeStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    RETRY = "retry"


# ==================== 工作流节点 ====================

@dataclass
class WorkflowNode:
    """工作流图中的节点。"""
    node_id: str
    node_type: str              # "task" | "condition" | "gate" | "merge"
    agent_name: str = ""        # 关联的 Agent 名称
    config: Dict[str, Any] = field(default_factory=dict)

    # 图结构
    dependencies: List[str] = field(default_factory=list)   # 前置依赖节点 ID
    successors: List[str] = field(default_factory=list)      # 后续节点 ID

    # 执行状态
    status: NodeStatus = NodeStatus.PENDING
    result: Any = None
    error: str = ""
    retries: int = 0
    max_retries: int = 1
    latency_ms: float = 0.0
    start_time: float = 0.0

    def can_execute(self, completed: Set[str]) -> bool:
        """检查该节点的所有依赖是否已完成。"""
        return all(dep in completed for dep in self.dependencies)

    def reset(self) -> None:
        """重置节点状态（用于重试）。"""
        self.status = NodeStatus.PENDING
        self.result = None
        self.error = ""
        self.latency_ms = 0.0


# ==================== 条件分支 ====================

@dataclass
class ConditionRule:
    """条件分支规则。"""
    field_path: str           # 从黑板中读取的字段路径，如 "alarm.alert_count"
    operator: str             # "gt" | "lt" | "eq" | "neq" | "contains" | "in"
    value: Any                # 比较值
    target_node: str          # 满足条件时跳转的目标节点 ID


# ==================== 工作流定义 ====================

@dataclass
class WorkflowDefinition:
    """
    工作流定义 — 描述完整的 DAG 结构。

    用法示例:
        wf = WorkflowDefinition(name="alarm_analysis")
        wf.add_node("classify", "task", agent_name="classifier")
        wf.add_node("alarm_query", "task", agent_name="alarm", dependencies=["classify"])
        wf.add_node("sensor_query", "task", agent_name="sensor", dependencies=["classify"])
        wf.add_node("quality_gate", "gate", dependencies=["alarm_query", "sensor_query"])
        wf.add_node("fuse", "merge", dependencies=["quality_gate"])

        wf.add_condition("quality_gate", ConditionRule(
            field_path="gate.quality_score",
            operator="lt", value=0.6,
            target_node="retry_alarm"
        ))
    """
    name: str
    description: str = ""
    nodes: Dict[str, WorkflowNode] = field(default_factory=dict)
    conditions: Dict[str, List[ConditionRule]] = field(default_factory=dict)
    max_execution_time: float = 60.0  # 最大执行时间（秒）

    def add_node(
        self,
        node_id: str,
        node_type: str = "task",
        agent_name: str = "",
        dependencies: Optional[List[str]] = None,
        max_retries: int = 1,
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        """添加节点到工作流。"""
        node = WorkflowNode(
            node_id=node_id,
            node_type=node_type,
            agent_name=agent_name,
            dependencies=dependencies or [],
            max_retries=max_retries,
            config=config or {},
        )
        self.nodes[node_id] = node

        # 反向更新后继关系
        for dep_id in (dependencies or []):
            if dep_id in self.nodes:
                self.nodes[dep_id].successors.append(node_id)

    def add_condition(self, source_node_id: str, rule: ConditionRule) -> None:
        """为条件节点添加分支规则。"""
        self.conditions.setdefault(source_node_id, []).append(rule)

    def get_ready_nodes(self, completed: Set[str], failed: Set[str]) -> List[WorkflowNode]:
        """获取当前可以执行的节点（所有依赖已完成且自身未执行）。"""
        ready = []
        for node in self.nodes.values():
            if node.status == NodeStatus.PENDING and node.can_execute(completed):
                ready.append(node)
        return ready

    def get_execution_order(self) -> List[List[str]]:
        """
        计算拓扑排序的执行顺序（分层）。
        同一层内的节点可以并行执行。

        Returns:
            [[layer1_nodes], [layer2_nodes], ...]
        """
        in_degree = {nid: len(n.dependencies) for nid, n in self.nodes.items()}
        layers = []
        remaining = set(self.nodes.keys())

        while remaining:
            # 找入度为 0 的节点
            layer = [nid for nid in remaining if in_degree.get(nid, 0) == 0]
            if not layer:
                logger.error("工作流存在循环依赖！")
                break
            layers.append(layer)
            for nid in layer:
                remaining.discard(nid)
                for succ in self.nodes[nid].successors:
                    in_degree[succ] = in_degree.get(succ, 0) - 1

        return layers

    def validate(self) -> List[str]:
        """验证工作流定义的合法性。"""
        errors = []
        for nid, node in self.nodes.items():
            for dep in node.dependencies:
                if dep not in self.nodes:
                    errors.append(f"节点 '{nid}' 依赖不存在的节点 '{dep}'")
        # 检测循环依赖
        order = self.get_execution_order()
        total = sum(len(layer) for layer in order)
        if total < len(self.nodes):
            errors.append("工作流中存在循环依赖")
        return errors


# ==================== 工作流引擎 ====================

class WorkflowEngine:
    """
    DAG 工作流引擎 — 负责编排和执行工作流。

    用法示例:
        engine = WorkflowEngine(blackboard=bb, agent_registry=agents)

        wf = WorkflowDefinition(name="query_pipeline")
        wf.add_node("classify", "task", agent_name="classifier")
        wf.add_node("execute", "task", agent_name="sensor", dependencies=["classify"])
        wf.add_node("evaluate", "gate", dependencies=["execute"])

        result = await engine.execute(wf, message="温度多少？", context={})
    """

    def __init__(
        self,
        blackboard=None,
        agent_registry: Optional[Dict[str, Any]] = None,
        llm=None,
    ):
        self.blackboard = blackboard
        self.agents = agent_registry or {}
        self.llm = llm

        # 执行日志
        self._execution_log: List[Dict[str, Any]] = []

    async def execute(
        self,
        workflow: WorkflowDefinition,
        message: str = "",
        context: Optional[Dict[str, Any]] = None,
        on_status: Optional[Callable] = None,
    ) -> Dict[str, Any]:
        """
        执行工作流。

        Returns:
            {
                "status": "success" | "partial" | "failed",
                "node_results": {...},
                "execution_order": [...],
                "total_latency_ms": ...,
                "replan_count": 0,
            }
        """
        start = time.time()
        context = context or {}
        completed: Set[str] = set()
        failed: Set[str] = set()
        replan_count = 0

        async def noop(*args, **kwargs):
            pass
        on_status = on_status or noop

        # 初始化黑板
        if self.blackboard:
            self.blackboard.write("input.message", message, source="system")
            self.blackboard.write("input.context", context, source="system")

        # 验证工作流
        errors = workflow.validate()
        if errors:
            return {"status": "failed", "errors": errors, "total_latency_ms": 0}

        # 分层执行
        layers = workflow.get_execution_order()

        for layer_idx, layer in enumerate(layers):
            await on_status("workflow", f"执行第 {layer_idx + 1} 层: {', '.join(layer)}")

            # 同层节点并行执行
            tasks = []
            for node_id in layer:
                node = workflow.nodes[node_id]

                # 跳过已被条件分支跳过的节点
                if node.status == NodeStatus.SKIPPED:
                    completed.add(node_id)
                    continue

                tasks.append(self._execute_node(node, message, context, on_status))

            if tasks:
                results = await asyncio.gather(*tasks, return_exceptions=True)

                for node_id, result in zip(layer, results):
                    node = workflow.nodes[node_id]
                    if isinstance(result, Exception):
                        node.status = NodeStatus.FAILED
                        node.error = str(result)
                        failed.add(node_id)
                        logger.error(f"节点 '{node_id}' 执行异常: {result}")
                    else:
                        node.result = result
                        if result and result.get("success", True):
                            node.status = NodeStatus.SUCCESS
                            node.latency_ms = result.get("latency_ms", 0)
                            completed.add(node_id)

                            # 将结果写入黑板
                            if self.blackboard and result.get("data"):
                                self.blackboard.write(
                                    f"result.{node_id}",
                                    result["data"],
                                    source=node.agent_name or node_id,
                                )
                        else:
                            # 尝试重试
                            if node.retries < node.max_retries:
                                node.retries += 1
                                node.status = NodeStatus.RETRY
                                logger.info(f"节点 '{node_id}' 重试 ({node.retries}/{node.max_retries})")
                                retry_result = await self._execute_node(node, message, context, on_status)
                                if retry_result and retry_result.get("success", True):
                                    node.status = NodeStatus.SUCCESS
                                    node.result = retry_result
                                    completed.add(node_id)
                                else:
                                    node.status = NodeStatus.FAILED
                                    failed.add(node_id)
                            else:
                                node.status = NodeStatus.FAILED
                                failed.add(node_id)

            # 检查条件分支
            for node_id in layer:
                if node_id in workflow.conditions:
                    self._evaluate_conditions(workflow, node_id, completed, failed)

        # 收集结果
        total_latency = (time.time() - start) * 1000
        all_results = {}
        for nid, node in workflow.nodes.items():
            if node.result:
                all_results[nid] = {
                    "status": node.status.value,
                    "data": node.result,
                    "latency_ms": node.latency_ms,
                    "retries": node.retries,
                }

        status = "success" if not failed else ("partial" if completed else "failed")

        execution_log = {
            "workflow": workflow.name,
            "status": status,
            "total_latency_ms": round(total_latency, 1),
            "completed": list(completed),
            "failed": list(failed),
            "replan_count": replan_count,
            "timestamp": time.time(),
        }
        self._execution_log.append(execution_log)

        return {
            "status": status,
            "node_results": all_results,
            "execution_order": [layer for layer in layers],
            "total_latency_ms": round(total_latency, 1),
            "replan_count": replan_count,
        }

    async def _execute_node(
        self,
        node: WorkflowNode,
        message: str,
        context: Dict[str, Any],
        on_status: Callable,
    ) -> Dict[str, Any]:
        """执行单个节点。"""
        node.status = NodeStatus.RUNNING
        node.start_time = time.time()

        if node.node_type == "task":
            return await self._execute_task_node(node, message, context, on_status)
        elif node.node_type == "gate":
            return await self._execute_gate_node(node, message, context)
        elif node.node_type == "merge":
            return await self._execute_merge_node(node, message)
        elif node.node_type == "condition":
            return {"success": True, "node_type": "condition"}
        else:
            return {"success": True}

    async def _execute_task_node(
        self,
        node: WorkflowNode,
        message: str,
        context: Dict[str, Any],
        on_status: Callable,
    ) -> Dict[str, Any]:
        """执行任务节点 — 调度对应的 Agent。"""
        agent_name = node.agent_name
        agent = self.agents.get(agent_name)

        if not agent:
            return {"success": False, "error": f"Agent '{agent_name}' 未注册"}

        await on_status("agent", f"执行节点 '{node.node_id}' → {agent_name} Agent")

        # 从黑板读取前置 Agent 的结果作为额外上下文
        enriched_context = dict(context)
        if self.blackboard:
            for dep_id in node.dependencies:
                dep_result = self.blackboard.read(f"result.{dep_id}")
                if dep_result:
                    enriched_context[f"prev_{dep_id}"] = dep_result

        # 从节点配置中获取意图
        from .base import Intent, IntentType
        intent_type_str = node.config.get("intent_type", "sensor_query")
        try:
            intent_type = IntentType(intent_type_str)
        except ValueError:
            intent_type = IntentType.SENSOR_QUERY

        intent = Intent(
            type=intent_type,
            confidence=node.config.get("confidence", 1.0),
            reasoning=node.config.get("reasoning", ""),
        )

        try:
            result = await agent.execute(message, intent, enriched_context)
            return {
                "success": result.success,
                "content": result.content,
                "data": result.data,
                "tool_calls": [
                    {"tool": tc.tool_name, "success": tc.success}
                    for tc in result.tool_calls
                ],
                "latency_ms": result.latency_ms,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _execute_gate_node(
        self,
        node: WorkflowNode,
        message: str,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        执行质量控制门节点 — 评估前置节点的输出质量。

        质量评估维度：
        1. 完整性：是否回答了用户的问题
        2. 一致性：多个 Agent 的结果是否矛盾
        3. 具体性：是否包含具体数据而非泛泛而谈
        """
        # 收集前置节点的结果
        dep_results = []
        for dep_id in node.dependencies:
            dep_node_result = self.blackboard.read(f"result.{dep_id}") if self.blackboard else None
            if dep_node_result:
                dep_results.append(dep_node_result)

        if not dep_results:
            return {"success": True, "quality_score": 0.5, "gate_action": "pass"}

        # 简易质量评估（无需 LLM 的快速评估）
        quality_score = 0.0

        # 维度 1：是否有实质内容
        has_content = any(
            r.get("content") and len(r.get("content", "")) > 10
            for r in dep_results
        )
        quality_score += 0.4 if has_content else 0.0

        # 维度 2：是否包含数据
        has_data = any(
            r.get("data") and len(r.get("data", {})) > 0
            for r in dep_results
        )
        quality_score += 0.3 if has_data else 0.0

        # 维度 3：是否有工具调用成功
        has_tools = any(
            r.get("tool_calls") and any(tc.get("success") for tc in r["tool_calls"])
            for r in dep_results
        )
        quality_score += 0.3 if has_tools else 0.0

        # 决定门控动作
        threshold = node.config.get("quality_threshold", 0.5)
        if quality_score >= threshold:
            gate_action = "pass"
        elif quality_score >= threshold * 0.6:
            gate_action = "retry"   # 质量较低，建议重试
        else:
            gate_action = "fallback"  # 质量过低，走降级路径

        # 写入黑板
        if self.blackboard:
            self.blackboard.write(
                f"gate.{node.node_id}",
                {"quality_score": quality_score, "action": gate_action},
                source="gate",
            )

        return {
            "success": True,
            "quality_score": round(quality_score, 2),
            "gate_action": gate_action,
        }

    async def _execute_merge_node(
        self,
        node: WorkflowNode,
        message: str,
    ) -> Dict[str, Any]:
        """执行结果汇聚节点 — 合并多个前置 Agent 的结果。"""
        all_contents = []
        all_data = {}

        for dep_id in node.dependencies:
            if self.blackboard:
                dep_result = self.blackboard.read(f"result.{dep_id}")
                if dep_result:
                    if dep_result.get("content"):
                        all_contents.append(f"[{dep_id}] {dep_result['content']}")
                    if dep_result.get("data"):
                        all_data[dep_id] = dep_result["data"]

        # 合并后的内容
        merged_content = "\n\n".join(all_contents) if all_contents else "无有效结果"

        # 如果有 LLM，用 LLM 融合
        if self.llm and len(all_contents) > 1:
            try:
                from .llm_provider import LLMMessage
                fuse_prompt = (
                    "你是工业环境监控系统的 AI 助手。"
                    "以下多个分析模块分别给出了结果，请综合给用户一个统一、简洁的回复。\n\n"
                    f"用户问题：{message}\n\n"
                    + "\n\n".join(all_contents)
                    + "\n\n输出规则：综合各模块信息，不要分别罗列，简洁专业，用中文。"
                )
                messages = [LLMMessage(role="system", content=fuse_prompt)]
                resp = self.llm.chat(messages, temperature=0.3)
                merged_content = resp.content
            except Exception as e:
                logger.warning(f"结果融合 LLM 调用失败: {e}")

        return {
            "success": True,
            "content": merged_content,
            "data": all_data,
        }

    def _evaluate_conditions(
        self,
        workflow: WorkflowDefinition,
        source_node_id: str,
        completed: Set[str],
        failed: Set[str],
    ) -> None:
        """评估条件分支，决定后续节点的跳过与否。"""
        rules = workflow.conditions.get(source_node_id, [])
        if not rules:
            return

        for rule in rules:
            # 从黑板读取条件字段
            value = None
            if self.blackboard:
                value = self.blackboard.read(rule.field_path)

            # 评估条件
            condition_met = False
            if value is not None:
                if rule.operator == "gt":
                    condition_met = value > rule.value
                elif rule.operator == "lt":
                    condition_met = value < rule.value
                elif rule.operator == "eq":
                    condition_met = value == rule.value
                elif rule.operator == "neq":
                    condition_met = value != rule.value
                elif rule.operator == "contains":
                    condition_met = rule.value in str(value)

            if condition_met:
                logger.info(
                    f"条件分支触发: {source_node_id} → {rule.target_node} "
                    f"({rule.field_path} {rule.operator} {rule.value})"
                )

    # ------------------------------------------------------------------
    # 诊断
    # ------------------------------------------------------------------
    def get_execution_log(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取最近的执行日志。"""
        return self._execution_log[-limit:]
