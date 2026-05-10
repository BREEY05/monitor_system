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
from typing import Optional, Dict, List, Any
from pathlib import Path
from queue import Queue

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import uvicorn

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
    "sensor_interval": 5,
    "database_backend": "sqlite",
    "supabase_url": "",
    "supabase_key": "",
    "postgres_dsn": "",
    "rag_enabled": True,
    "agent_search_enabled": True,
    "rag_top_k": 4,
    "device_info": {
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
        if self.backend != "postgres":
            return sql
        sql = sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
        sql = sql.replace("?", "%s")
        upper_sql = sql.lstrip().upper()
        returning_tables = ("INSERT INTO ALERTS", "INSERT INTO RAG_DOCUMENTS", "INSERT INTO SKILLS")
        if any(upper_sql.startswith(prefix) for prefix in returning_tables) and "RETURNING" not in upper_sql:
            sql = sql.rstrip() + " RETURNING id"
        return sql

    def execute(self, sql: str, params: tuple = ()):
        self.cursor.execute(self._sql(sql), params)
        upper_sql = sql.lstrip().upper()
        if self.backend == "postgres" and any(upper_sql.startswith(prefix) for prefix in ("INSERT INTO ALERTS", "INSERT INTO RAG_DOCUMENTS", "INSERT INTO SKILLS")):
            row = self.cursor.fetchone()
            self._lastrowid = row[0] if row else None
        else:
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


def get_database_backend() -> str:
    if CONFIG.get("database_backend") == "postgres" or CONFIG.get("postgres_dsn"):
        return "postgres"
    return "sqlite"


def connect_postgres():
    try:
        import psycopg2
        dsn = CONFIG.get("postgres_dsn", "").strip()
        if not dsn:
            raise RuntimeError("PostgreSQL DSN 未配置")
        return psycopg2.connect(dsn)
    except Exception as e:
        logger.warning(f"Supabase PostgreSQL 连接失败，回退到 SQLite: {e}")
        return None


def init_db():
    backend = get_database_backend()
    raw_conn = connect_postgres() if backend == "postgres" else None
    conn = DatabaseConnection(raw_conn, "postgres") if raw_conn else DatabaseConnection(sqlite3.connect(DB_PATH), "sqlite")
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
    
    conn.commit()
    conn.close()
    logger.info(f"数据库初始化完成: {DB_PATH}")

def get_db_connection():
    backend = get_database_backend()
    if backend == "postgres":
        raw_conn = connect_postgres()
        if raw_conn:
            return DatabaseConnection(raw_conn, "postgres")
    return DatabaseConnection(sqlite3.connect(DB_PATH), "sqlite")

# ==================== 数据模型 ====================
class SensorData(BaseModel):
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    pressure: Optional[float] = None
    vibration: Optional[float] = None

class ChatRequest(BaseModel):
    message: str
    model: Optional[str] = None
    api_url: Optional[str] = None

class OllamaTestRequest(BaseModel):
    model: Optional[str] = None
    api_url: Optional[str] = None

class DatabaseTestRequest(BaseModel):
    postgres_dsn: Optional[str] = None

class SkillUploadRequest(BaseModel):
    name: str
    content: str
    filename: Optional[str] = None

# ==================== 模拟传感器数据生成器 ====================
class SensorReader:
    def __init__(self):
        self.start_time = time.time()
        self.last_values = {"temperature": 22.0, "humidity": 55.0, "pressure": 1013.0, "vibration": 0.0}
    
    def read(self) -> SensorData:
        elapsed = time.time() - self.start_time
        
        base_temp = 25.0
        temp_cycle = 8.0 * math.sin(2 * math.pi * elapsed / 300)
        temp_noise = (hash(str(int(time.time()))) % 100) / 50 - 1.0
        temperature = round(base_temp + temp_cycle + temp_noise, 1)
        
        base_humid = 55.0
        humid_cycle = 15.0 * math.sin(2 * math.pi * elapsed / 600)
        humid_noise = (hash(str(int(time.time() + 1))) % 100) / 50 - 1.0
        humidity = round(base_humid + humid_cycle + humid_noise, 1)
        
        base_pressure = 1013.0
        pressure_drift = 2.0 * math.sin(2 * math.pi * elapsed / 1800)
        pressure_noise = (hash(str(int(time.time() + 2))) % 50) / 25 - 1.0
        pressure = round(base_pressure + pressure_drift + pressure_noise, 1)
        
        base_vibration = 0.0
        vibration_cycle = 0.15 * abs(math.sin(2 * math.pi * elapsed / 60))
        vibration_noise = (hash(str(int(time.time() + 3))) % 100) / 1000
        vibration = round(base_vibration + vibration_cycle + vibration_noise, 2)
        
        self.last_values = {
            "temperature": max(15.0, min(45.0, temperature)),
            "humidity": max(30.0, min(95.0, humidity)),
            "pressure": max(1000.0, min(1025.0, pressure)),
            "vibration": max(0.0, vibration)
        }
        
        return SensorData(**self.last_values)

# ==================== 模拟摄像头 ====================
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

# ==================== 报警检测 ====================
class AlarmChecker:
    def __init__(self):
        self.alert_counts = {}
        self.last_alert_time = {}
    
    def check(self, data: SensorData) -> List[Dict]:
        alerts = []
        now = datetime.now()
        
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
            
            if value > threshold:
                key = f"{sensor_type}_count"
                self.alert_counts[key] = self.alert_counts.get(key, 0) + 1
                
                if self.alert_counts[key] >= CONFIG["alarm_trigger_count"]:
                    time_key = f"{sensor_type}_last"
                    if time_key not in self.last_alert_time or (now - self.last_alert_time[time_key]).seconds > 300:
                        level = "danger" if value > threshold * 1.2 else "warning"
                        alerts.append({"type": sensor_type, "value": value, "threshold": threshold, "level": level})
                        self.last_alert_time[time_key] = now
            else:
                self.alert_counts[f"{sensor_type}_count"] = 0
        
        return alerts
    
    def save_alert(self, alert: Dict):
        conn = get_db_connection()
        c = conn.cursor()
        c.execute(
            "INSERT INTO alerts (timestamp, sensor_type, value, threshold, level) VALUES (?, ?, ?, ?, ?)",
            (datetime.now().isoformat(), alert["type"], alert["value"], alert["threshold"], alert["level"])
        )
        conn.commit()
        alert_id = c.lastrowid
        conn.close()
        
        self._notify_feishu(alert, alert_id)
        self._notify_websocket(alert, alert_id)
    
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
        asyncio.create_task(manager.broadcast(notification))

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
        return False
    try:
        import requests
        response = requests.post(
            webhook,
            json={"msg_type": "text", "content": {"text": text}},
            timeout=8
        )
        if response.status_code != 200:
            logger.warning(f"飞书机器人发送失败：status={response.status_code}, body={response.text[:200]}")
            return False
        return True
    except Exception as e:
        logger.warning(f"飞书机器人发送失败：{e}")
        return False

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
            send_feishu_text(f"飞书群消息回复：\n{reply}")
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

@app.on_event("startup")
async def on_startup():
    start_feishu_long_connection()

# ==================== 路由 ====================

@app.get("/", response_class=HTMLResponse)
async def root():
    """访问根路径返回前端页面"""
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    
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

@app.post("/api/database/test")
async def test_database_connection(request: DatabaseTestRequest):
    old_dsn = CONFIG.get("postgres_dsn", "")
    if request.postgres_dsn is not None:
        CONFIG["postgres_dsn"] = request.postgres_dsn.strip()
        CONFIG["database_backend"] = "postgres" if CONFIG["postgres_dsn"] else "sqlite"
    try:
        if CONFIG.get("database_backend") == "postgres":
            import psycopg2
            test_conn = psycopg2.connect(CONFIG["postgres_dsn"])
            test_conn.close()
        init_db()
        save_config()
        return {"success": True, "backend": get_database_backend(), "message": "数据库连接成功，表结构已检查"}
    except Exception as e:
        CONFIG["postgres_dsn"] = old_dsn
        CONFIG["database_backend"] = "postgres" if old_dsn else "sqlite"
        return {"success": False, "message": f"数据库连接失败: {e}"}

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
    data = sensor_reader.read()
    return {
        "temperature": data.temperature,
        "humidity": data.humidity,
        "pressure": data.pressure,
        "vibration": data.vibration,
        "timestamp": datetime.now().isoformat()
    }

@app.get("/api/sensors/current")
async def get_current_sensors():
    """获取当前传感器数据（供3D模型轮询使用）"""
    data = sensor_reader.read()
    return {
        "temperature": data.temperature,
        "humidity": data.humidity,
        "vibration": data.vibration,
        "timestamp": datetime.now().isoformat()
    }

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

@app.get("/api/alerts")
async def get_alerts():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id, timestamp, sensor_type, value, threshold, level FROM alerts ORDER BY timestamp DESC LIMIT 50")
    rows = c.fetchall()
    conn.close()
    
    messages = {"temperature": "温度", "humidity": "湿度", "vibration": "振动"}
    alerts = []
    for row in rows:
        level_text = "danger" if row[5] == "danger" else "warning"
        level_emoji = "🚨" if row[5] == "danger" else "⚠️"
        alerts.append({
            "id": row[0],
            "title": f"{level_emoji} {messages.get(row[2], row[2])}异常",
            "time": row[1],
            "source": "传感器节点",
            "level": level_text
        })
    
    return alerts

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
    ok = send_feishu_text("工业环境监控系统：飞书机器人测试消息发送成功。")
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
    ok = send_feishu_text(f"飞书群消息回复：\n{reply}")
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
    await websocket.accept()
    logger.info("AI 对话 WebSocket 已连接")
    try:
        while True:
            data = await websocket.receive_json()
            message = data.get("message", "")
            model = data.get("model")
            api_url = data.get("api_url")
            logger.info(f"收到 AI 消息：{message} (model={model}, api_url={api_url})")
            
            if not message:
                continue
            
            context_parts = []
            latest = sensor_reader.read()
            if latest.temperature: context_parts.append(f"温度：{latest.temperature}°C")
            if latest.humidity: context_parts.append(f"湿度：{latest.humidity}%")
            if latest.pressure: context_parts.append(f"气压：{latest.pressure}hPa")
            if latest.vibration: context_parts.append(f"振动：{latest.vibration}mm/s")
            context = ", ".join(context_parts) or "暂无数据"
            
            await chat_with_ollama_stream(websocket, message, context, model, api_url)
            
    except WebSocketDisconnect:
        logger.info("AI 对话 WebSocket 断开")
    except Exception as e:
        logger.error(f"AI 对话 WebSocket 错误：{e}")
        try:
            await websocket.send_json({"type": "error", "content": "处理消息时出错"})
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
                send_feishu_text(f"网页 AI 回复：\n{reply}")
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
                send_feishu_text(f"网页 AI 回复：\n{visible_reply.strip()}")
            
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
    await manager.connect(websocket)
    try:
        while True:
            data = sensor_reader.read()
            
            conn = get_db_connection()
            c = conn.cursor()
            c.execute(
                "INSERT INTO sensor_data (timestamp, temperature, humidity, pressure, vibration) VALUES (?, ?, ?, ?, ?)",
                (datetime.now().isoformat(), data.temperature, data.humidity, data.pressure, data.vibration)
            )
            conn.commit()
            conn.close()
            
            alerts = alarm_checker.check(data)
            for alert in alerts:
                alarm_checker.save_alert(alert)
            
            await websocket.send_json({
                "type": "sensor",
                "data": {
                    "temperature": data.temperature,
                    "humidity": data.humidity,
                    "pressure": data.pressure,
                    "vibration": data.vibration,
                    "timestamp": datetime.now().isoformat()
                }
            })
            
            await asyncio.sleep(CONFIG["sensor_interval"])
            
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket 错误: {e}")
        manager.disconnect(websocket)

@app.post("/api/settings")
async def update_settings(settings: dict):
    global CONFIG
    CONFIG.update(settings)
    if settings.get("postgres_dsn") is not None or settings.get("database_backend") is not None:
        init_db()
    save_config()
    return {"success": True}

@app.get("/api/settings")
async def get_settings():
    return CONFIG

@app.post("/api/device/model")
async def upload_device_model(file: UploadFile = File(...)):
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

    device_info = CONFIG.setdefault("device_info", {})
    device_info["model_url"] = f"/static/uploads/device_models/{filename}"
    device_info["model_filename"] = file.filename
    save_config()
    return {"success": True, "model_url": device_info["model_url"], "filename": file.filename}

# ==================== 启动服务 ====================
def start_server():
    init_db()
    
    logger.info("=" * 50)
    logger.info("  工业环境监控系统 - 纯软演示版")
    logger.info("=" * 50)
    logger.info(f"前端地址: http://localhost:8000")
    logger.info(f"API 地址: http://localhost:8000/api")
    logger.info(f"WebSocket: ws://localhost:8000/ws/sensor")
    logger.info(f"Ollama URL: {CONFIG['ollama_url']}")
    logger.info(f"Ollama Model: {CONFIG['ollama_model']}")
    logger.info(f"数据库: {DB_PATH}")
    logger.info("=" * 50)
    
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")

if __name__ == "__main__":
    start_server()
