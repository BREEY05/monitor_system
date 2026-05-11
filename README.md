# 工业环境监控系统

基于 FastAPI + WebSocket 的工业环境实时监控系统，支持多传感器数据采集、实时报警、AI 智能对话、RAG 知识库、飞书集成、设备3D模型和历史数据分析。

## 功能特性

### 核心功能
- **实时监控**：温度、湿度、气压、振动等环境参数实时采集与展示
- **WebSocket 推送**：实时数据通过 WebSocket 推送到前端，无需轮询
- **智能报警**：阈值检测 + 连续触发机制，支持飞书 Webhook 通知
- **历史数据**：存储和分析历史传感器数据，支持多时间范围查询

### AI 对话功能
- **集成 Ollama**：支持本地大语言模型（qwen3.5:0.8b 等）
- **流式输出**：实时流式响应，提升用户体验
- **模型管理**：支持多模型切换，预加载模型到内存
- **上下文感知**：结合当前传感器数据提供智能回答

### RAG 知识库
- **文档上传**：支持 `.txt`、`.md`、`.pdf`、`.doc/.docx`、`.csv`、`.json` 格式
- **文本切分**：智能切分为知识片段，支持 Ollama Embedding
- **语义检索**：对话时优先检索知识库片段，注入系统提示词
- **兜底检索**：当 embedding 不可用时，使用关键词进行检索

### Skills 管理
- **自定义 Skill**：上传和管理自定义 Skill 内容
- **功能扩展**：支持扩展系统能力的 Skill 机制

### 设备3D模型
- **模型上传**：支持上传设备 3D 模型文件
- **设备关联**：支持将模型与具体设备关联
- **WebGL 渲染**：支持在浏览器中预览 3D 模型

### 飞书集成
- **消息推送**：报警信息自动推送到飞书群
- **事件接收**：支持接收飞书群消息并回复
- **长连接模式**：使用 Feishu OpenAPI 事件订阅
- **AI 回复转发**：AI 对话回复自动转发到飞书群

### 地图功能
- **设备地图**：高德地图展示设备位置分布
- **地图样式切换**：支持标准、卫星、浅色三种地图模式
- **GPS 定位**：支持浏览器 GPS 精确定位
- **IP 定位**：基于高德 Web Service API 的 IP 定位

### 其他功能
- **摄像头监控**：视频监控画面预览与截图功能
- **模拟模式**：无需真实硬件即可运行演示
- **数据可视化**：ECharts 图表展示历史趋势
- **响应式设计**：适配桌面和移动设备

## 技术栈

- **后端**：FastAPI + Uvicorn
- **前端**：原生 HTML/CSS/JavaScript + ECharts + Three.js（3D模型）
- **AI**：Ollama (qwen3.5:0.8b) 本地大模型
- **RAG**：文档解析 + 文本切分 + Ollama Embedding + 向量/关键词检索
- **3D渲染**：Three.js + WebGL
- **地图**：高德地图 JavaScript API + Web Service API
- **飞书**：lark-oapi SDK
- **数据库**：SQLite / PostgreSQL（支持 Supabase PostgreSQL DSN）

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 启动服务

**Windows:**
```bash
python start.py
```

**Linux/Mac:**
```bash
bash start.sh
```

或直接运行：
```bash
python api_server.py
```

### 3. 访问系统

- 前端地址：http://localhost:8000
- API 文档：http://localhost:8000/api
- WebSocket：ws://localhost:8000/ws/sensor

### 4. AI 对话配置

