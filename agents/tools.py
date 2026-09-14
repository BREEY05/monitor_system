"""
工具注册表

定义所有 Agent 可调用的工具，并提供工具注册和发现机制。
工具实现直接访问项目现有的 SQLite/PostgreSQL 数据库和内存状态。
"""

import json
import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# ==================== 数据库路径 ====================
BASE_DIR = Path(__file__).parent.parent
DB_PATH = BASE_DIR / "monitor_data.db"


def _get_db():
    """获取数据库连接（优先使用项目全局连接，否则新建 SQLite 连接）。"""
    try:
        from api_server import get_db_connection
        return get_db_connection()
    except (ImportError, Exception):
        return sqlite3.connect(str(DB_PATH))


def _get_config():
    """获取系统配置。"""
    try:
        from api_server import CONFIG
        return CONFIG
    except ImportError:
        return {}


# ==================== 工具函数 ====================

def query_current_sensor() -> Dict[str, Any]:
    """查询最新 Raspberry Pi 实时数据；未接收到真实数据时明确返回不可用。"""
    try:
        from api_server import latest_pi_sensor_data
        if latest_pi_sensor_data.get("timestamp"):
            return {"source": "raspberry-live", **latest_pi_sensor_data}
        return {"source": "unavailable", "error": "暂无 Raspberry Pi 真实传感器数据"}
    except Exception as exc:
        return {"source": "unavailable", "error": str(exc)}


def query_sensor_history(period: str = "hour", device_id: str = "") -> Dict[str, Any]:
    """查询历史传感器数据。period 可选值：hour(1小时)、day(24小时)、week(7天)、month(30天)。"""
    periods = {
        "hour": timedelta(hours=1),
        "day": timedelta(days=1),
        "week": timedelta(weeks=1),
        "month": timedelta(days=30),
    }
    delta = periods.get(period, timedelta(hours=1))
    since = (datetime.now() - delta).isoformat()

    try:
        conn = _get_db()
        c = conn.cursor()
        c.execute(
            "SELECT timestamp, temperature, humidity, pressure, vibration, device_id, area "
            "FROM sensor_data WHERE timestamp >= ? ORDER BY timestamp DESC LIMIT 500",
            (since,),
        )
        rows = c.fetchall()
        conn.close()
        return {
            "period": period,
            "since": since,
            "count": len(rows),
            "records": [
                {
                    "timestamp": r[0], "temperature": r[1], "humidity": r[2],
                    "pressure": r[3], "vibration": r[4], "device_id": r[5], "area": r[6],
                }
                for r in rows
            ],
        }
    except Exception as e:
        return {"error": str(e), "period": period}


