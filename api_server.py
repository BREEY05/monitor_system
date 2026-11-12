"""
工业环境监控系统 - 本地/云端演示版
前端 + 后端 + AI 对话 一体化部署（无需硬件）

运行方式：
    cd /path/to/monitor_system
    python api_server.py

前端访问：
    http://localhost:8000
"""

import os
import sys
import time
import math
import json
import asyncio
import sqlite3
import logging
import threading
import shutil
import subprocess
import re
import io
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any, Tuple
from pathlib import Path
from queue import Queue
from itertools import count

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import uvicorn

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================== 多 Agent 协作框架 ====================
_orchestrator = None

def get_orchestrator():
    """获取或懒加载多 Agent 编排器实例。"""
    global _orchestrator
    if _orchestrator is None:
        try:
            from agents.graph import LangGraphOrchestrator
            from agents.llm_provider import LLMProvider
            backend = "ollama"
            base_url = CONFIG.get("ollama_url", "http://localhost:11434")
            model = CONFIG.get("ollama_model", "qwen3.5:0.8b")
            # 支持云端 API 配置
            if CONFIG.get("agent_api_backend") == "openai":
                backend = "openai"
                base_url = CONFIG.get("agent_api_url", base_url)
                model = CONFIG.get("agent_api_model", model)
            _orchestrator = LangGraphOrchestrator(LLMProvider(
                backend=backend,
                base_url=base_url,
                model=model,
                api_key=CONFIG.get("agent_api_key", ""),
                temperature=0.2,
                timeout=120,
            ))
            logger.info(f"LangGraph Agent 编排器初始化成功 (backend={backend}, model={model})")
        except Exception as e:
            logger.error(f"多 Agent 编排器初始化失败: {e}", exc_info=True)
            return None
    return _orchestrator

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "monitor_data.db"
CONFIG_PATH = BASE_DIR / "config.json"
STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(exist_ok=True)
UPLOAD_DIR = STATIC_DIR / "uploads"
DEVICE_MODEL_DIR = UPLOAD_DIR / "device_models"
DEVICE_MODEL_DIR.mkdir(parents=True, exist_ok=True)

# ==================== 配置 ====================
CONFIG = {
    "ollama_url": "http://localhost:11434",
    "ollama_model": "qwen3.5:0.8b",
    "ollama_enabled": True,
    "feishu_webhook": "",
    "feishu_verification_token": "",
    "feishu_forward_ai_replies": True,
    "feishu_receive_group_messages": True,
    "feishu_long_connection_enabled": True,
    "feishu_app_id": "",
    "feishu_app_secret": "",
    "thresholds": {
        "temperature": 40.0,
        "humidity": 80.0,
        "vibration": 0.5
    },
    "alarm_trigger_count": 3,
    "alarm_window_seconds": 60,
    "alarm_cooldown_seconds": 300,
    "sensor_interval": 5,
    "database_backend": "mysql",
    "mysql_host": "127.0.0.1",
    "mysql_port": 3307,
    "mysql_user": "root",
    "mysql_password": "",
    "mysql_database": "monitor_system",
    "rag_enabled": True,
    "agent_search_enabled": True,
    "rag_top_k": 4,
    # Agent 系统配置
    "agent_enabled": True,
    "agent_api_backend": "ollama",    # "ollama" | "openai"
    "agent_api_url": "",              # 云端 API 地址（openai 后端时使用）
    "agent_api_model": "",            # 云端模型名（openai 后端时使用）
    "agent_api_key": "",              # 云端 API 密钥
    "selected_device_id": "device-1",
    "devices": [],
    "device_info": {
        "id": "device-1",
        "name": "工业设备 #01",
        "latitude": "39.90923",
        "longitude": "116.397428",
        "registered_at": "",
        "status": "运行中",
        "model_url": "",
        "model_filename": ""
    }
}

def load_config():
    if not CONFIG_PATH.exists():
        return
    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as f:
            saved = json.load(f)
        if isinstance(saved, dict):
            CONFIG.update(saved)
            logger.info(f"已加载本地配置: {CONFIG_PATH}")
    except Exception as e:
        logger.warning(f"读取本地配置失败，继续使用默认配置: {e}")

def save_config():
    try:
        with CONFIG_PATH.open("w", encoding="utf-8") as f:
            json.dump(CONFIG, f, ensure_ascii=False, indent=2)
        logger.info(f"配置已保存: {CONFIG_PATH}")
    except Exception as e:
        logger.warning(f"保存配置失败: {e}")

load_config()

def normalize_device_config():
    legacy = CONFIG.get("device_info") if isinstance(CONFIG.get("device_info"), dict) else {}
    devices = CONFIG.get("devices")
    if not isinstance(devices, list) or not devices:
        device = {
            "id": legacy.get("id") or "device-1",
            "name": legacy.get("name") or "工业设备 #01",
            "latitude": legacy.get("latitude") or "39.90923",
            "longitude": legacy.get("longitude") or "116.397428",
            "registered_at": legacy.get("registered_at") or "",
            "status": legacy.get("status") or "运行中",
            "model_url": legacy.get("model_url") or "",
            "model_filename": legacy.get("model_filename") or ""
        }
        CONFIG["devices"] = [device]
        CONFIG["selected_device_id"] = CONFIG.get("selected_device_id") or device["id"]
    else:
        normalized = []
        for idx, device in enumerate(devices):
            if not isinstance(device, dict):
                continue
            normalized.append({
                "id": device.get("id") or f"device-{idx + 1}",
                "name": device.get("name") or f"工业设备 #{idx + 1:02d}",
                "latitude": device.get("latitude") or "",
                "longitude": device.get("longitude") or "",
                "registered_at": device.get("registered_at") or "",
                "status": device.get("status") or "运行中",
                "model_url": device.get("model_url") or "",
                "model_filename": device.get("model_filename") or ""
            })
        CONFIG["devices"] = normalized or [{
            "id": "device-1",
            "name": "工业设备 #01",
            "latitude": "39.90923",
            "longitude": "116.397428",
            "registered_at": "",
            "status": "运行中",
            "model_url": "",
            "model_filename": ""
        }]
    selected_id = CONFIG.get("selected_device_id")
    if not any(device.get("id") == selected_id for device in CONFIG["devices"]):
        CONFIG["selected_device_id"] = CONFIG["devices"][0]["id"]
    CONFIG["device_info"] = next(
        (device for device in CONFIG["devices"] if device.get("id") == CONFIG["selected_device_id"]),
        CONFIG["devices"][0]
    )

normalize_device_config()

def config_for_cloud() -> Dict[str, Any]:
    hidden_keys = {"mysql_password"}
    return {key: value for key, value in CONFIG.items() if key not in hidden_keys}

def apply_cloud_settings(settings: Dict[str, Any]):
    if not isinstance(settings, dict):
        return
    CONFIG.update(settings)
    normalize_device_config()

# ==================== Ollama 服务管理 ====================
def find_ollama_executable() -> Optional[str]:
    """查找 Windows/macOS/Linux 上可用的 ollama 可执行文件"""
    cli_path = shutil.which("ollama")
    if cli_path:
        return cli_path
    
    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe",
        Path(os.environ.get("ProgramFiles", "")) / "Ollama" / "ollama.exe",
        Path(os.environ.get("ProgramFiles(x86)", "")) / "Ollama" / "ollama.exe",
        Path.home() / "AppData" / "Local" / "Programs" / "Ollama" / "ollama.exe",
        Path("/usr/local/bin/ollama"),
        Path("/usr/bin/ollama"),
    ]
    
    for candidate in candidates:
        try:
            if candidate and candidate.exists():
                return str(candidate)
        except PermissionError:
            # Some Windows environments deny stat() from sandboxed shells even when
            # the current user can execute Ollama from PowerShell.
            if candidate.name.lower() == "ollama.exe":
                return str(candidate)
        except OSError:
            continue
    return None

def is_ollama_running(api_url: str) -> bool:
    try:
        import requests
        response = requests.get(f"{api_url}/api/tags", timeout=2)
        return response.status_code == 200
    except Exception:
        return False

def start_ollama_service(api_url: str) -> Dict:
    """如果 Ollama 未运行，尝试在后台启动 ollama serve。"""
    if is_ollama_running(api_url):
        return {"success": True, "message": "Ollama 服务已运行"}
    
    ollama_exe = find_ollama_executable()
    if not ollama_exe:
        return {
            "success": False,
            "message": "未找到 ollama 可执行文件，请安装 Ollama 或将 ollama 加入 PATH"
        }
    
    logger.info(f"尝试启动 Ollama 服务：{ollama_exe} serve")
    try:
        startupinfo = None
        creationflags = 0
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            creationflags = subprocess.CREATE_NO_WINDOW
        
        subprocess.Popen(
            [ollama_exe, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            startupinfo=startupinfo,
            creationflags=creationflags,
        )
        
        for _ in range(20):
            time.sleep(0.5)
            if is_ollama_running(api_url):
                return {"success": True, "message": "Ollama 服务已启动"}
        
        return {
            "success": False,
            "message": "已尝试启动 Ollama，但服务未在预期时间内响应"
        }
    except Exception as e:
        logger.error(f"启动 Ollama 服务失败：{e}")
        return {
            "success": False,
            "message": f"启动 Ollama 服务失败：{str(e)}"
        }

# ==================== 数据库 ====================
class DatabaseCursor:
    def __init__(self, cursor, backend: str):
        self.cursor = cursor
        self.backend = backend
        self._lastrowid = None

    def _sql(self, sql: str) -> str:
        if self.backend == "mysql":
            sql = sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "INTEGER PRIMARY KEY AUTO_INCREMENT")
            sql = sql.replace("TEXT PRIMARY KEY", "VARCHAR(191) PRIMARY KEY")
            sql = sql.replace("?", "%s")
            sql = re.sub(r"ON CONFLICT\s*\([^)]*\)\s*DO UPDATE SET", "ON DUPLICATE KEY UPDATE", sql)
            sql = re.sub(r"EXCLUDED\.([A-Za-z_][A-Za-z0-9_]*)", r"VALUES(\1)", sql)
        return sql

    def execute(self, sql: str, params: tuple = ()):
        self.cursor.execute(self._sql(sql), params)
        self._lastrowid = getattr(self.cursor, "lastrowid", None)
        return self

    def fetchall(self):
        return self.cursor.fetchall()

    def fetchone(self):
        return self.cursor.fetchone()

    @property
    def lastrowid(self):
        return self._lastrowid or getattr(self.cursor, "lastrowid", None)


class DatabaseConnection:
    def __init__(self, conn, backend: str):
        self.conn = conn
        self.backend = backend

    def cursor(self):
        return DatabaseCursor(self.conn.cursor(), self.backend)

    def commit(self):
        self.conn.commit()

    def close(self):
        self.conn.close()


# MySQL 连接失败后的冷却时间，避免每个请求都卡在连接超时上。
_MYSQL_RETRY_AFTER = 0.0
_MYSQL_LAST_ERROR = ""


def get_database_backend() -> str:
    backend = str(CONFIG.get("database_backend") or "sqlite").strip().lower()
    return "mysql" if backend == "mysql" else "sqlite"


