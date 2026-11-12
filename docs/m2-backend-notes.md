# M2 后端实现说明（飞书扫码登录 + 手机孪生页）

更新时间：2026-11-12　对应代码：api_server.py（飞书登录块约 470 行）、static/mobile-twin.html

## 1. 本轮新增能力

| 能力 | 接口 | 说明 |
| --- | --- | --- |
| 发起扫码登录 | GET /api/mobile/feishu/start | 生成 300s 有效 state，返回飞书授权 URL（网页授权 code 流） |
| 授权回调 | GET /api/mobile/feishu/callback | 校验 state → 用 code 换 open_id → 白名单校验 → 写入 60s 一次性票据 → 返回浅色结果页 |
| App 轮询取 token | POST /api/mobile/feishu/poll | pending / ready / denied / expired / error；ready 时返回 JWT（一次性） |
| 白名单管理 | GET/POST /api/mobile/feishu/allowlist | 仅 admin；读写 config.json 的 feishu_login_allowed_open_ids，并同步 mobile_auth.json 用户 |
| 手机孪生页 | GET /mobile/twin | 返回 static/mobile-twin.html（no-store），页面用 ?token= 调 /api/twin/* |
| 健康检查（M0） | GET /api/system/health | 供 App 服务器连接页探测 |

公开路径（不需要 Bearer）：/api/mobile/feishu/start、/api/mobile/feishu/callback、/api/mobile/feishu/poll（以及 M0 的 bootstrap/login/refresh 等）。

## 2. 登录时序

```
App                        后端                          飞书开放平台
 |--GET /feishu/start------>|                                  |
 |<--authorize_url,state----|                                  |
 |  打开浏览器/WebView 授权页 ---------------------------------->|
 |                          |<----GET /feishu/callback?code&state
 |                          |--POST authen/v1/access_token---->|
 |                          |<---open_id,name,avatar_url-------|
 |                          |--白名单校验 + 签 JWT + 存票据     |
 |<--GET /feishu/callback 结果页（手机浏览器）                   |
 |--POST /feishu/poll------>| (2s 间隔，最多 300s)              |
 |<--token + user + server--|                                  |
 |--Authorization: Bearer-->| 之后所有 /api/mobile/* 与 /api/twin/*
```

- 票据一次性：poll 返回 ready 后状态即置为 expired，重复 poll 返回 expired。
- 首登引导：当 mobile_auth.json 中还没有任何飞书用户且白名单为空时，第一个扫码用户自动成为 admin 并写入白名单（同时记 audit: feishu.bootstrap）。之后只允许白名单用户。
- 拒绝页会显示 open_id，方便管理员复制到白名单。

## 3. 配置项（config.json）

| 键 | 默认值 | 说明 |
| --- | --- | --- |
| mobile_public_base_url | https://pulse.ainavi.online | 飞书回调地址的基址，必须与飞书后台 redirect URL 完全一致 |
| feishu_login_enabled | true | 关闭后 start 返回 400 |
| feishu_login_allowed_open_ids | [] | 允许登录的飞书 open_id 列表 |
| feishu_app_id / feishu_app_secret | 已有 | 复用现有飞书应用凭证 |
| mobile_token_hours | 12 | JWT 有效期 |

飞书后台需要（用户操作，本机无法完成）：
1. 应用开启「网页应用」能力；
2. 重定向 URL 添加 https://pulse.ainavi.online/api/mobile/feishu/callback；
3. 权限添加 contact:user.base:readonly（读取姓名/头像）；
4. 创建版本并发布，可用范围包含使用者；
5. 域名 pulse.ainavi.online 解析到 81.70.92.137 并由 Caddy 提供 HTTPS。

## 4. 本地测试与 Mock

测试钩子：环境变量 PULSE_FEISHU_MOCK=1
- _feishu_app_access_token() 直接返回 mock-app-access-token；
- _feishu_exchange_code() 解析 code 形如 `mock:<open_id>:<name>:<avatar>`，不访问飞书。

回归脚本：`.local-tools/m2_auth_test.py`（TestClient，39 项，全部 PASS）
覆盖：start 字段/URL 转义、pending→ready、一次性票据、me 返回 avatar_url/auth_provider、白名单拒绝与加入后放行、admin/viewer 权限、重复回调、未知 state、取消授权、关闭开关、twin 页面、限流。

孪生页真机链路验证：`.local-tools/twin_webview_shot.mjs`（Playwright msedge 390×844 dsf3）
- 用 mock 登录拿真实 JWT → 打开 /mobile/twin?token=... → 等待 GLB 加载 → 截图；
- 输出 output/mobile-mockups/app-twin-webview.png、app-twin-webview-sheet.png；
- 断言：7 个设备标签、分区 chips（泵组区 3 / 装配区 3 / 配电区 1）、无 4xx、无 console error。

## 5. 手机孪生页（static/mobile-twin.html）

- 只读：设备按 config 的 position/rotation 摆放，GLTFLoader 加载 /static/uploads/device_models/*.glb，加载失败退化为白盒占位；
- 交互：OrbitControls 单指旋转/双指缩放、+/−/复位按钮、分区 chips 过滤、点击模型或标签选中设备；
- 标签：HTML 气泡每帧投影定位，含碰撞避让（同列上移），z-index 低于底部 sheet；
- 底部 sheet：状态、station/id、温度/湿度/振动（车间级实时值，超阈值变色）、数据来源、风险等级、未处理报警、最近报警、阈值、以及「设备级/车间级」说明；无实时数据时显示「暂无」；
- WebView 返回：优先 window.FlutterBridge.postMessage('twin:back')，否则 history.back；
- 异常：无 token/401 → 登录过期遮罩；接口失败 → 加载失败遮罩。

已知限制：
- 孪生页依赖 /static/vendor/three 本地 vendor（已存在），不访问 CDN；
- 无实时 WS 更新（页面打开时拉一次 + 依赖用户重新进入），M2 App 侧在原生页面用 /ws/sensor；孪生页 M3 再评估加 WS；
- 模型最大 80MB 限制沿用后端 /api/device/model，移动端只读不提供上传。

## 6. 安全边界

- JWT：HS256，secret 存 data/mobile_auth.json（已 gitignore）；移动端 token 12h 过期；
- 反向代理场景：中间件对带 X-Forwarded-For 的 /api/* 强制 token；/ws/* 需 ?token= 或 Sec-WebSocket-Protocol；
- 飞书登录限流：start 10/60s/IP、poll 5/1s/(IP+state)、callback 30/60s/IP；
- 审计：feishu.login / feishu.bootstrap / feishu.denied / feishu.allowlist_add 均写 _audit；
- 设置页 secret 字段仍只写不回显。

## 7. 待办

- Flutter：登录页接 start+poll、token 持久化、401 拦截、mock→真实 API、孪生 WebView、WS 报警；
- 部署产物：Caddyfile / systemd / docker-compose / docs/deploy-ainavi.md；
- 用户侧：飞书后台 4 项配置 + DNS + 服务器 SSH 凭据；
- 真实飞书联调（本地只能 mock）。
