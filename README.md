# 工业环境监控系统

基于 FastAPI + WebSocket 的工业环境实时监控系统，采用**多 Agent 协作架构**，支持多设备传感器数据采集、实时报警、AI 智能对话（本地/云端大模型）、RAG 知识库、联网搜索、飞书集成、设备3D模型和历史数据分析。

---

## 功能特性

### 核心功能
- **多设备监控**：支持多个设备同时接入，温度、湿度、气压、振动等参数实时采集与展示
- **WebSocket 推送**：实时数据通过 WebSocket 推送到前端，无需轮询
- **智能报警**：阈值检测 + 时间窗口机制 + 冷却期，支持飞书 Webhook 通知
- **历史数据**：存储和分析历史传感器数据，支持多时间范围查询（小时/天/周/月）

### AI 对话功能（多 Agent 协作）
- **多 Agent 编排**：Orchestrator 自动识别用户意图，路由到专业子 Agent 处理
- **LLM 双后端**：支持 Ollama 本地模型和 OpenAI 兼容云端 API（通义千问、DeepSeek 等）灵活切换
- **流式输出**：实时流式响应，提升用户体验
- **上下文感知**：结合当前传感器数据提供智能回答
- **思考过滤**：自动过滤 `<think>` 思考标签
- **联网搜索**：支持 DuckDuckGo 联网检索最新信息

### RAG 知识库
- **文档上传**：支持 `.txt`、`.md`、`.pdf`、`.doc/.docx`、`.csv`、`.json` 格式
- **文本切分**：智能切分为知识片段，支持 Ollama Embedding 向量生成
- **语义检索**：对话时优先检索知识库片段，注入系统提示词
- **兜底检索**：当 embedding 不可用时，使用关键词进行检索
- **知识库优先**：资料、文档类问题默认优先使用本地知识库，不直接联网

### Skills 管理
- **自定义 Skill**：上传和管理自定义 Skill 内容
- **功能扩展**：支持扩展系统能力的 Skill 机制

### 设备3D模型
- **模型上传**：支持上传设备 3D 模型文件（GLB/GLTF/BIN）
- **设备关联**：支持将模型与具体设备关联
- **本地/云端存储**：支持本地存储或 Supabase Storage 云端存储
- **WebGL 渲染**：使用 Three.js 在浏览器中预览 3D 模型

### 飞书集成
- **消息推送**：报警信息自动推送到飞书群（Webhook）
- **长连接模式**：使用 lark-oapi WebSocket 客户端接收飞书群消息并自动回复
- **AI 回复转发**：AI 对话回复自动转发到飞书群

### 地图功能
- **设备地图**：高德地图展示设备位置分布
- **地图样式切换**：支持标准、卫星、浅色三种地图模式
- **GPS 定位**：支持浏览器 GPS 精确定位
- **IP 定位**：基于高德 Web Service API 的 IP 定位

### 其他功能
- **摄像头监控**：模拟摄像头画面预览与截图功能（PIL 生成）
- **数据可视化**：ECharts 图表展示历史趋势
- **响应式设计**：适配桌面和移动设备

---

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | FastAPI + Uvicorn |
| 前端 | 原生 HTML/CSS/JavaScript + ECharts + Three.js |
| AI | Ollama (qwen3.5 等) 本地大模型 |
| RAG | 文档解析 + Ollama Embedding + 向量/关键词检索 |
| 3D渲染 | Three.js + WebGL |
| 地图 | 高德地图 JavaScript API + Web Service API |
| 飞书 | lark-oapi SDK (WebSocket 长连接模式) |
| 数据库 | SQLite（本地演示）/ PostgreSQL（Supabase 正式部署） |
| 外部存储 | Supabase Storage（设备模型云端存储） |
| 联网搜索 | DuckDuckGo Search / LangChain Tools |
| Agent 框架 | 自研多 Agent 协作框架（Orchestrator + 专业子 Agent） |

---

## 多 Agent 协作架构

系统采用基于意图驱动的多 Agent 协作架构。用户消息首先由 Orchestrator 编排器进行意图分类，然后根据执行计划调度专业子 Agent 处理，最后融合多个 Agent 的结果生成统一回复。

### 架构概览

