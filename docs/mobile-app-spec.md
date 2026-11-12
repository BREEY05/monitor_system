# PULSE · 工业监控移动端 App 方案（v0.1）

> 配套概念稿：`output/mobile-mockups/index.html`（5 屏，390×844）
> 效果图：`output/mobile-mockups/all-screens.png`
> 适用系统：当前工作区的 FastAPI 监控后端 + MySQL + Ollama + 飞书

---

## 1. 一句话结论

做一个 **"现场配置 + 远程运维"** 的 Flutter App，而不是手机版大屏：
公网 HTTPS 连回厂内服务器，核心是 **AI 对话 + 结构化状态 + 一屏闭环的报警处理 + 可审计的配置修改**。
视觉用原创的 **PULSE（脉冲）** 语言：浅色极简底 + 蓝色脉搏环 + 蓝紫渐变 AI 光球；与 Web 端密集的大屏/表格形成明显差异。

---

## 2. 目标与边界

### 2.1 要做
- 远程查看：系统健康、设备状态、传感器实时值、报警时间线。
- 远程配置：阈值、设备、AI/知识库、飞书、地图；所有写入有校验、有版本、可回滚。
- AI 对话：基于现有 Orchestrator / 多 Agent / RAG，回答带指标卡、图表、工具轨迹，不是纯文本聊天。
- 报警推送：前台 WebSocket + 后台厂商通道 + 飞书群兜底。
- Android 优先（Flutter），兼容鸿蒙 4（APK 直接安装），后续再评估鸿蒙 NEXT。

### 2.2 不做（一期）
- 不做手机端 3D 数字孪生编辑器（Web 端保留）。
- 不做多租户 SaaS；只服务本厂/本团队。
- 不做离线全功能；离线只保留"最近数据缓存 + 配置草稿"。
- 不替代 Web 端的大屏与 3D 场景。

---

## 3. 上手前必须先补的三件事（后端）

当前后端 **没有任何鉴权**，且配置是整包覆盖。App 一旦上公网，这三件事是硬前提：

| 问题 | 现状 | 必须改成 |
|---|---|---|
| 无鉴权 | 任意人可访问 `/api/settings`、`/api/chat` | JWT 登录 + 角色权限 + 登录限速 |
| 整包覆盖 | `POST /api/settings` 执行 `CONFIG.update(settings)`（api_server.py:2819） | PATCH 合并 + JSON Schema 校验 + 乐观锁版本号 |
| 无审计/回滚 | 改完即生效，无历史 | 每次写入存版本、记录操作人/IP/diff，支持回滚 |
| 敏感字段回显 | GET /api/settings 返回 `feishu_app_secret` 等（api_server.py:2856） | 只写不回显，返回 `******` 掩码 |
| 无设备 CRUD | 设备只能整包改 devices 数组 | 独立设备接口 + 二维码绑定 |

> 结论：先做 M0（约 3–5 天）把后端安全补齐，再开始接 App。否则 App 做得再好也不能上线。

---

## 4. 总体架构

```
┌──────────────┐    HTTPS 443 (公网)     ┌─────────────────────────────┐
│  Android App │ ──────────────────────▶ │  Caddy / Nginx 反向代理      │
│  Flutter     │   WSS /ws/sensor        │  - 自动证书 (Let's Encrypt)  │
│  鸿蒙4 可装  │ ◀────────────────────── │  - 只放行 /api/* 与 /ws/*    │
└──────────────┘                         └──────────────┬──────────────┘
                                                        │ 127.0.0.1:8000
┌──────────────┐    HTTP 内网             ┌──────────────▼──────────────┐
│  Web 大屏     │ ──────────────────────▶ │  FastAPI (api_server.py)     │
│  仅内网       │   http://server:8000     │  REST + WebSocket            │
└──────────────┘                         └──────┬────────┬──────────────┘
                                                │        │
                                     ┌──────────▼──┐  ┌──▼─────────────┐
                                     │ MySQL 3307  │  │ Ollama 11434   │
                                     │ 仅 127.0.0.1│  │ 仅 127.0.0.1   │
                                     └─────────────┘  └────────────────┘

推送：App 前台 WS → 本地通知；App 后台 → 厂商通道（华为/小米/OPPO/vivo 或极光聚合）
兜底：飞书群机器人（已有 webhook，零额外成本）
```

关键点：
- **Web 与 App 共用一套 API**，但反向代理只把 `/api/*`、`/ws/*` 暴露到公网，`/` 与 `/static/*` 公网返回 404；Web 端继续走内网 8000。
- MySQL、Ollama 一律绑定 `127.0.0.1`，不暴露公网。
- 80MB 的 3D 模型上传：反代 `client_max_body_size` 调到 100M，超时调到 300s；App 端分片/断点续传放二期。

---

## 5. 公网部署（有公网 IP 的落地方式）

