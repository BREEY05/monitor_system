"""Read-only prediction boundary.

The GRU checkpoint is intentionally not trained or fabricated by the web service.
Until a trained checkpoint is configured, this service reports its real-data state.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List


class PredictionService:
    model_name = "GRU"
    minimum_samples = 60

    def _history(self, device_id: str, limit: int = 500) -> List[Dict[str, Any]]:
        from api_server import get_db_connection

        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            query = (
                "SELECT timestamp, temperature, humidity, pressure, vibration "
                "FROM sensor_data WHERE device_id = ? ORDER BY timestamp ASC LIMIT ?"
            )
            cursor.execute(query, (device_id, limit))
            rows = cursor.fetchall()
            return [
                {"timestamp": row[0], "temperature": row[1], "humidity": row[2],
                 "pressure": row[3], "vibration": row[4]}
                for row in rows
            ]
        finally:
            conn.close()

    def predict(self, device_id: str, metric: str = "temperature", horizon: int = 10) -> Dict[str, Any]:
        if metric != "temperature":
            return {"status": "unsupported_metric", "message": "第一阶段仅支持温度预测", "metric": metric}
        if horizon < 1 or horizon > 120:
            return {"status": "invalid_request", "message": "预测步数必须在 1 到 120 之间"}

        records = self._history(device_id)
        usable = [row for row in records if row["temperature"] is not None]
        if len(usable) < self.minimum_samples:
            return {
                "status": "insufficient_data", "device_id": device_id, "metric": metric,
                "sample_count": len(usable), "minimum_samples": self.minimum_samples,
                "message": "当前设备真实历史数据不足，暂无法进行可靠趋势预测。请继续采集 Raspberry Pi 数据。",
            }

        # A service must never train or invent a numerical forecast during a request.
        return {
            "status": "model_unavailable", "device_id": device_id, "metric": metric,
            "sample_count": len(usable), "model": self.model_name, "horizon": horizon,
            "message": "已具备真实历史数据，但尚未部署训练完成的 GRU 模型。",
        }

    def status(self, device_id: str) -> Dict[str, Any]:
        records = self._history(device_id)
        return {
            "device_id": device_id, "model": self.model_name, "trained": False,
            "sample_count": sum(1 for row in records if row["temperature"] is not None),
            "minimum_samples": self.minimum_samples,
            "last_data_time": records[-1]["timestamp"] if records else None,
        }

    def history(self, device_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        from api_server import get_db_connection
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, device_id, metric, model_name, prediction_time, horizon, prediction_values, created_at "
                "FROM prediction_records WHERE device_id = ? ORDER BY id DESC LIMIT ?", (device_id, limit)
            )
            rows = cursor.fetchall()
            return [
                {"id": row[0], "device_id": row[1], "metric": row[2], "model": row[3],
                 "prediction_time": row[4], "horizon": row[5], "predictions": json.loads(row[6] or "[]"),
                 "created_at": row[7]}
                for row in rows
            ]
        finally:
            conn.close()