```
用户消息 (WebSocket / HTTP)
  │
  ▼
┌──────────────────────────────┐
│     OrchestratorAgent         │  ← 编排器：意图分类 → 计划生成 → 调度 → 融合
│  ┌────────────────────────┐  │
│  │ IntentClassifier        │  │  ← LLM 驱动 + 关键词降级双模式
│  │ PlanGenerator           │  │  ← 单 Agent / 多 Agent 并行协作
│  │ ResultFuser             │  │  ← 多 Agent 结果智能融合
│  └────────────────────────┘  │
└───────────┬──────────────────┘
            │ 调度（按执行计划）
  ┌─────────┼─────────┬────────┬────────┐
  ▼         ▼         ▼        ▼        ▼
┌───────┐┌────────┐┌───────┐┌──────┐┌───────┐
│Sensor ││Knowledge││Search ││Alarm ││Device │  ← 专业子 Agent
│Agent  ││ Agent   ││Agent  ││Agent ││Agent  │
└───┬───┘└───┬────┘└───┬───┘└──┬───┘└───┬───┘
    │        │         │       │        │
    ▼        ▼         ▼       ▼        ▼
┌──────────────────────────────────────────────┐
│             Tool Registry                     │  ← 统一工具注册表
├──────────────────────────────────────────────┤
│ query_current_sensor │ search_knowledge_base  │
│ query_sensor_history │ search_web             │
│ query_recent_alerts  │ analyze_sensor_trend   │
│ query_device_list    │ get_threshold_config   │
└──────────┬──────────────────────┬────────────┘
           │                      │
    ┌──────┼──────┐         ┌─────┼─────┐
    ▼      ▼      ▼         ▼           ▼
┌──────┐┌──────┐┌────┐  ┌────────┐ ┌──────┐
│SQLite││Ollama││Duck│  │Raspberry│ │Feishu│
│  DB  ││ LLM  ││Duck│  │  Pi    │ │  API │
└──────┘└──────┘└────┘  └────────┘ └──────┘
```

### 子 Agent 说明

| Agent | 职责 | 可用工具 |
|-------|------|---------|
| **SensorAgent** | 实时数据查询、历史趋势分析 | `query_current_sensor`, `query_sensor_history`, `analyze_sensor_trend` |
| **KnowledgeAgent** | RAG 知识库语义检索与问答 | `search_knowledge_base` |
| **SearchAgent** | 联网搜索与信息综合 | `search_web` |
| **AlarmAgent** | 报警查询、异常分析、处置建议 | `query_recent_alerts`, `query_anomaly_data`, `query_current_sensor`, `get_threshold_config` |
| **DeviceAgent** | 设备列表、状态、位置查询 | `query_device_list`, `query_device_status`, `query_current_sensor` |

### 意图分类与路由

Orchestrator 使用 **LLM 驱动 + 关键词降级** 双模式意图分类：

1. **LLM 模式**（优先）：将用户消息发送给 LLM，通过结构化 Prompt 解析出意图类型和置信度
2. **关键词模式**（降级）：当 LLM 不可用或超时，使用预定义关键词表快速分类

支持的意图类型：`sensor_query`, `history_query`, `alarm_query`, `alarm_handle`, `knowledge`, `search`, `device_manage`, `system_config`, `chitchat`, `complex`

### 多 Agent 协作策略

- **单意图**：直接路由到对应的专业 Agent 处理
- **多意图**：识别出多个意图后，按置信度排序依次调度对应 Agent，最终通过 ResultFuser 融合结果
- **复杂任务**：当识别为 `complex` 类型时，拆解为子任务并行调度

### LLM 双后端支持

通过 `LLMProvider` 统一接口，支持：

- **Ollama 本地模型**（默认）：零成本、隐私友好、适合内网部署
- **OpenAI 兼容云端 API**：通义千问、DeepSeek 等，能力更强

在 `config.json` 中配置切换：

```json
{
    "agent_enabled": true,
    "agent_api_backend": "ollama",
    "agent_api_url": "http://localhost:11434",
    "agent_api_model": "qwen3.5:0.8b",
    "agent_api_key": ""
}
```

切换为云端 API：

```json
{
    "agent_api_backend": "openai",
    "agent_api_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "agent_api_model": "qwen-plus",
    "agent_api_key": "sk-xxx"
}
```

### Agent API 接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/agent/chat` | POST | Agent 对话（非流式，返回完整分析过程） |
| `/api/agent/status` | GET | Agent 系统状态和运行统计 |
| `/api/agent/test` | POST | 测试 Agent 系统连通性 |
| `/ws/chat` | WebSocket | Agent 对话（流式，默认 Agent 模式） |

