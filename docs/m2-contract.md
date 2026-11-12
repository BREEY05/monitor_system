# M2 契约：飞书扫码登录 + 手机端接真实 API（2026-11-12）

> 目标：App 通过 \`https://pulse.ainavi.online\` 访问部署在公网服务器上的本系统，登录方式为飞书扫码/授权，首期范围「看 + 报警 + AI」。

## 0. 环境与前提（用户侧动作）
1. **DNS**：\`pulse.ainavi.online\` A 记录 → \`81.70.92.137\`（ainavi.online 当前解析到的服务器）。
2. **服务器**：80/443 放行；Caddy 自动签 Let's Encrypt 证书（域名已具备，无需 ICP 影响，仅备案合规另说）。
3. **飞书开放平台**（应用 app_id=\`cli_a9…\`，config.json 已配置）：
   - 应用能力 → 添加「网页应用」；
   - 安全设置 → 重定向 URL 增加：\`https://pulse.ainavi.online/api/mobile/feishu/callback\`；
   - 权限：获取用户基本信息（\`contact:user.base:readonly\`）、获取用户 user ID（可选 \`contact:user.employee_id:readonly\`）；
   - 版本管理与发布 → 创建版本并发布（企业内自建应用需管理员审核通过），并把使用者加入可用范围。
4. **后端配置**（config.json 或设置页）：
   - \`mobile_public_base_url\`: \`https://pulse.ainavi.online\`
   - \`feishu_login_enabled\`: true
   - \`feishu_login_allowed_open_ids\`: []（先留空，首个登录者自动成为 admin 并写入，见 §2.3）

## 1. 登录流程图（App ↔ 后端 ↔ 飞书）
\`\`\`
App                      PULSE 后端                        飞书
 |  GET /api/mobile/feishu/start  |                          |
 |----------------------------->| 生成 state（5 分钟 TTL）   |
 |<-- {state, authorize_url} ---|                          |
 | 展示二维码 / 打开飞书  ------------------------------------->| 用户授权
 |                              |<-- GET /api/mobile/feishu/callback?code&state
 |                              |-- POST /open-apis/authen/v1/access_token (app_access_token) --> 换取 UAT + 用户信息
 |                              |-- allowlist 校验 / 建用户 / 发 JWT
 |  POST /api/mobile/feishu/poll {state}（每 2s）              |
 |----------------------------->|                          |
 |<-- {status:"ready", token, user}                            |
 | 保存 token → 进首页；401 时清 token 回登录页                 |
\`\`\`

## 2. 新增后端接口（全部公网可达，无需 token，需限流）

### 2.1 GET /api/mobile/feishu/start
Query: \`redirect\`（可选，默认 \`app\`）。
响应：
\`\`\`json
{
  "state": "32 位随机串",
  "authorize_url": "https://open.feishu.cn/open-apis/authen/v1/index?app_id=...&redirect_uri=...&state=...",
  "expires_in": 300,
  "poll_interval": 2,
  "enabled": true
}
\`\`\`
- 限流：同一 IP 60 秒内最多 10 次，超出 429。
- 若 \`feishu_login_enabled\` 为 false 或 app_id/secret 缺失 → 400 \`{"detail":"飞书登录未配置"}\`。

### 2.2 GET /api/mobile/feishu/callback?code=&state=
- state 不存在/过期 → 返回 HTML 错误页（含「返回 App 重试」提示），不泄露内部信息。
- 成功：用 app_access_token 调 \`POST https://open.feishu.cn/open-apis/authen/v1/access_token\`（body \`{"grant_type":"authorization_code","code":...}\`），取 \`data.open_id / name / avatar_url\`；
- allowlist 校验（见 2.3）→ upsert 用户 → 生成 JWT → 存到 state 的登录票据（一次性，poll 取走后立即失效）→ 返回 HTML 成功页（浅色 PULSE 风格，含「已登录，请返回 App」）。
- 失败（code 无效 / 飞书报错）→ HTML 失败页，state 标记 denied，poll 返回 \`denied\`。

### 2.3 允许名单与首个管理员（bootstrap）
- 存储：\`data/mobile_auth.json\` 的 users 增加 \`feishu_open_id\`、\`avatar_url\`、\`auth_provider:"feishu"\` 字段。
- 允许名单：\`CONFIG["feishu_login_allowed_open_ids"]\`（list[str]）。
- 规则：
  1. open_id 在名单 → 允许，按已有用户或新建 viewer；
  2. 名单为空且系统里还没有 feishu 用户 → **首个登录者成为 admin**，写入名单，审计 \`feishu.bootstrap\`，并在响应/日志中提示「已自动授予管理员，请到设置页核对」；
  3. 其他情况 → 拒绝，HTML 页显示「未授权：请联系管理员加入允许名单」，并给出 open_id（方便管理员复制）。
- 管理员加人：\`POST /api/mobile/feishu/allowlist\`（admin token）body \`{"open_id":"ou_...","display_name":"张三","role":"viewer"}\` → 写名单 + 建用户 + 审计。

### 2.4 POST /api/mobile/feishu/poll
body \`{"state": "..."}\` →
- pending: \`{"status":"pending"}\`
- ready: \`{"status":"ready","token":"...","token_type":"Bearer","expires_in":43200,"user":{...},"server":{...}}\`（一次性，二次取返回 expired）
- denied / expired / error: \`{"status":"denied","message":"..."}\`
- 限流：同 IP 每秒 ≤ 5 次（App 每 2s 一次，正常不会触发）。

### 2.5 公开路径与中间件
\`MOBILE_PUBLIC_PATHS\` 增加：\`/api/mobile/feishu/start\`、\`/api/mobile/feishu/callback\`、\`/api/mobile/feishu/poll\`、\`/api/mobile/ping\`、\`/api/mobile/bootstrap\`、\`/api/mobile/login\`。
\`/api/mobile/feishu/allowlist\` 需 admin token。

### 2.6 GET /mobile/twin（数字孪生 WebView 页）
- 返回 \`static/mobile-twin.html\`（FileResponse，公开）。
- 页面从 URL \`?token=JWT\` 取 token，调用 \`/api/twin/scene\`、\`/api/twin/overview\` 时带 \`Authorization: Bearer\`。
- 只读：旋转/缩放/点击设备，点击后底部 sheet 显示该设备状态与指标（JS 内计算），不写任何数据。
- 复用 \`static/vendor/three/\` 与现有 GLB（\`static/uploads/device_models/\`），手机端相机与 \`output/mobile-mockups/twin-screen.html\` 一致（CAM pos [6.5,10.5,11.5]）。
- 无 token 或 401 → 页面显示「登录已过期」。

## 3. App 使用的既有接口（M0/M1 已有，均可经反代 + Bearer 访问）
| 接口 | 用途 | 关键字段 |
|---|---|---|
| GET /api/mobile/bootstrap | 连接检查（公开） | server.version、auth.token_hours、features |
| GET /api/mobile/me | 当前用户 | user.display_name/role/permissions |
| GET /api/system/health | 总览健康 | status、uptime_seconds、database、sensor、devices{total,running,maintenance,offline}、ai |
| GET /api/twin/overview | 总览+设备页聚合 | plant{temperature,humidity,pressure,vibration,statuses,available,timestamp}、thresholds、devices[{id,name,status,online,risk,alerts{open,latest_at}}]、alerts{open_total,items,by_device}、summary{total,online,alerting,data_online}、source{label,age_seconds,stale} |
| GET /api/devices | 设备列表 | devices[]、selected_device_id、version |
| GET /api/alerts | 报警列表 | [{id,title,time,source,level(danger/warning),detail{type,value,threshold,count,device_id,area},handled}] |
| POST /api/alerts/{id}/handle | 处理报警 | {success, remaining} |
| POST /api/agent/chat | AI 对话（非流式） | {reply, intents[], plan{agent_sequence}, agent_results[], tool_calls[], latency_ms} |
| WS /ws/chat?token= | AI 流式 | 发 {message, agent_mode:true}；收 {type:status|content|done, content/full_reply} |
| WS /ws/sensor?token= | 实时传感/报警 | {type:"sensor",data:{temperature,humidity,pressure,vibration,timestamp,device_id,area,statuses}}；{type:"alert",data:{id,title,level,time,source}} |
| GET /api/twin/scene | 孪生场景 | scene{zones[]}、devices[{id,name,position,rotation,state,model_url}] |

注意：
- 反代会带 \`X-Forwarded-For\`，中间件对所有 \`/api/*\` 强制 JWT（公开路径除外）；WebSocket 用 \`?token=\`。
- 报警广播里的 \`title\` 含 emoji（既有实现），App 侧展示时去除 emoji / 用本地文案映射，保持无 emoji 设计。

## 4. App 侧（Flutter）要求
- 服务器地址：登录页可编辑，默认 \`https://pulse.ainavi.online\`，持久化；支持 http 自签/内网调试（允许明文，仅调试）。
- 登录页：PULSE 浅色风格；「使用飞书登录」→ start → 显示二维码（qr_flutter）+ 6 位用户码不可用（飞书网页登录无 user_code）→ 文案「用飞书扫码，或在手机上直接打开」+ 按钮「打开飞书」；每 2s poll；成功保存 token。
- Token：flutter_secure_storage；401 自动清 token 回登录页。
- 数据层：Repository + 真实 API 替换 mock（总览、设备、报警、AI、孪生），保留 mock 作为离线/异常兜底并显式标注「示例数据」。
- 报警：WebSocket 实时推送 → 应用内顶部横幅 + 报警 tab 红点；不接系统级推送（首期仅飞书 + App 前台）。
- AI：优先 WS 流式，失败回退 /api/agent/chat；展示 reply + agent/tool 轨迹（复用 M1 卡片）。
- 孪生：WebView 打开 \`{base}/mobile/twin?token=...\`；失败/弱网降级为 M1 原生等距示意。

## 5. 验收（M2）
1. \`.local-tools/m2_auth_test.py\`：start/poll/callback（monkeypatch 飞书 HTTP）、allowlist、限流、一次性票据、state 过期，全部通过。
2. \`flutter analyze\` 0 issue、\`flutter test\` 通过（新增登录/数据映射单元测试）。
3. 本机起服务 + Web 构建截图：登录页、总览（真实数据）、报警、AI 对话、孪生 WebView 五张图。
4. 部署文档：DNS、飞书后台、Caddy、systemd、验证 curl 全流程。
