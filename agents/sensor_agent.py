"""
SensorAgent — 传感器数据查询与分析 Agent

负责实时传感器数据查询、历史数据趋势分析和数据统计。
当用户询问"温度多少"、"最近的数据"、"历史趋势"等问题时被调度。
"""

import json
import logging
import time
from typing import Any, Dict

from .base import AgentResult, BaseAgent, Intent, ToolCall
from .llm_provider import LLMMessage

logger = logging.getLogger(__name__)


class SensorAgent(BaseAgent):
    name = "sensor"
    description = "传感器数据查询与趋势分析"

    def system_prompt(self) -> str:
        tool_desc = "\n".join(
            f"- {t['name']}: {t['description']}"
            for t in self.get_tool_descriptions()
        )
        return f"""你是工业环境监控系统的「传感器数据分析专家」。

职责：
1. 查询实时传感器数据（温度、湿度、气压、振动）
2. 查询历史数据并分析趋势
3. 对用户的数据问题给出专业、简洁的分析

可用工具：
{tool_desc}

输出规则：
- 直接给出数据和结论，不要重复用户问题
- 数值精确到小数点后 1 位
- 如有异常趋势需主动提示
- 用中文回复，简洁专业"""

    async def execute(
        self, message: str, intent: Intent, context: Dict[str, Any]
    ) -> AgentResult:
        start = time.time()
        tool_calls = []

        # 1. 判断是否需要历史数据
        need_history = any(
            kw in message for kw in
            ("历史", "趋势", "变化", "最近", "一周", "一天", "today", "trend", "hour", "day", "week")
        )

        # 2. 调用工具获取数据
        # 始终获取实时数据
        current_data = self.call_tool("query_current_sensor")
        tool_calls.append(ToolCall(tool_name="query_current_sensor", params={}, result=current_data))

        history_data = None
        trend_data = None
        if need_history or intent.type.value == "history_query":
            period = "day"  # 默认查一天
            if "周" in message or "week" in message.lower():
                period = "week"
            elif "月" in message or "month" in message.lower():
                period = "month"
            elif "小时" in message or "hour" in message.lower():
                period = "hour"
            history_data = self.call_tool("query_sensor_history", period=period)
            tool_calls.append(ToolCall(tool_name="query_sensor_history", params={"period": period}, result=history_data))
            trend_data = self.call_tool("analyze_sensor_trend", period=period)
            tool_calls.append(ToolCall(tool_name="analyze_sensor_trend", params={"period": period}, result=trend_data))

        # 3. 构建上下文给 LLM 生成分析
        data_context = f"实时数据：{json.dumps(current_data, ensure_ascii=False)}"
        if history_data:
            data_context += f"\n历史数据摘要：共 {history_data.get('count', 0)} 条记录"
        if trend_data:
            data_context += f"\n趋势分析：{json.dumps(trend_data, ensure_ascii=False)}"

        messages = self.build_messages(message, data_context)
        try:
            resp = self.llm.chat(messages)
            content = resp.content
        except Exception as e:
            logger.error(f"SensorAgent LLM 调用失败: {e}")
            # 降级：直接格式化数据
            content = self._format_fallback(current_data, trend_data)

        latency = (time.time() - start) * 1000
        return AgentResult(
            agent_name=self.name,
            content=content,
            data={"current": current_data, "history": history_data, "trend": trend_data},
            tool_calls=tool_calls,
            latency_ms=latency,
        )

    def _format_fallback(self, current: Dict, trend: Dict) -> str:
        """LLM 不可用时的降级格式化输出。"""
        parts = ["**当前传感器数据**"]
        if "error" not in current:
            parts.append(f"- 温度: {current.get('temperature', '--')}°C")
            parts.append(f"- 湿度: {current.get('humidity', '--')}%")
            parts.append(f"- 气压: {current.get('pressure', '--')} hPa")
            parts.append(f"- 振动: {current.get('vibration', '--')} mm/s")
        if trend and "error" not in trend:
            parts.append("\n**趋势分析**")
            for sensor in ("temperature", "humidity", "vibration"):
                s = trend.get(sensor, {})
                if s:
                    parts.append(f"- {sensor}: 均值 {s.get('avg', '--')}, "
                                 f"最大 {s.get('max', '--')}, 最小 {s.get('min', '--')}, "
                                 f"趋势 {s.get('trend', '--')}")
        return "\n".join(parts)