> **2026-11-12 更新**：实际落地改为「云服务器只做公网入口（nginx + Let's Encrypt + frps），后端 / MySQL / Ollama 全部留在本机，通过 frp 反向隧道对外」。完整步骤见 `docs/deploy-frp-local-engine.md`，本文下面的 Caddy 方案仅作历史参考。

### 5.1 推荐：域名 + Caddy 自动 HTTPS
Let's Encrypt **不给纯 IP 签证书**，所以需要：
1. 一个域名（如 `monitor.example.com`），A 记录指向公网 IP；
2. 服务器 80/443 放行，Caddy 自动申请/续期证书；
3. 若服务器在中国大陆，域名需 **ICP 备案**（否则 80/443 会被拦）；不想备案就把服务器放境外/香港，但延迟与合规要权衡。

Caddyfile 示例：

```caddy
monitor.example.com {
    encode zstd gzip
    request_body {
        max_size 100MB
    }

    # 只暴露 App 需要的 API 与 WebSocket
    @api path /api/* /ws/*
    handle @api {
        reverse_proxy 127.0.0.1:8000 {
            transport http {
                read_timeout 300s
                write_timeout 300s
            }
        }
    }

    # 其余（Web 页面、静态资源）公网一律拒绝
    handle {
        respond "Not Found" 404
    }
}
```

### 5.2 只有 IP、没有域名时的备选
- 方案 A：买最便宜域名 + 备案/境外服务器（首选，长期最省心）。
- 方案 B：自签证书 + App 内置证书指纹（certificate pinning）。能用，但浏览器/应用商店合规差、换证书要发版，不推荐生产。
- 方案 C：Cloudflare Tunnel / frp 内网穿透（仍需域名），适合没有公网 IP 的场景。

### 5.3 服务器加固清单
- 只开 22（限制来源 IP）、80、443；8000/3307/11434 不对公网开放。
- SSH 禁密码登录，改用密钥；fail2ban。
- 后端以非 root 用户运行；配置/密钥文件权限 600。
- 日志脱敏（不记录 token、密码、飞书 secret）。
- 每日备份 MySQL + config.json，保留 7/30 天。

---

## 6. 鉴权与权限模型

### 6.1 登录（M0 已实现）
- `POST /api/mobile/login`：用户名 + 密码，校验 PBKDF2-HMAC-SHA256（210000 次迭代 + 16 字节随机盐），返回 Bearer Token（HS256 JWT，默认 12 小时）与用户信息。
- 首次启动自动创建 `admin`：初始密码写入 `data/mobile_admin_credentials.txt`，也可用环境变量 `MOBILE_ADMIN_PASSWORD` 预先指定。
- 登录失败按 IP + 账号限速：5 次失败 / 5 分钟 → 429；成功即清零。登录成功/失败都写审计。
- App 端 token 存 `flutter_secure_storage`（Android Keystore），不落普通 SharedPreferences。
- 【二期】refresh token 旋转、飞书扫码登录、登出黑名单。

### 6.2 角色
| 角色 | 查看 | 报警处理 | 改阈值/设备 | 改 AI/飞书/数据库 | 用户管理 |
|---|---|---|---|---|---|
| viewer 只读 | ✓ | — | — | — | — |
| operator 运维 | ✓ | ✓ | ✓ | — | — |
| admin 管理员 | ✓ | ✓ | ✓ | ✓ | ✓ |

### 6.3 审计
- 所有写操作记录：who、when、IP、UA、接口、对象、旧值/新值 diff、结果。
- App 内"审计日志"可查最近 30 天；敏感字段在日志中同样掩码。

---

## 7. API 契约（新增/改造）

> **M0 状态（2026-11-12）**：以下 7.1–7.6 中标注"已实现"的接口均已落地在 `api_server.py`，并用 TestClient 做了 41 项回归测试（脚本 `.local-tools/m0_test.py`，隔离 `PULSE_MOBILE_DATA_DIR`，不写真实配置/MySQL）。
> **鉴权边界**：局域网直连（请求不带 `X-Forwarded-For` / `X-Real-IP`）保持原 Web 体验，不强制 Token；一旦经过反向代理（公网入口）则 `/api/*` 与 `/ws/*` 必须携带 Token。这样同一套后端可同时服务"内网 Web 大屏"和"公网手机 App"。可用 `mobile_auth_enabled` 开关关闭强制鉴权（不建议公网使用）。

### 7.1 认证（已实现）
```
POST /api/mobile/login      {username, password}
     -> {success, token, token_type:"Bearer", expires_in, expires_at, user, server}
POST /api/mobile/refresh    Authorization: Bearer <token> -> 重新签发 token
GET  /api/mobile/me         -> {user, server, auth}
GET  /api/mobile/ping       -> 公开心跳 {ok, server}
```
- `user` 结构：`{username, display_name, role, permissions[], created_at}`；角色等级 viewer=1 / operator=2 / admin=3。
- `/api/mobile/*` 除 login/bootstrap/ping 外全部要求 Token。
- 【二期】POST /api/mobile/logout、refresh token 旋转。