def mysql_settings(overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    settings = {
        "host": str(CONFIG.get("mysql_host") or "127.0.0.1").strip(),
        "port": int(CONFIG.get("mysql_port") or 3307),
        "user": str(CONFIG.get("mysql_user") or "root").strip(),
        "password": str(CONFIG.get("mysql_password") or ""),
        "database": str(CONFIG.get("mysql_database") or "monitor_system").strip(),
    }
    if overrides:
        for key in ("host", "user", "password", "database"):
            value = overrides.get(key)
            if value is None:
                continue
            if key == "password":
                settings[key] = str(value)
            elif str(value).strip() != "":
                settings[key] = str(value).strip()
        port = overrides.get("port")
        if port not in (None, ""):
            try:
                settings["port"] = int(port)
            except (TypeError, ValueError):
                pass
    settings["database"] = re.sub(r"[^A-Za-z0-9_]+", "_", settings["database"]) or "monitor_system"
    return settings


def connect_mysql(overrides: Optional[Dict[str, Any]] = None, create_database: bool = True, timeout: int = 4):
    import pymysql
    settings = mysql_settings(overrides)
    if create_database:
        server = pymysql.connect(
            host=settings["host"], port=settings["port"], user=settings["user"],
            password=settings["password"], charset="utf8mb4",
            connect_timeout=timeout, autocommit=True,
        )
        try:
            with server.cursor() as cursor:
                cursor.execute(
                    "CREATE DATABASE IF NOT EXISTS `" + settings["database"] + "` "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
        finally:
            server.close()
    return pymysql.connect(
        host=settings["host"], port=settings["port"], user=settings["user"],
        password=settings["password"], database=settings["database"],
        charset="utf8mb4", connect_timeout=timeout, autocommit=False,
    )


def connect_cloud_database():
    """连接配置中的 MySQL；失败时记录错误并在冷却期内直接回退到 SQLite。"""
    global _MYSQL_RETRY_AFTER, _MYSQL_LAST_ERROR
    if get_database_backend() != "mysql":
        return None
    if time.time() < _MYSQL_RETRY_AFTER:
        return None
    try:
        conn = connect_mysql()
        _MYSQL_LAST_ERROR = ""
        return conn
    except Exception as e:
        _MYSQL_LAST_ERROR = str(e)
        _MYSQL_RETRY_AFTER = time.time() + 30
        logger.warning(f"MySQL 连接失败，暂时回退到 SQLite: {e}")
        return None


def init_cloud_tables(conn: DatabaseConnection):
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS app_settings (
            setting_key TEXT PRIMARY KEY,
            setting_value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS devices (
            id TEXT PRIMARY KEY,
            name TEXT,
            latitude TEXT,
            longitude TEXT,
            registered_at TEXT,
            status TEXT,
            model_url TEXT,
            model_filename TEXT,
            updated_at TEXT NOT NULL
        )
    ''')
    conn.commit()


def load_cloud_config() -> bool:
    if get_database_backend() != "mysql":
        return False
    raw_conn = connect_cloud_database()
    if not raw_conn:
        return False
    conn = DatabaseConnection(raw_conn, "mysql")
    try:
        init_cloud_tables(conn)
        c = conn.cursor()
        c.execute("SELECT setting_value FROM app_settings WHERE setting_key = ?", ("config",))
        row = c.fetchone()
        if not row:
            return False
        settings = json.loads(row[0])
        apply_cloud_settings(settings)
        logger.info("已从云端数据库加载配置")
        return True
    except Exception as e:
        logger.warning(f"读取云端配置失败，继续使用本地配置: {e}")
        return False
    finally:
        conn.close()


def save_cloud_config() -> bool:
    if get_database_backend() != "mysql":
        return False
    raw_conn = connect_cloud_database()
    if not raw_conn:
        return False
    conn = DatabaseConnection(raw_conn, "mysql")
    try:
        init_cloud_tables(conn)
        now = datetime.now().isoformat()
        c = conn.cursor()
        c.execute(
            """
            INSERT INTO app_settings (setting_key, setting_value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT (setting_key) DO UPDATE SET setting_value = EXCLUDED.setting_value, updated_at = EXCLUDED.updated_at
            """,
            ("config", json.dumps(config_for_cloud(), ensure_ascii=False), now)
        )
        for device in CONFIG.get("devices", []):
            c.execute(
                """
                INSERT INTO devices (id, name, latitude, longitude, registered_at, status, model_url, model_filename, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    latitude = EXCLUDED.latitude,
                    longitude = EXCLUDED.longitude,
                    registered_at = EXCLUDED.registered_at,
                    status = EXCLUDED.status,
                    model_url = EXCLUDED.model_url,
                    model_filename = EXCLUDED.model_filename,
                    updated_at = EXCLUDED.updated_at
                """,
                (
                    device.get("id"),
                    device.get("name", ""),
                    device.get("latitude", ""),
                    device.get("longitude", ""),
                    device.get("registered_at", ""),
                    device.get("status", ""),
                    device.get("model_url", ""),
                    device.get("model_filename", ""),
                    now
                )
            )
        conn.commit()
        logger.info("配置已同步到云端数据库")
        return True
    except Exception as e:
        logger.warning(f"同步配置到云端数据库失败: {e}")
        return False
    finally:
        conn.close()


def init_db():
    backend = get_database_backend()
    raw_conn = connect_cloud_database() if backend == "mysql" else None
    if raw_conn:
        conn = DatabaseConnection(raw_conn, "mysql")
    else:
        conn = DatabaseConnection(sqlite3.connect(DB_PATH), "sqlite")
    c = conn.cursor()
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS sensor_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            temperature REAL,
            humidity REAL,
            pressure REAL,
            vibration REAL
        )
    ''')
    # Non-destructive migration for installations created before multi-device data.
    if conn.backend == "mysql":
        c.execute(
            "SELECT COLUMN_NAME FROM information_schema.columns "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'sensor_data'"
        )
        columns = {str(row[0]).lower() for row in c.fetchall()}
        if "device_id" not in columns:
            c.execute("ALTER TABLE sensor_data ADD COLUMN device_id VARCHAR(191)")
        if "area" not in columns:
            c.execute("ALTER TABLE sensor_data ADD COLUMN area VARCHAR(191)")
    else:
        c.execute("PRAGMA table_info(sensor_data)")
        columns = {row[1] for row in c.fetchall()}
        if "device_id" not in columns:
            c.execute("ALTER TABLE sensor_data ADD COLUMN device_id TEXT")
        if "area" not in columns:
            c.execute("ALTER TABLE sensor_data ADD COLUMN area TEXT")

    c.execute('''
        CREATE TABLE IF NOT EXISTS sensor_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            device_id TEXT,
            area TEXT,
            sensor_type TEXT NOT NULL,
            value REAL NOT NULL,
            threshold REAL,
            status TEXT NOT NULL
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS anomaly_sensor_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            device_id TEXT,
            area TEXT,
            sensor_type TEXT NOT NULL,
            value REAL NOT NULL,
            threshold REAL,
            status TEXT NOT NULL,
            alert_batch_id TEXT
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            sensor_type TEXT NOT NULL,
            value REAL NOT NULL,
            threshold REAL NOT NULL,
            level TEXT NOT NULL,
            handled INTEGER DEFAULT 0
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS camera_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            event_type TEXT,
            image_path TEXT
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS rag_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            filename TEXT NOT NULL,
            content_type TEXT,
            size INTEGER DEFAULT 0,
            chunk_count INTEGER DEFAULT 0
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS rag_chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL,
            chunk_index INTEGER NOT NULL,
            content TEXT NOT NULL,
            embedding TEXT
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS skills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            name TEXT NOT NULL,
            filename TEXT NOT NULL,
            content TEXT NOT NULL
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS prediction_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL, metric TEXT NOT NULL, model_name TEXT NOT NULL,
            prediction_time TEXT NOT NULL, horizon INTEGER NOT NULL,
            prediction_values TEXT NOT NULL, created_at TEXT NOT NULL
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS risk_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL, risk_level TEXT NOT NULL, risk_score REAL NOT NULL,
            anomaly_score REAL DEFAULT 0, prediction_score REAL DEFAULT 0,
            reason TEXT, created_at TEXT NOT NULL
        )
    ''')

    if conn.backend == "mysql":
        init_cloud_tables(conn)
    
    conn.commit()
    conn.close()
    if conn.backend == "mysql":
        settings = mysql_settings()
        logger.info(f"数据库初始化完成: MySQL {settings['host']}:{settings['port']}/{settings['database']}")
    else:
        logger.info(f"数据库初始化完成: SQLite {DB_PATH}")

def get_db_connection():
    backend = get_database_backend()
    if backend == "mysql":
        raw_conn = connect_cloud_database()
        if raw_conn:
            return DatabaseConnection(raw_conn, "mysql")
    return DatabaseConnection(sqlite3.connect(DB_PATH), "sqlite")

# ==================== 数据模型 ====================
class SensorData(BaseModel):
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    pressure: Optional[float] = None
    vibration: Optional[float] = None
    device_id: Optional[str] = "raspberry-pi-5"
    area: Optional[str] = "A区"
    timestamp: Optional[str] = None

class RaspberrySensorPayload(BaseModel):
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    pressure: Optional[float] = None
    vibration: Optional[float] = None
    device_id: Optional[str] = "raspberry-pi-5"
    area: Optional[str] = "A区"
    timestamp: Optional[str] = None

class ChatRequest(BaseModel):
    message: str
    model: Optional[str] = None
    api_url: Optional[str] = None

class PredictionRequest(BaseModel):
    device_id: str = Field(min_length=1, max_length=128)
    metric: str = "temperature"
    horizon: int = Field(default=10, ge=1, le=120)

class RiskRequest(BaseModel):
    device_id: str = Field(min_length=1, max_length=128)
class OllamaTestRequest(BaseModel):
    model: Optional[str] = None
    api_url: Optional[str] = None

class DatabaseTestRequest(BaseModel):
    backend: Optional[str] = None
    mysql_host: Optional[str] = None
    mysql_port: Optional[int] = None
    mysql_user: Optional[str] = None
    mysql_password: Optional[str] = None
    mysql_database: Optional[str] = None

class SkillUploadRequest(BaseModel):
    name: str
    content: str
    filename: Optional[str] = None

# ==================== 真实传感器读取适配器 ====================
class SensorReader:
    """Legacy adapter that exposes only the latest Raspberry Pi reading."""
    def read(self) -> SensorData:
        live = globals().get("latest_pi_sensor_data", {})
        return SensorData(
            temperature=live.get("temperature"), humidity=live.get("humidity"),
            pressure=live.get("pressure"), vibration=live.get("vibration"),
            device_id=live.get("device_id"), area=live.get("area"), timestamp=live.get("timestamp"),
        )

# ==================== 摄像头 ====================
class CameraCapture:
    def __init__(self):
        self.snapshot_count = 0
    
    def capture_frame(self) -> Optional[bytes]:
        try:
            from PIL import Image, ImageDraw, ImageFont
            import io
            
            img = Image.new('RGB', (640, 480), color=(31, 41, 55))
            draw = ImageDraw.Draw(img)
            
            draw.rectangle([10, 10, 630, 470], outline=(59, 130, 246), width=2)
            
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            draw.text((20, 30), f"模拟摄像头 #{self.snapshot_count + 1}", fill=(255, 255, 255))
            draw.text((20, 60), f"时间: {timestamp}", fill=(156, 163, 175))
            draw.text((20, 90), "演示模式 - 未连接真实摄像头", fill=(239, 68, 68))
            
            center_x, center_y = 320, 280
            draw.ellipse([center_x-60, center_y-60, center_x+60, center_y+60], outline=(245, 158, 11), width=3)
            draw.ellipse([center_x-40, center_y-40, center_x+40, center_y+40], outline=(16, 185, 129), width=2)
            draw.ellipse([center_x-20, center_y-20, center_x+20, center_y+20], fill=(59, 130, 246))
            
            buffer = io.BytesIO()
            img.save(buffer, format='JPEG', quality=85)
            return buffer.getvalue()
        except ImportError:
            return None
    
    def save_snapshot(self, label: str = "manual") -> Optional[str]:
        frame = self.capture_frame()
        if frame is None:
            return None
        
        self.snapshot_count += 1
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"snapshot_{label}_{timestamp}_{self.snapshot_count}.jpg"
        filepath = STATIC_DIR / filename
        
        try:
            with open(filepath, 'wb') as f:
                f.write(frame)
            return f"/static/{filename}"
        except Exception as e:
            logger.error(f"快照保存失败: {e}")
        return None
    
    def release(self):
        pass

# ==================== WebSocket 管理 ====================
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
    
    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
    
    async def broadcast(self, message: dict):
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)
        for ws in disconnected:
            self.disconnect(ws)

manager = ConnectionManager()
alert_id_counter = count(1)

def next_alert_id() -> int:
    return int(time.time() * 1000) * 1000 + next(alert_id_counter) % 1000

# ==================== 报警检测 ====================
class AlarmChecker:
    def __init__(self):
        self.anomaly_windows = {}
        self.last_alert_time = {}
        self.alert_lock = threading.Lock()
    
    def check(self, data: SensorData, timestamp: str = None, device_id: str = "", area: str = "") -> List[Dict]:
        alerts = []
        now = datetime.now()
        event_time = timestamp or now.isoformat()
        window_seconds = int(CONFIG.get("alarm_window_seconds", 60))
        trigger_count = 1
        
        for sensor_type, value in [
            ("temperature", data.temperature),
            ("humidity", data.humidity),
            ("vibration", data.vibration)
        ]:
            if value is None:
                continue
            
            threshold = CONFIG["thresholds"].get(sensor_type)
            if threshold is None:
                continue
            
            key = f"{device_id}:{area}:{sensor_type}"
            if value <= threshold:
                self.anomaly_windows.pop(key, None)
                continue

            if value > threshold:
                dedupe_key = f"{area}:{sensor_type}"
                points = self.anomaly_windows.get(key, [])
                points.append({"time": now, "timestamp": event_time, "value": value})
                cutoff = now - timedelta(seconds=window_seconds)
                points = [point for point in points if point["time"] >= cutoff]
                self.anomaly_windows[key] = points

                if len(points) >= trigger_count:
                    level = "danger" if any(point["value"] > threshold * 1.2 for point in points) else "warning"
                    logger.warning(
                        "触发报警: type=%s value=%s threshold=%s count=%s window=%ss area=%s",
                        sensor_type, value, threshold, len(points), window_seconds, area
                    )
                    alerts.append({
                        "type": sensor_type,
                        "value": value,
                        "threshold": threshold,
                        "level": level,
                        "count": len(points),
                        "window_seconds": window_seconds,
                        "start_time": points[0]["timestamp"],
                        "end_time": points[-1]["timestamp"],
                        "device_id": device_id,
                        "area": area or "未知区域",
                        "batch_id": f"{sensor_type}-{int(now.timestamp())}"
                    })
                    self.last_alert_time[key] = now
        
        return alerts
    
    def save_alert(self, alert: Dict):
        global latest_alerts
        dedupe_key = f"{alert.get('area')}:{alert.get('type')}"
        with self.alert_lock:
            existing = next((item for item in latest_alerts if item.get("dedupe_key") == dedupe_key and not item.get("handled")), None)
            if existing:
                existing["time"] = datetime.now().isoformat()
                existing["level"] = alert.get("level", existing.get("level", "warning"))
                existing["detail"] = alert
                self._notify_websocket(alert, int(existing.get("id", next_alert_id())))
                return
            alert_id = next_alert_id()
            alert_record = {
                "id": alert_id,
                "title": f"{SENSOR_META.get(alert['type'], {}).get('label', alert['type'])}异常",
                "time": datetime.now().isoformat(),
                "source": alert.get("area") or "树莓派",
                "level": alert.get("level", "warning"),
                "detail": alert,
                "dedupe_key": dedupe_key,
                "handled": False
            }
            latest_alerts = [alert_record] + latest_alerts[:49]
        threading.Thread(target=send_feishu_text, args=(build_alarm_message(alert),), daemon=True).start()
        self._notify_websocket(alert, alert_id)
        try:
            conn = get_db_connection()
            c = conn.cursor()
            c.execute(
                "INSERT INTO alerts (timestamp, sensor_type, value, threshold, level) VALUES (?, ?, ?, ?, ?)",
                (datetime.now().isoformat(), alert["type"], alert["value"], alert["threshold"], alert["level"])
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"保存报警记录到数据库失败: {e}")
    
    def handle_alert(self, alert_id: int) -> int:
        global latest_alerts
        with self.alert_lock:
            handled = next((alert for alert in latest_alerts if int(alert.get("id", 0)) == alert_id), None)
            if handled:
                handled["handled"] = True
                handled["handled_at"] = datetime.now().isoformat()
            remaining = sum(1 for alert in latest_alerts if not alert.get("handled"))
        try:
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("UPDATE alerts SET handled = 1 WHERE id = ?", (alert_id,))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"标记报警已处理失败: {e}")
        return remaining

    def _notify_feishu(self, alert: Dict, alert_id: int):
        if not CONFIG["feishu_webhook"]:
            return
        try:
            import requests
            messages = {"temperature": "温度", "humidity": "湿度", "vibration": "振动"}
            level_emoji = "🔴" if alert["level"] == "danger" else "🟡"
            
            content = f"""{level_emoji} 工业环境监控报警

传感器: {messages.get(alert['type'], alert['type'])}
当前值: {alert['value']}
阈值: {alert['threshold']}
时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

请及时处理！"""

            requests.post(CONFIG["feishu_webhook"], json={"msg_type": "text", "content": {"text": content}}, timeout=5)
        except Exception as e:
            logger.warning(f"飞书通知失败: {e}")
    
    def _notify_websocket(self, alert: Dict, alert_id: int):
        messages = {"temperature": "温度偏高", "humidity": "湿度偏高", "vibration": "振动超标"}
        level_emoji = "🚨" if alert["level"] == "danger" else "⚠️"
        
        notification = {
            "type": "alert",
            "data": {
                "id": alert_id,
                "title": f"{level_emoji} {messages.get(alert['type'], alert['type'])}",
                "level": alert["level"],
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "source": "传感器节点"
            }
        }
        try:
            asyncio.get_running_loop().create_task(manager.broadcast(notification))
        except RuntimeError:
            logger.debug("当前没有运行中的事件循环，跳过报警 WebSocket 广播")

# ==================== AI 对话 ====================
def build_ai_system_prompt(context: str) -> str:
    return f"""你是工业环境监控系统的 AI 助手，只输出面向用户的最终答案。

当前传感器数据：{context}

输出规则：
1. 禁止输出思考过程、推理过程、用户意图分析、草稿、"首先，用户..." 这类内部说明。
2. 问候类消息只做简短问候，并引导用户询问环境状态、报警、趋势、设备状态。
3. 具体业务问题必须按以下格式回复：
当前数据
- 用 1-3 条概括可用数据；没有数据时说明"当前暂无真实传感器数据"。

简短分析
- 用 1-3 条说明状态或风险，不要展开长篇推理。

建议
- 给出 1-3 条可执行建议。
4. 如果当前上下文包含"知识库片段"，资料、文档、检索类问题必须优先依据知识库片段回答；片段不足时直接说明"知识库中未找到足够信息"，不要编造。
5. 每条尽量短，语言专业、直接、中文回复。"""

def is_greeting_message(message: str) -> bool:
    text = message.strip().lower()
    greetings = {"你好", "您好", "hello", "hi", "嗨", "在吗", "在不在"}
    return text in greetings or text in {f"{g}！" for g in greetings} or text in {f"{g}!" for g in greetings}

def greeting_reply() -> str:
    return "您好，我是工业环境监控系统 AI 助手。\n\n您可以询问：\n- 当前环境状态\n- 报警与异常情况\n- 温湿度趋势\n- 设备运行状态"

async def send_text_stream(websocket: WebSocket, text: str, chunk_size: int = 8, delay: float = 0.02):
    for i in range(0, len(text), chunk_size):
        try:
            await websocket.send_json({"type": "content", "content": text[i:i + chunk_size]})
        except WebSocketDisconnect:
            logger.info("AI 对话连接已断开，停止发送流式文本")
            return False
        except RuntimeError as e:
            if "close message has been sent" in str(e):
                logger.info("AI 对话连接已关闭，停止发送流式文本")
                return False
            raise
        await asyncio.sleep(delay)
    return True

def strip_thinking_text(text: str) -> str:
    """移除常见模型思考标签和明显的内部推理开头。"""
    import re
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.IGNORECASE | re.DOTALL)
    cleaned = re.sub(r"<thinking>.*?</thinking>", "", cleaned, flags=re.IGNORECASE | re.DOTALL)
    if "</think>" in cleaned.lower():
        lower_cleaned = cleaned.lower()
        cleaned = cleaned[lower_cleaned.rfind("</think>") + len("</think>"):]
    if "</thinking>" in cleaned.lower():
        lower_cleaned = cleaned.lower()
        cleaned = cleaned[lower_cleaned.rfind("</thinking>") + len("</thinking>"):]
    blocked_prefixes = (
        "首先，用户",
        "首先, 用户",
        "用户说",
        "我需要",
        "作为工业环境监控系统的AI助手，我需要",
        "作为工业环境监控系统的 AI 助手，我需要",
    )
    for prefix in blocked_prefixes:
        if cleaned.lstrip().startswith(prefix):
            return ""
    return cleaned

def send_feishu_text(text: str) -> bool:
    webhook = CONFIG.get("feishu_webhook", "").strip()
    if not webhook:
        logger.warning("飞书机器人 webhook 未配置，消息未发送")
        return False
    try:
        import requests
        response = requests.post(
            webhook,
            json={"msg_type": "text", "content": {"text": text}},
            timeout=8
        )
        if response.status_code != 200:
            logger.warning("飞书机器人发送失败: status=%s body=%s", response.status_code, response.text[:300])
            return False
        logger.info("飞书机器人消息已发送")
        return True
    except Exception as e:
        logger.warning("飞书机器人发送异常: %s", e, exc_info=True)
        return False


def format_timestamp(value: str = None) -> str:
    if not value:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(value)


def build_alarm_message(alert: Dict) -> str:
    names = {"temperature": "温度", "humidity": "湿度", "vibration": "振动"}
    level = "严重" if alert.get("level") == "danger" else "预警"
    area = alert.get("area") or "未知区域"
    return f"""{level} 工业环境监控报警

时间段: {format_timestamp(alert.get("start_time"))} 至 {format_timestamp(alert.get("end_time"))}
异常类型: {names.get(alert.get("type"), alert.get("type"))}
异常数量: {alert.get("count", 1)} 条
最新数值: {alert.get("value")}
阈值: {alert.get("threshold")}
设备: {alert.get("device_id") or "未知设备"}
判断: {area}有问题

请及时处理。"""

def send_feishu_text_fixed(text: str) -> bool:
    return send_feishu_text(text)

def build_alarm_message_fixed(alert: Dict) -> str:
    names = {"temperature": "温度", "humidity": "湿度", "vibration": "振动"}
    level = "严重" if alert.get("level") == "danger" else "预警"
    area = alert.get("area") or "未知区域"
    return f"""{level} 工业环境监控报警

时间段: {format_timestamp(alert.get("start_time"))} 至 {format_timestamp(alert.get("end_time"))}
异常类型: {names.get(alert.get("type"), alert.get("type"))}
异常数量: {alert.get("count", 1)} 条
最新数值: {alert.get("value")}
阈值: {alert.get("threshold")}
设备: {alert.get("device_id") or "未知设备"}
判断: {area}有问题
请及时处理。"""

def extract_feishu_text_message(payload: dict) -> Optional[str]:
    event = payload.get("event", {})
    message = event.get("message", {})
    msg_type = message.get("message_type")
    if msg_type and msg_type != "text":
        return None
    
    content = message.get("content", "")
    try:
        content_obj = json.loads(content) if isinstance(content, str) else content
        text = content_obj.get("text", "") if isinstance(content_obj, dict) else ""
    except Exception:
        text = content if isinstance(content, str) else ""
    
    return text.strip() or None

def build_sensor_context() -> str:
    context_parts = []
    latest = sensor_reader.read()
    if latest.temperature: context_parts.append(f"温度：{latest.temperature}°C")
    if latest.humidity: context_parts.append(f"湿度：{latest.humidity}%")
    if latest.pressure: context_parts.append(f"气压：{latest.pressure}hPa")
    if latest.vibration: context_parts.append(f"振动：{latest.vibration}mm/s")
    return ", ".join(context_parts) or "暂无数据"

