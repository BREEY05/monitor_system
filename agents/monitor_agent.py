"""
MonitorAgent — 主动监控 Agent

将系统从「纯被动响应」升级为「主动感知 + 被动响应」双模式。
MonitorAgent 周期性分析传感器数据流，主动发现异常模式并生成预警。

核心能力：
  1. 趋势异常检测 — 识别温度骤升、振动异常等趋势性异常
  2. 关联分析     — 多个传感器指标之间的关联异常
  3. 预测性告警   — 根据趋势预测即将触发的阈值
  4. 巡检报告     — 定时生成设备健康巡检摘要

学术价值：
  主动感知是 Agent 系统从「工具」到「助手」的关键跃迁，
  结合简单统计模型的异常检测方案适合工业 IoT 场景论文。
"""

import json
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from .base import AgentResult, BaseAgent, Intent, IntentType, ToolCall
from .llm_provider import LLMMessage

logger = logging.getLogger(__name__)


# ==================== 异常检测器 ====================

@dataclass
class AnomalySignal:
    """异常信号。"""
    signal_type: str          # "trend_spike" | "threshold_approach" | "correlation_break" | "stagnation"
    severity: str             # "low" | "medium" | "high" | "critical"
    metric: str               # 涉及的指标名
    description: str          # 人类可读描述
    value: float = 0.0        # 当前值
    reference: float = 0.0    # 参考值（历史均值、阈值等）
    timestamp: float = 0.0
    raw_data: Dict[str, Any] = field(default_factory=dict)


class StatisticalDetector:
    """
    基于统计的异常检测器。

    无需 ML 框架，使用简单的统计方法实现异常检测：
    1. Z-Score 检测：识别偏离均值过大的数据点
    2. 变化率检测：识别骤升骤降
    3. 阈值接近度：预测即将触发的报警
    4. 数据停滞检测：传感器可能掉线
    """

    def __init__(self, window_size: int = 50):
        self.window_size = window_size
        # 滑动窗口缓存
        self._windows: Dict[str, deque] = {}

    def update(self, metric: str, value: float) -> List[AnomalySignal]:
        """接收新数据点，返回检测到的异常信号。"""
        signals = []

        if metric not in self._windows:
            self._windows[metric] = deque(maxlen=self.window_size)

        window = self._windows[metric]
        window.append({"value": value, "timestamp": time.time()})

        if len(window) < 5:
            return signals  # 数据不足，跳过检测

        values = [d["value"] for d in window]

        # 1. Z-Score 异常（>2σ）
        mean = sum(values) / len(values)
        std = (sum((v - mean) ** 2 for v in values) / len(values)) ** 0.5
        if std > 0:
            z_score = abs(value - mean) / std
            if z_score > 2.5:
                severity = "high" if z_score > 3.0 else "medium"
                signals.append(AnomalySignal(
                    signal_type="trend_spike",
                    severity=severity,
                    metric=metric,
                    description=f"{metric} 偏离均值 {z_score:.1f} 个标准差 (当前: {value:.1f}, 均值: {mean:.1f})",
                    value=value,
                    reference=mean,
                    timestamp=time.time(),
                ))

        # 2. 变化率异常（相邻两点变化过快）
        if len(values) >= 3:
            delta = values[-1] - values[-2]
            prev_delta = values[-2] - values[-3]
            if abs(delta) > abs(prev_delta) * 3 and abs(delta) > 1.0:
                signals.append(AnomalySignal(
                    signal_type="trend_spike",
                    severity="medium",
                    metric=metric,
                    description=f"{metric} 变化率异常: 最近变化 {delta:+.1f}, 此前变化 {prev_delta:+.1f}",
                    value=value,
                    reference=prev_delta,
                    timestamp=time.time(),
                ))

        # 3. 阈值接近度检测
        thresholds = self._get_thresholds()
        if metric in thresholds:
            th = thresholds[metric]
            high = th.get("high")
            low = th.get("low")
            if high and value >= high * 0.9 and value < high:
                signals.append(AnomalySignal(
                    signal_type="threshold_approach",
                    severity="low",
                    metric=metric,
                    description=f"{metric} 接近上限阈值 ({value:.1f}/{high})",
                    value=value,
                    reference=high,
                    timestamp=time.time(),
                ))
            if low and value <= low * 1.1 and value > low:
                signals.append(AnomalySignal(
                    signal_type="threshold_approach",
                    severity="low",
                    metric=metric,
                    description=f"{metric} 接近下限阈值 ({value:.1f}/{low})",
                    value=value,
                    reference=low,
                    timestamp=time.time(),
                ))

        # 4. 数据停滞检测（最近 N 个点完全相同）
        if len(values) >= 5:
            recent = values[-5:]
            if len(set(round(v, 4) for v in recent)) == 1:
                signals.append(AnomalySignal(
                    signal_type="stagnation",
                    severity="medium",
                    metric=metric,
                    description=f"{metric} 连续 5 个采样点数据完全相同 ({value:.2f})，传感器可能掉线",
                    value=value,
                    timestamp=time.time(),
                ))

        return signals

    def _get_thresholds(self) -> Dict[str, Dict[str, float]]:
        """获取阈值配置。"""
        try:
            from .tools import get_threshold_config
            config = get_threshold_config()
            th = config.get("thresholds", {})
            return {
                "temperature": {"high": th.get("temperature", 50), "low": th.get("temperature_low", 0)},
                "humidity":    {"high": th.get("humidity", 90),    "low": th.get("humidity_low", 20)},
                "vibration":   {"high": th.get("vibration", 10),   "low": None},
            }
        except Exception:
            return {
                "temperature": {"high": 50, "low": 0},
                "humidity":    {"high": 90, "low": 20},
                "vibration":   {"high": 10, "low": None},
            }