1. 安装 [Ollama](https://ollama.ai/)
2. 拉取模型：`ollama pull qwen3.5:0.8b`
3. 启动 Ollama 服务：`ollama serve`（通常自动启动）
4. 在系统前端选择模型并点击"启动模型服务"

**可用模型：**
- qwen3.5:0.8b（推荐，资源占用小）
- qwen3.5:1.7b
- qwen3.5:3b
- qwen3.5:7b

## 项目结构

```
monitor_system/
├── api_server.py          # FastAPI 主服务（核心逻辑）
├── start.py               # 启动脚本（自动安装依赖）
├── index.html              # 前端页面入口（软链接）
├── config.json             # 运行配置持久化文件（自动创建）
├── requirements.txt        # Python 依赖
├── start.bat/start.sh      # 平台启动脚本
├── static/
│   └── index.html          # 前端静态资源
├── device_models/          # 设备3D模型上传目录（自动创建）
└── monitor_data.db         # SQLite 数据库（自动创建）
```

## 模块重要构成

### 1. 前端交互模块
- **主要文件**：`static/index.html`
- **核心页面**：监控大屏、AI 对话、数据分析、摄像头监控、设备地图、报警中心、设备管理、系统设置
- **关键能力**：
  - 通过 `/ws/sensor` 接收实时传感器数据并刷新仪表盘
  - 通过 `/ws/chat` 与本地 Ollama 模型进行流式 AI 对话
  - 在 AI 对话右侧提供模型管理、RAG 文档上传、快捷提问入口
  - 使用 ECharts 绘制实时曲线、历史趋势和异常统计
  - 使用 Three.js 渲染设备 3D 模型

### 2. 后端 API 模块
- **主要文件**：`api_server.py`
- **框架入口**：FastAPI `app`
- **关键能力**：
  - 提供传感器、报警、历史数据、AI 对话、RAG、Skills、飞书、地图、设备模型与系统设置接口
  - 维护 WebSocket 连接管理器，将实时数据推送到前端
  - 对配置变更进行持久化，服务重启后自动读取 `config.json`
  - 支持 SQLite 本地演示，也支持 PostgreSQL/Supabase 作为正式数据后端

### 3. 数据采集与报警模块
- **核心类**：`SensorReader`、`AlarmChecker`
- **相关表**：`sensor_data`、`alerts`
- **关键能力**：
  - 在无硬件时生成模拟温度、湿度、气压、振动数据
  - 按阈值和连续触发次数判断报警，避免单点抖动误报
  - 报警可保存到数据库，并可通过飞书 Webhook 推送

### 4. AI 对话与 RAG 知识库模块
- **核心接口**：`/ws/chat`、`/api/chat`、`/api/rag/upload`、`/api/rag/documents`
- **相关表**：`rag_documents`、`rag_chunks`
- **关键能力**：
  - 上传 `.txt`、`.md`、`.pdf`、`.doc/.docx`、`.csv`、`.json` 文档
  - 抽取文本后切分为知识片段，并尽量生成 Ollama embedding
  - 对话时优先检索知识库片段，再把命中的内容注入系统提示词
  - 当 embedding 不可用时，使用文件名、中文短词、关键词进行兜底检索
  - 资料、文档、知识库类问题默认优先使用本地/数据库知识库，不直接联网

### 5. Skills 管理模块
- **核心接口**：`/api/skills`
- **关键能力**：
  - 上传和管理自定义 Skill 内容
  - 支持文件上传或直接输入内容
  - Skill 内容可被系统读取和执行

### 6. 设备 3D 模型模块
- **核心接口**：`/api/device/model`
- **存储目录**：`device_models/`
- **关键能力**：
  - 上传设备 3D 模型文件（GLB/GLTF 格式）
  - 将模型与具体设备关联
  - 使用 Three.js 在前端渲染 3D 模型

### 7. 数据库与配置模块
- **配置文件**：`config.json`
- **默认数据库**：`monitor_data.db`
- **可选数据库**：Supabase/PostgreSQL，通过 `postgres_dsn` 配置
- **关键能力**：
  - 首次运行时自动创建所需表结构
  - `/api/settings` 保存系统配置，避免重启后丢失数据库、飞书、模型等设置
  - `/api/database/test` 用于测试 PostgreSQL DSN，并在成功后初始化表结构

### 8. 飞书与外部集成模块
- **核心接口**：`/api/feishu/test`、`/api/feishu/events`
- **关键能力**：
  - 报警和 AI 回复可转发到飞书群
  - 支持飞书事件回调和长连接消息接收
  - 可配置 Webhook、App ID、App Secret、Verification Token

### 9. 地图与摄像头模块
- **核心接口**：`/api/camera/capture`
- **前端依赖**：高德地图 JavaScript API + Three.js
- **关键能力**：
  - 展示设备地图、定位与地图样式切换
  - 支持设备 3D 模型在地图上展示
  - 提供摄像头预览、截图、录制和全屏入口
  - 当前摄像头模块以演示占位为主，接入真实视频流后可扩展

## API 接口

### 传感器数据
| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/sensors/latest` | GET | 获取最新传感器数据 |
| `/api/sensors/current` | GET | 获取当前数据（轮询） |
| `/api/history` | GET | 获取历史数据 |
| `/api/alerts` | GET | 获取报警记录 |
| `/api/config` | GET | 获取配置信息 |

### AI 对话
| 接口 | 方法 | 说明 |
|------|------|------|
| `/ws/chat` | WebSocket | AI 对话 WebSocket |
| `/api/chat` | POST | AI 对话 HTTP 接口 |
| `/api/ollama/test` | POST | 测试 Ollama 连接 |
| `/api/ollama/models` | GET | 获取可用模型列表 |
| `/api/ollama/start` | POST | 启动模型服务 |

### RAG 知识库
| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/rag/upload` | POST | 上传文档到 RAG 知识库 |
| `/api/rag/documents` | GET | 获取 RAG 文档列表 |

### Skills 管理
| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/skills` | GET | 获取 Skills 列表 |
| `/api/skills` | POST | 上传新 Skill |

### 设备管理
| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/device/model` | POST | 上传设备 3D 模型 |

### 数据库
| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/database/test` | POST | 测试数据库连接 |

### 飞书集成
| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/feishu/test` | POST | 测试飞书连接 |
| `/api/feishu/events` | POST | 飞书事件回调 |

### 其他
| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/camera/capture` | POST | 摄像头截图 |
| `/api/settings` | GET/POST | 系统配置 |
| `/ws/sensor` | WebSocket | 传感器数据流 |

## 传感器阈值配置

| 参数 | 默认阈值 | 单位 |
|------|----------|------|
| 温度 | 40.0 | °C |
| 湿度 | 80.0 | %RH |
| 振动 | 0.5 | mm/s |

连续触发 3 次超过阈值才会触发报警。

## 数据库表结构

- `sensor_data`：传感器历史数据
- `alerts`：报警记录
- `camera_logs`：摄像头日志
- `rag_documents`：RAG 知识库文档元数据
- `rag_chunks`：RAG 知识库文本片段与 embedding
- `skills`：上传的 Skill 内容

## 配置文件

系统默认配置位于 `api_server.py` 中的 `CONFIG` 字典，运行时保存到 `config.json`。服务启动时会优先读取 `config.json`，因此前端保存过的模型、飞书、数据库等配置不会因重启丢失。

```python
CONFIG = {
    "ollama_url": "http://localhost:11434",
    "ollama_model": "qwen3.5:0.8b",
    "ollama_enabled": True,
    "feishu_webhook": "",  # 飞书 Webhook 地址
    "feishu_app_id": "",   # 飞书应用 ID
    "feishu_app_secret": "",  # 飞书应用密钥
    "feishu_receive_group_messages": True,
    "feishu_forward_ai_replies": True,
    "database_backend": "sqlite",
    "postgres_dsn": "",  # Supabase/PostgreSQL 连接串
    "rag_enabled": True,
    "rag_top_k": 4,
    "thresholds": {
        "temperature": 40.0,
        "humidity": 80.0,
        "vibration": 0.5
    },
    "alarm_trigger_count": 3,  # 报警触发次数
    "sensor_interval": 5       # 数据采集间隔（秒）
}
```

## 飞书集成配置

### 消息推送
1. 在飞书群中添加自定义机器人
2. 获取 Webhook 地址
3. 将 Webhook 地址配置到系统设置

### 事件订阅
1. 在飞书开放平台创建应用
2. 配置应用权限和事件订阅
3. 将 App ID 和 App Secret 配置到系统

## 地图功能

系统使用高德地图 JavaScript API 和 Web Service API：

### JavaScript API
- 用于前端地图展示
- 支持标准、卫星、浅色三种地图样式
- 支持标记点、定位、路线规划等功能

### Web Service API
- 用于 IP 定位服务
- 提供地理编码、逆地理编码等功能

**注意**：需要配置有效的高德地图 API Key 才能使用地图功能。

## 设备 3D 模型

系统支持上传和展示设备 3D 模型：

### 支持格式
- GLB（二进制 GLTF）
- GLTF（JSON 格式）

### 使用方法
1. 进入设备管理页面
2. 选择设备并上传 3D 模型文件
3. 模型将自动与设备关联
4. 在设备详情页面可以查看 3D 模型

### 渲染技术
- Three.js WebGL 渲染
- 支持模型旋转、缩放、平移
- 支持环境光照和材质渲染

## 使用说明

### 首次使用
1. 启动服务后访问 http://localhost:8000
2. 在设置中配置传感器阈值
3. 如需 AI 对话，在 AI 对话界面选择模型并启动
4. 如需 RAG 知识库，上传相关文档
5. 如需飞书集成，配置飞书 Webhook 或应用凭证
6. 如需设备 3D 模型，在设备管理页面上传模型文件

### 日常使用
1. 启动服务：`python start.py`
2. 访问 http://localhost:8000
3. 监控系统运行状态
4. 查看历史数据和报警记录
5. 使用 AI 对话查询系统状态
6. 管理 RAG 知识库文档

### AI 对话
1. 打开 AI 对话界面
2. 选择 Ollama 模型
3. 点击"启动模型服务"预加载模型
4. 输入问题进行对话
5. AI 会结合当前传感器数据给出回答
6. 可以上传 RAG 文档让 AI 基于知识库回答

## 许可证

MIT License