def query_recent_alerts(limit: int = 10) -> Dict[str, Any]:
    """查询最近的报警记录，包括报警类型、级别、数值和时间。"""
    try:
        from api_server import latest_alerts
        alerts = latest_alerts[:limit]
        return {"count": len(alerts), "alerts": alerts}
    except Exception:
        pass
    try:
        conn = _get_db()
        c = conn.cursor()
        c.execute(
            "SELECT id, timestamp, sensor_type, value, threshold, level FROM alerts "
            "ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        rows = c.fetchall()
        conn.close()
        return {
            "count": len(rows),
            "alerts": [
                {
                    "id": r[0], "timestamp": r[1], "sensor_type": r[2],
                    "value": r[3], "threshold": r[4], "level": r[5],
                }
                for r in rows
            ],
        }
    except Exception as e:
        return {"error": str(e)}


def query_anomaly_data(limit: int = 20) -> Dict[str, Any]:
    """查询最近的异常传感器数据记录。"""
    try:
        conn = _get_db()
        c = conn.cursor()
        c.execute(
            "SELECT * FROM anomaly_sensor_data ORDER BY rowid DESC LIMIT ?",
            (limit,),
        )
        rows = c.fetchall()
        columns = [desc[0] for desc in c.description] if c.description else []
        conn.close()
        return {
            "count": len(rows),
            "records": [dict(zip(columns, row)) for row in rows],
        }
    except Exception as e:
        return {"error": str(e)}


def query_device_list() -> Dict[str, Any]:
    """获取所有已注册的设备列表，包括设备名称、位置、状态和3D模型信息。"""
    try:
        config = _get_config()
        devices = config.get("devices", [])
        selected = config.get("selected_device_id", "")
        return {
            "count": len(devices),
            "selected_device_id": selected,
            "devices": devices,
        }
    except Exception as e:
        return {"error": str(e)}


def query_device_status(device_id: str = "") -> Dict[str, Any]:
    """查询指定设备的当前状态，包括最新传感器读数和报警情况。"""
    sensor = query_current_sensor()
    alerts = query_recent_alerts(limit=5)
    return {
        "device_id": device_id or "current",
        "latest_sensor": sensor,
        "recent_alerts": alerts.get("alerts", [])[:3],
    }


def search_knowledge_base(query: str, top_k: int = 4) -> Dict[str, Any]:
    """在 RAG 知识库中检索与查询相关的文档片段，返回最相关的 top_k 条结果。"""
    try:
        from api_server import search_rag_context
        context = search_rag_context(query, top_k)
        return {"query": query, "context": context, "found": bool(context)}
    except Exception:
        pass
    # 降级：直接查数据库
    try:
        conn = _get_db()
        c = conn.cursor()
        c.execute(
            "SELECT content, document_id FROM rag_chunks ORDER BY id DESC LIMIT 100"
        )
        rows = c.fetchall()
        conn.close()
        query_lower = query.lower()
        matched = [r for r in rows if any(term in (r[0] or "").lower() for term in query_lower.split())]
        if not matched:
            return {"query": query, "context": "", "found": False}
        context = "\n---\n".join(r[0] for r in matched[:top_k])
        return {"query": query, "context": context, "found": True}
    except Exception as e:
        return {"query": query, "error": str(e), "found": False}


def search_web(query: str, max_results: int = 3) -> Dict[str, Any]:
    """使用搜索引擎搜索互联网上的最新信息，适用于查询新闻、最新技术动态等。"""
    try:
        from api_server import online_search_context
        context = online_search_context(query, max_results)
        return {"query": query, "context": context, "found": bool(context)}
    except Exception:
        pass
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        lines = [
            f"- {r.get('title', '')}: {r.get('body', '')} {r.get('href', '')}"
            for r in results
        ]
        context = "\n".join(lines) if lines else ""
        return {"query": query, "context": context, "found": bool(context)}
    except Exception as e:
        return {"query": query, "error": str(e), "found": False}


def get_threshold_config() -> Dict[str, Any]:
    """获取当前系统的所有报警阈值配置，包括温度、湿度、振动阈值和报警参数。"""
    config = _get_config()
    return {
        "thresholds": config.get("thresholds", {}),
        "alarm_trigger_count": config.get("alarm_trigger_count", 1),
        "alarm_window_seconds": config.get("alarm_window_seconds", 60),
        "alarm_cooldown_seconds": config.get("alarm_cooldown_seconds", 300),
    }


def analyze_sensor_trend(period: str = "day") -> Dict[str, Any]:
    """分析传感器数据趋势，计算均值、最大值、最小值和变化趋势。"""
    history = query_sensor_history(period)
    records = history.get("records", [])
    if not records:
        return {"period": period, "error": "无历史数据", "trend": "unknown"}

    temps = [r["temperature"] for r in records if r.get("temperature") is not None]
    humids = [r["humidity"] for r in records if r.get("humidity") is not None]
    vibs = [r["vibration"] for r in records if r.get("vibration") is not None]

    def stats(values):
        if not values:
            return {}
        return {
            "avg": round(sum(values) / len(values), 2),
            "max": round(max(values), 2),
            "min": round(min(values), 2),
            "count": len(values),
            "trend": "rising" if len(values) > 2 and values[-1] > values[0] else
                     "falling" if len(values) > 2 and values[-1] < values[0] else "stable",
        }

    return {
        "period": period,
        "sample_count": len(records),
        "temperature": stats(temps),
        "humidity": stats(humids),
        "vibration": stats(vibs),
    }


def predict_device_trend(device_id: str, metric: str = "temperature", horizon: int = 10) -> Dict[str, Any]:
    """调用已部署模型基于真实 Raspberry Pi 历史记录进行趋势预测。"""
    from prediction import PredictionService
    return PredictionService().predict(device_id, metric, horizon)


def analyze_device_risk(device_id: str) -> Dict[str, Any]:
    """综合真实当前状态、历史异常及预测结果，计算可解释风险等级。"""
    from api_server import _risk_analysis
    return _risk_analysis(device_id)

# ==================== 工具注册表 ====================

TOOL_REGISTRY: Dict[str, Callable] = {}


def register_all_tools():
    """注册所有可用工具到全局注册表。"""
    global TOOL_REGISTRY
    new_tools = {
        "query_current_sensor": query_current_sensor,
        "query_sensor_history": query_sensor_history,
        "query_recent_alerts": query_recent_alerts,
        "query_anomaly_data": query_anomaly_data,
        "query_device_list": query_device_list,
        "query_device_status": query_device_status,
        "search_knowledge_base": search_knowledge_base,
        "search_web": search_web,
        "get_threshold_config": get_threshold_config,
        "analyze_sensor_trend": analyze_sensor_trend,
        "predict_device_trend": predict_device_trend,
        "analyze_device_risk": analyze_device_risk,
    }
    TOOL_REGISTRY.clear()
    TOOL_REGISTRY.update(new_tools)
    return TOOL_REGISTRY


def get_tools_for_agent(agent_name: str) -> Dict[str, Callable]:
    """根据 Agent 名称返回其可用的工具子集。"""
    if not TOOL_REGISTRY:
        register_all_tools()

    agent_tools = {
        "sensor":  ["query_current_sensor", "query_sensor_history", "analyze_sensor_trend"],
        "knowledge": ["search_knowledge_base"],
        "search":  ["search_web"],
        "alarm":   ["query_recent_alerts", "query_anomaly_data", "get_threshold_config",
                     "query_current_sensor"],
        "device":  ["query_device_list", "query_device_status", "query_current_sensor"],
        "prediction": ["query_sensor_history", "predict_device_trend"],
        "risk": ["query_current_sensor", "query_recent_alerts", "analyze_device_risk"],
    }
    tool_names = agent_tools.get(agent_name, list(TOOL_REGISTRY.keys()))
    return {name: TOOL_REGISTRY[name] for name in tool_names if name in TOOL_REGISTRY}


# ==================== 工具 Schema（用于系统提示词）====================

TOOL_SCHEMAS = [
    {
        "name": "query_current_sensor",
        "description": "查询最新的传感器实时数据（温度、湿度、气压、振动）",
        "params": {},
    },
    {
        "name": "query_sensor_history",
        "description": "查询历史传感器数据",
        "params": {"period": "时间范围: hour|day|week|month", "device_id": "设备ID（可选）"},
    },
    {
        "name": "query_recent_alerts",
        "description": "查询最近的报警记录",
        "params": {"limit": "返回条数（默认10）"},
    },
    {
        "name": "query_anomaly_data",
        "description": "查询异常传感器数据",
        "params": {"limit": "返回条数（默认20）"},
    },
    {
        "name": "query_device_list",
        "description": "获取所有已注册设备列表",
        "params": {},
    },
    {
        "name": "query_device_status",
        "description": "查询指定设备当前状态",
        "params": {"device_id": "设备ID"},
    },
    {
        "name": "search_knowledge_base",
        "description": "在 RAG 知识库中检索文档片段",
        "params": {"query": "检索关键词", "top_k": "返回条数（默认4）"},
    },
    {
        "name": "search_web",
        "description": "搜索互联网信息",
        "params": {"query": "搜索关键词", "max_results": "最大结果数（默认3）"},
    },
    {
        "name": "get_threshold_config",
        "description": "获取报警阈值配置",
        "params": {},
    },
    {
        "name": "analyze_sensor_trend",
        "description": "分析传感器数据趋势（均值、极值、升降趋势）",
        "params": {"period": "时间范围: hour|day|week|month"},
    },
    {
        "name": "predict_device_trend",
        "description": "使用真实历史传感器数据调用已部署 GRU 的温度趋势预测；数据不足会明确返回",
        "params": {"device_id": "设备ID", "metric": "当前仅 temperature", "horizon": "预测步数"},
    },
    {
        "name": "analyze_device_risk",
        "description": "综合当前状态、历史异常和预测趋势计算设备风险等级",
        "params": {"device_id": "设备ID"},
    },]