### 7.2 启动引导（已实现，公开）
```
GET /api/mobile/bootstrap
-> {
     server: {name, version, time, config_version},
     auth:   {required: true, scheme: "Bearer", login: "/api/mobile/login", token_hours: 12},
     features: {twin_scene, config_patch, config_history, device_crud, audit_log, alerts, ai_chat}
   }
GET /api/mobile/config-schema   (需 Token)
-> {version, updated_at, updated_by,
    groups: [ {id, title, description, fields: [
        {key, label, type, unit?, min?, max?, options?,
         sensitive?, restart_required?, current, has_value?}
    ]} ],
    devices_managed_by: "/api/device", roles: {...}}
```
- 设置页按 `groups` 动态渲染，共 5 组：database / thresholds / ai / feishu / system。
- secret 字段只返回 `current: null` + `has_value: bool`，永不回显明文。

### 7.3 配置（M0 已实现）
```
GET   /api/settings                 -> 配置（mysql_password 不回显，返回 mysql_password_set）
PATCH /api/settings
      body: {base_version: 42, changes: {...}, reason?: "..."}   # 只传要改的字段
      -> 200 {success, version: 43, changed: [...], warnings: [...], database?}
      -> 409 {detail: {code: "version_conflict", current_version: 43, your_version: 42}}
      -> 422 {detail: {code: "validation_failed", errors: [{key, message}]}}

GET   /api/settings/history?limit=20 -> {version, updated_at, updated_by, items: [...]}
POST  /api/settings/rollback {version, reason?} -> {success, version, rolled_back_to, changed}
GET   /api/system/audit?limit=50     -> {items, count}（仅 admin）
```

规则（与实现一致）：
- 版本号存 `data/config_state.json`，每次成功写入 +1，保留最近 20 个带快照的版本；`base_version` 不符直接 409，绝不静默覆盖。
- 服务端按字段元数据校验类型/范围/枚举；未知键、整包 `devices`、越界值 → 422 并返回逐字段错误。
- 阈值可写成嵌套 `{"thresholds": {"temperature": 30.5}}`，内部归一化为 `thresholds.temperature`。
- 敏感字段：读接口不回显；写接口收到 `"***"` 表示"不修改"；审计与历史快照中一律掩码。
- 回滚只应用快照中非敏感字段，敏感字段保持当前值；回滚本身也会生成新版本。
- 【二期】阈值"全局默认 + 单设备覆盖"；PATCH 后 WebSocket 广播 `config.changed`；历史 diff 视图。

### 7.4 设备（M0 已实现）
```
GET    /api/devices                    -> {devices, selected_device_id, version}
POST   /api/device                     -> {success, device, version}
PATCH  /api/device/{device_id}         -> {success, device, version}
DELETE /api/device/{device_id}         -> {success, deleted, version}
POST   /api/device/model               -> 复用现有模型上传（Web 端）
GET    /api/twin/scene                 -> 数字孪生场景（见 11.5）
```
- 字段：`name / latitude / longitude / status / model_url / model_filename / zone / twin{position, rotation, zone}`。
- 校验：`status ∈ {运行中, 维护中, 离线, 停用}`；`model_url` 必须以 `/static/uploads/device_models/` 开头；`model_filename` 不允许路径分隔符；`twin.position` 为 `[x,y,z]`。
- 删除为硬删除，但**至少保留 1 台**；删除当前选中设备会自动切换。
- 【二期】软删除、扫码一次性绑定码、`/api/devices/{id}/telemetry`、`status`/`q` 过滤。

二维码内容（建议）：
```json
{"v":1,"type":"pulse-device","device_id":"device-177847165324","name":"工业设备 #03","secret":"一次性绑定码"}
```
绑定码一次性、5 分钟有效，防止随便扫码接入。

### 7.5 报警 / 健康 / 推送
```
GET  /api/alerts?level=&status=&cursor=&limit=20   -> 分页时间线
POST /api/alerts/{id}/handle  {action: handle|silence|ignore, minutes?}
GET  /api/system/health -> {api, mysql, ollama, feishu, ws_clients, uptime}
POST /api/mobile/push-token {provider, token, device_id}
DELETE /api/mobile/push-token
```

### 7.6 WebSocket（M0 已加鉴权）
```
wss://host/ws/sensor?token=<token>
wss://host/ws/chat?token=<token>
消息：{type: "sensor"|"alert"|"config.changed", seq, ts, data}
```
- 直连（局域网、无反代头）放行，不影响 Web 首页；经反向代理（存在 X-Forwarded-For / X-Real-IP）时必须携带 `?token=`，否则以 1008 关闭。
- 也支持 `Sec-WebSocket-Protocol: bearer,<token>` 传 token（避免 URL 留痕）。
- 心跳 25s；断线指数退避重连（1s→30s）；断线期间 App 用 `seq`/时间戳增量拉取，避免漏报警。
- 【二期】`config.changed` 广播、`seq` 续传。

