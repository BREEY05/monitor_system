"""
AlarmAgent — 报警与异常管理 Agent

负责查询报警记录、分析异常数据、解释报警原因和提供处置建议。
当用户询问"报警"、"异常"、"告警"、"处理"等问题时被调度。
"""

import json
import logging
import time
from typing import Any, Dict

from .base import AgentResult, BaseAgent, Intent, ToolCall

logger = logging.getLogger(__name__)


class AlarmAgent(BaseAgent):
    name = "alarm"
    description = "报警查询与异常分析"

    def system_prompt(self) -> str:
        return """你是工业环境监控系统的「报警分析专家」。

职责：
1. 查询当前和历史报警记录
2. 分析报警原因和严重程度
3. 提供处置建议

可用工具：
- query_recent_alerts: 查询最近报警记录
- query_anomaly_data: 查询异常传感器数据
- query_current_sensor: 查询当前传感器数据
- get_threshold_config: 获取报警阈值配置

输出规则：
- 列出报警时标注时间、类型、级别
- 分析原因时结合当前传感器数据和阈值配置
- 给出具体的处置建议（如检查设备、调整阈值、联系维修）
- 用中文回复，专业简洁"""

    async def execute(
        self, message: str, intent: Intent, context: Dict[str, Any]
    ) -> AgentResult:
        start = time.time()
        tool_calls = []

        # 1. 收集报警相关数据
        alerts = self.call_tool("query_recent_alerts", limit=10)
        tool_calls.append(ToolCall(tool_name="query_recent_alerts", params={"limit": 10}, result=alerts))

        anomalies = self.call_tool("query_anomaly_data", limit=10)
        tool_calls.append(ToolCall(tool_name="query_anomaly_data", params={"limit": 10}, result=anomalies))

        current = self.call_tool("query_current_sensor")
        tool_calls.append(ToolCall(tool_name="query_current_sensor", params={}, result=current))

        thresholds = self.call_tool("get_threshold_config")
        tool_calls.append(ToolCall(tool_name="get_threshold_config", params={}, result=thresholds))

        # 2. 构建上下文
        alarm_context = (
            f"当前报警记录（{alerts.get('count', 0)}条）：{json.dumps(alerts.get('alerts', [])[:5], ensure_ascii=False)}\n"
            f"异常数据（{anomalies.get('count', 0)}条）：{json.dumps(anomalies.get('records', [])[:5], ensure_ascii=False)}\n"
            f"当前传感器：{json.dumps(current, ensure_ascii=False)}\n"
            f"阈值配置：{json.dumps(thresholds, ensure_ascii=False)}"
        )

        # 3. LLM 分析
        messages = self.build_messages(message, alarm_context)
        try:
            resp = self.llm.chat(messages)
            content = resp.content
        except Exception as e:
            logger.error(f"AlarmAgent LLM 调用失败: {e}")
            content = self._format_fallback(alerts, thresholds)

        latency = (time.time() - start) * 1000
        return AgentResult(
            agent_name=self.name,
            content=content,
            data={
                "alert_count": alerts.get("count", 0),
                "anomaly_count": anomalies.get("count", 0),
                "alerts": alerts.get("alerts", []),
            },
            tool_calls=tool_calls,
            latency_ms=latency,
        )

    def _format_fallback(self, alerts: Dict, thresholds: Dict) -> str:
        """LLM 不可用时的降级输出。"""
        parts = ["**报警状态**"]
        alert_list = alerts.get("alerts", [])
        if not alert_list:
            parts.append("当前无活跃报警。")
        else:
            parts.append(f"最近 {len(alert_list)} 条报警记录：")
            for a in alert_list[:5]:
                parts.append(
                    f"- [{a.get('level', 'unknown')}] {a.get('title', '')} "
                    f"时间: {a.get('time', '--')}"
                )
        th = thresholds.get("thresholds", {})
        if th:
            parts.append(f"\n**当前阈值**: 温度 {th.get('temperature', '--')}°C, "
                         f"湿度 {th.get('humidity', '--')}%, "
                         f"振动 {th.get('vibration', '--')} mm/s")
        return "\n".join(parts)