### 代码结构

```
agents/
├── __init__.py                  # 包初始化 + 工厂函数
├── llm_provider.py              # LLM 统一接口（Ollama + OpenAI 兼容 API）
├── base.py                      # Agent 基类 + Intent/Plan/AgentResult 数据模型
├── tools.py                     # 工具注册表 + 所有工具函数实现
├── orchestrator.py              # v1 编排器（意图分类 + 计划生成 + 调度 + 融合）
├── sensor_agent.py              # 传感器数据查询与趋势分析 Agent
├── knowledge_agent.py           # RAG 知识库检索 Agent
├── search_agent.py              # 联网搜索 Agent
├── alarm_agent.py               # 报警与异常管理 Agent
├── device_agent.py              # 设备管理 Agent
│
│  ── v2 增强架构新增 ──
│
├── blackboard.py                # 共享状态黑板 — Agent 间中间结果通信
├── memory_manager.py            # 对话记忆管理器 — 短期记忆 + 长期画像 + 自动摘要
├── workflow_engine.py           # DAG 工作流引擎 — 条件分支 + 并行 + 重试 + 门控
├── evaluator_agent.py           # 自评估 Agent — 质量门控 + 重试决策
├── monitor_agent.py             # 主动监控 Agent — 统计异常检测 + 巡检报告
└── enhanced_orchestrator.py     # v2 增强编排器 — 整合所有新组件
```

## 改进的多 Agent Workflow 架构 (v2)

在原架构基础上，新增了六大核心能力，将系统从「线性 Pipeline」升级为「DAG 工作流引擎」：

### 原架构局限 vs 增强架构

| 维度 | v1 原架构 | v2 增强架构 |
|------|-----------|-------------|
| 执行流程 | 线性 Pipeline | DAG 工作流 + 动态重规划 |
| 状态管理 | 无状态 | 短期记忆 + 长期画像 + 自动摘要 |
| 质量控制 | 无 | 自评估 + 重试 + 降级 |
| Agent 通信 | 结果合并 | 黑板共享中间结果 |
| 监控模式 | 纯被动 | 主动异常检测 + 巡检报告 |
| 多轮对话 | 不支持 | 上下文感知 + 引用解析 |

### 新增核心组件

- **Blackboard（共享状态黑板）**：Agent 间通过黑板共享中间结果，后续 Agent 可读取前置 Agent 的产出作为上下文
- **MemoryManager（对话记忆）**：滑动窗口式短期记忆 + 用户画像长期记忆 + LLM 自动摘要压缩
- **WorkflowEngine（DAG 工作流引擎）**：支持条件分支、并行执行、质量门控、动态重试的有向无环图执行引擎
- **EvaluatorAgent（自评估 Agent）**：从完整性、准确性、具体性、工具成功率四个维度评估输出质量，质量不达标时触发重试
- **MonitorAgent（主动监控 Agent）**：基于 Z-Score、变化率、阈值接近度、数据停滞四种统计方法的异常检测器
- **EnhancedOrchestrator（增强编排器）**：整合所有新组件的总入口，向后兼容原 API

### 增强版执行流程

```
用户消息
  │
  ▼
0. 引用解析 ─── 检查是否引用了上一轮对话（"刚才"、"上面说的"等）
  │
  ▼
1. 记忆注入 ─── 将对话历史 + 用户画像注入上下文
  │
  ▼
2. 意图分类 ─── LLM 驱动 + 关键词降级
  │
  ▼
3. 计划生成 ─── 确定 Agent 调度序列
  │
  ▼
4. DAG 执行 ─── 通过工作流引擎调度，Agent 间通过黑板通信
  │     │
  │     ▼
5. 自评估 ──── 评估输出质量，不达标则重试（最多 N 次）
  │
  ▼
6. 结果融合 ─── LLM 合成多 Agent 结果
  │
  ▼
7. 记忆更新 ─── 记录本轮对话 + 更新用户画像
  │
  ▼
8. 主动监控 ── 附带最新健康检查状态
```

### 快速使用