---

## 8. 配置写入时序（防互盖）

```
App                         API                         DB
 |-- PATCH /api/settings --->|                          |
 |   If-Match: 42            |-- 校验 schema ---------->|
 |                           |-- 校验 version=42 ------>|
 |                           |-- 写 config_versions --->|
 |                           |-- 更新 config ---------->|
 |<-- 200 {version:43} ------|                          |
 |                           |-- WS 广播 config.changed |
```
冲突时返回 409，App 展示"配置已被他人修改"并提供 **diff 对比 + 重新应用**，不静默覆盖。

---

## 9. 报警推送策略

| 场景 | 通道 | 说明 |
|---|---|---|
| App 在前台 | WebSocket → 本地通知/横幅 | 零延迟、免费 |
| App 在后台（Android） | 厂商通道（华为/小米/OPPO/vivo 或极光/个推聚合） | 国内 FCM 不可用；华为通道覆盖鸿蒙 4 |
| 所有情况兜底 | 飞书群机器人（已有） | 零开发成本，保证"至少有人知道" |
| 严重报警 | 厂商通道 + 飞书 + 电话（可选，二期） | 分级升级 |

细节：
- 推送 payload 只带 `alert_id / level / title / device`，点开再拉详情，避免敏感数据经过第三方。
- 去重键：`device_id + metric + level + 时间窗`，防止 3 条连续触发刷屏。
- 免打扰时段只静默"提示"级，"严重"级仍推送。
- 推送到达率要埋点统计（发送/展示/点击），否则无法优化。

---

## 10. 移动端技术选型

| 层 | 选择 | 理由 |
|---|---|---|
| 框架 | Flutter 3.x stable / Dart 3 | 一套代码 Android + 鸿蒙 4（APK），UI 还原度高 |
| 状态 | Riverpod | 编译期安全、易测试 |
| 路由 | go_router | 深链（推送点开直达报警详情） |
| 网络 | dio + 拦截器 | 统一注入 token、401 自动刷新、重试 |
| 实时 | web_socket_channel | 轻量；配重连/心跳封装 |
| 存储 | flutter_secure_storage + drift(SQLite) | token 进 Keystore；离线缓存/草稿 |
| 图表 | 自绘 CustomPainter | 脉搏环、迷你趋势线需要独特视觉，现成库风格不搭 |
| 推送 | 厂商通道 SDK / 极光聚合 | 按最终选型接入 |
| 最低版本 | Android 8.0 (API 26) / arm64-v8a | 覆盖鸿蒙 4 与主流机型 |

### 鸿蒙 4 说明
- 鸿蒙 4（HarmonyOS 4.x）仍兼容 Android APK，Flutter 产物可直接安装，**一期不需要 Flutter OHOS 分支**。
- 需在华为应用市场单独提交（软著、隐私政策、备案等资质）。
- 若未来上 **HarmonyOS NEXT**（纯血鸿蒙，不兼容 APK），才需要 Flutter OHOS 适配或原生 ArkTS 重写，成本高，放二期评估。

### 包体
- `--split-per-abi` + 图标 tree-shake，预计 15–22MB。
- 3D 模型不打进包，按需下载/缓存。

---

## 11. PULSE 设计系统

### 11.1 设计关键词
**浅色极简 · 大留白 · 数据脉冲 · AI 前置 · 克制的蓝紫渐变**

与 Web 端（`#eef2f8` / 蓝 `#1d4ed8`，密集表格 + 3D 大屏）区分：手机是"随身巡检仪"——白卡、大留白、大字号、AI 优先；Web 是"白天控制台"。二者同属浅色，但信息密度与交互路径完全不同。

### 11.2 Design Tokens

| Token | 值 | 用途 |
|---|---|---|
| `bg` | `#F4F5F7` | 页面底色（画板 `#ECEEF2`） |
| `card` | `#FFFFFF` | 卡片 |
| `card-2` | `#F8F9FB` | 卡片内嵌块 |
| `line` | `#EAECF0` | 描边/分割 |
| `text` | `#101828` | 主文字 |
| `sub` | `#667085` | 次要文字 |
| `dim` | `#98A2B3` | 弱化文字 |
| `accent` | `#3D5AFE` | 主色/数据/AI |
| `accent-2` | `#8B5CF6` | 渐变次色/提示 |
| `amber` | `#F79009` | 警告/维护 |
| `red` | `#F04438` | 严重/离线 |
| `green` | `#12B76A` | 正常/恢复 |
| 圆角 | 12 / 16 / 18 / 24 px | 按钮/卡片/大卡/手机屏 |
| 间距 | 4 的倍数；页面左右 18 | — |
| 字体 | 系统无衬线 + `tabular-nums` | 数字等宽，读数不跳动 |

