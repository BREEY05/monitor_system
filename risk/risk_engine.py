"""Rule-based risk scoring using only current persisted/live system state."""

from __future__ import annotations

from typing import Any, Dict, List


class RiskEngine:
    weights = {"current": 40, "prediction": 30, "history": 20, "proximity": 10}

    @staticmethod
    def level(score: float) -> str:
        if score >= 75:
            return "CRITICAL"
        if score >= 50:
            return "WARNING"
        if score >= 30:
            return "WATCH"
        return "NORMAL"

    def analyze(self, device_id: str, current: Dict[str, Any], thresholds: Dict[str, Any],
                recent_alert_count: int, prediction: Dict[str, Any] | None = None) -> Dict[str, Any]:
        reasons: List[str] = []
        current_score = 0.0
        proximity_score = 0.0
        for metric in ("temperature", "humidity", "pressure", "vibration"):
            value, threshold = current.get(metric), thresholds.get(metric)
            if value is None or not threshold or float(threshold) <= 0:
                continue
            ratio = float(value) / float(threshold)
            if ratio > 1:
                current_score = self.weights["current"]
                reasons.append(f"当前{metric}={value} 已超过阈值 {threshold}")
            elif ratio >= 0.9:
                proximity_score = max(proximity_score, self.weights["proximity"] * (ratio - 0.9) / 0.1)
                reasons.append(f"当前{metric} 接近阈值")

        prediction_score = 0.0
        if prediction and prediction.get("status") == "success":
            values = prediction.get("predictions", [])
            temperature_limit = thresholds.get("temperature")
            if temperature_limit and any(float(value) > float(temperature_limit) for value in values):
                prediction_score = self.weights["prediction"]
                reasons.append("预测温度可能超过阈值")

        history_score = min(self.weights["history"], recent_alert_count * 4)
        if recent_alert_count:
            reasons.append(f"近期开启记录 {recent_alert_count} 条")
        score = round(min(100.0, current_score + prediction_score + history_score + proximity_score), 1)
        return {
            "device_id": device_id, "risk_score": score, "risk_level": self.level(score),
            "components": {"current": current_score, "prediction": prediction_score,
                           "history": history_score, "proximity": round(proximity_score, 1)},
            "reasons": reasons or ["当前真实数据未显示超过已配置阈值的情况"],
        }
