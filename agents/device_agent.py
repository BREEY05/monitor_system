"""
DeviceAgent — 设备管理 Agent

负责查询设备列表、设备状态、设备位置（地图）和3D模型信息。
当用户询问"设备"、"有哪些设备"、"设备位置"等问题时被调度。
"""

import json
import logging
import time
from typing import Any, Dict

from .base import AgentResult, BaseAgent, Intent, ToolCall

logger = logging.getLogger(__name__)


class DeviceAgent(BaseAgent):
    name = "device"
    description = "设备信息查询与管理"

    def system_prompt(self) -> str:
        return """你是工业环境监控系统的「设备管理专家」。

职责：
1. 查询已注册的设备列表
2. 展示设备状态、位置信息
3. 提供设备相关的管理建议

可用工具：
- query_device_list: 获取所有设备列表
- query_device_status: 查询指定设备的详细状态
- query_current_sensor: 查询当前传感器数据

输出规则：
- 列出设备时包含名称、状态、位置
- 如有经纬度信息，可以提示用户可在地图上查看
- 如有3D模型，提示可在系统中预览
- 用中文回复，简洁专业"""

    async def execute(
        self, message: str, intent: Intent, context: Dict[str, Any]
    ) -> AgentResult:
        start = time.time()
        tool_calls = []

        # 1. 获取设备列表
        devices = self.call_tool("query_device_list")
        tool_calls.append(ToolCall(tool_name="query_device_list", params={}, result=devices))

        # 2. 获取当前选中设备的状态
        selected_id = devices.get("selected_device_id", "")
        if selected_id:
            status = self.call_tool("query_device_status", device_id=selected_id)
            tool_calls.append(ToolCall(tool_name="query_device_status", params={"device_id": selected_id}, result=status))
        else:
            status = {}

        # 3. 构建上下文
        device_context = (
            f"设备列表（{devices.get('count', 0)}台）：{json.dumps(devices.get('devices', []), ensure_ascii=False)}\n"
            f"当前选中设备：{selected_id}\n"
            f"设备状态：{json.dumps(status, ensure_ascii=False)}"
        )

        # 4. LLM 生成回答
        messages = self.build_messages(message, device_context)
        try:
            resp = self.llm.chat(messages)
            content = resp.content
        except Exception as e:
            logger.error(f"DeviceAgent LLM 调用失败: {e}")
            content = self._format_fallback(devices)

        latency = (time.time() - start) * 1000
        return AgentResult(
            agent_name=self.name,
            content=content,
            data={"devices": devices, "status": status},
            tool_calls=tool_calls,
            latency_ms=latency,
        )

    def _format_fallback(self, devices: Dict) -> str:
        """LLM 不可用时的降级输出。"""
        device_list = devices.get("devices", [])
        if not device_list:
            return "当前没有注册的设备。"
        parts = [f"**已注册设备（{len(device_list)}台）**\n"]
        for d in device_list:
            parts.append(
                f"- **{d.get('name', '未命名')}** (ID: {d.get('id', '--')})\n"
                f"  状态: {d.get('status', '--')} | "
                f"位置: ({d.get('latitude', '--')}, {d.get('longitude', '--')})"
            )
            if d.get("model_url"):
                parts.append(f"  3D模型: 已上传")
        return "\n".join(parts)