规则：**无 emoji、图标全部内联 SVG、数字一律等宽、红色只给严重级**。

### 11.3 六屏结构

1. **总览**：脉搏环（系统健康分）为视觉核心 → 4 个指标 tile（温度/湿度/气压/振动，带阈值与迷你趋势）→ AI 洞察卡（主动指出异常与建议）→ 最新报警。
2. **AI 对话**：结论卡（状态标签 + 一句话结论）→ 指标卡 → 24h 趋势图 → 工具轨迹（实时数据/历史趋势/维护手册）→ 分点分析 → 一键动作（生成巡检报告/查看设备/订阅报警）。输入栏支持语音与"继续追问"。
3. **设备**：列表/地图/巡检三种视图；设备卡带状态光环、关键指标、迷你趋势；扫码接入；地图用抽象车间分区（一期不做真 GIS）。
4. **报警**：等级筛选 → 时间线（严重/警告/提示）→ 一键处理/静默/追问 AI → 推送开关 → AI 复盘。
5. **我的**：账号与角色、公网服务器状态（TLS/延迟/心跳）、配置入口（阈值/设备/AI/知识库/飞书/审计）、推送开关、运维工具（网络诊断/健康检查/配置回滚）。
6. **数字孪生**（第 6 屏，从设备页/设备详情/报警定位进入）：聚焦式 3D 车间场景——分区 chips + 状态图例 + 缩放复位 + 设备热点标签；点击设备后底部弹出数据 sheet（关键指标、24h 趋势、AI 诊断）。

底部 Dock 中央是 **AI 光球**，任何页面一键进入对话——AI 是核心入口，不是第五个 Tab。

### 11.4 交互与动效
- 脉搏环呼吸动画（2.4s，低幅度），仅总览；低电量/减弱动效时关闭。
- 数字变化滚动 300ms；报警新条目从顶部滑入并高亮 1.2s。
- 所有可点区域 ≥ 44dp；浅色底上正文对比度 ≥ 4.5:1（白卡上避免使用 `#98A2B3` 做正文）。
- 危险操作（回滚配置、删除设备）二次确认 + 输入设备名。

### 11.5 数字孪生（手机端）

**定位**：手机上的孪生不是 Web 控制台的缩小版，而是"聚焦式场景"——一次看一个车间、点一台设备、看一组数据。3D 负责空间感与定位，数据 sheet 负责读数与行动。

- **入口**：设备页地图卡（数字孪生）→ 设备详情"查看 3D" → 报警详情"定位到设备" → 我的/设备与 3D 模型。
- **交互**：单指旋转、双指缩放、双击复位；分区 chips 过滤（全部/泵组区/装配区/配电区）；点设备 → 光环高亮 + 底部 sheet 弹起（振动/温度/电流 + 24h 趋势 + 阈值线）；"AI 诊断"把设备上下文带入 AI 对话。
- **实现路线 A（推荐）**：Flutter 壳 + WebView 复用现有 Three.js 场景。新增移动版页面 `/mobile/twin`（复用 `static/vendor/three` 与 `equipment-scene.js` 的加载/光照/拾取逻辑），通过 JS bridge 传 JWT、选中设备、主题 token。优点：3D 逻辑零重写、模型与材质现成，工作量集中在 UI 与手势；代价：WebView 首帧与内存、手势冲突、鸿蒙 WebView 差异需要单独验证。
- **实现路线 B（二期）**：Flutter 原生 3D（Impeller 自绘 / flutter_gl / three_dart）。体验与性能更好，但需要重写拾取、光照与后处理，一期不做。
- **性能预算**：同屏设备 ≤ 5 台（其余 LOD 或合并批次）；单模型 ≤ 300KB（Draco + KTX2 压缩）；4G 首屏 ≤ 1.5s；纹理 ≤ 1024；目标 45–60fps，低端机降 30fps 并关阴影；加载失败/弱网降级为现有 2D 平面图卡片。
- **边界**：手机端只读（旋转/缩放/选中/看数据）；模型上传、设备增删留在 Web 或"我的 → 设备与 3D 模型"表单，80MB 上传提示仅 Wi-Fi。
- **数据**：沿用 `GET /api/twin/overview`；移动版补 `GET /api/twin/scene`（分区、设备坐标、状态色）并用 `/ws/sensor` 叠加实时状态；热点坐标取 `config.devices[].position`。
- **安全**：场景页与 API 同域 + JWT；WebView 关闭 file 访问、限定白名单域，禁止把 token 写进 URL。

---

## 12. 里程碑（建议）