# ==================== 主动监控 Agent ====================

class MonitorAgent(BaseAgent):
    """
    主动监控 Agent — 周期性分析传感器数据流。

    用法示例:
        monitor = MonitorAgent(llm)

        # 周期性调用（如每 30 秒）
        alerts = await monitor.check_health()

        # 获取巡检报告
        report = await monitor.generate_inspection_report(period="hour")
    """
    name = "monitor"
    description = "主动异常检测与巡检报告"

    def __init__(self, llm, tools=None, check_interval: int = 30):
        super().__init__(llm, tools)
        self.detector = StatisticalDetector()
        self.check_interval = check_interval

        # 历史异常记录
        self._anomaly_history: deque = deque(maxlen=100)
        # 上次检查时间
        self._last_check: float = 0
        # 累计检查次数
        self._check_count: int = 0

    def system_prompt(self) -> str:
        return """你是工业环境监控系统的「主动监控分析专家」。

职责：
1. 分析传感器数据流中的异常模式
2. 生成设备健康巡检报告
3. 提供预防性维护建议

输出规则：
- 突出异常和风险，正常情况一笔带过
- 给出具体数值和建议
- 用中文回复，专业简洁"""

    async def execute(
        self, message: str, intent: Intent, context: Dict[str, Any]
    ) -> AgentResult:
        """响应式执行 — 当用户询问系统健康状态时调用。"""
        start = time.time()

        # 执行健康检查
        alerts = await self.check_health()

        # 生成报告
        if alerts:
            alert_text = json.dumps(
                [{"type": a.signal_type, "severity": a.severity, "desc": a.description}
                 for a in alerts],
                ensure_ascii=False,
            )
            messages = self.build_messages(
                message,
                f"主动监控检测结果：\n{alert_text}",
            )
            try:
                resp = self.llm.chat(messages)
                content = resp.content
            except Exception:
                content = self._format_alerts(alerts)
        else:
            content = "系统运行正常，所有传感器指标在正常范围内，未发现异常模式。"

        latency = (time.time() - start) * 1000
        return AgentResult(
            agent_name=self.name,
            content=content,
            data={"alerts": len(alerts), "check_count": self._check_count},
            latency_ms=latency,
        )

    # ------------------------------------------------------------------
    # 核心：健康检查
    # ------------------------------------------------------------------
    async def check_health(self) -> List[AnomalySignal]:
        """
        执行一轮健康检查 — 读取最新传感器数据并进行异常检测。

        Returns:
            检测到的异常信号列表
        """
        self._check_count += 1
        self._last_check = time.time()
        new_signals = []

        try:
            from .tools import query_current_sensor
            sensor_data = query_current_sensor()

            if "error" in sensor_data:
                new_signals.append(AnomalySignal(
                    signal_type="data_error",
                    severity="high",
                    metric="all",
                    description=f"传感器数据获取失败: {sensor_data['error']}",
                    timestamp=time.time(),
                ))
            else:
                # 对每个指标进行异常检测
                for metric in ("temperature", "humidity", "pressure", "vibration"):
                    value = sensor_data.get(metric)
                    if value is not None and isinstance(value, (int, float)):
                        signals = self.detector.update(metric, float(value))
                        new_signals.extend(signals)

        except Exception as e:
            logger.error(f"健康检查异常: {e}")
            new_signals.append(AnomalySignal(
                signal_type="system_error",
                severity="critical",
                metric="system",
                description=f"健康检查系统异常: {str(e)}",
                timestamp=time.time(),
            ))

        # 记录异常
        for signal in new_signals:
            self._anomaly_history.append(signal)

        # 只返回高优先级信号
        high_priority = [s for s in new_signals if s.severity in ("medium", "high", "critical")]
        return high_priority

    # ------------------------------------------------------------------
    # 巡检报告
    # ------------------------------------------------------------------
    async def generate_inspection_report(self, period: str = "hour") -> Dict[str, Any]:
        """
        生成巡检报告 — 汇总一段时间内的监控情况。

        Args:
            period: "hour" | "day" | "shift"(8小时)

        Returns:
            结构化巡检报告
        """
        # 统计信息
        recent_anomalies = [
            a for a in self._anomaly_history
            if (time.time() - a.timestamp) < {"hour": 3600, "day": 86400, "shift": 28800}.get(period, 3600)
        ]

        # 获取当前状态
        current_status = "normal"
        if any(a.severity in ("high", "critical") for a in recent_anomalies):
            current_status = "warning"
        elif any(a.severity == "medium" for a in recent_anomalies):
            current_status = "attention"

        # 获取当前传感器数据
        sensor_snapshot = {}
        try:
            from .tools import query_current_sensor
            sensor_snapshot = query_current_sensor()
        except Exception:
            pass

        report = {
            "period": period,
            "generated_at": datetime.now().isoformat(),
            "check_count": self._check_count,
            "status": current_status,
            "anomaly_count": len(recent_anomalies),
            "anomalies": [
                {
                    "type": a.signal_type,
                    "severity": a.severity,
                    "metric": a.metric,
                    "description": a.description,
                    "time": datetime.fromtimestamp(a.timestamp).strftime("%H:%M:%S"),
                }
                for a in recent_anomalies[-10:]
            ],
            "current_sensor": sensor_snapshot,
        }

        # 用 LLM 生成自然语言摘要
        try:
            report_text = json.dumps(report, ensure_ascii=False, default=str)
            messages = [
                LLMMessage(role="system", content=self.system_prompt()),
                LLMMessage(
                    role="user",
                    content=f"请根据以下巡检数据生成一份简洁的巡检报告摘要：\n{report_text}",
                ),
            ]
            resp = self.llm.chat(messages)
            report["summary"] = resp.content
        except Exception:
            report["summary"] = self._format_summary(report)

        return report

    # ------------------------------------------------------------------
    # 格式化辅助
    # ------------------------------------------------------------------
    def _format_alerts(self, alerts: List[AnomalySignal]) -> str:
        """格式化异常信号为文本。"""
        parts = ["**主动监控告警**"]
        for a in alerts:
            icon = {"high": "🔴", "critical": "🔴", "medium": "🟡", "low": "🟢"}.get(a.severity, "⚪")
            parts.append(f"{icon} [{a.severity.upper()}] {a.description}")
        return "\n".join(parts)

    def _format_summary(self, report: Dict) -> str:
        """降级格式化巡检摘要。"""
        status_map = {"normal": "正常", "attention": "需关注", "warning": "告警"}
        lines = [
            f"巡检状态: {status_map.get(report['status'], '未知')}",
            f"检查次数: {report['check_count']}",
            f"异常数量: {report['anomaly_count']}",
        ]
        for a in report.get("anomalies", [])[:5]:
            lines.append(f"  - [{a['severity']}] {a['description']}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # 统计
    # ------------------------------------------------------------------
    def get_stats(self) -> Dict[str, Any]:
        """获取监控统计。"""
        return {
            "check_count": self._check_count,
            "total_anomalies": len(self._anomaly_history),
            "last_check": self._last_check,
            "recent_anomaly_types": {
                a.signal_type: sum(1 for x in self._anomaly_history if x.signal_type == a.signal_type)
                for a in list(self._anomaly_history)[-20:]
            },
        }