```python
from agents import create_enhanced_orchestrator

# 一行代码创建，自动启用所有新特性
orch = create_enhanced_orchestrator(
    backend="ollama",
    model="qwen3.5:0.8b",
    enable_memory=True,       # 对话记忆
    enable_evaluator=True,    # 自评估循环
    enable_monitor=True,      # 主动监控
    quality_threshold=0.5,    # 质量阈值
)

# 基础对话（自动记忆管理）
result = await orch.handle_message("温度多少？")
result = await orch.handle_message("刚才那个数据正常吗？")  # 自动解析引用

# 主动监控
alerts = await orch.run_proactive_check()

# 巡检报告
report = await orch.generate_report(period="day")

# 自定义 DAG 工作流
from agents.workflow_engine import WorkflowDefinition, ConditionRule

wf = WorkflowDefinition(name="deep_analysis")
wf.add_node("alarm", "task", agent_name="alarm")
wf.add_node("sensor", "task", agent_name="sensor")
wf.add_node("gate", "gate", dependencies=["alarm", "sensor"])
wf.add_node("fuse", "merge", dependencies=["gate"])

result = await orch.workflow_engine.execute(wf, message="分析报警原因")
```

### 架构可视化

打开 `improved_workflow_architecture.html` 查看完整的交互式架构图，包含组件总览、执行流程、代码示例和文件结构。

---

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

### 4. AI 对话配置