| 阶段 | 内容 | 工期 |
|---|---|---|
| M0 ✅ | 后端安全：JWT、PATCH+校验+版本、审计、掩码、设备 CRUD、health、twin scene（**已完成，41 项回归测试通过**） | 3–5 天 |
| M1 ✅ | Flutter 工程 + PULSE 设计系统 + 6 屏 Mock 数据跑通（**已完成**：analyze 0 issue、test 2/2、debug/release APK 均构建成功，六屏真机同款截图见 `output/mobile-mockups/app-screens-board.png`） | 4–6 天 |
| M2 ⏳ | 接真 API：登录、总览、设备、报警、设置、AI 对话（REST+WS）；数字孪生 WebView 移动版（替换 M1 的 CustomPainter 占位） | 8–12 天 |
| M3 | 公网部署（域名/证书/反代/加固）+ 推送 + 内测包 | 3–5 天 |
| M4 | 真机兼容（鸿蒙 4/主流安卓）、崩溃/性能、商店上架 | 5–7 天 |

> 合计约 4–5 周（1 人全栈节奏）。先做 M0+M1，能最早看到"真机上的 PULSE"。

---

## 13. 风险与对策

| 风险 | 影响 | 对策 |
|---|---|---|
| 公网暴露无鉴权 | 数据泄露/被改配置 | M0 必做；反代只放行 /api、/ws |
| 纯 IP 无证书 | 无法 HTTPS，商店/合规不过 | 买域名；境外服务器可免备案 |
| 国内安卓后台被杀 | 收不到推送 | 厂商通道 + 飞书兜底 + 前台 WS |
| Ollama 资源占用 | 服务器卡顿 | 限制并发/模型大小；GPU 可选 |
| 80MB 模型上传 | 反代 413/超时 | body limit 100M、超时 300s、二期分片 |
| 鸿蒙 NEXT 不兼容 APK | 未来机型装不上 | 一期明确支持鸿蒙 4；NEXT 二期评估 |
| 合规 | 上架被拒 | 软著、ICP 备案、隐私政策、权限最小化、SDK 合规清单 |
| 配置误改 | 生产事故 | 校验 + diff 预览 + 版本回滚 + 审计 |

---

## 14. 需要确认的决策（开工前）

1. **域名与服务器**：是否有域名？服务器在境内还是境外（决定是否备案）？
2. **登录方式**：账号密码，还是直接用飞书扫码登录？
3. **推送通道**：只做"飞书 + App 前台"，还是一期就接华为/小米等厂商通道？
4. **视觉确认**：PULSE 浅色极简六屏方向是否 OK？Flutter 版六屏已按此实现（`output/mobile-mockups/app-screens-board.png`），如要调整配色/密度，现在改成本最低。
5. **首期范围**：只做"看 + 报警 + AI"，还是配置修改也一期上？（建议配置放 M2 后半段）

---

## 15. 当前产物

| 文件 | 说明 |
|---|---|
| `output/mobile-mockups/index.html` | 6 屏高保真概念稿 · 浅色版（可直接浏览器打开） |
| `output/mobile-mockups/all-screens.png` | 六屏总览图 |
| `output/mobile-mockups/01-overview.png` … `06-twin.png` | 单屏 2x 图 |
| `output/mobile-mockups/twin-screen.html` | 数字孪生单屏独立页（Three.js 真实模型） |
| `mobile/` | Flutter 工程（38 个 dart 文件：theme / models / mock_data / 6 screens / 22 widgets / smoke test） |
| `mobile/build/app/outputs/flutter-apk/app-arm64-v8a-release.apk` | 可直接安装的 Android 包（15.7 MB；arm64/armeabi-v7a/x86_64 三 ABI） |
| `output/mobile-mockups/app-01-overview.png` … `app-06-twin.png` | Flutter 实际渲染的六屏截图（1170×2532） |
| `output/mobile-mockups/app-screens-board.png` | 六屏拼图（Flutter 真机同款渲染，用于视觉验收） |
| `output/mobile-mockups/m2-01-overview.png` … `m2-05-profile.png`、`m2-02-ai-chat.png` | M2 接真实接口后的六屏截图（1170×2532） |
| `output/mobile-mockups/m2-screens-board.png` | M2 验收拼图（5 屏 App + 1 屏真实孪生 WebView） |
| `static/mobile-twin.html` | 手机端数字孪生页（Three.js + GLB，被 App WebView 加载） |
| `docs/m2-backend-notes.md` | M2 后端契约、飞书后台配置 5 步、安全边界 |
| `docs/mobile-app-spec.md` | 本方案 |
| `api_server.py` | M0 后端安全层：移动端鉴权、配置补丁/版本/回滚、审计、掩码、设备 CRUD、system health、twin scene |
| `.local-tools/m0_test.py` | M0 回归测试（TestClient，41 项断言，隔离临时 data 目录） |
| `data/`（运行时生成，已 gitignore） | `mobile_auth.json` 账号与 JWT 密钥、`config_state.json` 版本与快照、`audit.jsonl` 审计、`mobile_admin_credentials.txt` 初始密码 |


