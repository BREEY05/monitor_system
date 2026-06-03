"""
EvaluatorAgent — 自评估 Agent

对其它 Agent 的输出进行质量评估，是改进 Workflow 的「质量保障层」。

评估维度：
  1. 完整性 (Completeness) — 是否回答了用户的核心问题
  2. 准确性 (Accuracy)     — 数值和结论是否与工具返回的原始数据一致
  3. 具体性 (Specificity)  — 是否包含具体数据而非泛泛而谈
  4. 一致性 (Consistency)  — 多个 Agent 的结果是否存在矛盾
  5. 可操作性 (Actionability) — 是否给出了有用的建议

评估结果可用于：
  - 触发重试（质量不达标时重新调度 Agent）
  - 动态补充（缺少数据时追加调用其它 Agent）
  - 统计报告（输出质量追踪）

学术价值：
  Agent 自评估是区别于传统 Pipeline 的重要创新，
  体现了 LLM Agent 系统的「反思 (Self-Reflection)」能力。
"""

import json
import logging
import time
from typing import Any, Dict, List, Optional

from .base import AgentResult, BaseAgent, Intent, IntentType, ToolCall
from .llm_provider import LLMMessage

logger = logging.getLogger(__name__)


# ==================== 快速评估（无需 LLM）====================

class QuickEvaluator:
    """
    快速规则评估器 — 不依赖 LLM，基于规则快速判断输出质量。

    评分维度（各 0-1 分，总分取加权平均）：
    """

    @staticmethod
    def evaluate(
        message: str,
        agent_result: AgentResult,
        intent: Intent,
    ) -> Dict[str, Any]:
        """
        快速评估 Agent 输出质量。

        Returns:
            {
                "overall_score": 0.0-1.0,
                "completeness": 0.0-1.0,
                "specificity": 0.0-1.0,
                "data_presence": 0.0-1.0,
                "tool_success": 0.0-1.0,
                "action": "pass" | "retry" | "fallback",
                "reasons": [...],
            }
        """
        reasons = []
        content = agent_result.content or ""

        # 1. 完整性：内容长度是否足够
        if len(content) < 10:
            completeness = 0.1
            reasons.append("输出过短，可能未回答问题")
        elif len(content) < 30:
            completeness = 0.5
        elif len(content) < 100:
            completeness = 0.8
        else:
            completeness = 1.0

        # 2. 具体性：是否包含数值
        import re
        number_count = len(re.findall(r'\d+\.?\d*', content))
        specificity = min(number_count * 0.15, 1.0)
        if number_count == 0 and intent.type in (IntentType.SENSOR_QUERY, IntentType.ALARM_QUERY):
            specificity = 0.2
            reasons.append("数据查询类回答缺少具体数值")

        # 3. 数据存在性：工具是否返回了有效数据
        data = agent_result.data
        has_valid_data = bool(data) and any(
            v for v in data.values()
            if v and (isinstance(v, (dict, list)) and len(str(v)) > 10)
        )
        data_presence = 0.8 if has_valid_data else 0.3
        if not has_valid_data:
            reasons.append("Agent 未获取到有效数据")

        # 4. 工具成功率
        tool_calls = agent_result.tool_calls
        if tool_calls:
            success_count = sum(1 for tc in tool_calls if tc.success)
            tool_success = success_count / len(tool_calls)
        else:
            tool_success = 0.5  # 没有工具调用不一定是错误

        # 加权总分
        overall = (
            completeness * 0.30 +
            specificity * 0.25 +
            data_presence * 0.25 +
            tool_success * 0.20
        )

        # 决定动作
        if overall >= 0.6:
            action = "pass"
        elif overall >= 0.35:
            action = "retry"
            reasons.append("质量偏低，建议重试")
        else:
            action = "fallback"
            reasons.append("质量过低，走降级路径")

        return {
            "overall_score": round(overall, 2),
            "completeness": round(completeness, 2),
            "specificity": round(specificity, 2),
            "data_presence": round(data_presence, 2),
            "tool_success": round(tool_success, 2),
            "action": action,
            "reasons": reasons,
        }


# ==================== LLM 深度评估 ====================

EVALUATION_PROMPT = """你是一个 AI 输出质量评估器。

请评估以下 AI 助手对用户问题的回答质量，从以下维度打分（每项 0-10 分）：

1. 完整性：是否回答了用户的核心问题
2. 准确性：数值和结论是否合理
3. 具体性：是否包含具体数据和可操作建议
4. 专业性：语言是否专业简洁

用户问题：{message}
AI 回答：{response}
参考数据：{reference_data}

只输出 JSON：
```json
{{
    "completeness": 0-10,
    "accuracy": 0-10,
    "specificity": 0-10,
    "professionalism": 0-10,
    "overall": 0-10,
    "feedback": "简要评价和改进建议"
}}
```"""