def extract_uploaded_text(filename: str, content_type: str, data: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(data))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as e:
            logger.warning(f"PDF 解析失败，按文本读取: {e}")
    if suffix in {".docx", ".doc"}:
        try:
            import docx
            doc = docx.Document(io.BytesIO(data))
            return "\n".join(p.text for p in doc.paragraphs)
        except Exception as e:
            logger.warning(f"Word 解析失败，按文本读取: {e}")
    for encoding in ("utf-8", "gb18030", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return ""

def split_text_for_rag(text: str) -> List[str]:
    clean = re.sub(r"\s+", " ", text).strip()
    if not clean:
        return []
    try:
        from langchain_text_splitters import RecursiveCharacterTextSplitter
        splitter = RecursiveCharacterTextSplitter(chunk_size=900, chunk_overlap=120)
        return [chunk.strip() for chunk in splitter.split_text(clean) if chunk.strip()]
    except Exception:
        chunks = []
        step = 780
        size = 900
        for i in range(0, len(clean), step):
            chunk = clean[i:i + size].strip()
            if chunk:
                chunks.append(chunk)
        return chunks

def get_ollama_embedding(text: str) -> Optional[List[float]]:
    try:
        import requests
        response = requests.post(
            f"{CONFIG.get('ollama_url', 'http://localhost:11434')}/api/embeddings",
            json={"model": CONFIG.get("ollama_model"), "prompt": text[:4000]},
            timeout=30,
        )
        if response.status_code == 200:
            embedding = response.json().get("embedding")
            if isinstance(embedding, list):
                return embedding
    except Exception as e:
        logger.debug(f"生成向量失败，将使用关键词检索: {e}")
    return None

def cosine_similarity(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0

def extract_rag_terms(query: str) -> List[str]:
    text = query.lower()
    raw_terms = [t for t in re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]+", text) if len(t) > 1]
    terms = set(raw_terms)
    for term in raw_terms:
        if re.fullmatch(r"[\u4e00-\u9fff]+", term):
            max_size = min(4, len(term))
            for size in range(2, max_size + 1):
                for i in range(0, len(term) - size + 1):
                    terms.add(term[i:i + size])
    stop_terms = {"什么", "怎么", "如何", "一下", "资料", "文档", "搜索", "检索", "知识库"}
    return sorted((t for t in terms if t not in stop_terms), key=len, reverse=True)

def search_rag_context(query: str, top_k: Optional[int] = None) -> str:
    if not CONFIG.get("rag_enabled", True):
        return ""
    top_k = top_k or int(CONFIG.get("rag_top_k", 4))
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        SELECT rag_chunks.content, rag_chunks.embedding, rag_documents.filename
        FROM rag_chunks
        LEFT JOIN rag_documents ON rag_documents.id = rag_chunks.document_id
        ORDER BY rag_chunks.id DESC
        LIMIT 300
    """)
    rows = c.fetchall()
    conn.close()
    if not rows:
        return ""

    query_embedding = get_ollama_embedding(query)
    terms = extract_rag_terms(query)
    scored = []
    for content, embedding_json, filename in rows:
        score = 0.0
        if query_embedding and embedding_json:
            try:
                score = cosine_similarity(query_embedding, json.loads(embedding_json))
            except Exception:
                score = 0.0
        if terms:
            lower_content = content.lower()
            lower_filename = (filename or "").lower()
            keyword_score = sum(2 if term in lower_filename else 1 for term in terms if term in lower_content or term in lower_filename)
            score = max(score, float(keyword_score))
        if score > 0:
            source = f"来源文档：{filename}\n" if filename else ""
            scored.append((score, source + content))
    scored.sort(key=lambda item: item[0], reverse=True)
    selected = [content for _, content in scored[:top_k]]
    if not selected:
        return ""
    return "\n\n知识库片段：\n" + "\n---\n".join(selected)

def is_knowledge_search_request(message: str) -> bool:
    text = message.lower()
    triggers = (
        "资料", "文档", "知识库", "向量库", "向量知识库", "知识", "文件", "手册",
        "说明书", "规范", "制度", "检索", "查资料", "找资料", "搜索资料",
        "rag", "knowledge", "document", "docs", "manual"
    )
    return any(trigger in text for trigger in triggers)

def should_use_online_search(message: str) -> bool:
    if not CONFIG.get("agent_search_enabled", True):
        return False
    text = message.lower()
    explicit_online_triggers = ("联网", "网上", "互联网", "新闻", "最新", "latest", "today", "web", "online")
    if is_knowledge_search_request(message) and not any(trigger in text for trigger in explicit_online_triggers):
        return False
    triggers = ("搜索", "联网", "网上", "最新", "今天", "新闻", "查一下", "search", "latest", "today")
    return any(trigger in text for trigger in triggers)

def online_search_context(query: str, max_results: int = 3) -> str:
    try:
        from langchain_community.tools import DuckDuckGoSearchResults
        tool = DuckDuckGoSearchResults(num_results=max_results, output_format="list")
        results = tool.invoke(query)
        lines = []
        for item in results if isinstance(results, list) else []:
            title = item.get("title") or ""
            snippet = item.get("snippet") or item.get("body") or ""
            link = item.get("link") or item.get("href") or ""
            lines.append(f"- {title}: {snippet} {link}".strip())
        if lines:
            return "\n\n在线搜索结果：\n" + "\n".join(lines)
    except Exception as e:
        logger.debug(f"LangChain 搜索工具不可用，尝试 duckduckgo_search: {e}")
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        lines = []
        for item in results:
            title = item.get("title") or ""
            body = item.get("body") or ""
            href = item.get("href") or ""
            lines.append(f"- {title}: {body} {href}".strip())
        return "\n\n在线搜索结果：\n" + "\n".join(lines) if lines else ""
    except Exception as e:
        logger.warning(f"在线搜索失败: {e}")
        return ""

def build_augmented_context(message: str, context: str, include_search: bool = True) -> str:
    parts = [context] if context else []
    rag_context = search_rag_context(message)
    if rag_context:
        parts.append(rag_context)
    if include_search and should_use_online_search(message):
        search_context = online_search_context(message)
        if search_context:
            parts.append(search_context)
    return "\n\n".join(parts)

def send_feishu_app_message(chat_id: str, text: str) -> bool:
    try:
        import requests
        
        token_response = requests.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={
                "app_id": CONFIG["feishu_app_id"],
                "app_secret": CONFIG["feishu_app_secret"],
            },
            timeout=10,
        )
        token_data = token_response.json()
        tenant_access_token = token_data.get("tenant_access_token")
        if not tenant_access_token:
            logger.warning(f"获取飞书 tenant_access_token 失败：{token_data}")
            return False
        
        response = requests.post(
            "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id",
            headers={"Authorization": f"Bearer {tenant_access_token}"},
            json={
                "receive_id": chat_id,
                "msg_type": "text",
                "content": json.dumps({"text": text}, ensure_ascii=False),
            },
            timeout=10,
        )
        result = response.json()
        if result.get("code") != 0:
            logger.warning(f"飞书应用消息发送失败：{result}")
            return False
        return True
    except Exception as e:
        logger.warning(f"飞书应用消息发送失败：{e}")
        return False

def handle_feishu_long_message(chat_id: str, text: str):
    try:
        if not text or text.startswith("网页 AI 回复：") or text.startswith("飞书群消息回复："):
            return
        logger.info(f"长连接收到飞书群消息：chat_id={chat_id}, text={text[:80]}")
        reply = asyncio.run(chat_with_ollama(text, build_sensor_context()))
        ok = send_feishu_app_message(chat_id, reply)
        if not ok:
            send_feishu_text_fixed(f"飞书群消息回复：\n{reply}")
        logger.info(f"长连接飞书群消息回复结果：{ok}")
    except Exception as e:
        logger.error(f"处理飞书长连接消息失败：{e}", exc_info=True)

feishu_ws_client = None
feishu_ws_thread = None

def start_feishu_long_connection():
    global feishu_ws_client, feishu_ws_thread
    if not CONFIG.get("feishu_long_connection_enabled", False):
        logger.info("飞书长连接未启用")
        return
    if feishu_ws_thread and feishu_ws_thread.is_alive():
        return
    if not CONFIG.get("feishu_app_id") or not CONFIG.get("feishu_app_secret"):
        logger.warning("飞书长连接未启动：缺少 App ID 或 App Secret")
        return
    
    def run_client():
        global feishu_ws_client
        try:
            import lark_oapi as lark
            from lark_oapi.api.im.v1 import P2ImMessageReceiveV1
            
            def on_message(data: P2ImMessageReceiveV1):
                try:
                    event_data = json.loads(lark.JSON.marshal(data))
                    event = event_data.get("event", {})
                    message = event.get("message", {})
                    if message.get("message_type") != "text":
                        return
                    chat_id = message.get("chat_id")
                    content = message.get("content", "{}")
                    content_obj = json.loads(content) if isinstance(content, str) else content
                    text = (content_obj.get("text") or "").strip()
                    if chat_id and text:
                        threading.Thread(
                            target=handle_feishu_long_message,
                            args=(chat_id, text),
                            daemon=True
                        ).start()
                except Exception as e:
                    logger.error(f"解析飞书长连接消息失败：{e}", exc_info=True)
            
            event_handler = lark.EventDispatcherHandler.builder("", "") \
                .register_p2_im_message_receive_v1(on_message) \
                .build()
            
            feishu_ws_client = lark.ws.Client(
                CONFIG["feishu_app_id"],
                CONFIG["feishu_app_secret"],
                event_handler=event_handler,
                log_level=lark.LogLevel.INFO
            )
            logger.info("飞书长连接监听启动中...")
            feishu_ws_client.start()
        except ImportError:
            logger.warning("未安装 lark-oapi，飞书长连接无法启动。请执行：pip install lark-oapi")
        except Exception as e:
            logger.error(f"飞书长连接监听退出：{e}", exc_info=True)
    
    feishu_ws_thread = threading.Thread(target=run_client, daemon=True)
    feishu_ws_thread.start()

async def chat_with_ollama(message: str, context: str = "") -> str:
    if not CONFIG.get("ollama_enabled", False):
        return generate_mock_reply(message, context)
    
    try:
        import requests
        
        if is_greeting_message(message):
            return greeting_reply()
        
        context = build_augmented_context(message, context)
        system_prompt = build_ai_system_prompt(context)
        
        response = requests.post(
            f"{CONFIG['ollama_url']}/api/chat",
            json={
                "model": CONFIG["ollama_model"],
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"/no_think\n{message}"}
                ],
                "stream": False,
                "think": False
            },
            timeout=60
        )
        
        if response.status_code == 200:
            result = response.json()
            content = result.get("message", {}).get("content", "抱歉，我无法理解您的问题。")
            return strip_thinking_text(content) or "我已收到问题，但模型返回了内部推理内容。请换一种问法或重试。"
        else:
            return "AI 服务暂时不可用，请稍后重试。"
    except Exception as e:
        logger.error(f"Ollama 连接失败: {e}")
        return generate_mock_reply(message, context)

def generate_mock_reply(message: str, context: str = "") -> str:
    msg_lower = message.lower()
    
    if "环境" in message or "怎么样" in message:
        return f"""当前环境状态：
- {context or '暂无实时数据'}

系统运行在演示模式，所有功能正常。接入真实传感器后可获取实时数据。"""
    
    elif "温度" in message:
        return "当前温度在正常范围内波动。演示模式下使用模拟数据，趋势显示正常。"
    
    elif "湿度" in message:
        return "当前湿度在正常范围内。演示模式下数据周期性波动，模拟真实环境变化。"
    
    elif "趋势" in message or "图表" in message:
        return "历史数据趋势已更新。您可以在数据分析页面查看详细的温度、湿度和气压趋势图表。"
    
    elif "报警" in message or "异常" in message:
        return "当前无异常报警。系统持续监控传感器数据，超过阈值时会自动推送通知。"
    
    elif "报告" in message:
        return f"""今日系统报告：
运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}
状态: 正常
数据点: 演示模式
建议: 系统运行稳定，无需干预。"""
    
    else:
        return f"""收到您的问题: "{message}"

当前系统处于演示模式。我可以帮您：
1. 查看当前环境状态
2. 分析温度/湿度趋势
3. 生成系统报告
4. 检查报警状态

请尝试具体提问，我会为您提供更详细的回答。"""

# ==================== FastAPI 应用 ====================
app = FastAPI(title="工业环境监控系统", version="1.0.0")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

sensor_reader = SensorReader()
camera = CameraCapture()
alarm_checker = AlarmChecker()
latest_pi_sensor_data = {
    "source": "raspberry-live",
    "timestamp": None,
    "temperature": None,
    "humidity": None,
    "pressure": None,
    "vibration": None,
    "device_id": "",
    "area": ""
}
latest_sensor_events: List[Dict[str, Any]] = []
latest_alerts: List[Dict[str, Any]] = []

SENSOR_META = {
    "temperature": {"label": "温度", "unit": "°C"},
    "humidity": {"label": "湿度", "unit": "%RH"},
    "pressure": {"label": "气压", "unit": "hPa"},
    "vibration": {"label": "振动", "unit": "mm/s"},
}

def sensor_status(sensor_type: str, value: Optional[float]) -> str:
    if value is None:
        return "missing"
    threshold = CONFIG.get("thresholds", {}).get(sensor_type)
    if threshold is None:
        return "normal"
    return "danger" if value > threshold * 1.2 else ("warning" if value > threshold else "normal")

def insert_sensor_payload(payload: RaspberrySensorPayload) -> Dict[str, Any]:
    timestamp = payload.timestamp or datetime.now().isoformat()
    device_id = payload.device_id or "raspberry-pi-5"
    area = payload.area or "A区"
    data = SensorData(
        temperature=payload.temperature,
        humidity=payload.humidity,
        pressure=payload.pressure,
        vibration=payload.vibration,
        device_id=device_id,
        area=area,
        timestamp=timestamp
    )
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "INSERT INTO sensor_data (timestamp, temperature, humidity, pressure, vibration, device_id, area) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (timestamp, data.temperature, data.humidity, data.pressure, data.vibration, device_id, area)
    )
    inserted = []
    for sensor_type, value in [
        ("temperature", data.temperature),
        ("humidity", data.humidity),
        ("pressure", data.pressure),
        ("vibration", data.vibration),
    ]:
        if value is None:
            continue
        threshold = CONFIG.get("thresholds", {}).get(sensor_type)
        status = sensor_status(sensor_type, value)
        c.execute(
            "INSERT INTO sensor_events (timestamp, device_id, area, sensor_type, value, threshold, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (timestamp, device_id, area, sensor_type, float(value), threshold, status)
        )
        inserted.append({"type": sensor_type, "value": float(value), "threshold": threshold, "status": status})
        if status in {"warning", "danger"}:
            c.execute(
                "INSERT INTO anomaly_sensor_data (timestamp, device_id, area, sensor_type, value, threshold, status, alert_batch_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (timestamp, device_id, area, sensor_type, float(value), threshold, status, None)
            )
    conn.commit()
    conn.close()

    alerts = alarm_checker.check(data, timestamp=timestamp, device_id=device_id, area=area)
    for alert in alerts:
        alarm_checker.save_alert(alert)
    asyncio.create_task(manager.broadcast({"type": "sensor", "data": sensor_payload_response(data, timestamp, device_id, area)}))
    return {"timestamp": timestamp, "device_id": device_id, "area": area, "readings": inserted, "alerts": len(alerts)}

def sensor_payload_response(data: SensorData, timestamp: str, device_id: str = "", area: str = "") -> Dict[str, Any]:
    return {
        "temperature": data.temperature,
        "humidity": data.humidity,
        "pressure": data.pressure,
        "vibration": data.vibration,
        "timestamp": timestamp,
        "device_id": device_id,
        "area": area,
        "source": "database",
        "statuses": {
            "temperature": sensor_status("temperature", data.temperature),
            "humidity": sensor_status("humidity", data.humidity),
            "vibration": sensor_status("vibration", data.vibration),
        }
    }

def build_sensor_events(data: SensorData, timestamp: str, device_id: str, area: str) -> List[Dict[str, Any]]:
    events = []
    for sensor_type, value in [
        ("temperature", data.temperature),
        ("humidity", data.humidity),
        ("pressure", data.pressure),
        ("vibration", data.vibration),
    ]:
        if value is None:
            continue
        threshold = CONFIG.get("thresholds", {}).get(sensor_type)
        status = sensor_status(sensor_type, value)
        events.append({
            "timestamp": timestamp,
            "device_id": device_id,
            "area": area,
            "sensor_type": sensor_type,
            "sensor_label": SENSOR_META.get(sensor_type, {}).get("label", sensor_type),
            "value": float(value),
            "threshold": threshold,
            "status": status
        })
    return events

def remember_live_sensor_data(payload: RaspberrySensorPayload) -> Dict[str, Any]:
    global latest_pi_sensor_data, latest_sensor_events
    timestamp = payload.timestamp or datetime.now().isoformat()
    device_id = payload.device_id or "raspberry-pi-5"
    area = payload.area or "A区"
    data = SensorData(
        temperature=payload.temperature,
        humidity=payload.humidity,
        pressure=payload.pressure,
        vibration=payload.vibration,
        device_id=device_id,
        area=area,
        timestamp=timestamp
    )
    live = sensor_payload_response(data, timestamp, device_id, area)
    live["source"] = "raspberry-live"
    live["statuses"] = {
        "temperature": sensor_status("temperature", data.temperature),
        "humidity": sensor_status("humidity", data.humidity),
        "vibration": sensor_status("vibration", data.vibration),
    }
    latest_pi_sensor_data = live
    latest_sensor_events = (build_sensor_events(data, timestamp, device_id, area) + latest_sensor_events)[:100]
    alerts = alarm_checker.check(data, timestamp=timestamp, device_id=device_id, area=area)
    live["alerts"] = len(alerts)
    for alert in alerts:
        threading.Thread(target=process_live_alert_background, args=(alert,), daemon=True).start()
    return live

def process_live_alert_background(alert: Dict[str, Any]):
    try:
        alarm_checker.save_alert(alert)
    except Exception as e:
        logger.warning(f"后台处理实时报警失败: {e}", exc_info=True)

def persist_sensor_payload_background(payload: RaspberrySensorPayload):
    try:
        insert_sensor_payload(payload)
    except Exception as e:
        logger.warning(f"后台保存树莓派传感器数据失败: {e}", exc_info=True)

@app.on_event("startup")
async def on_startup():
    # Start scripts and Uvicorn both pass here; this keeps schemas available without reset.
    await asyncio.to_thread(init_db)
    start_feishu_long_connection()

# ==================== 路由 ====================

@app.get("/", response_class=HTMLResponse)
async def root():
    """访问根路径返回前端页面"""
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path, headers={"Cache-Control": "no-store, no-cache, must-revalidate"})
    
    return HTMLResponse("""
    <html><head><title>工业环境监控系统</title></head>
    <body style="font-family:sans-serif;text-align:center;padding:50px;">
        <h1>工业环境监控系统</h1>
        <p>请将 index.html 放入 static 目录</p>
        <p>或访问 <a href="/api">API 文档</a></p>
    </body></html>
    """)

@app.get("/api")
async def api_info():
    return {
        "name": "工业环境监控系统 API",
        "version": "1.0.0",
        "endpoints": {
            "sensors": "/api/sensors/latest",
            "history": "/api/history?range=day",
            "alerts": "/api/alerts",
            "chat": "POST /api/chat",
            "camera": "POST /api/camera/capture",
            "websocket": "/ws/sensor"
        }
    }

@app.get("/api/raspberry/ping")
async def raspberry_ping():
    return {"ok": True, "time": datetime.now().isoformat()}

def database_status() -> Dict[str, Any]:
    """当前数据库生效状态，供设置页状态条与验收脚本使用。"""
    backend = get_database_backend()
    settings = mysql_settings()
    status = {
        "backend": backend,
        "configured": backend == "mysql",
        "connected": backend == "sqlite",
        "fallback": False,
        "host": settings["host"],
        "port": settings["port"],
        "user": settings["user"],
        "database": settings["database"],
        "server_version": "",
        "table_count": 0,
        "message": "",
    }
    if backend != "mysql":
        status["message"] = "当前使用 SQLite 本地数据库"
        return status
    conn = connect_cloud_database()
    if not conn:
        status.update({
            "connected": False,
            "fallback": True,
            "message": f"MySQL 未连接，已回退 SQLite：{(_MYSQL_LAST_ERROR or '未知错误')[:200]}",
        })
        return status
    try:
        status["server_version"] = conn.get_server_info()
        with conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = DATABASE()")
            row = cursor.fetchone()
            status["table_count"] = int(row[0]) if row else 0
        status["connected"] = True
        status["message"] = f"MySQL 已连接（{settings['database']}）"
    except Exception as e:
        status.update({
            "connected": False,
            "fallback": True,
            "message": f"MySQL 状态检查失败：{str(e)[:200]}",
        })
    finally:
        try:
            conn.close()
        except Exception:
            pass
    return status


@app.get("/api/database/status")
async def database_status_api():
    return database_status()


@app.post("/api/database/test")
async def test_database_connection(request: DatabaseTestRequest):
    backend = str(request.backend or CONFIG.get("database_backend") or "mysql").strip().lower()
    if backend == "sqlite":
        return {"success": True, "backend": "sqlite", "message": "SQLite 本地数据库可用（无需连接测试）", "tables": 0}
    overrides = {
        "host": request.mysql_host,
        "port": request.mysql_port,
        "user": request.mysql_user,
        "password": request.mysql_password,
        "database": request.mysql_database,
    }
    try:
        conn = connect_mysql(overrides, create_database=True, timeout=5)
        try:
            version = conn.get_server_info()
            with conn.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = DATABASE()")
                row = cursor.fetchone()
                tables = int(row[0]) if row else 0
        finally:
            conn.close()
        settings = mysql_settings(overrides)
        return {
            "success": True,
            "backend": "mysql",
            "server_version": version,
            "database": settings["database"],
            "tables": tables,
            "message": f"MySQL 连接成功（MySQL {version}，{settings['database']}）",
        }
    except Exception as e:
        return {"success": False, "backend": "mysql", "message": f"MySQL 连接失败：{str(e)[:300]}"}

@app.post("/api/rag/upload")
async def upload_rag_document(file: UploadFile = File(...)):
    data = await file.read()
    text = extract_uploaded_text(file.filename, file.content_type or "", data)
    chunks = split_text_for_rag(text)
    if not chunks:
        raise HTTPException(status_code=400, detail="未能从文件中解析出文本内容")

    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "INSERT INTO rag_documents (timestamp, filename, content_type, size, chunk_count) VALUES (?, ?, ?, ?, ?)",
        (datetime.now().isoformat(), file.filename, file.content_type or "", len(data), len(chunks))
    )
    document_id = c.lastrowid
    for idx, chunk in enumerate(chunks):
        embedding = get_ollama_embedding(chunk)
        c.execute(
            "INSERT INTO rag_chunks (document_id, chunk_index, content, embedding) VALUES (?, ?, ?, ?)",
            (document_id, idx, chunk, json.dumps(embedding) if embedding else None)
        )
    conn.commit()
    conn.close()
    return {"success": True, "document_id": document_id, "filename": file.filename, "chunks": len(chunks)}

@app.get("/api/rag/documents")
async def list_rag_documents():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id, timestamp, filename, content_type, size, chunk_count FROM rag_documents ORDER BY timestamp DESC LIMIT 100")
    rows = c.fetchall()
    conn.close()
    return [
        {"id": r[0], "timestamp": r[1], "filename": r[2], "content_type": r[3], "size": r[4], "chunk_count": r[5]}
        for r in rows
    ]

@app.post("/api/skills")
async def upload_skill(file: Optional[UploadFile] = File(None), name: Optional[str] = Form(None), content: Optional[str] = Form(None)):
    filename = "skill.md"
    skill_content = content or ""
    if file:
        filename = file.filename
        raw = await file.read()
        skill_content = extract_uploaded_text(file.filename, file.content_type or "", raw)
    skill_name = (name or Path(filename).stem).strip()
    if not skill_name or not skill_content.strip():
        raise HTTPException(status_code=400, detail="skill 名称和内容不能为空")

    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "INSERT INTO skills (timestamp, name, filename, content) VALUES (?, ?, ?, ?)",
        (datetime.now().isoformat(), skill_name, filename, skill_content)
    )
    skill_id = c.lastrowid
    conn.commit()
    conn.close()
    return {"success": True, "id": skill_id, "name": skill_name, "filename": filename}

@app.get("/api/skills")
async def list_skills():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id, timestamp, name, filename FROM skills ORDER BY timestamp DESC LIMIT 100")
    rows = c.fetchall()
    conn.close()
    return [{"id": r[0], "timestamp": r[1], "name": r[2], "filename": r[3]} for r in rows]

@app.get("/api/sensors/latest")
async def get_latest_sensor():
    if latest_pi_sensor_data.get("timestamp"):
        return latest_pi_sensor_data
    return {"source": "live-memory", "timestamp": None, "message": "暂无树莓派实时数据"}

@app.post("/api/raspberry/sensors")
async def receive_raspberry_sensors(payload: RaspberrySensorPayload):
    if all(getattr(payload, field) is None for field in ("temperature", "humidity", "pressure", "vibration")):
        raise HTTPException(status_code=400, detail="至少需要上传一个传感器数据")
    live = remember_live_sensor_data(payload)
    try:
        asyncio.get_running_loop().call_soon(
            asyncio.create_task,
            manager.broadcast({"type": "sensor", "data": live})
        )
    except RuntimeError:
        pass
    asyncio.create_task(asyncio.to_thread(persist_sensor_payload_background, payload))
    return {"success": True, "mode": "live-first", "data": live}

@app.get("/api/sensors/current")
async def get_current_sensors():
    """获取当前传感器数据（供3D模型轮询使用）"""
    return await get_latest_sensor()

@app.get("/api/config")
async def get_config():
    """获取系统配置（阈值等）"""
    return {
        "temp_upper": CONFIG["thresholds"]["temperature"],
        "humidity_upper": CONFIG["thresholds"]["humidity"],
        "vibration_upper": CONFIG["thresholds"]["vibration"]
    }

@app.get("/api/history")
async def get_history(range: str = "day"):
    conn = get_db_connection()
    c = conn.cursor()
    
    now = datetime.now()
    if range == "hour":
        start = now - timedelta(hours=1)
    elif range == "day":
        start = now - timedelta(days=1)
    elif range == "week":
        start = now - timedelta(weeks=1)
    elif range == "month":
        start = now - timedelta(days=30)
    else:
        start = now - timedelta(days=1)
    
    c.execute(
        "SELECT timestamp, temperature, humidity, pressure, vibration FROM sensor_data WHERE timestamp >= ? ORDER BY timestamp ASC",
        (start.isoformat(),)
    )
    
    rows = c.fetchall()
    conn.close()
    
    if not rows:
        return {"labels": [], "temperature": [], "humidity": [], "pressure": [], "vibration": []}
    
    labels = [r[0][11:16] for r in rows]
    return {
        "labels": labels,
        "temperature": [r[1] for r in rows if r[1] is not None],
        "humidity": [r[2] for r in rows if r[2] is not None],
        "pressure": [r[3] for r in rows if r[3] is not None],
        "vibration": [r[4] for r in rows if r[4] is not None]
    }

@app.post("/api/prediction/predict")
async def predict_device_trend(request: PredictionRequest):
    """Use only persisted Raspberry Pi history; this endpoint never fabricates a forecast."""
    from prediction import PredictionService
    return PredictionService().predict(request.device_id, request.metric, request.horizon)

@app.get("/api/prediction/history")
async def prediction_history(device_id: str, limit: int = 50):
    from prediction import PredictionService
    return {"device_id": device_id, "records": PredictionService().history(device_id, max(1, min(limit, 200)))}

@app.get("/api/prediction/status/{device_id}")
async def prediction_status(device_id: str):
    from prediction import PredictionService
    return PredictionService().status(device_id)

def _risk_analysis(device_id: str) -> Dict[str, Any]:
    from prediction import PredictionService
    from risk import RiskEngine
    current = latest_pi_sensor_data if latest_pi_sensor_data.get("device_id") == device_id else {}
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM anomaly_sensor_data WHERE device_id = ? AND timestamp >= ?", (device_id, (datetime.now() - timedelta(days=1)).isoformat()))
        row = cursor.fetchone()
        alerts = int(row[0]) if row else 0
    finally:
        conn.close()
    prediction = PredictionService().predict(device_id)
    result = RiskEngine().analyze(device_id, current, CONFIG.get("thresholds", {}), alerts, prediction)
    result["current_data_available"] = bool(current)
    result["prediction_status"] = prediction.get("status")
    return result

@app.get("/api/risk/{device_id}")
async def get_device_risk(device_id: str):
    return _risk_analysis(device_id)

@app.post("/api/risk/analyze")
async def analyze_device_risk(request: RiskRequest):
    result = _risk_analysis(request.device_id)
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        components = result["components"]
        cursor.execute("INSERT INTO risk_records (device_id, risk_level, risk_score, anomaly_score, prediction_score, reason, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)", (request.device_id, result["risk_level"], result["risk_score"], components["current"], components["prediction"], json.dumps(result["reasons"], ensure_ascii=False), datetime.now().isoformat()))
        conn.commit()
    finally:
        conn.close()
    return result
@app.get("/api/sensor-events")
async def get_sensor_events(limit: int = 100):
    limit = max(1, min(limit, 500))
    return latest_sensor_events[:limit]

@app.get("/api/anomaly-data")
async def get_anomaly_data(limit: int = 500):
    limit = max(1, min(limit, 5000))
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "SELECT timestamp, device_id, area, sensor_type, value, threshold, status, alert_batch_id FROM anomaly_sensor_data ORDER BY timestamp DESC LIMIT ?",
        (limit,)
    )
    rows = c.fetchall()
    conn.close()
    return [
        {
            "timestamp": row[0],
            "device_id": row[1],
            "area": row[2],
            "sensor_type": row[3],
            "value": row[4],
            "threshold": row[5],
            "status": row[6],
            "alert_batch_id": row[7]
        }
        for row in rows
    ]

@app.get("/api/alerts")
async def get_alerts():
    return latest_alerts

@app.post("/api/alerts/{alert_id}/handle")
async def handle_alert(alert_id: int):
    remaining = alarm_checker.handle_alert(alert_id)
    return {"success": True, "remaining": remaining}

# ==================== 数字孪生聚合视图 ====================
TWIN_ALERT_LIMIT = 12
TWIN_SENSOR_STALE_SECONDS = 30

def _parse_iso_datetime(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone().replace(tzinfo=None)
        return parsed
    except Exception:
        return None

def _flatten_twin_alert(record: Dict[str, Any]) -> Dict[str, Any]:
    detail = record.get("detail") or {}
    return {
        "id": record.get("id"),
        "title": record.get("title") or "设备告警",
        "time": record.get("time"),
        "source": record.get("source") or detail.get("area") or "",
        "level": record.get("level") or detail.get("level") or "warning",
        "type": detail.get("type"),
        "value": detail.get("value"),
        "threshold": detail.get("threshold"),
        "device_id": detail.get("device_id") or "",
        "area": detail.get("area") or record.get("source") or "",
        "handled": bool(record.get("handled")),
    }

def _device_is_online(status: Any) -> bool:
    text = str(status or "")
    if not text:
        return False
    return any(word in text for word in ("运行", "在线", "正常")) and not any(
        word in text for word in ("离线", "停机", "故障", "告警")
    )

def _twin_plant_metrics(live: Dict[str, Any]) -> Dict[str, Any]:
    metrics: Dict[str, Any] = {}
    for key in ("temperature", "humidity", "pressure", "vibration"):
        value = live.get(key)
        try:
            metrics[key] = None if value is None or value == "" else float(value)
        except (TypeError, ValueError):
            metrics[key] = None
    metrics["statuses"] = {
        "temperature": sensor_status("temperature", metrics["temperature"]),
        "humidity": sensor_status("humidity", metrics["humidity"]),
        "vibration": sensor_status("vibration", metrics["vibration"]),
    }
    return metrics

@app.get("/api/twin/overview")
async def twin_overview():
    """数字孪生页一次性聚合数据：设备、实时工况、风险、告警与阈值。"""
    from risk import RiskEngine

    now = datetime.now()
    live = latest_pi_sensor_data if isinstance(latest_pi_sensor_data, dict) else {}
    live_timestamp = live.get("timestamp")
    live_time = _parse_iso_datetime(live_timestamp)
    age_seconds = int(max(0, (now - live_time).total_seconds())) if live_time else None
    stale = age_seconds is not None and age_seconds > TWIN_SENSOR_STALE_SECONDS
    plant = _twin_plant_metrics(live)
    plant_available = any(plant.get(key) is not None for key in ("temperature", "humidity", "vibration"))
    source_online = bool(live_time) and plant_available and not stale

    live_device_id = str(live.get("device_id") or "")
    live_area = str(live.get("area") or "")
    if not live_timestamp:
        source_label = "暂无实时上报"
    elif stale:
        source_label = "实时数据已过期"
    else:
        source_label = "树莓派实时上报"

    flat_alerts = [_flatten_twin_alert(record) for record in (latest_alerts or [])[:50]]
    open_alerts = [item for item in flat_alerts if not item.get("handled")]
    by_device: Dict[str, int] = {}
    for item in open_alerts:
        key = str(item.get("device_id") or "")
        if key:
            by_device[key] = by_device.get(key, 0) + 1

    thresholds = CONFIG.get("thresholds", {}) or {}
    engine = RiskEngine()
    devices: List[Dict[str, Any]] = []
    for index, device in enumerate(CONFIG.get("devices", []) or []):
        device_id = str(device.get("id") or "")
        bound = bool(live_device_id) and live_device_id == device_id
        scope = "device" if bound else ("plant" if plant_available else "none")
        current = {key: plant.get(key) for key in ("temperature", "humidity", "pressure", "vibration")} if plant_available else {}
        device_alerts = [item for item in open_alerts if device_id and item.get("device_id") == device_id]
        risk = engine.analyze(device_id, current, thresholds, len(device_alerts), None)
        risk["data_scope"] = scope
        risk["current_data_available"] = bool(current)
        risk["prediction_status"] = "not_requested"
        latest_alert_at = next(
            (item.get("time") for item in flat_alerts if device_id and item.get("device_id") == device_id),
            None,
        )
        devices.append({
            "id": device_id,
            "name": device.get("name") or device_id or "未命名设备",
            "status": device.get("status") or "未配置",
            "online": _device_is_online(device.get("status")),
            "station": f"工位 {index + 1:02d}",
            "index": index,
            "model_url": device.get("model_url") or "",
            "model_filename": device.get("model_filename") or "",
            "has_model": bool(device.get("model_url")),
            "sensor_bound": bound,
            "risk": risk,
            "alerts": {
                "open": len(device_alerts),
                "latest_at": latest_alert_at,
            },
        })

    total = len(devices)
    online_count = sum(1 for device in devices if device["online"])
    alerting_names = {device["id"] for device in devices if device["alerts"]["open"] > 0}
    alerting = len(alerting_names)

    return {
        "generated_at": now.isoformat(),
        "source": {
            "type": "raspberry-live" if live_timestamp else "none",
            "timestamp": live_timestamp,
            "age_seconds": age_seconds,
            "stale": stale,
            "online": source_online,
            "device_id": live_device_id,
            "area": live_area,
            "label": source_label,
            "interval_seconds": CONFIG.get("sensor_interval", 5),
        },
        "thresholds": {
            "temperature": thresholds.get("temperature"),
            "humidity": thresholds.get("humidity"),
            "vibration": thresholds.get("vibration"),
        },
        "plant": {
            "available": plant_available,
            "temperature": plant.get("temperature"),
            "humidity": plant.get("humidity"),
            "pressure": plant.get("pressure"),
            "vibration": plant.get("vibration"),
            "statuses": plant.get("statuses") or {},
            "timestamp": live_timestamp,
        },
        "devices": devices,
        "alerts": {
            "open_total": len(open_alerts),
            "items": open_alerts[:TWIN_ALERT_LIMIT],
            "by_device": by_device,
        },
        "summary": {
            "total": total,
            "online": online_count,
            "alerting": alerting,
            "data_online": source_online,
        },
    }

@app.post("/api/ollama/test")
async def test_ollama_connection(request: OllamaTestRequest):
    """测试 Ollama 模型连接"""
    model = request.model or CONFIG["ollama_model"]
    api_url = request.api_url or CONFIG['ollama_url']
    
    logger.info(f"测试 Ollama 连接：url={api_url}, model={model}")
    
    try:
        import requests
        
        response = requests.get(f"{api_url}/api/tags", timeout=10)
        if response.status_code != 200:
            return {
                "success": False,
                "message": f"无法连接 Ollama 服务 (状态码：{response.status_code})"
            }
        
        models_data = response.json()
        available_models = [m["name"] for m in models_data.get("models", [])]
        
        if model not in available_models:
            return {
                "success": False,
                "message": f"模型 '{model}' 不存在。可用模型：{', '.join(available_models)}"
            }
        
        test_response = requests.post(
            f"{api_url}/api/generate",
            json={
                "model": model,
                "prompt": "收到",
                "stream": False
            },
            timeout=60
        )
        
        if test_response.status_code == 200:
            result = test_response.json()
            reply = result.get("response", "")
            return {
                "success": True,
                "message": f"模型 '{model}' 连接成功！",
                "reply": reply,
                "available_models": available_models
            }
        else:
            return {
                "success": False,
                "message": f"模型测试失败 (状态码：{test_response.status_code})"
            }
            
    except requests.exceptions.Timeout:
        return {
            "success": False,
            "message": "连接超时，请检查 Ollama 服务是否运行"
        }
    except requests.exceptions.ConnectionError:
        return {
            "success": False,
            "message": "无法连接到 Ollama 服务，请确认服务已启动"
        }
    except Exception as e:
        logger.error(f"测试 Ollama 连接失败：{e}")
        return {
            "success": False,
            "message": f"测试失败：{str(e)}"
        }

@app.get("/api/ollama/models")
async def list_ollama_models(api_url: Optional[str] = None):
    """返回本机 Ollama 实际已安装的模型列表"""
    ollama_url = api_url or CONFIG['ollama_url']
    logger.info(f"查询 Ollama 模型列表：url={ollama_url}")
    
    try:
        import requests
        
        service_status = start_ollama_service(ollama_url)
        if not service_status["success"]:
            return {
                "success": False,
                "models": [],
                "message": service_status["message"]
            }
        
        response = requests.get(f"{ollama_url}/api/tags", timeout=5)
        if response.status_code != 200:
            return {
                "success": False,
                "models": [],
                "message": f"Ollama 服务返回异常状态码：{response.status_code}"
            }
        
        models_data = response.json()
        models = []
        for item in models_data.get("models", []):
            name = item.get("name")
            if name:
                models.append({
                    "name": name,
                    "size": item.get("size"),
                    "modified_at": item.get("modified_at")
                })
        
        return {
            "success": True,
            "models": models,
            "message": f"已发现 {len(models)} 个本机模型"
        }
    except requests.exceptions.ConnectionError:
        return {
            "success": False,
            "models": [],
            "message": "无法连接到 Ollama 服务，请先启动 Ollama"
        }
    except requests.exceptions.Timeout:
        return {
            "success": False,
            "models": [],
            "message": "连接 Ollama 超时，请检查服务状态"
        }
    except Exception as e:
        logger.error(f"查询 Ollama 模型列表失败：{e}")
        return {
            "success": False,
            "models": [],
            "message": f"查询失败：{str(e)}"
        }

@app.post("/api/ollama/start")
async def start_ollama_model(request: OllamaTestRequest):
    """启动 Ollama 模型（预加载到内存）"""
    model = request.model or CONFIG["ollama_model"]
    api_url = request.api_url or CONFIG['ollama_url']
    
    logger.info(f"启动 Ollama 模型：url={api_url}, model={model}")
    
    try:
        import requests
        
        service_status = start_ollama_service(api_url)
        if not service_status["success"]:
            return {
                "success": False,
                "message": service_status["message"]
            }
        
        response = requests.get(f"{api_url}/api/tags", timeout=10)
        if response.status_code != 200:
            return {
                "success": False,
                "message": f"无法连接 Ollama 服务"
            }
        
        models_data = response.json()
        available_models = [m["name"] for m in models_data.get("models", [])]
        
        if model not in available_models:
            return {
                "success": False,
                "message": f"模型 '{model}' 不存在。可用模型：{', '.join(available_models)}"
            }
        
        logger.info(f"开始预加载模型 {model}...")
        
        preload_response = requests.post(
            f"{api_url}/api/generate",
            json={
                "model": model,
                "prompt": "预热",
                "stream": False
            },
            timeout=120
        )
        
        if preload_response.status_code == 200:
            result = preload_response.json()
            reply = result.get("response", "")
            logger.info(f"模型 {model} 预加载成功")
            return {
                "success": True,
                "message": f"模型 '{model}' 启动成功！已加载到内存",
                "reply": reply,
                "available_models": available_models
            }
        else:
            return {
                "success": False,
                "message": f"模型启动失败 (状态码：{preload_response.status_code})"
            }
            
    except requests.exceptions.Timeout:
        return {
            "success": False,
            "message": "模型加载超时，可能需要更长时间"
        }
    except requests.exceptions.ConnectionError:
        return {
            "success": False,
            "message": "无法连接到 Ollama 服务，请确认服务已启动"
        }
    except Exception as e:
        logger.error(f"启动 Ollama 模型失败：{e}")
        return {
            "success": False,
            "message": f"启动失败：{str(e)}"
        }

@app.post("/api/feishu/test")
async def test_feishu_webhook(payload: dict = None):
    webhook = (payload or {}).get("webhook") or CONFIG.get("feishu_webhook", "")
    if webhook:
        CONFIG["feishu_webhook"] = webhook
        save_config()
    ok = send_feishu_text_fixed("工业环境监控系统：飞书机器人测试消息发送成功。")
    return {"success": ok, "message": "测试消息已发送" if ok else "测试消息发送失败，请检查 Webhook 地址"}

@app.post("/api/feishu/events")
async def feishu_events(request: Request):
    payload = await request.json()
    logger.info(f"收到飞书事件回调：keys={list(payload.keys())}")
    
    challenge = payload.get("challenge") or payload.get("event", {}).get("challenge")
    if challenge:
        token = CONFIG.get("feishu_verification_token", "")
        payload_token = payload.get("token") or payload.get("header", {}).get("token")
        if token and payload_token != token:
            logger.warning("飞书 URL 校验失败：verification token 不匹配")
            raise HTTPException(status_code=403, detail="invalid verification token")
        logger.info("飞书 URL 校验成功")
        return {"challenge": challenge}
    
    if not CONFIG.get("feishu_receive_group_messages", False):
        logger.info("飞书群消息接收已关闭，忽略事件")
        return {"success": True, "message": "Feishu message receiving disabled"}
    
    token = CONFIG.get("feishu_verification_token", "")
    if token and payload.get("token") != token and payload.get("header", {}).get("token") != token:
        logger.warning("飞书事件校验失败：verification token 不匹配")
        raise HTTPException(status_code=403, detail="invalid verification token")
    
    event_type = payload.get("header", {}).get("event_type") or payload.get("type")
    logger.info(f"飞书事件类型：{event_type}")
    if event_type and "message" not in event_type:
        logger.info("忽略非消息类飞书事件")
        return {"success": True, "message": "ignored non-message event"}
    
    text = extract_feishu_text_message(payload)
    if not text:
        logger.info("忽略非文本飞书消息或空消息")
        return {"success": True, "message": "ignored non-text message"}
    
    if text.startswith("网页 AI 回复：") or text.startswith("飞书群消息回复："):
        logger.info("忽略机器人自身回显消息")
        return {"success": True, "message": "ignored bot echo"}
    
    logger.info(f"收到飞书群文本消息：{text[:80]}")
    
    context_parts = []
    latest = sensor_reader.read()
    if latest.temperature: context_parts.append(f"温度：{latest.temperature}°C")
    if latest.humidity: context_parts.append(f"湿度：{latest.humidity}%")
    if latest.pressure: context_parts.append(f"气压：{latest.pressure}hPa")
    if latest.vibration: context_parts.append(f"振动：{latest.vibration}mm/s")
    context = ", ".join(context_parts) or "暂无数据"
    
    reply = await chat_with_ollama(text, context)
    ok = send_feishu_text_fixed(f"飞书群消息回复：\n{reply}")
    logger.info(f"飞书群消息回复发送结果：{ok}")
    return {"success": True}

@app.post("/api/chat")
async def chat(request: ChatRequest):
    context_parts = []
    latest = sensor_reader.read()
    if latest.temperature: context_parts.append(f"温度: {latest.temperature}°C")
    if latest.humidity: context_parts.append(f"湿度: {latest.humidity}%")
    if latest.pressure: context_parts.append(f"气压: {latest.pressure}hPa")
    if latest.vibration: context_parts.append(f"振动: {latest.vibration}mm/s")
    
    context = ", ".join(context_parts) or "暂无数据"
    reply = await chat_with_ollama(request.message, context)
    
    return {"reply": reply}

@app.websocket("/ws/chat")
async def chat_websocket(websocket: WebSocket):
    if not _ws_allowed(websocket):
        await websocket.close(code=1008)
        return
    await websocket.accept()
    logger.info("AI 对话 WebSocket 已连接")
    try:
        while True:
            data = await websocket.receive_json()
            message = data.get("message", "")
            model = data.get("model")
            api_url = data.get("api_url")
            use_agent = data.get("agent_mode", True)  # 默认启用 Agent 模式
            logger.info(f"收到 AI 消息：{message} (model={model}, agent_mode={use_agent})")
            
            if not message:
                continue
            
            context_parts = []
            latest = sensor_reader.read()
            if latest.temperature: context_parts.append(f"温度：{latest.temperature}°C")
            if latest.humidity: context_parts.append(f"湿度：{latest.humidity}%")
            if latest.pressure: context_parts.append(f"气压：{latest.pressure}hPa")
            if latest.vibration: context_parts.append(f"振动：{latest.vibration}mm/s")
            context = ", ".join(context_parts) or "暂无数据"
            
            # Agent 模式：通过编排器路由
            if use_agent:
                orchestrator = get_orchestrator()
                if orchestrator:
                    await _handle_agent_chat(websocket, message, context, orchestrator)
                    continue
                else:
                    logger.warning("Agent 编排器不可用，降级为直接对话模式")
            
            # 降级模式：直接调用 Ollama
            await chat_with_ollama_stream(websocket, message, context, model, api_url)
            
    except WebSocketDisconnect:
        logger.info("AI 对话 WebSocket 断开")
    except Exception as e:
        logger.error(f"AI 对话 WebSocket 错误：{e}")
        try:
            await websocket.send_json({"type": "error", "content": "处理消息时出错"})
        except:
            pass


async def _handle_agent_chat(websocket: WebSocket, message: str, context: str, orchestrator):
    """通过多 Agent 编排器处理 WebSocket 聊天消息。"""
    try:
        async def on_status(status_type, data):
            try:
                await websocket.send_json({"type": "status", "agent_status": status_type, "content": data})
            except (WebSocketDisconnect, RuntimeError):
                pass
        
        async def on_content(chunk):
            try:
                await websocket.send_json({"type": "content", "content": chunk})
            except (WebSocketDisconnect, RuntimeError):
                pass
        
        reply = await orchestrator.handle_message_stream(
            message=message,
            context={"sensor_context": context},
            on_status=on_status,
            on_content=on_content,
        )
        
        try:
            await websocket.send_json({"type": "done", "full_reply": reply})
        except (WebSocketDisconnect, RuntimeError):
            pass
        
        # 飞书转发
        if CONFIG.get("feishu_forward_ai_replies", False) and reply.strip():
            send_feishu_text_fixed(f"网页 AI 回复：\n{reply.strip()}")
        
    except WebSocketDisconnect:
        logger.info("Agent 对话 WebSocket 断开")
    except Exception as e:
        logger.error(f"Agent 对话处理失败: {e}", exc_info=True)
        try:
            await websocket.send_json({"type": "content", "content": f"\nAgent 系统暂时不可用：{str(e)[:100]}"})
            await websocket.send_json({"type": "done"})
        except:
            pass

async def chat_with_ollama_stream(websocket: WebSocket, message: str, context: str = "", model: str = None, api_url: str = None) -> str:
    logger.info("=" * 60)
    logger.info(f"开始处理 AI 对话：message={message}")
    logger.info(f"配置：model={model}, api_url={api_url}")
    
    if not CONFIG.get("ollama_enabled", False):
        logger.warning("Ollama 未启用，使用模拟回复")
        reply = generate_mock_reply(message, context)
        await websocket.send_json({"type": "content", "content": reply})
        await websocket.send_json({"type": "done"})
        logger.info("=" * 60)
        return reply
    
    ollama_url = api_url or CONFIG['ollama_url']
    ollama_model = model or CONFIG["ollama_model"]
    
    logger.info(f"准备连接 Ollama: url={ollama_url}, model={ollama_model}")
    
    try:
        import requests
        
        if is_greeting_message(message):
            reply = greeting_reply()
            await send_text_stream(websocket, reply)
            if CONFIG.get("feishu_forward_ai_replies", False):
                send_feishu_text_fixed(f"网页 AI 回复：\n{reply}")
            await websocket.send_json({"type": "done", "full_reply": reply})
            logger.info("问候类消息已使用系统标准回复")
            logger.info("=" * 60)
            return reply
        
        logger.info("已导入依赖库，准备发送请求到 Ollama...")
        
        system_prompt = build_ai_system_prompt(context)
        
        logger.info(f"发送请求到 {ollama_url}/api/chat")
        logger.info(f"Prompt: {message}")
        
        if is_knowledge_search_request(message):
            await websocket.send_json({"type": "searching", "content": "正在检索知识库..."})
        elif should_use_online_search(message):
            await websocket.send_json({"type": "searching", "content": "正在搜索..."})
        context = build_augmented_context(message, context)
        system_prompt = build_ai_system_prompt(context)

        response = requests.post(
            f"{ollama_url}/api/chat",
            json={
                "model": ollama_model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"/no_think\n{message}"}
                ],
                "stream": True,
                "think": False,
                "options": {
                    "temperature": 0.2,
                    "top_p": 0.8
                }
            },
            stream=True,
            timeout=300
        )
        
        logger.info(f"Ollama 响应状态码：{response.status_code}")
        
        if response.status_code == 200:
            logger.info("Ollama 响应成功，开始接收流式数据...")
            full_reply = ""
            visible_reply = ""
            chunk_count = 0
            emitted_len = 0
            thinking_notified = False
            
            for line in response.iter_lines():
                if line:
                    try:
                        chunk_count += 1
                        line_str = line.decode('utf-8')
                        
                        chunk = json.loads(line_str)
                        content = chunk.get("message", {}).get("content", "")
                        is_done = chunk.get("done", False)
                        
                        if chunk_count <= 3 or chunk_count % 500 == 0:
                            logger.info(f"数据块 {chunk_count}: done={is_done}, 内容长度={len(content) if content else 0}")
                        
                        if content:
                            full_reply += content
                            lower_full = full_reply.lower()
                            has_think_start = "<think>" in lower_full or "<thinking>" in lower_full
                            has_think_end = "</think>" in lower_full or "</thinking>" in lower_full
                            if has_think_start and not has_think_end:
                                if not thinking_notified:
                                    await websocket.send_json({"type": "thinking"})
                                    thinking_notified = True
                                continue
                            
                            cleaned_full = strip_thinking_text(full_reply)
                            blocked_starts = (
                                "首先，用户", "首先, 用户", "用户说", "我需要",
                                "作为工业环境监控系统的AI助手，我需要",
                                "作为工业环境监控系统的 AI 助手，我需要",
                            )
                            if any(cleaned_full.lstrip().startswith(prefix) for prefix in blocked_starts):
                                if not thinking_notified:
                                    await websocket.send_json({"type": "thinking"})
                                    thinking_notified = True
                                continue
                            
                            if len(cleaned_full) > emitted_len:
                                emit = cleaned_full[emitted_len:]
                                emitted_len = len(cleaned_full)
                                visible_reply = cleaned_full
                                try:
                                    await websocket.send_json({"type": "content", "content": emit})
                                except WebSocketDisconnect:
                                    logger.info("AI 对话连接已断开，停止接收 Ollama 流式结果")
                                    logger.info("=" * 60)
                                    return visible_reply or strip_thinking_text(full_reply)
                                except RuntimeError as e:
                                    if "close message has been sent" in str(e):
                                        logger.info("AI 对话连接已关闭，停止接收 Ollama 流式结果")
                                        logger.info("=" * 60)
                                        return visible_reply or strip_thinking_text(full_reply)
                                    raise
                                await asyncio.sleep(0.005)
                        
                        if is_done:
                            logger.info(f"收到 done 标志，停止接收，共 {chunk_count} 个数据块")
                            break
                    except json.JSONDecodeError as e:
                        logger.warning(f"JSON 解析失败: {e}, 原始数据: {line_str[:50]}")
                        continue
            
            logger.info(f"接收完成，共 {chunk_count} 个数据块")
            if not visible_reply.strip() and full_reply.strip():
                fallback = strip_thinking_text(full_reply).strip()
                if fallback:
                    visible_reply = fallback
                    if not await send_text_stream(websocket, visible_reply):
                        return visible_reply
            
            if not visible_reply.strip():
                visible_reply = "模型返回了内部推理内容，已被系统拦截。请换一种问法或稍后重试。"
                if not await send_text_stream(websocket, visible_reply):
                    return visible_reply
            
            logger.info(f"完整回复：{visible_reply[:100]}...")
            if CONFIG.get("feishu_forward_ai_replies", False) and visible_reply.strip():
                send_feishu_text_fixed(f"网页 AI 回复：\n{visible_reply.strip()}")
            
            try:
                await websocket.send_json({"type": "done", "full_reply": visible_reply})
            except WebSocketDisconnect:
                logger.info("AI 对话连接已断开，跳过 done 消息")
            except RuntimeError as e:
                if "close message has been sent" not in str(e):
                    raise
                logger.info("AI 对话连接已关闭，跳过 done 消息")
            logger.info("=" * 60)
            return visible_reply
        else:
            logger.error(f"Ollama 返回错误状态码：{response.status_code}")
            await websocket.send_json({"type": "content", "content": "\n⚠️ AI服务返回错误"})
            await websocket.send_json({"type": "done"})
            logger.info("=" * 60)
            return "AI 服务暂时不可用"
    except requests.exceptions.Timeout:
        logger.error(f"Ollama 连接超时（超过 300 秒）")
        await websocket.send_json({"type": "content", "content": "\n⏳ AI模型加载超时，请稍后重试或检查Ollama服务状态"})
        await websocket.send_json({"type": "done"})
        logger.info("=" * 60)
        return "Ollama 连接超时"
    except requests.exceptions.ConnectionError as e:
        logger.error(f"Ollama 连接失败：{e}")
        reply = generate_mock_reply(message, context)
        await websocket.send_json({"type": "content", "content": "\n" + reply})
        await websocket.send_json({"type": "done"})
        logger.info("=" * 60)
        return reply
    except ImportError as e:
        logger.error(f"ImportError: {e}")
        reply = generate_mock_reply(message, context)
        await websocket.send_json({"type": "content", "content": "\n" + reply})
        await websocket.send_json({"type": "done"})
        logger.info("=" * 60)
        return reply
    except WebSocketDisconnect:
        logger.info("AI 对话连接已断开，停止当前流式对话")
        logger.info("=" * 60)
        return ""
    except RuntimeError as e:
        if "close message has been sent" in str(e):
            logger.info("AI 对话连接已关闭，停止当前流式对话")
            logger.info("=" * 60)
            return ""
        logger.error(f"Ollama 流式对话失败: {e}", exc_info=True)
        reply = generate_mock_reply(message, context)
        try:
            await websocket.send_json({"type": "content", "content": "\n" + reply})
            await websocket.send_json({"type": "done"})
        except Exception:
            logger.info("AI 对话连接已关闭，跳过错误兜底回复")
        logger.info("=" * 60)
        return reply
    except Exception as e:
        logger.error(f"Ollama 流式对话失败: {e}", exc_info=True)
        reply = generate_mock_reply(message, context)
        try:
            await websocket.send_json({"type": "content", "content": "\n" + reply})
            await websocket.send_json({"type": "done"})
        except Exception:
            logger.info("AI 对话连接已关闭，跳过错误兜底回复")
        logger.info("=" * 60)
        return reply

@app.post("/api/camera/capture")
async def capture_image():
    path = camera.save_snapshot("manual")
    if path:
        return {"success": True, "path": path}
    return {"success": False, "message": "摄像头不可用"}

@app.get("/static/{path:path}")
async def get_static(path: str):
    target = (STATIC_DIR / path).resolve()
    if not str(target).startswith(str(STATIC_DIR.resolve())) or not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(target)

@app.websocket("/ws/sensor")
async def websocket_endpoint(websocket: WebSocket):
    if not _ws_allowed(websocket):
        await websocket.close(code=1008)
        return
    await manager.connect(websocket)
    try:
        while True:
            await asyncio.sleep(60)
            
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket 错误: {e}")
        manager.disconnect(websocket)

@app.post("/api/settings")
async def update_settings(settings: dict):
    global CONFIG
    CONFIG.update(settings)
    if isinstance(CONFIG.get("thresholds"), dict):
        CONFIG["thresholds"]["temperature"] = float(CONFIG["thresholds"].get("temperature", 40))
        CONFIG["thresholds"]["humidity"] = float(CONFIG["thresholds"].get("humidity", 80))
        CONFIG["thresholds"]["vibration"] = float(CONFIG["thresholds"].get("vibration", 0.5))
    CONFIG["alarm_trigger_count"] = int(CONFIG.get("alarm_trigger_count", 3))
    CONFIG["alarm_window_seconds"] = int(CONFIG.get("alarm_window_seconds", 60))
    CONFIG["alarm_cooldown_seconds"] = 0
    if any(key in settings for key in ("thresholds", "alarm_trigger_count", "alarm_window_seconds")):
        alarm_checker.anomaly_windows.clear()
        alarm_checker.last_alert_time.clear()
    normalize_device_config()
    db_keys = ("database_backend", "mysql_host", "mysql_port", "mysql_user", "mysql_password", "mysql_database")
    db_changed = any(key in settings for key in db_keys)
    if db_changed:
        init_db()
    save_config()
    cloud_saved = save_cloud_config()
    status = database_status()
    result = {
        "success": True,
        "cloud_saved": cloud_saved,
        "backend": get_database_backend(),
        "database": status,
        "message": "配置已保存",
    }
    if db_changed:
        if get_database_backend() == "mysql" and not status.get("connected"):
            result["success"] = False
            result["message"] = status.get("message") or "MySQL 连接失败，配置已保存为待修正状态"
        else:
            result["message"] = "数据库配置已保存并完成初始化"
    return result

@app.get("/api/settings")
async def get_settings():
    load_cloud_config()
    payload = {key: value for key, value in CONFIG.items() if key != "mysql_password"}
    payload["mysql_password_set"] = bool(CONFIG.get("mysql_password"))
    return payload

@app.post("/api/device/model")
async def upload_device_model(file: UploadFile = File(...), device_id: Optional[str] = Form(None)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".glb", ".gltf", ".bin"}:
        raise HTTPException(status_code=400, detail="仅支持 .glb/.gltf/.bin 设备模型文件")
    safe_stem = re.sub(r"[^a-zA-Z0-9_-]+", "_", Path(file.filename).stem).strip("_") or "device_model"
    filename = f"{safe_stem}_{int(time.time())}{suffix}"
    filepath = DEVICE_MODEL_DIR / filename
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="模型文件不能为空")
    if len(data) > 80 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="模型文件不能超过 80MB")
    filepath.write_bytes(data)
    model_url = f"/static/uploads/device_models/{filename}"
    storage_backend = "local"

    device_info = next(
        (device for device in CONFIG.get("devices", []) if device.get("id") == (device_id or CONFIG.get("selected_device_id"))),
        CONFIG.setdefault("device_info", {})
    )
    device_info["model_url"] = model_url
    device_info["model_filename"] = file.filename
    for idx, device in enumerate(CONFIG.get("devices", [])):
        if device.get("id") == device_info.get("id"):
            CONFIG["devices"][idx] = device_info
            break
    CONFIG["device_info"] = device_info
    save_config()
    cloud_saved = save_cloud_config()
    return {
        "success": True,
        "device_id": device_info.get("id"),
        "model_url": device_info["model_url"],
        "filename": file.filename,
        "storage_backend": storage_backend,
        "cloud_saved": cloud_saved
    }

# ==================== Agent 系统 API ====================

@app.get("/api/agent/status")
async def agent_status():
    """获取多 Agent 编排器的状态和运行统计。"""
    orchestrator = get_orchestrator()
    if not orchestrator:
        return {"enabled": False, "message": "Agent 编排器未初始化"}
    from agents import TOOL_SCHEMAS
    return {
        "enabled": True,
        "stats": orchestrator.get_stats(),
        "available_tools": TOOL_SCHEMAS,
        "llm_backend": orchestrator.llm.backend,
        "llm_model": orchestrator.llm.model,
    }

@app.post("/api/agent/chat")
async def agent_chat(request: ChatRequest):
    """通过 Agent 系统处理对话（非流式 HTTP 接口）。"""
    orchestrator = get_orchestrator()
    if not orchestrator:
        return JSONResponse(
            status_code=503,
            content={"reply": "Agent 系统暂不可用，请检查 LLM 后端配置。"}
        )
    context_parts = []
    latest = sensor_reader.read()
    if latest.temperature: context_parts.append(f"温度：{latest.temperature}°C")
    if latest.humidity: context_parts.append(f"湿度：{latest.humidity}%")
    if latest.pressure: context_parts.append(f"气压：{latest.pressure}hPa")
    if latest.vibration: context_parts.append(f"振动：{latest.vibration}mm/s")
    context = ", ".join(context_parts) or "暂无数据"

    result = await orchestrator.handle_message(
        message=request.message,
        context={"sensor_context": context},
    )
    return result

@app.post("/api/agent/test")
async def agent_test():
    """测试 Agent 编排器是否正常工作。"""
    orchestrator = get_orchestrator()
    if not orchestrator:
        return {"success": False, "message": "Agent 编排器初始化失败"}
    llm_status = orchestrator.llm.test_connection()
    return {
        "success": llm_status.get("success", False),
        "llm": llm_status,
        "agents": list(orchestrator.agents.keys()),
    }

# ==================== 移动端安全层与配置契约（M0） ====================
import base64
import copy
import hashlib
import hmac
import secrets as _secrets

APP_VERSION = "1.0.0"
SERVER_START_TS = time.time()
MOBILE_DATA_DIR = Path(os.environ.get("PULSE_MOBILE_DATA_DIR") or (BASE_DIR / "data"))
MOBILE_DATA_DIR.mkdir(parents=True, exist_ok=True)
AUTH_FILE = MOBILE_DATA_DIR / "mobile_auth.json"
AUDIT_FILE = MOBILE_DATA_DIR / "audit.jsonl"
CONFIG_STATE_FILE = MOBILE_DATA_DIR / "config_state.json"
ADMIN_CREDENTIALS_FILE = MOBILE_DATA_DIR / "mobile_admin_credentials.txt"

CONFIG.setdefault("mobile_auth_enabled", True)
CONFIG.setdefault("mobile_token_hours", 12)
CONFIG.setdefault("mobile_public_base_url", "https://pulse.ainavi.online")
CONFIG.setdefault("feishu_login_enabled", True)
CONFIG.setdefault("feishu_login_allowed_open_ids", [])

_SECRET_KEYS = {"mysql_password", "feishu_app_secret", "feishu_verification_token", "agent_api_key"}
_ROLE_LEVEL = {"viewer": 1, "operator": 2, "admin": 3}
_AUTH_STORE = None
_AUTH_LOCK = threading.Lock()
_AUDIT_LOCK = threading.Lock()
_CONFIG_LOCK = threading.Lock()
_LOGIN_FAILS = {}
_LOGIN_LOCK = threading.Lock()
LOGIN_WINDOW_SECONDS = 300
LOGIN_MAX_FAILS = 5
PBKDF2_ITERATIONS = 210000


def _utc_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _hash_password(password: str, salt_hex: str) -> str:
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), PBKDF2_ITERATIONS)
    return digest.hex()


def _add_user(store: Dict[str, Any], username: str, password: str, role: str = "viewer", display_name: str = "") -> Dict[str, Any]:
    salt = _secrets.token_hex(16)
    user = {
        "username": username,
        "display_name": display_name or username,
        "role": role,
        "salt": salt,
        "password_hash": _hash_password(password, salt),
        "disabled": False,
        "created_at": _utc_now(),
    }
    store.setdefault("users", []).append(user)
    return user


def _save_auth(store: Dict[str, Any]) -> None:
    try:
        AUTH_FILE.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        logger.error("写入移动端账号文件失败: %s", exc)


def _auth_store() -> Dict[str, Any]:
    global _AUTH_STORE
    if _AUTH_STORE is not None:
        return _AUTH_STORE
    with _AUTH_LOCK:
        if _AUTH_STORE is not None:
            return _AUTH_STORE
        store = None
        if AUTH_FILE.exists():
            try:
                store = json.loads(AUTH_FILE.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.warning("读取移动端账号文件失败: %s", exc)
        if not isinstance(store, dict) or not store.get("jwt_secret"):
            store = {"jwt_secret": _secrets.token_hex(32), "users": [], "created_at": _utc_now()}
            password = os.environ.get("MOBILE_ADMIN_PASSWORD") or _secrets.token_urlsafe(9)
            _add_user(store, "admin", password, role="admin", display_name="管理员")
            _save_auth(store)
            try:
                ADMIN_CREDENTIALS_FILE.write_text(
                    "PULSE 移动端初始管理员\n用户名: admin\n密码: " + password + "\n生成时间: " + _utc_now() + "\n请登录后立即修改，并删除本文件。\n",
                    encoding="utf-8",
                )
            except Exception:
                pass
            logger.warning("已生成移动端初始管理员 admin，密码见 %s（或用环境变量 MOBILE_ADMIN_PASSWORD 指定）", ADMIN_CREDENTIALS_FILE)
        _AUTH_STORE = store
    return _AUTH_STORE


def _find_user(username: str) -> Optional[Dict[str, Any]]:
    for user in _auth_store().get("users", []):
        if user.get("username") == username:
            return user
    return None


def _verify_password(user: Dict[str, Any], password: str) -> bool:
    try:
        expected = user.get("password_hash") or ""
        actual = _hash_password(password, user.get("salt") or "")
        return bool(expected) and hmac.compare_digest(expected, actual)
    except Exception:
        return False


def _public_user(user: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "username": user.get("username"),
        "display_name": user.get("display_name") or user.get("username"),
        "role": user.get("role") or "viewer",
        "permissions": [name for name, level in _ROLE_LEVEL.items() if level <= _ROLE_LEVEL.get(user.get("role") or "viewer", 0)]
        + ["read"],
        "created_at": user.get("created_at"),
        "avatar_url": user.get("avatar_url") or "",
        "auth_provider": user.get("auth_provider") or "password",
    }


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64d(text: str) -> bytes:
    return base64.urlsafe_b64decode((text + "=" * (-len(text) % 4)).encode("ascii"))


def _issue_token(user: Dict[str, Any], hours: Optional[int] = None) -> Dict[str, Any]:
    hours = hours or int(CONFIG.get("mobile_token_hours", 12))
    now = int(time.time())
    payload = {
        "sub": user.get("username"),
        "role": user.get("role") or "viewer",
        "name": user.get("display_name") or user.get("username"),
        "iat": now,
        "exp": now + max(1, hours) * 3600,
        "iss": "pulse-mobile",
    }
    header_b64 = _b64e(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode("utf-8"))
    payload_b64 = _b64e(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    signing_input = header_b64 + "." + payload_b64
    signature = hmac.new(_auth_store()["jwt_secret"].encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256).digest()
    return {"token": signing_input + "." + _b64e(signature), "expires_in": max(1, hours) * 3600, "expires_at": payload["exp"]}


def _decode_token(token: str) -> Optional[Dict[str, Any]]:
    try:
        parts = (token or "").split(".")
        if len(parts) != 3:
            return None
        signing_input = parts[0] + "." + parts[1]
        expected = hmac.new(_auth_store()["jwt_secret"].encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256).digest()
        if not hmac.compare_digest(_b64e(expected), parts[2]):
            return None
        payload = json.loads(_b64d(parts[1]).decode("utf-8"))
        if int(payload.get("exp") or 0) < int(time.time()):
            return None
        return payload
    except Exception:
        return None


def _token_from_headers(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    value = authorization.strip()
    if value.lower().startswith("bearer "):
        return value[7:].strip()
    return value


def _user_from_request(request: Request) -> Optional[Dict[str, Any]]:
    token = _token_from_headers(request.headers.get("authorization"))
    if not token:
        return None
    payload = _decode_token(token)
    if not payload:
        return None
    user = _find_user(payload.get("sub") or "")
    if not user or user.get("disabled"):
        return None
    return user


def _require_user(request: Request, min_role: Optional[str] = None) -> Dict[str, Any]:
    user = _user_from_request(request)
    if not user:
        raise HTTPException(status_code=401, detail="未登录或登录已过期", headers={"WWW-Authenticate": "Bearer"})
    if min_role:
        need = _ROLE_LEVEL.get(min_role, 1)
        have = _ROLE_LEVEL.get(user.get("role") or "viewer", 0)
        if have < need:
            raise HTTPException(status_code=403, detail="权限不足，需要 " + min_role + " 角色")
    return user


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return getattr(request.client, "host", "") or ""


def _request_via_proxy(request: Request) -> bool:
    return bool(request.headers.get("x-forwarded-for") or request.headers.get("x-real-ip"))


def _ws_allowed(websocket: WebSocket) -> bool:
    headers = websocket.headers
    if not (headers.get("x-forwarded-for") or headers.get("x-real-ip")):
        return True
    if not CONFIG.get("mobile_auth_enabled", True):
        return True
    token = websocket.query_params.get("token")
    if not token:
        protocol = headers.get("sec-websocket-protocol") or ""
        if protocol.startswith("bearer,"):
            token = protocol.split(",", 1)[1].strip()
    payload = _decode_token(token or "")
    if not payload:
        return False
    user = _find_user(payload.get("sub") or "")
    return bool(user and not user.get("disabled"))


def _unauthorized(message: str) -> JSONResponse:
    return JSONResponse(status_code=401, content={"detail": message, "code": "unauthorized"}, headers={"WWW-Authenticate": "Bearer"})


MOBILE_PUBLIC_PATHS = {
    "/api/mobile/login",
    "/api/mobile/bootstrap",
    "/api/mobile/ping",
    "/api/mobile/feishu/start",
    "/api/mobile/feishu/callback",
    "/api/mobile/feishu/poll",
}
API_PUBLIC_PATHS = {"/api", "/api/raspberry/ping", "/api/raspberry/sensors", "/api/feishu/events"}


@app.middleware("http")
async def mobile_auth_guard(request: Request, call_next):
    path = request.url.path
    if request.method == "OPTIONS" or not path.startswith("/api"):
        return await call_next(request)
    if path in API_PUBLIC_PATHS:
        return await call_next(request)
    user = _user_from_request(request)
    is_mobile_path = path == "/api/mobile" or path.startswith("/api/mobile/")
    if path in MOBILE_PUBLIC_PATHS:
        return await call_next(request)
    if is_mobile_path:
        if not user:
            return _unauthorized("移动端接口需要登录")
        request.state.user = user
        return await call_next(request)
    if CONFIG.get("mobile_auth_enabled", True) and _request_via_proxy(request) and not user:
        return _unauthorized("公网访问需要登录")
    if user:
        request.state.user = user
    return await call_next(request)


def _audit(actor: str, role: str, action: str, target: str = "", before: Any = None, after: Any = None, reason: str = "", ip: str = "") -> None:
    record = {
        "ts": _utc_now(),
        "actor": actor or "anonymous",
        "role": role or "",
        "action": action,
        "target": target,
        "before": _mask_value(before),
        "after": _mask_value(after),
        "reason": reason or "",
        "ip": ip,
    }
    try:
        with _AUDIT_LOCK:
            AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)
            with AUDIT_FILE.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning("写入审计日志失败: %s", exc)


def _mask_value(value: Any) -> Any:
    if isinstance(value, dict):
        masked = {}
        for key, item in value.items():
            if key in _SECRET_KEYS and item:
                masked[key] = "***"
            elif key == "devices" and isinstance(item, list):
                masked[key] = "[%d devices]" % len(item)
            elif key == "device_info":
                masked[key] = item.get("id") if isinstance(item, dict) else item
            else:
                masked[key] = item
        return masked
    if isinstance(value, list):
        return [_mask_value(item) for item in value]
    return value


class MobileLoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=200)


def _login_locked(key: str) -> bool:
    now = time.time()
    with _LOGIN_LOCK:
        fails = [ts for ts in _LOGIN_FAILS.get(key, []) if now - ts < LOGIN_WINDOW_SECONDS]
        _LOGIN_FAILS[key] = fails
        return len(fails) >= LOGIN_MAX_FAILS


def _record_login_fail(key: str) -> None:
    with _LOGIN_LOCK:
        _LOGIN_FAILS.setdefault(key, []).append(time.time())


def _clear_login_fails(key: str) -> None:
    with _LOGIN_LOCK:
        _LOGIN_FAILS.pop(key, None)


def _server_meta() -> Dict[str, Any]:
    return {
        "name": "PULSE · 工业监控",
        "version": APP_VERSION,
        "time": _utc_now(),
        "config_version": _config_version(),
    }


@app.get("/api/mobile/ping")
async def mobile_ping():
    return {"ok": True, "server": _server_meta()}


@app.get("/api/mobile/bootstrap")
async def mobile_bootstrap():
    return {
        "server": _server_meta(),
        "auth": {"required": True, "scheme": "Bearer", "login": "/api/mobile/login", "token_hours": int(CONFIG.get("mobile_token_hours", 12))},
        "features": {
            "twin_scene": True,
            "config_patch": True,
            "config_history": True,
            "device_crud": True,
            "audit_log": True,
            "alerts": True,
            "ai_chat": True,
        },
    }


@app.post("/api/mobile/login")
async def mobile_login(request: Request, payload: MobileLoginRequest):
    ip = _client_ip(request)
    key = ip + "|" + payload.username
    if _login_locked(key):
        raise HTTPException(status_code=429, detail="尝试次数过多，请 5 分钟后再试")
    store = _auth_store()
    user = _find_user(payload.username)
    if not user or user.get("disabled") or not _verify_password(user, payload.password):
        _record_login_fail(key)
        _audit(payload.username, "", "login_failed", target="mobile", ip=ip)
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    _clear_login_fails(key)
    token = _issue_token(user)
    _audit(user.get("username"), user.get("role"), "login", target="mobile", ip=ip)
    return {"success": True, "token": token["token"], "token_type": "Bearer", "expires_in": token["expires_in"], "expires_at": token["expires_at"], "user": _public_user(user), "server": _server_meta()}


@app.get("/api/mobile/me")
async def mobile_me(request: Request):
    user = _require_user(request)
    return {"user": _public_user(user), "server": _server_meta(), "auth": {"required": True, "token_hours": int(CONFIG.get("mobile_token_hours", 12))}}


@app.post("/api/mobile/refresh")
async def mobile_refresh(request: Request):
    user = _require_user(request)
    token = _issue_token(user)
    return {"success": True, "token": token["token"], "expires_in": token["expires_in"], "expires_at": token["expires_at"]}

# ==================== 飞书扫码登录（M2） ====================
from urllib.parse import quote

FEISHU_OPEN_BASE = "https://open.feishu.cn"
FEISHU_STATE_TTL = 300
FEISHU_TICKET_TTL = 60
_FEISHU_LOCK = threading.Lock()
_FEISHU_APP_CACHE: Dict[str, Any] = {"token": "", "expires_at": 0.0}
_FEISHU_STATES: Dict[str, Dict[str, Any]] = {}
_FEISHU_RATE: Dict[str, List[float]] = {}
_FEISHU_RATE_LOCK = threading.Lock()


def _feishu_rate_ok(key: str, limit: int, window: float) -> bool:
    now = time.time()
    with _FEISHU_RATE_LOCK:
        if len(_FEISHU_RATE) > 4096:
            for stale in [k for k, v in _FEISHU_RATE.items() if not v or now - v[-1] > 120]:
                _FEISHU_RATE.pop(stale, None)
        points = [ts for ts in _FEISHU_RATE.get(key, []) if now - ts < window]
        if len(points) >= limit:
            _FEISHU_RATE[key] = points
            return False
        points.append(now)
        _FEISHU_RATE[key] = points
        return True


def _feishu_ready() -> Tuple[bool, str]:
    if not CONFIG.get("feishu_login_enabled", True):
        return False, "飞书登录已关闭"
    if not CONFIG.get("feishu_app_id") or not CONFIG.get("feishu_app_secret"):
        return False, "飞书登录未配置"
    if not (CONFIG.get("mobile_public_base_url") or "").strip():
        return False, "未配置 mobile_public_base_url"
    return True, ""


def _feishu_app_access_token(force: bool = False) -> str:
    if os.environ.get("PULSE_FEISHU_MOCK") == "1":
        return "mock-app-access-token"
    now = time.time()
    with _FEISHU_LOCK:
        cached = _FEISHU_APP_CACHE.get("token") or ""
        if cached and not force and _FEISHU_APP_CACHE.get("expires_at", 0.0) > now + 120:
            return cached
    resp = requests.post(
        FEISHU_OPEN_BASE + "/open-apis/auth/v3/app_access_token/internal",
        json={"app_id": CONFIG.get("feishu_app_id"), "app_secret": CONFIG.get("feishu_app_secret")},
        timeout=10,
    )
    data = resp.json()
    if int(data.get("code") or 0) != 0:
        raise RuntimeError(data.get("msg") or "获取飞书应用凭证失败")
    token = data.get("app_access_token") or (data.get("data") or {}).get("app_access_token") or ""
    if not token:
        raise RuntimeError("飞书应用凭证为空")
    expire = int(data.get("expire") or 7200)
    with _FEISHU_LOCK:
        _FEISHU_APP_CACHE["token"] = token
        _FEISHU_APP_CACHE["expires_at"] = now + max(60, expire - 120)
    return token


def _feishu_exchange_code(code: str) -> Dict[str, Any]:
    if os.environ.get("PULSE_FEISHU_MOCK") == "1":
        parts = (code or "").split(":")
        open_id = parts[1] if len(parts) > 1 and parts[1] else "ou_mock_user"
        name = parts[2] if len(parts) > 2 and parts[2] else "飞书用户"
        avatar = parts[3] if len(parts) > 3 else ""
        return {"open_id": open_id, "name": name, "avatar_url": avatar}
    app_token = _feishu_app_access_token()
    resp = requests.post(
        FEISHU_OPEN_BASE + "/open-apis/authen/v1/access_token",
        headers={"Authorization": "Bearer " + app_token, "Content-Type": "application/json; charset=utf-8"},
        json={"grant_type": "authorization_code", "code": code},
        timeout=10,
    )
    payload = resp.json()
    if int(payload.get("code") or 0) != 0:
        raise RuntimeError(payload.get("msg") or "飞书授权码无效")
    data = payload.get("data") or {}
    open_id = data.get("open_id") or ""
    if not open_id:
        raise RuntimeError("飞书未返回 open_id")
    return {
        "open_id": open_id,
        "name": data.get("name") or data.get("en_name") or open_id,
        "avatar_url": data.get("avatar_url") or "",
    }


def _feishu_cleanup_states() -> None:
    now = time.time()
    for key in [k for k, v in _FEISHU_STATES.items() if now - float(v.get("created_at") or 0) > FEISHU_STATE_TTL + 120]:
        _FEISHU_STATES.pop(key, None)


def _feishu_allowed_ids() -> List[str]:
    raw = CONFIG.get("feishu_login_allowed_open_ids") or []
    if isinstance(raw, str):
        raw = [item.strip() for item in raw.split(",")]
    return [str(item).strip() for item in raw if str(item).strip()]


def _feishu_upsert_user(info: Dict[str, Any], ip: str = "") -> Tuple[Optional[Dict[str, Any]], str]:
    open_id = (info.get("open_id") or "").strip()
    if not open_id:
        return None, "未获取到飞书用户标识"
    with _AUTH_LOCK:
        store = _auth_store()
        users = store.setdefault("users", [])
        allowed = _feishu_allowed_ids()
        user = next((item for item in users if item.get("feishu_open_id") == open_id), None)
        bootstrapped = False
        if user is None:
            has_feishu = any(item.get("feishu_open_id") for item in users)
            if open_id not in allowed:
                if allowed or has_feishu:
                    return None, "未授权：请联系管理员把您的飞书账号加入允许名单"
            role = "viewer"
            if not allowed and not has_feishu:
                role = "admin"
                bootstrapped = True
                CONFIG["feishu_login_allowed_open_ids"] = [open_id]
            user = {
                "username": open_id,
                "display_name": info.get("name") or open_id,
                "role": role,
                "salt": "",
                "password_hash": "",
                "disabled": False,
                "created_at": _utc_now(),
                "auth_provider": "feishu",
                "feishu_open_id": open_id,
                "avatar_url": info.get("avatar_url") or "",
            }
            users.append(user)
        else:
            if open_id not in allowed:
                return None, "未授权：您的飞书账号已从允许名单移除"
            user["display_name"] = info.get("name") or user.get("display_name") or open_id
            user["avatar_url"] = info.get("avatar_url") or user.get("avatar_url") or ""
            user["auth_provider"] = "feishu"
        _save_auth(store)
    if bootstrapped:
        try:
            save_config()
        except Exception as exc:
            logger.warning("保存飞书允许名单失败: %s", exc)
        _audit(open_id, "admin", "feishu.bootstrap", target="mobile", after={"open_id": open_id}, ip=ip)
        logger.warning("飞书首登引导：%s 已自动成为管理员，并写入允许名单", open_id)
    return user, ""


def _feishu_esc(text: Any) -> str:
    return (
        str(text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def _feishu_page(title: str, message: str, detail: str = "", ok: bool = True) -> HTMLResponse:
    accent = "#12B76A" if ok else "#F04438"
    title = _feishu_esc(title)
    message = _feishu_esc(message)
    detail_html = ('<div class="detail">' + _feishu_esc(detail).replace("\n", "<br>") + "</div>") if detail else ""
    html = (
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>" + title + " · PULSE</title><style>"
        "html,body{margin:0;min-height:100%;background:#F4F5F7;color:#101828;"
        "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif}"
        ".wrap{min-height:100vh;display:flex;align-items:center;justify-content:center;padding:24px;box-sizing:border-box}"
        ".card{width:100%;max-width:360px;background:#fff;border:1px solid #EAECF0;border-radius:20px;"
        "box-shadow:0 18px 40px rgba(16,24,40,.08);padding:28px 24px;text-align:center}"
        ".brand{font-size:12px;letter-spacing:.16em;color:#98A2B3;margin-bottom:18px}"
        ".badge{width:56px;height:56px;border-radius:18px;margin:0 auto 18px;display:flex;align-items:center;"
        "justify-content:center;background:" + accent + "14;color:" + accent + ";font-size:24px;font-weight:600}"
        "h1{font-size:20px;line-height:1.35;margin:0 0 10px}"
        "p{font-size:14px;line-height:1.6;color:#667085;margin:0}"
        ".detail{margin-top:14px;padding:12px 14px;background:#F8F9FB;border:1px solid #F2F4F7;border-radius:12px;"
        "font-size:12px;color:#475467;word-break:break-all;text-align:left}"
        ".foot{margin-top:20px;font-size:12px;color:#98A2B3}"
        "</style></head><body><div class=\"wrap\"><div class=\"card\">"
        '<div class="brand">PULSE · 工业监控</div>'
        '<div class="badge">' + ("&#10003;" if ok else "!") + "</div>"
        "<h1>" + title + "</h1><p>" + message + "</p>"
        + detail_html
        + '<div class="foot">可以关闭此页面，返回 PULSE App</div>'
        "</div></div></body></html>"
    )
    return HTMLResponse(html, status_code=200 if ok else 400)


class FeishuPollRequest(BaseModel):
    state: str = Field(min_length=4, max_length=128)


class FeishuAllowlistRequest(BaseModel):
    open_id: str = Field(min_length=4, max_length=128)
    display_name: str = Field(default="", max_length=64)
    role: str = Field(default="viewer", max_length=16)


@app.get("/api/mobile/feishu/start")
async def feishu_login_start(request: Request, redirect: str = "app"):
    ip = _client_ip(request)
    if not _feishu_rate_ok("feishu-start:" + ip, 10, 60):
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")
    ready, reason = _feishu_ready()
    if not ready:
        raise HTTPException(status_code=400, detail=reason)
    _feishu_cleanup_states()
    state = _secrets.token_urlsafe(24)
    base = (CONFIG.get("mobile_public_base_url") or "").strip().rstrip("/")
    redirect_uri = base + "/api/mobile/feishu/callback"
    app_id = str(CONFIG.get("feishu_app_id") or "")
    authorize_url = (
        FEISHU_OPEN_BASE + "/open-apis/authen/v1/index?app_id=" + quote(app_id)
        + "&redirect_uri=" + quote(redirect_uri, safe="")
        + "&state=" + quote(state, safe="")
    )
    _FEISHU_STATES[state] = {
        "created_at": time.time(),
        "status": "pending",
        "redirect": redirect,
        "ip": ip,
    }
    return {
        "enabled": True,
        "state": state,
        "authorize_url": authorize_url,
        "expires_in": FEISHU_STATE_TTL,
        "poll_interval": 2,
        "server": _server_meta(),
    }


@app.get("/api/mobile/feishu/callback")
async def feishu_login_callback(request: Request, code: str = "", state: str = "", error: str = ""):
    ip = _client_ip(request)
    if not _feishu_rate_ok("feishu-cb:" + ip, 30, 60):
        return _feishu_page("请求过于频繁", "请稍后在 App 内重新发起登录。", ok=False)
    _feishu_cleanup_states()
    item = _FEISHU_STATES.get(state)
    if not item:
        return _feishu_page("登录链接已失效", "请回到 App，重新点击“使用飞书登录”。", ok=False)
    if item.get("status") == "ready":
        return _feishu_page("已完成授权", "请返回 App 继续使用。")
    if error or not code:
        item["status"] = "denied"
        item["message"] = "您取消了飞书授权"
        return _feishu_page("已取消授权", "如仍需登录，请回到 App 重试。", ok=False)
    try:
        info = _feishu_exchange_code(code)
    except Exception as exc:
        logger.warning("飞书授权码换取失败: %s", exc)
        item["status"] = "error"
        item["message"] = "飞书授权失败，请重试"
        return _feishu_page("授权失败", "飞书返回异常，请回到 App 重新登录。", detail=str(exc)[:120], ok=False)
    user, reason = _feishu_upsert_user(info, ip=ip)
    if not user:
        item["status"] = "denied"
        item["message"] = reason
        item["open_id"] = info.get("open_id") or ""
        _audit(info.get("open_id") or "", "", "feishu.denied", target="mobile", reason=reason, ip=ip)
        detail = "open_id: " + (info.get("open_id") or "") + ("\n请把上面的 open_id 发给管理员，加入允许名单后再登录。" if info.get("open_id") else "")
        return _feishu_page("未授权", reason, detail=detail, ok=False)
    token = _issue_token(user)
    item.update({
        "status": "ready",
        "ticket": token["token"],
        "ticket_expires_at": time.time() + FEISHU_TICKET_TTL,
        "user": _public_user(user),
        "server": _server_meta(),
    })
    _audit(user.get("username"), user.get("role"), "feishu.login", target="mobile", ip=ip)
    return _feishu_page("登录成功", "已通过飞书完成授权，请返回 App 继续。")


@app.post("/api/mobile/feishu/poll")
async def feishu_login_poll(request: Request, payload: FeishuPollRequest):
    ip = _client_ip(request)
    if not _feishu_rate_ok("feishu-poll:" + ip + ":" + str(payload.state)[:16], 5, 1):
        raise HTTPException(status_code=429, detail="轮询过于频繁")
    _feishu_cleanup_states()
    item = _FEISHU_STATES.get(payload.state)
    if not item:
        return {"status": "expired", "message": "登录二维码已过期，请重新发起"}
    if time.time() - float(item.get("created_at") or 0) > FEISHU_STATE_TTL:
        _FEISHU_STATES.pop(payload.state, None)
        return {"status": "expired", "message": "登录二维码已过期，请重新发起"}
    status = item.get("status") or "pending"
    if status == "pending":
        return {"status": "pending", "poll_interval": 2}
    if status == "ready":
        ticket = item.get("ticket") or ""
        if not ticket or time.time() > float(item.get("ticket_expires_at") or 0):
            item["status"] = "expired"
            return {"status": "expired", "message": "登录票据已过期，请重新发起"}
        item["status"] = "expired"
        item.pop("ticket", None)
        return {
            "status": "ready",
            "token": ticket,
            "token_type": "Bearer",
            "expires_in": max(1, int(CONFIG.get("mobile_token_hours", 12))) * 3600,
            "user": item.get("user"),
            "server": item.get("server") or _server_meta(),
        }
    if status == "denied":
        return {"status": "denied", "message": item.get("message") or "授权未通过", "open_id": item.get("open_id") or ""}
    if status == "expired":
        return {"status": "expired", "message": "登录已失效，请重新发起"}
    return {"status": "error", "message": item.get("message") or "登录失败，请重试"}


@app.get("/api/mobile/feishu/allowlist")
async def feishu_allowlist_get(request: Request):
    user = _require_user(request, "admin")
    ids = _feishu_allowed_ids()
    users = [
        {"open_id": item.get("feishu_open_id"), "username": item.get("username"), "display_name": item.get("display_name"),
         "role": item.get("role"), "disabled": bool(item.get("disabled")), "created_at": item.get("created_at")}
        for item in _auth_store().get("users", [])
        if item.get("feishu_open_id")
    ]
    return {"allowed_open_ids": ids, "users": users, "updated_by": user.get("username")}


@app.post("/api/mobile/feishu/allowlist")
async def feishu_allowlist_add(request: Request, payload: FeishuAllowlistRequest):
    actor = _require_user(request, "admin")
    open_id = payload.open_id.strip()
    if not open_id:
        raise HTTPException(status_code=422, detail="open_id 不能为空")
    role = payload.role if payload.role in _ROLE_LEVEL else "viewer"
    ids = _feishu_allowed_ids()
    if open_id not in ids:
        ids.append(open_id)
        CONFIG["feishu_login_allowed_open_ids"] = ids
    with _AUTH_LOCK:
        store = _auth_store()
        users = store.setdefault("users", [])
        target = next((item for item in users if item.get("feishu_open_id") == open_id), None)
        if target is None:
            target = {
                "username": open_id,
                "display_name": payload.display_name or open_id,
                "role": role,
                "salt": "",
                "password_hash": "",
                "disabled": False,
                "created_at": _utc_now(),
                "auth_provider": "feishu",
                "feishu_open_id": open_id,
                "avatar_url": "",
            }
            users.append(target)
        else:
            target["role"] = role
            if payload.display_name:
                target["display_name"] = payload.display_name
        _save_auth(store)
    try:
        save_config()
    except Exception as exc:
        logger.warning("保存飞书允许名单失败: %s", exc)
    _audit(actor.get("username"), actor.get("role"), "feishu.allowlist_add", target=open_id, after={"role": role}, ip=_client_ip(request))
    return {"success": True, "allowed_open_ids": ids, "user": _public_user(target)}


@app.get("/mobile/twin")
async def mobile_twin_page():
    target = STATIC_DIR / "mobile-twin.html"
    if not target.exists():
        raise HTTPException(status_code=404, detail="孪生页面未部署")
    return FileResponse(target, headers={"Cache-Control": "no-store, no-cache, must-revalidate"})




try:
    _auth_store()
except Exception as _auth_exc:
    logger.warning("初始化移动端账号失败: %s", _auth_exc)


# ---------- 配置 Schema ----------
_CONFIG_SCHEMA_GROUPS = [
    {
        "id": "database",
        "title": "数据库与存储",
        "description": "MySQL 连接失败会自动回退 SQLite；修改后需重新初始化。",
        "fields": [
            {"key": "database_backend", "label": "数据库后端", "type": "enum", "options": ["mysql", "sqlite"], "restart_required": True},
            {"key": "mysql_host", "label": "MySQL 主机", "type": "string", "max_length": 120},
            {"key": "mysql_port", "label": "MySQL 端口", "type": "int", "min": 1, "max": 65535},
            {"key": "mysql_user", "label": "MySQL 用户", "type": "string", "max_length": 64},
            {"key": "mysql_password", "label": "MySQL 密码", "type": "secret", "sensitive": True},
            {"key": "mysql_database", "label": "数据库名", "type": "string", "max_length": 64},
        ],
    },
    {
        "id": "thresholds",
        "title": "阈值与报警",
        "description": "超过阈值并满足连续触发次数后产生报警。",
        "fields": [
            {"key": "thresholds.temperature", "label": "温度阈值", "type": "float", "min": -40, "max": 150, "unit": "°C", "step": 0.5},
            {"key": "thresholds.humidity", "label": "湿度阈值", "type": "float", "min": 0, "max": 100, "unit": "%", "step": 1},
            {"key": "thresholds.vibration", "label": "振动阈值", "type": "float", "min": 0, "max": 20, "unit": "mm/s", "step": 0.01},
            {"key": "alarm_trigger_count", "label": "连续触发次数", "type": "int", "min": 1, "max": 20},
            {"key": "alarm_window_seconds", "label": "报警窗口", "type": "int", "min": 1, "max": 3600, "unit": "秒"},
            {"key": "alarm_cooldown_seconds", "label": "报警冷却", "type": "int", "min": 0, "max": 3600, "unit": "秒"},
            {"key": "sensor_interval", "label": "采集间隔", "type": "int", "min": 1, "max": 300, "unit": "秒"},
        ],
    },
    {
        "id": "ai",
        "title": "AI 模型与 RAG",
        "fields": [
            {"key": "ollama_enabled", "label": "启用 Ollama", "type": "bool"},
            {"key": "ollama_url", "label": "Ollama 地址", "type": "url", "placeholder": "http://localhost:11434"},
            {"key": "ollama_model", "label": "模型名称", "type": "string", "max_length": 120},
            {"key": "rag_enabled", "label": "启用知识库", "type": "bool"},
            {"key": "rag_top_k", "label": "检索片段数", "type": "int", "min": 1, "max": 20},
            {"key": "agent_enabled", "label": "启用多 Agent", "type": "bool"},
            {"key": "agent_api_backend", "label": "Agent 后端", "type": "enum", "options": ["ollama", "openai"], "restart_required": True},
            {"key": "agent_api_url", "label": "云端 API 地址", "type": "url"},
            {"key": "agent_api_model", "label": "云端模型", "type": "string", "max_length": 120},
            {"key": "agent_api_key", "label": "云端 API Key", "type": "secret", "sensitive": True},
            {"key": "agent_search_enabled", "label": "允许联网检索", "type": "bool"},
        ],
    },
    {
        "id": "feishu",
        "title": "飞书与通知",
        "fields": [
            {"key": "feishu_webhook", "label": "群机器人 Webhook", "type": "url", "sensitive": True},
            {"key": "feishu_app_id", "label": "应用 App ID", "type": "string", "max_length": 120},
            {"key": "feishu_app_secret", "label": "应用 App Secret", "type": "secret", "sensitive": True},
            {"key": "feishu_verification_token", "label": "事件校验 Token", "type": "secret", "sensitive": True},
            {"key": "feishu_event_url", "label": "事件回调地址", "type": "url"},
            {"key": "feishu_forward_ai_replies", "label": "转发 AI 回复", "type": "bool"},
            {"key": "feishu_receive_group_messages", "label": "接收群消息", "type": "bool"},
            {"key": "feishu_long_connection_enabled", "label": "长连接接收事件", "type": "bool"},
        ],
    },
    {
        "id": "system",
        "title": "移动端与安全",
        "fields": [
            {"key": "mobile_auth_enabled", "label": "公网访问强制鉴权", "type": "bool", "help": "开启后，经反向代理（带 X-Forwarded-For）的请求必须携带 Token。"},
            {"key": "mobile_token_hours", "label": "Token 有效期", "type": "int", "min": 1, "max": 240, "unit": "小时"},
        ],
    },
]

_SCHEMA_FLAT = {}
for _group in _CONFIG_SCHEMA_GROUPS:
    for _field in _group["fields"]:
        _SCHEMA_FLAT[_field["key"]] = _field


def _get_path(key: str) -> Any:
    value = CONFIG
    for part in key.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def _set_path(key: str, value: Any) -> None:
    parts = key.split(".")
    target = CONFIG
    for part in parts[:-1]:
        if not isinstance(target.get(part), dict):
            target[part] = {}
        target = target[part]
    target[parts[-1]] = value


def _schema_payload() -> Dict[str, Any]:
    groups = []
    for group in _CONFIG_SCHEMA_GROUPS:
        fields = []
        for field in group["fields"]:
            current = _get_path(field["key"])
            if field.get("type") == "secret":
                item = {**field, "current": None, "has_value": bool(current)}
            else:
                item = {**field, "current": current}
            fields.append(item)
        groups.append({"id": group["id"], "title": group.get("title"), "description": group.get("description", ""), "fields": fields})
    state = _load_config_state()
    return {
        "version": _config_version(),
        "updated_at": state.get("updated_at"),
        "updated_by": state.get("updated_by"),
        "groups": groups,
        "devices_managed_by": "/api/device",
        "roles": _ROLE_LEVEL,
    }


# ---------- 配置版本/审计 ----------
def _load_config_state() -> Dict[str, Any]:
    if CONFIG_STATE_FILE.exists():
        try:
            state = json.loads(CONFIG_STATE_FILE.read_text(encoding="utf-8"))
            if isinstance(state, dict):
                state.setdefault("version", 1)
                state.setdefault("history", [])
                return state
        except Exception as exc:
            logger.warning("读取配置版本文件失败: %s", exc)
    return {"version": 1, "updated_at": None, "updated_by": None, "history": []}


def _save_config_state(state: Dict[str, Any]) -> None:
    try:
        CONFIG_STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        logger.warning("写入配置版本文件失败: %s", exc)


def _config_version() -> int:
    try:
        return int(_load_config_state().get("version") or 1)
    except Exception:
        return 1


def _masked_snapshot() -> Dict[str, Any]:
    snapshot = copy.deepcopy(CONFIG)
    for key in _SECRET_KEYS:
        if key in snapshot:
            snapshot[key] = ""
    return snapshot


def _masked_changes(changes: Dict[str, Any]) -> Dict[str, Any]:
    masked = {}
    for key, value in changes.items():
        masked[key] = "***" if key in _SECRET_KEYS and value else value
    return masked


def _bump_config_version(actor: str, role: str, action: str, changes: Dict[str, Any], reason: str = "") -> int:
    with _CONFIG_LOCK:
        state = _load_config_state()
        state["version"] = int(state.get("version") or 1) + 1
        state["updated_at"] = _utc_now()
        state["updated_by"] = actor
        entry = {
            "version": state["version"],
            "at": state["updated_at"],
            "by": actor,
            "role": role,
            "action": action,
            "reason": reason or "",
            "changes": _masked_changes(changes),
            "snapshot": _masked_snapshot(),
        }
        state.setdefault("history", []).append(entry)
        state["history"] = state["history"][-20:]
        _save_config_state(state)
        return state["version"]


def _coerce_config_types() -> None:
    if isinstance(CONFIG.get("thresholds"), dict):
        CONFIG["thresholds"]["temperature"] = float(CONFIG["thresholds"].get("temperature", 40))
        CONFIG["thresholds"]["humidity"] = float(CONFIG["thresholds"].get("humidity", 80))
        CONFIG["thresholds"]["vibration"] = float(CONFIG["thresholds"].get("vibration", 0.5))
    for key in ("alarm_trigger_count", "alarm_window_seconds", "alarm_cooldown_seconds", "sensor_interval", "rag_top_k", "mysql_port", "mobile_token_hours"):
        try:
            CONFIG[key] = int(CONFIG.get(key))
        except (TypeError, ValueError):
            pass


def _validate_changes(changes: Dict[str, Any]) -> Dict[str, Any]:
    flat = {}
    errors = []
    for key, value in (changes or {}).items():
        if key == "thresholds" and isinstance(value, dict):
            for sub_key, sub_value in value.items():
                flat["thresholds." + sub_key] = sub_value
            continue
        if key == "devices":
            errors.append({"key": key, "message": "设备请使用 /api/device 接口管理"})
            continue
        flat[key] = value
    clean = {}
    for key, value in flat.items():
        if key == "selected_device_id":
            if not any(device.get("id") == value for device in CONFIG.get("devices", [])):
                errors.append({"key": key, "message": "设备不存在"})
            else:
                clean[key] = value
            continue
        field = _SCHEMA_FLAT.get(key)
        if not field:
            errors.append({"key": key, "message": "未知配置项"})
            continue
        field_type = field.get("type")
        if field_type == "secret" and value == "***":
            continue
        if field_type == "bool":
            if not isinstance(value, bool):
                errors.append({"key": key, "message": "需要布尔值"})
                continue
        elif field_type == "int":
            if isinstance(value, bool) or not isinstance(value, int):
                errors.append({"key": key, "message": "需要整数"})
                continue
            if "min" in field and value < field["min"] or "max" in field and value > field["max"]:
                errors.append({"key": key, "message": "超出范围 %s ~ %s" % (field.get("min"), field.get("max"))})
                continue
        elif field_type == "float":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                errors.append({"key": key, "message": "需要数字"})
                continue
            value = float(value)
            if ("min" in field and value < field["min"]) or ("max" in field and value > field["max"]):
                errors.append({"key": key, "message": "超出范围 %s ~ %s" % (field.get("min"), field.get("max"))})
                continue
        elif field_type in ("string", "secret", "url"):
            if not isinstance(value, str):
                errors.append({"key": key, "message": "需要字符串"})
                continue
            if len(value) > int(field.get("max_length", 500)):
                errors.append({"key": key, "message": "长度超限"})
                continue
            if field_type == "url" and value and not value.startswith(("http://", "https://")):
                errors.append({"key": key, "message": "需要 http(s) 地址"})
                continue
        elif field_type == "enum":
            if value not in field.get("options", []):
                errors.append({"key": key, "message": "可选值: " + ", ".join(field.get("options", []))})
                continue
        clean[key] = value
    if errors:
        raise HTTPException(status_code=422, detail={"code": "validation_failed", "errors": errors})
    return clean


class ConfigPatchRequest(BaseModel):
    base_version: int
    changes: Dict[str, Any]
    reason: Optional[str] = Field(default=None, max_length=200)


def _apply_changes(clean: Dict[str, Any]) -> List[str]:
    changed = []
    for key, value in clean.items():
        if _get_path(key) == value:
            continue
        _set_path(key, value)
        changed.append(key)
    if not changed:
        return changed
    _coerce_config_types()
    normalize_device_config()
    alarm_keys = ("thresholds.temperature", "thresholds.humidity", "thresholds.vibration", "alarm_trigger_count", "alarm_window_seconds")
    if any(key in alarm_keys for key in changed):
        alarm_checker.anomaly_windows.clear()
        alarm_checker.last_alert_time.clear()
    save_config()
    try:
        save_cloud_config()
    except Exception as exc:
        logger.warning("保存云端配置失败: %s", exc)
    if any(key.startswith("mysql_") or key == "database_backend" for key in changed):
        try:
            init_db()
        except Exception as exc:
            logger.warning("数据库配置变更后初始化失败: %s", exc)
    return changed


@app.get("/api/mobile/config-schema")
async def mobile_config_schema(request: Request):
    _require_user(request)
    return _schema_payload()


@app.get("/api/config/schema")
async def config_schema_alias(request: Request):
    _require_user(request)
    return _schema_payload()


@app.patch("/api/settings")
async def patch_settings(request: Request, payload: ConfigPatchRequest):
    user = _require_user(request, "admin")
    current = _config_version()
    if int(payload.base_version) != current:
        raise HTTPException(status_code=409, detail={"code": "version_conflict", "current_version": current, "your_version": payload.base_version})
    clean = _validate_changes(payload.changes)
    changed = _apply_changes(clean)
    if not changed:
        return {"success": True, "version": current, "changed": [], "message": "没有变化"}
    version = _bump_config_version(user.get("username"), user.get("role"), "settings.patch", clean, payload.reason or "")
    _audit(user.get("username"), user.get("role"), "settings.patch", target="config", after=clean, reason=payload.reason or "", ip=_client_ip(request))
    warnings = [field["key"] + " 需要重启服务后生效" for field in _SCHEMA_FLAT.values() if field.get("restart_required") and field["key"] in changed]
    return {"success": True, "version": version, "changed": changed, "warnings": warnings, "database": database_status() if any(key.startswith("mysql_") or key == "database_backend" for key in changed) else None}


@app.get("/api/settings/history")
async def settings_history(request: Request, limit: int = 20):
    _require_user(request)
    state = _load_config_state()
    history = list(reversed(state.get("history", [])))[: max(1, min(limit, 50))]
    items = [{key: value for key, value in entry.items() if key != "snapshot"} for entry in history]
    return {"version": state.get("version"), "updated_at": state.get("updated_at"), "updated_by": state.get("updated_by"), "items": items}


class ConfigRollbackRequest(BaseModel):
    version: int
    reason: Optional[str] = Field(default=None, max_length=200)


@app.post("/api/settings/rollback")
async def rollback_settings(request: Request, payload: ConfigRollbackRequest):
    user = _require_user(request, "admin")
    state = _load_config_state()
    entry = next((item for item in reversed(state.get("history", [])) if int(item.get("version", -1)) == int(payload.version)), None)
    if not entry or not isinstance(entry.get("snapshot"), dict):
        raise HTTPException(status_code=404, detail="找不到该版本的配置快照")
    snapshot = entry["snapshot"]
    changes = {}
    for key, value in snapshot.items():
        if key in _SECRET_KEYS or key in ("device_info",):
            continue
        if key == "devices":
            CONFIG["devices"] = copy.deepcopy(value)
            changes["devices"] = "[%d devices]" % len(value)
            continue
        CONFIG[key] = copy.deepcopy(value)
        changes[key] = value
    _coerce_config_types()
    normalize_device_config()
    save_config()
    try:
        save_cloud_config()
    except Exception as exc:
        logger.warning("回滚后保存云端配置失败: %s", exc)
    version = _bump_config_version(user.get("username"), user.get("role"), "settings.rollback", {"target_version": payload.version}, payload.reason or "")
    _audit(user.get("username"), user.get("role"), "settings.rollback", target="config", after={"target_version": payload.version}, reason=payload.reason or "", ip=_client_ip(request))
    return {"success": True, "version": version, "rolled_back_to": payload.version, "changed": list(changes.keys())}


@app.get("/api/system/audit")
async def system_audit(request: Request, limit: int = 50):
    _require_user(request, "admin")
    items = []
    if AUDIT_FILE.exists():
        try:
            lines = AUDIT_FILE.read_text(encoding="utf-8").splitlines()
            for line in reversed(lines[-max(1, min(limit, 200)):]):
                try:
                    items.append(json.loads(line))
                except Exception:
                    continue
        except Exception as exc:
            logger.warning("读取审计日志失败: %s", exc)
    return {"items": items, "count": len(items)}


# ---------- 设备 CRUD ----------
_DEVICE_STATUS = {"运行中", "维护中", "离线", "停用"}


class DeviceCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    latitude: Optional[str] = ""
    longitude: Optional[str] = ""
    status: Optional[str] = "运行中"
    model_url: Optional[str] = ""
    model_filename: Optional[str] = ""
    zone: Optional[str] = ""
    twin: Optional[Dict[str, Any]] = None


class DevicePatchRequest(BaseModel):
    name: Optional[str] = None
    latitude: Optional[str] = None
    longitude: Optional[str] = None
    status: Optional[str] = None
    model_url: Optional[str] = None
    model_filename: Optional[str] = None
    zone: Optional[str] = None
    twin: Optional[Dict[str, Any]] = None


def _validate_device_fields(payload: Dict[str, Any]) -> Dict[str, Any]:
    clean = {}
    for key in ("name", "latitude", "longitude"):
        if payload.get(key) is not None:
            value = str(payload[key]).strip()
            if key == "name" and not value:
                raise HTTPException(status_code=422, detail="设备名称不能为空")
            if len(value) > 120:
                raise HTTPException(status_code=422, detail=key + " 过长")
            clean[key] = value
    if payload.get("status") is not None:
        if payload["status"] not in _DEVICE_STATUS:
            raise HTTPException(status_code=422, detail="状态可选: " + ", ".join(sorted(_DEVICE_STATUS)))
        clean["status"] = payload["status"]
    if payload.get("model_url") is not None:
        value = str(payload["model_url"]).strip()
        if value and not value.startswith("/static/uploads/device_models/"):
            raise HTTPException(status_code=422, detail="模型地址必须位于 /static/uploads/device_models/ 下")
        clean["model_url"] = value
    if payload.get("model_filename") is not None:
        value = str(payload["model_filename"]).strip()
        if value and ("/" in value or "\\" in value or ".." in value):
            raise HTTPException(status_code=422, detail="模型文件名不合法")
        clean["model_filename"] = value[:200]
    if payload.get("zone") is not None:
        clean["zone"] = str(payload["zone"]).strip()[:32]
    if payload.get("twin") is not None:
        twin = payload["twin"]
        if not isinstance(twin, dict):
            raise HTTPException(status_code=422, detail="twin 需要对象")
        position = twin.get("position")
        if position is not None and (not isinstance(position, list) or len(position) != 3 or not all(isinstance(item, (int, float)) for item in position)):
            raise HTTPException(status_code=422, detail="twin.position 需要 [x, y, z]")
        rotation = twin.get("rotation")
        if rotation is not None and not isinstance(rotation, (int, float)):
            raise HTTPException(status_code=422, detail="twin.rotation 需要数字")
        clean["twin"] = {
            "position": [float(item) for item in position] if position is not None else None,
            "rotation": float(rotation) if rotation is not None else None,
            "zone": str(twin.get("zone") or "").strip()[:32] or None,
        }
        clean["twin"] = {key: value for key, value in clean["twin"].items() if value is not None}
    return clean


@app.get("/api/devices")
async def list_devices(request: Request):
    _require_user(request)
    devices = []
    for device in CONFIG.get("devices", []):
        item = dict(device)
        item["selected"] = device.get("id") == CONFIG.get("selected_device_id")
        devices.append(item)
    return {"devices": devices, "selected_device_id": CONFIG.get("selected_device_id"), "version": _config_version()}


@app.post("/api/device")
async def create_device(request: Request, payload: DeviceCreateRequest):
    user = _require_user(request, "admin")
    clean = _validate_device_fields(payload.model_dump(exclude_none=True))
    device_id = "device-" + str(int(time.time() * 1000))
    while any(device.get("id") == device_id for device in CONFIG.get("devices", [])):
        device_id = "device-" + str(int(time.time() * 1000) + _secrets.randbelow(1000))
    device = {
        "id": device_id,
        "name": clean.get("name") or "新设备",
        "latitude": clean.get("latitude") or "",
        "longitude": clean.get("longitude") or "",
        "registered_at": datetime.now().date().isoformat(),
        "status": clean.get("status") or "运行中",
        "model_url": clean.get("model_url") or "",
        "model_filename": clean.get("model_filename") or "",
    }
    if clean.get("zone"):
        device["zone"] = clean["zone"]
    if clean.get("twin"):
        device["twin"] = clean["twin"]
    CONFIG.setdefault("devices", []).append(device)
    normalize_device_config()
    save_config()
    version = _bump_config_version(user.get("username"), user.get("role"), "device.create", {"device_id": device_id}, "")
    _audit(user.get("username"), user.get("role"), "device.create", target=device_id, after=_mask_value(device), ip=_client_ip(request))
    return {"success": True, "device": device, "version": version}


@app.patch("/api/device/{device_id}")
async def patch_device(request: Request, device_id: str, payload: DevicePatchRequest):
    user = _require_user(request, "admin")
    device = next((item for item in CONFIG.get("devices", []) if item.get("id") == device_id), None)
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")
    clean = _validate_device_fields(payload.model_dump(exclude_none=True))
    before = {key: device.get(key) for key in clean}
    device.update(clean)
    normalize_device_config()
    save_config()
    version = _bump_config_version(user.get("username"), user.get("role"), "device.update", {"device_id": device_id}, "")
    _audit(user.get("username"), user.get("role"), "device.update", target=device_id, before=before, after=clean, ip=_client_ip(request))
    return {"success": True, "device": device, "version": version}


@app.delete("/api/device/{device_id}")
async def delete_device(request: Request, device_id: str):
    user = _require_user(request, "admin")
    devices = CONFIG.get("devices", [])
    device = next((item for item in devices if item.get("id") == device_id), None)
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")
    if len(devices) <= 1:
        raise HTTPException(status_code=400, detail="至少保留一台设备")
    CONFIG["devices"] = [item for item in devices if item.get("id") != device_id]
    if CONFIG.get("selected_device_id") == device_id:
        CONFIG["selected_device_id"] = CONFIG["devices"][0]["id"]
    normalize_device_config()
    save_config()
    version = _bump_config_version(user.get("username"), user.get("role"), "device.delete", {"device_id": device_id}, "")
    _audit(user.get("username"), user.get("role"), "device.delete", target=device_id, before=_mask_value(device), ip=_client_ip(request))
    return {"success": True, "deleted": device_id, "version": version}


# ---------- 健康检查 ----------
_HEALTH_CACHE = {"ts": 0.0, "db": None}


def _cached_database_status() -> Dict[str, Any]:
    now = time.time()
    if _HEALTH_CACHE["db"] and now - _HEALTH_CACHE["ts"] < 10:
        return _HEALTH_CACHE["db"]
    status = database_status()
    _HEALTH_CACHE.update(ts=now, db=status)
    return status


@app.get("/api/system/health")
async def system_health(detail: bool = False):
    db = database_status() if detail else _cached_database_status()
    devices = CONFIG.get("devices", [])
    counts = {"total": len(devices), "running": 0, "maintenance": 0, "offline": 0}
    for device in devices:
        status = device.get("status") or "运行中"
        if status == "运行中":
            counts["running"] += 1
        elif status in ("维护中", "停用"):
            counts["maintenance"] += 1
        else:
            counts["offline"] += 1
    sensor_ts = latest_pi_sensor_data.get("timestamp")
    sensor_online = False
    if sensor_ts:
        try:
            sensor_online = (datetime.now() - datetime.fromisoformat(str(sensor_ts))).total_seconds() < 180
        except Exception:
            sensor_online = False
    healthy = bool(db.get("connected") or db.get("backend") == "sqlite") and not db.get("fallback")
    return {
        "status": "ok" if healthy else "degraded",
        "time": _utc_now(),
        "uptime_seconds": int(time.time() - SERVER_START_TS),
        "version": APP_VERSION,
        "config_version": _config_version(),
        "database": db,
        "sensor": {"online": sensor_online, "last_seen": sensor_ts},
        "devices": counts,
        "ai": {"agent_enabled": bool(CONFIG.get("agent_enabled")), "backend": CONFIG.get("agent_api_backend"), "model": CONFIG.get("ollama_model"), "ollama_enabled": bool(CONFIG.get("ollama_enabled"))},
        "auth": {"enabled": bool(CONFIG.get("mobile_auth_enabled")), "mode": "jwt", "proxy_guard": True},
        "alarms": {"unhandled": None},
    }


# ---------- 数字孪生场景 ----------
_TWIN_ZONES = [
    {"id": "zone-pump", "name": "泵组区", "position": [-1.6, 0, 2.0], "size": [4.8, 2.6], "color": "#EEF2FF"},
    {"id": "zone-assembly", "name": "装配区", "position": [-2.6, 0, -1.2], "size": [3.4, 3.2], "color": "#F3F6FB"},
    {"id": "zone-power", "name": "配电区", "position": [2.3, 0, -1.3], "size": [2.4, 2.2], "color": "#FFFAEB"},
]

_TWIN_SLOTS = [
    ("pump_test_bench", "zone-pump", [-0.6, 0, 1.6], 0.35),
    ("robotic_arm_cell", "zone-assembly", [-2.6, 0, -1.0], 0.8),
    ("electrical_cabinet", "zone-power", [2.2, 0, -1.4], -0.5),
    ("cooling_fan", "zone-assembly", [-0.4, 0, -3.6], 0.3),
    ("conveyor_line", "zone-assembly", [3.0, 0, 1.4], -0.4),
    ("cnc_machining_center", "zone-pump", [1.6, 0, 2.4], 0.5),
    ("industrial_sensor", "zone-pump", [-2.6, 0, 2.4], 0.0),
]


def _twin_slot(device: Dict[str, Any], index: int) -> Dict[str, Any]:
    twin = device.get("twin") if isinstance(device.get("twin"), dict) else {}
    if twin.get("position"):
        return {"zone": twin.get("zone") or device.get("zone") or "zone-assembly", "position": twin["position"], "rotation": float(twin.get("rotation") or 0.0)}
    filename = str(device.get("model_filename") or device.get("model_url") or "").lower()
    for stem, zone, position, rotation in _TWIN_SLOTS:
        if stem in filename:
            return {"zone": zone, "position": position, "rotation": rotation}
    fallback = [[-1.8, 0, 1.8], [0.4, 0, 1.6], [-2.2, 0, -1.4], [1.4, 0, -1.6], [2.6, 0, 1.6], [0.2, 0, -3.2]]
    position = fallback[index % len(fallback)]
    return {"zone": device.get("zone") or "zone-unassigned", "position": position, "rotation": 0.0}


@app.get("/api/twin/scene")
async def twin_scene(request: Request):
    _require_user(request)
    devices = []
    for index, device in enumerate(CONFIG.get("devices", [])):
        slot = _twin_slot(device, index)
        status = device.get("status") or "运行中"
        state = "running" if status == "运行中" else ("maintenance" if status in ("维护中", "停用") else "offline")
        devices.append({
            "id": device.get("id"),
            "name": device.get("name"),
            "zone": slot["zone"],
            "position": slot["position"],
            "rotation": slot["rotation"],
            "state": state,
            "status": status,
            "model_url": device.get("model_url") or "",
            "model_filename": device.get("model_filename") or "",
        })
    zones = list(_TWIN_ZONES)
    if any(device.get("zone") == "zone-unassigned" for device in devices):
        zones.append({"id": "zone-unassigned", "name": "未分区", "position": [4.6, 0, 2.2], "size": [2.4, 2.4], "color": "#F2F4F7"})
    return {"scene": {"id": "plant-1", "name": "一号车间", "unit": "米", "zones": zones}, "devices": devices, "updated_at": _utc_now(), "config_version": _config_version()}


# ==================== 启动服务 ====================
def start_server():
    init_db()
    load_cloud_config()
    
    logger.info("=" * 50)
    logger.info("  工业环境监控系统 - 纯软演示版")
    logger.info("=" * 50)
    logger.info(f"前端地址: http://localhost:8000")
    logger.info(f"API 地址: http://localhost:8000/api")
    logger.info(f"WebSocket: ws://localhost:8000/ws/sensor")
    logger.info(f"Ollama URL: {CONFIG['ollama_url']}")
    logger.info(f"Ollama Model: {CONFIG['ollama_model']}")
    db_status = database_status()
    logger.info(f"数据库: {db_status['backend']} - {db_status['message']}")
    logger.info("=" * 50)
    
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")

if __name__ == "__main__":
    start_server()