---

## 16. M1 实现现状（2026-11-12）

### 已完成
- Flutter 3.50 / Dart 3.14，`package:material_ui`（Flutter 3.50 起 `flutter/material.dart` 已废弃），零第三方运行时依赖。
- 主题：`mobile/lib/theme/pulse_theme.dart`（PulseColors / PulseRadius / PulseShadow / PulseText / pageGradient / accentGradient / avatarGradient / insightBarGradient / sparkArea），数字统一 tabular figures。
- 六屏：总览（脉搏环 + 4 指标 + AI 洞察 + 最新报警）、AI 助手（上下文 chips + 结论卡 + 24h 趋势 + 工具轨迹 + 分析 + 输入栏）、设备（列表/地图/巡检 segment + 状态光晕卡 + 车间地图 + 扫码入口）、报警（筛选 + 时间线 + 推送开关 + AI 复盘 + 近 7 天）、我的（用户 + 公网服务器 + 配置组 + 推送 + 运维工具）、数字孪生（等距占位场景 + 热点标签 + 缩放 + 底部数据 sheet）。
- 导航：`RootShell` 用 `IndexedStack` 保活 4 个 Tab，固定悬浮 dock，中央 AI 光球 push 全屏 AI 页。
- 数据：`mobile/lib/data/mock_data.dart` 全量中文 mock（设备、报警、AI 结构化回答、近 7 天报警、AI 洞察/复盘文案），便于 M2 逐项替换成 API。

### 构建与验收
- `flutter analyze` 0 issue；`flutter test` 2/2（首屏文案 + dock 切 4 Tab）。
- `app-debug.apk` 174.3 MB；`--split-per-abi` release：arm64 15.7 MB / armeabi-v7a 13.5 MB / x86_64 17.0 MB；包名 `com.pulse.pulse_mobile`、minSdk 24、targetSdk 36。
- 视觉：`flutter build web` + Chromium 390×844 dpr3 截六屏，拼图 `output/mobile-mockups/app-screens-board.png`；本轮据此修掉 6 个真实布局/绘制问题（详见 README「构建验证结果」）。

### M1 明确没做（M2 处理）
- 登录页 / Token 存储 / 401 拦截器 / 401 后跳登录（M0 后端接口已就绪：`POST /api/mobile/login`、`GET /api/mobile/bootstrap`、`GET /api/mobile/config/schema`、`GET /api/system/health`、`GET /api/twin/scene`、设备 CRUD、配置 PATCH + 版本回滚 + 审计）。
- mock → 真实 API（总览指标、设备列表、报警、AI 对话 REST+WS、设置项）。
- 数字孪生：M1 为 `CustomPainter` 等距示意（可缩放，不可旋转）；M2 用 WebView 承载 `output/mobile-mockups/twin-screen.html` 这套 Three.js 场景（真实 GLB），JS bridge 传 token 与选中设备。
- 推送（前台 WS + 飞书兜底 + 厂商通道）、扫码（`mobile_scanner`）、语音输入、鸿蒙 4 真机验证、release 正式签名（当前用 debug key）、应用图标/启动图。

---

## 17. M2 实现现状（2026-11-12）

M2 目标：飞书扫码登录 + App 接真实 API + 数字孪生 WebView。当前状态：**代码全部落盘并通过静态检查 / 单测 / Web 渲染验收**，APK 正在做最后一轮 release 构建。

### 17.1 登录方式（飞书扫码，账号密码兜底）
- 后端 3 个公开接口（时序见 `docs/m2-backend-notes.md`）：`GET /api/mobile/feishu/start` 返回 `authorize_url` + `state`（限流 10/60s，state 5 分钟有效）；飞书回调 `GET /api/mobile/feishu/callback` 用 code 换 open_id/name/avatar → 白名单校验 → 签发 JWT，页面提示「登录成功，请返回手机」；App 用 `POST /api/mobile/feishu/poll {state}` 拿一次性票据（60s 有效、取走即失效）。
- 白名单：`feishu_login_allowed_open_ids`；首位登录者可 bootstrap 为 admin，其余需管理员在网页端加白名单（`GET/POST /api/mobile/feishu/allowlist`，写入 `config.json` + `data/mobile_auth.json` 并记审计）。
- App 侧：登录页「使用飞书登录」→ 全屏 WebView 打开授权页 → 监听 `/api/mobile/feishu/callback` 后按 2s 轮询 poll → 拿到 token 写入 `shared_preferences`，`AuthGate` 切到主界面；主框架加载失败 / denied / expired 都有中文提示。局域网调试可用同页的「管理员账号登录」（`POST /api/mobile/login`）。