class EvaluatorAgent(BaseAgent):
    """
    自评估 Agent — 结合规则快速评估和 LLM 深度评估。

    用法示例:
        evaluator = EvaluatorAgent(llm)

        # 快速评估
        quick_result = evaluator.quick_evaluate(message, agent_result, intent)

        # LLM 深度评估
        deep_result = await evaluator.deep_evaluate(message, agent_result, context)

        # 根据评估结果决定是否重试
        if quick_result["action"] == "retry":
            # 重新调度 Agent
    """
    name = "evaluator"
    description = "Agent 输出质量评估"

    def __init__(self, llm, tools=None, quick_threshold: float = 0.5):
        super().__init__(llm, tools)
        self.quick_evaluator = QuickEvaluator()
        self.quick_threshold = quick_threshold
        self._eval_history: List[Dict[str, Any]] = []

    def system_prompt(self) -> str:
        return "你是一个专业的 AI 输出质量评估器。"

    async def execute(
        self, message: str, intent: Intent, context: Dict[str, Any]
    ) -> AgentResult:
        """EvaluatorAgent 的 execute 接口（评估 context 中的 agent_result）。"""
        agent_result = context.get("agent_result")
        if not agent_result:
            return AgentResult(
                agent_name=self.name,
                content="无待评估内容",
                success=False,
            )

        # 先快速评估
        quick = self.quick_evaluate(message, agent_result, intent)

        # 如果快速评估分数低，启用 LLM 深度评估
        if quick["overall_score"] < self.quick_threshold:
            deep = await self.deep_evaluate(message, agent_result, context)
            quick["deep_evaluation"] = deep

        self._eval_history.append({
            "message": message,
            "quick_score": quick["overall_score"],
            "action": quick["action"],
        })

        return AgentResult(
            agent_name=self.name,
            content=json.dumps(quick, ensure_ascii=False),
            data=quick,
            success=True,
        )

    def quick_evaluate(
        self, message: str, agent_result: AgentResult, intent: Intent
    ) -> Dict[str, Any]:
        """快速规则评估。"""
        return self.quick_evaluator.evaluate(message, agent_result, intent)

    async def deep_evaluate(
        self,
        message: str,
        agent_result: AgentResult,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """LLM 深度评估。"""
        reference_data = json.dumps(
            {k: str(v)[:200] for k, v in agent_result.data.items()},
            ensure_ascii=False,
        )

        prompt = EVALUATION_PROMPT.format(
            message=message,
            response=agent_result.content[:500],
            reference_data=reference_data,
        )

        messages = [LLMMessage(role="system", content=prompt)]
        try:
            result = self.llm.chat_json(messages)
            if result and "overall" in result:
                # 归一化到 0-1
                result["normalized_score"] = result["overall"] / 10.0
                return result
        except Exception as e:
            logger.warning(f"LLM 深度评估失败: {e}")

        return {"error": "评估失败", "normalized_score": 0.5}

    # ------------------------------------------------------------------
    # 批量评估（用于多 Agent 结果的交叉评估）
    # ------------------------------------------------------------------
    def batch_evaluate(
        self,
        message: str,
        results: List[AgentResult],
        intents: List[Intent],
    ) -> Dict[str, Any]:
        """批量评估多个 Agent 的输出质量。"""
        evaluations = []
        for i, result in enumerate(results):
            intent = intents[i] if i < len(intents) else intents[0]
            ev = self.quick_evaluate(message, result, intent)
            ev["agent_name"] = result.agent_name
            evaluations.append(ev)

        # 一致性检查：多个 Agent 是否矛盾
        consistency_issues = []
        if len(results) > 1:
            # 简易检查：数值型数据的矛盾
            for r1 in results:
                for r2 in results:
                    if r1.agent_name != r2.agent_name:
                        # 检查两个 Agent 是否对同一指标给出不同结论
                        d1, d2 = r1.data, r2.data
                        if d1.get("temperature") and d2.get("temperature"):
                            diff = abs(d1["temperature"] - d2["temperature"])
                            if diff > 5:
                                consistency_issues.append(
                                    f"{r1.agent_name} 和 {r2.agent_name} 的温度数据差异过大 ({diff}°C)"
                                )

        avg_score = sum(e["overall_score"] for e in evaluations) / max(len(evaluations), 1)

        return {
            "evaluations": evaluations,
            "average_score": round(avg_score, 2),
            "consistency_issues": consistency_issues,
            "pass_count": sum(1 for e in evaluations if e["action"] == "pass"),
            "retry_count": sum(1 for e in evaluations if e["action"] == "retry"),
        }

    # ------------------------------------------------------------------
    # 统计
    # ------------------------------------------------------------------
    def get_eval_stats(self) -> Dict[str, Any]:
        """获取评估统计。"""
        if not self._eval_history:
            return {"total": 0}
        scores = [e["quick_score"] for e in self._eval_history]
        return {
            "total": len(scores),
            "avg_score": round(sum(scores) / len(scores), 2),
            "pass_rate": round(
                sum(1 for e in self._eval_history if e["action"] == "pass") / len(scores), 2
            ),
            "recent": self._eval_history[-5:],
        }