1. 安装 [Ollama](https://ollama.ai/)
2. 拉取模型：`ollama pull qwen3.5:0.8b`（或其他模型）
3. 启动 Ollama 服务：`ollama serve`（通常自动启动）
4. 在系统前端选择模型并点击"启动模型服务"

---

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
│   └── index.html          # 前端静态资源（单页应用）
├── uploads/
│   └── device_models/      # 设备3D模型上传目录
└── monitor_data.db         # SQLite 数据库（自动创建）
```

---

## 核心模块

### 1. 传感器数据采集

**数据来源**：树莓派等设备通过 REST API 上报真实传感器数据

```
POST /api/raspberry/sensors
Content-Type: application/json

{
  "temperature": 25.3,
  "humidity": 58.2,
  "pressure": 1013.5,
  "vibration": 0.12,
  "device_id": "raspberry-pi-5",
  "area": "A区",
  "timestamp": "2026-05-23T10:30:00"
}
```

**数据存储**：
- `sensor_data` - 原始传感器历史数据
- `sensor_events` - 带状态标记的传感器事件
- `anomaly_sensor_data` - 异常数据记录（含批次 ID）

### 2. 报警检测

**配置参数**：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `alarm_window_seconds` | 60 | 时间窗口（秒），窗口内多次超阈值才触发报警 |
| `alarm_trigger_count` | 1 | 触发报警所需的超阈值次数 |
| `alarm_cooldown_seconds` | 300 | 报警冷却期（秒） |

**报警级别**：
- `warning` - 超过阈值
- `danger` - 超过阈值的 120%

### 3. AI 对话与 RAG

**对话接口**：
- WebSocket: `ws://localhost:8000/ws/chat`
- HTTP: `POST /api/chat`

**RAG 流程**：
1. 上传文档 → 解析文本 → 切分片段 → 生成 Embedding → 存储
2. 对话时检索相似片段 → 注入系统提示词 → 调用 Ollama

**联网搜索**：消息含"搜索/联网"等关键词时，自动调用 DuckDuckGo 搜索

### 4. 飞书集成

**长连接模式**（默认启用）：
- 使用 `lark-oapi` WebSocket 客户端
- 自动接收飞书群消息并回复
- 配置项：`feishu_long_connection_enabled`、`feishu_app_id`、`feishu_app_secret`

**Webhook 模式**（传统）：
- 报警信息通过 HTTP POST 推送
- 配置项：`feishu_webhook`

### 5. 设备与模型管理

- 多设备注册：`CONFIG["devices"]` 列表
- 设备信息：id、name、latitude、longitude、registered_at、status、model_url
- 3D 模型支持本地存储或 Supabase Storage 云端存储

---

## API 接口

### 传感器
| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/raspberry/sensors` | POST | 接收树莓派传感器数据（真实数据） |
| `/api/raspberry/ping` | GET | 设备心跳检测 |
| `/api/sensors/latest` | GET | 获取最新传感器数据 |
| `/api/sensors/current` | GET | 获取当前数据（轮询） |
| `/api/sensor-events` | GET | 获取传感器事件列表 |
| `/api/anomaly-data` | GET | 获取异常数据记录 |
| `/api/history` | GET | 获取历史数据（hour/day/week/month） |

### 报警
| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/alerts` | GET | 获取报警记录 |
| `/api/alerts/{id}/handle` | POST | 标记报警已处理 |

### AI 对话
| 接口 | 方法 | 说明 |
|------|------|------|
| `/ws/chat` | WebSocket | AI 对话流式接口 |
| `/api/chat` | POST | AI 对话 HTTP 接口 |
| `/api/ollama/test` | POST | 测试 Ollama 连接 |
| `/api/ollama/models` | GET | 获取可用模型列表 |
| `/api/ollama/start` | POST | 启动/预加载模型 |

### RAG 知识库
| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/rag/upload` | POST | 上传文档到知识库 |
| `/api/rag/documents` | GET | 获取知识库文档列表 |

### Skills
| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/skills` | GET | 获取 Skills 列表 |
| `/api/skills` | POST | 上传新 Skill |

### 设备模型
| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/device/model` | POST | 上传设备 3D 模型 |

### 数据库
| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/database/test` | POST | 测试 PostgreSQL 连接 |

### 飞书
| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/feishu/test` | POST | 测试飞书连接 |
| `/api/feishu/events` | POST | 飞书事件回调（Webhook） |

### 其他
| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/camera/capture` | POST | 摄像头截图 |
| `/api/settings` | GET/POST | 系统配置 |
| `/api/config` | GET | 获取阈值配置 |
| `/ws/sensor` | WebSocket | 传感器数据流 |

---

## 配置文件

系统配置在 `api_server.py` 的 `CONFIG` 字典，运行时持久化到 `config.json`。

```python
CONFIG = {
    # Ollama
    "ollama_url": "http://localhost:11434",
    "ollama_model": "qwen3.5:0.8b",
    "ollama_enabled": True,

    # 飞书
    "feishu_webhook": "",
    "feishu_verification_token": "",
    "feishu_app_id": "",
    "feishu_app_secret": "",
    "feishu_long_connection_enabled": True,
    "feishu_receive_group_messages": True,
    "feishu_forward_ai_replies": True,

    # 数据库
    "database_backend": "sqlite",
    "postgres_dsn": "",
    "supabase_url": "",
    "supabase_key": "",
    "supabase_storage_bucket": "device-models",

    # RAG
    "rag_enabled": True,
    "rag_top_k": 4,
    "agent_search_enabled": True,

    # 报警阈值
    "thresholds": {
        "temperature": 40.0,
        "humidity": 80.0,
        "vibration": 0.5
    },
    "alarm_trigger_count": 1,
    "alarm_window_seconds": 60,
    "alarm_cooldown_seconds": 300,
    "sensor_interval": 5,

    # 设备
    "devices": [],
    "selected_device_id": "device-1"
}
```

---

## 传感器阈值

| 参数 | 默认阈值 | 单位 |
|------|----------|------|
| 温度 | 40.0 | °C |
| 湿度 | 80.0 | %RH |
| 振动 | 0.5 | mm/s |

---

## 数据库表结构

| 表名 | 说明 |
|------|------|
| `sensor_data` | 传感器历史数据 |
| `sensor_events` | 带状态的传感器事件 |
| `anomaly_sensor_data` | 异常数据记录（含批次 ID） |
| `alerts` | 报警记录 |
| `camera_logs` | 摄像头日志 |
| `rag_documents` | RAG 知识库文档元数据 |
| `rag_chunks` | RAG 知识库文本片段与 embedding |
| `skills` | 上传的 Skill 内容 |

---

## 使用说明

### 首次使用

1. 启动服务后访问 http://localhost:8000
2. 接入真实传感器设备，数据自动上报
3. 在设置中配置传感器阈值和报警规则
4. 如需 AI 对话，在 AI 对话界面选择模型并启动
5. 如需 RAG 知识库，上传相关文档
6. 如需飞书集成，配置飞书 Webhook 或 App 凭证

### AI 对话

1. 打开 AI 对话界面
2. 选择 Ollama 模型
3. 点击"启动模型服务"预加载模型
4. 输入问题进行对话
5. AI 会结合当前传感器数据给出回答
6. 可以上传 RAG 文档让 AI 基于知识库回答
7. 消息含"搜索/联网"等关键词时，AI 会联网检索

---

## 许可证

MIT License