### 17.2 App 架构（mobile/lib）
| 模块 | 文件 | 职责 |
|---|---|---|
| 网络 | `core/api_client.dart` | `package:http`（Web 与 Android 同一套代码），BaseUrl 归一化（补 https、去尾斜杠），Bearer 注入，`ApiException(statusCode,isUnauthorized,isNetwork)` |
| 会话 | `core/session.dart` | token/用户/服务器地址持久化（`pulse.token`/`pulse.user_json`/`pulse.base_url`），启动 `bootstrap()` + 后台 `refreshMe()`，401 自动登出并提示「登录已过期」 |
| 实时数据 | `core/live_data.dart` | 15s 轮询 `GET /api/twin/overview` + `WS /ws/sensor?token=`（sensor/alert 事件即时刷新，断线 10s 重连）；`healthScore` 由在线率/未处理/严重/数据源折算 35–99 |
| 映射 | `core/live_view.dart` | 后端 JSON → UI 模型（指标/设备/报警/洞察文案）；无数据统一「暂无」，折线用按 key 派生的确定性波形占位 |
| 门禁 | `app.dart` AuthGate | booting→Splash、未登录→LoginScreen、已登录→RootShell（进入即 `PulseData.start()`，退出 stop） |

### 17.3 六屏接真数据
- 总览：脉搏环=健康分，4 指标来自 `plant`，AI 洞察与最新报警取自 `alerts`/`source`，数据源离线显示琥珀 chip。
- 设备：真实 7 台设备（列表/地图/巡检 segment），无设备级传感器时卡片显示「暂无实时数据 · 车间级指标见总览」。
- 报警：`alerts.items` 分级时间线 +「处理」调用 `POST /api/alerts/{id}/handle`；近 7 天图表在后端无按天聚合时按总数缩放，0 条显示「近 7 天暂无报警」。
- AI 助手：`POST /api/agent/chat` 真对话（Orchestrator 耗时、工具 chips、Markdown 渲染见 17.4），空态给 3 条建议问题。
- 我的：真实用户/角色/服务器/延迟，配置项提示「首期 App 只做查看 / 报警 / AI」，退出登录二次确认。
- 数字孪生：WebView 打开 `{baseUrl}/mobile/twin?token=…`，承载 Three.js 真实 GLB 场景；`JavaScriptChannel('FlutterBridge')` 接 `twin:back` 返回；加载中遮罩、主框架错误提示；Flutter Web 预览下用说明卡代替（WebView 在 Web 无实现）。

### 17.4 AI 对话链路（本轮修的两个真问题）
1. **工具 chips 永远为空**：后端 `tool_calls` 返回字符串数组，App 原按 `item['tool']` 取值 → 改为兼容 `Map` 与字符串并去重。
2. **qwen3 thinking 让一次问答 100s+**：`agents/llm_provider.py` 的 Ollama 请求统一加 `think: False`（模型不支持时回退重试）；`/api/agent/chat` 实测 8.7–10.4s。

同时收紧提示词：无实时传感器数据时 alarm/sensor agent 只能说明「当前没有实时上报、建议检查网关与传感器」，**不得**推断设备故障或给出停产建议；降级文案不再只输出一行标题。
App 侧新增 `widgets/reply_text.dart` 轻量 Markdown（加粗、列表、`###` 标题、整行加粗小标题），回复正文不再显示原始 `**` 与 `###`。

### 17.5 验收
| 检查 | 结果 |
|---|---|
| `flutter analyze` | No issues found |
| `flutter test` | 8/8（JSON→Snapshot→LiveView 映射、健康分、空态、登录页、总览/报警空态、Markdown 渲染） |
| Web 渲染（同一套 Dart） | `output/mobile-mockups/m2-*.png` 六张 1170×2532；拼图 `m2-screens-board.png` |
| 真实 API | 登录、overview、sensor WS、alerts handle、agent chat、twin 页面全部走本机 uvicorn 实测 |
| release APK | `--split-per-abi` OK：armeabi-v7a 15.3 MB / arm64-v8a 17.5 MB / x86_64 18.8 MB（比 M1 增加 webview_flutter / shared_preferences / http 原生依赖） |

### 17.6 M2 仍未做
- 真机 / 鸿蒙 4 安装验证（当前只有 Web 渲染 + APK 构建验证）。
- 推送通道：App 前台「报警推送」开关目前只影响本地提示，服务端仍是飞书 webhook 兜底；厂商通道（华为/小米/极光）留到 M4。
- 扫码接入设备、语音输入、release 正式签名、应用图标/启动图。
- M3 部署：已产出 `deploy/frp/`（云 frps 安装脚本、Windows frpc 与后端开机自启脚本、隧道看门狗）、`deploy/nginx/pulse.ainavi.online.conf`、`docs/deploy-frp-local-engine.md`；架构为云入口 + 本机引擎（Caddy 方案废弃）。


