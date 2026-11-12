# PULSE · 本机引擎 + frp 公网入口部署指南

> 适用：**AI 与数据留在自己电脑**，只要公网能访问。云服务器 2 核 1.9G 不够跑 Ollama，所以它只做「公网入口」。
>
> 如果你更想「全部部署到云服务器」，看 `docs/deploy-ainavi.md`（**已不采用**，本机没有公网 IP 时那条路需要把服务搬上云）。

## 0. 架构

```
手机 App（HTTPS）┐
                ├─► 云服务器 81.70.92.137
外部浏览器（HTTPS）┘   nginx :443（TLS 终止，Let's Encrypt）
                        │  proxy_pass 127.0.0.1:18000
                        ▼
                     frps :7000（云）
                        ▲  反向长连接（由本机主动外连，无需公网 IP、不改路由器）
                        │
                     frpc（你的 Windows 电脑，开机自启）
                        │
                        ▼
                     127.0.0.1:8000  uvicorn api_server.py
                     ├─ MySQL / SQLite
                     ├─ 传感器数据 / Agent / RAG
                     └─ Ollama（RTX 4060 本地推理）
```

要点：

- 数据、AI 交互全部在本机，**不出内网**；云上只转发字节。
- 云只装 nginx + frps（约 20MB 内存），不装 Python / MySQL / Ollama。
- 后端代码不用改：`api_server.py` 仍然监听 `127.0.0.1:8000`，App 服务器地址仍然是 `https://pulse.ainavi.online`。
- 飞书回调 `https://pulse.ainavi.online/api/mobile/feishu/callback` 也走同一条隧道，不用改后台配置。
- 隧道断开 / 电脑关机时，nginx 返回「本地引擎离线」页（HTTP 503），不会看到 nginx 默认 502。

代价（必须接受）：

1. **电脑必须常开且不休眠**，否则公网全挂。
2. 体验受**家宽/公司网上行带宽**影响（API JSON 很小；3D GLB 共约 1MB，首次加载稍慢）。
3. 公网暴露 = 必须保留 App 鉴权（JWT + 飞书白名单已经做了，别关）。
4. 本机模型质量取决于显卡：RTX 4060 8G 建议 `qwen3:8b`（q4 量化，约 5GB 显存）。

---

## 1. 前置检查

云服务器（Ubuntu 24.04，已有 nginx 占用 80/443）：

```bash
# 域名已解析（应该都是 81.70.92.137）
getent hosts pulse.ainavi.online
nginx -v && systemctl is-active nginx
ss -lntp | grep -E ':80|:443|:7000|:18000'
```

需要用户操作：

- [ ] 云控制台安全组**入站放行 TCP 7000**（frp 控制端口）；80/443 保持现状。
- [ ] 不要在云上装 Caddy / Docker / Ollama（会和现有 nginx 抢 443，2G 内存也跑不动）。
- [ ] 电脑侧：Windows 电源计划设为「从不睡眠」，硬盘不休眠。

---

## 2. 云服务器：安装 frps

```bash
cd /opt
sudo git clone https://github.com/BREEY05/monitor_system.git pulse-deploy
cd pulse-deploy
git pull            # 已有仓库就更新
sudo bash deploy/frp/install-frps.sh
```

脚本会：下载 frp 最新版 → 安装 `/usr/local/bin/frps` → 生成 `/etc/frp/frps.toml`（随机 token，只允许 18000 一个远端端口，隧道落地端口只绑 `127.0.0.1`）→ 注册并启动 `frps`。

脚本结束时打印：

```
服务器地址（frps）：81.70.92.137
控制端口（frps）  ：7000
鉴权 token        ：<24 字节随机串>   ← 抄下来，第 5 步要用
远端端口（默认）  ：18000
```

验证：

```bash
systemctl status frps --no-pager
ss -lntp | grep 7000          # frps 监听 0.0.0.0:7000
curl -s http://127.0.0.1:18000/api/mobile/ping   # 现在应该连不上（隧道还没连）
```

> 重新运行脚本是安全的：已有 `frps.toml` 会保留 token。

---

## 3. 云服务器：nginx 站点 + 证书

```bash
# 1) 证书工具（这台机器之前没装 certbot）
sudo apt-get update
sudo apt-get install -y certbot python3-certbot-nginx

# 2) 站点配置（只放 pulse 子域名，不动 ainavi.online 主站）
cd /opt/pulse-deploy
sudo cp deploy/nginx/pulse.ainavi.online.conf /etc/nginx/sites-available/pulse.ainavi.online
sudo ln -sf /etc/nginx/sites-available/pulse.ainavi.online /etc/nginx/sites-enabled/pulse.ainavi.online
sudo nginx -t && sudo systemctl reload nginx

# 3) 签证书（certbot --nginx 会自动复制出 443 server 块并加 HTTP→HTTPS 跳转）
sudo certbot --nginx -d pulse.ainavi.online --redirect
```

验证：

```bash
curl -I https://pulse.ainavi.online          # 现在应是 503 + 「本地引擎离线」页（正常，隧道未连）
sudo certbot renew --dry-run                 # 续期演练
```

> certbot 会改写站点文件（新增 443 块）。以后更新配置时以 `/etc/nginx/sites-available/pulse.ainavi.online` 为准，不要再从仓库覆盖，否则会丢 443 块。

---

## 4. 云服务器（可选但强烈建议）：隧道看门狗

隧道断/电脑关机时，让飞书立刻告诉你，而不是等用户反馈。

1) 飞书群 → 设置 → 群机器人 → 添加「自定义机器人」→ 复制 webhook 地址。

2) 写环境文件：

```bash
sudo tee /etc/pulse-watch.env >/dev/null <<'EOF'
FEISHU_WEBHOOK=https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxxxx
HEALTH_URL=http://127.0.0.1:18000/api/mobile/ping
EOF
sudo chmod 600 /etc/pulse-watch.env
```

3) 安装探测脚本 + systemd timer：

```bash
cd /opt/pulse-deploy
sudo install -m 0755 deploy/frp/tunnel-watch.sh /usr/local/bin/pulse-tunnel-watch
sudo cp deploy/frp/tunnel-watch.service /etc/systemd/system/
sudo cp deploy/frp/tunnel-watch.timer   /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now pulse-tunnel-watch.timer

# 手动跑一次验证（状态从 unknown → down，会发一条「首次探测失败」）
sudo systemctl start pulse-tunnel-watch
journalctl -u pulse-tunnel-watch -n 20 --no-pager
```

行为：每分钟探测一次；**只在状态变化时**发飞书（离线一条、恢复一条），平时静默。

---

## 5. Windows：frpc + 后端开机自启

在**管理员 PowerShell**里（项目目录下）：

```powershell
# 1) 隧道客户端（自动下载 frp、写配置、注册 SYSTEM 开机自启任务 PULSE-frpc；整行复制）
powershell -ExecutionPolicy Bypass -File deploy\frp\install-frpc.ps1 -ServerAddr 81.70.92.137 -Token <第 2 步打印的 token>

# 2) 本机后端开机自启（任务 PULSE-backend，只监听 127.0.0.1:8000；整行复制）
powershell -ExecutionPolicy Bypass -File deploy\frp\install-backend-task.ps1 -Python "D:\anaconda\envs\agent\python.exe" -WorkDir "D:\anaconda\envs\agent\monitor_system"
```

验证：

```powershell
Get-ScheduledTask PULSE-frpc, PULSE-backend | Format-Table TaskName, State
Get-Process frpc
curl.exe http://127.0.0.1:8000/api/mobile/ping        # 本机后端
# 云端视角（应在第 5 步完成后 200）
curl.exe https://pulse.ainavi.online/api/mobile/ping
```

说明：

- 本机**不需要**开防火墙入站：uvicorn 只绑 `127.0.0.1`，frpc 是出站连接。
- `frpc.toml` 在 `C:\pulse\frp\frpc.toml`；日志在前台手动运行时才看得到，平时用任务计划历史。
- 电脑重启后自动恢复：任务计划在登录前（SYSTEM）就启动 frpc 与后端。

### Ollama 开机自启

Ollama Windows 安装后默认「登录时启动」。如果不是，用任务计划加一条：

```powershell
$exe = "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe"
$action = New-ScheduledTaskAction -Execute $exe -Argument "serve"
$trigger = New-ScheduledTaskTrigger -AtStartup
Register-ScheduledTask -TaskName "Ollama" -Action $action -Trigger $trigger -User "SYSTEM" -RunLevel Highest -Force
```

确认：

```powershell
curl.exe http://127.0.0.1:11434/api/tags
```

### 电源设置（关键）

```powershell
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
powercfg /change monitor-timeout-ac 10
powercfg /change disk-timeout-ac 0
```

---

## 6. 飞书后台

- 重定向 URL 保持：`https://pulse.ainavi.online/api/mobile/feishu/callback`
- 应用能力：网页应用；权限 `contact:user.base:readonly`；已发布版本、可用范围包含使用者。
- 第一个飞书登录的用户会成为管理员（写入 `data/mobile_auth.json` 与 `config.json` 的 `feishu_login_allowed_open_ids`），其他人需要在网页端「飞书与通知」里加白名单。

---

## 7. 手机 App

- App 服务器地址填 `https://pulse.ainavi.online`（默认值就是它）。
- 登录方式：飞书扫码（推荐）或管理员账号。
- 之后所有请求都走：手机 → 云 nginx → frp → 本机，数据与 AI 都在本机执行。

---

## 8. 验收清单

| 检查 | 期望 |
|---|---|
| `curl https://pulse.ainavi.online/api/mobile/ping` | 200，JSON 里有 `server`、`config_version` |
| 浏览器打开 `https://pulse.ainavi.online` | 网页端能加载，数据实时 |
| App 登录 | 飞书扫码成功，进总览；无「登录已过期」 |
| App 总览/设备/报警 | 15s 自动刷新；WS 连通（我的页显示「实时通道正常」） |
| App 数字孪生 | 3D 场景 + GLB 模型加载，点击设备出底部数据卡 |
| App AI | 发一条问题，8–20s 返回结构化回答（本机 4060 推理） |
| 断线演练 | 停止 `PULSE-frpc` → 网页/App 变「本地引擎离线」+ 飞书告警；恢复后自动好 |
| 重启电脑 | 不手动启动任何东西，5 分钟内公网自动恢复 |

---

## 9. 本机模型选择（RTX 4060 8G）

| 模型 | 显存 | 速度 | 建议 |
|---|---|---|---|
| `qwen3:8b` | ~5.0–5.8GB | 中 | **首选**，中文与工具调用都够用 |
| `qwen3:4b` | ~2.8GB | 快 | 追求响应速度时用 |
| `qwen3.5:0.8b` | ~1GB | 很快 | 只适合演示，结论质量一般 |

```powershell
ollama pull qwen3:8b
```

切换模型：网页端「设置 → AI 与 Skill → Ollama 模型」下拉选择（列表来自 `GET /api/ollama/models`），保存后 App 对话即生效，**不需要重启后端**。

> 后端已对所有 Ollama 请求设置 `think: false`，否则 qwen3 思考链会让一次问答超过 100 秒。

---

## 10. 日常运维

**开机顺序**：无脑开机即可（任务计划会自动拉起后端 + frpc）；确认 Ollama 已启动。

**更新代码**：

```powershell
cd D:\anaconda\envs\agent\monitor_system
git pull
# 重启后端
Restart-ScheduledTask -TaskName PULSE-backend
```

云上更新（一般只在改 nginx/frp 配置时）：

```bash
cd /opt/pulse-deploy && git pull
sudo nginx -t && sudo systemctl reload nginx
```

**更换 token（怀疑泄露时）**：

```bash
sudo sed -i 's/^auth.token = .*/auth.token = "'$(openssl rand -hex 24)'"/' /etc/frp/frps.toml
sudo systemctl restart frps
grep auth.token /etc/frp/frps.toml     # 复制新 token
```
然后 Windows 上改 `C:\pulse\frp\frpc.toml` 的 `auth.token`，再 `Restart-ScheduledTask PULSE-frpc`。

**日志位置**：

- 云：`journalctl -u frps -f`、`journalctl -u pulse-tunnel-watch -f`、`/var/log/nginx/pulse.error.log`
- 本机：任务计划历史、`uvicorn` 输出（前台运行时）

---

## 11. 常见问题

| 现象 | 原因 / 处理 |
|---|---|
| 全站 503「本地引擎离线」 | frpc 没跑 / token 不对 / 本机后端没起 / 电脑休眠。依次查：`Get-Process frpc`、`curl 127.0.0.1:8000/api/mobile/ping`、任务计划状态 |
| 云上 `curl 127.0.0.1:18000` 连不上 | frps 没跑，或 frpc 未连接：`journalctl -u frps -n 50` |
| 502 而不是 503 | nginx 站点文件被 certbot 改过后 `error_page` 丢了：重新对比仓库里的 `deploy/nginx/pulse.ainavi.online.conf` |
| App 一直转圈、网页正常 | WebSocket 被挡：确认 nginx 里有 `Upgrade`/`Connection` 两行；浏览器 F12 看 `/ws/sensor` 是否 101 |
| 飞书扫码后 400/拒绝 | 重定向 URL 不是 `https://pulse.ainavi.online/api/mobile/feishu/callback`，或账号不在白名单（拒绝页会给出 open_id） |
| AI 很慢 / 超时 | 本机显卡被占满或模型太大；换 `qwen3:4b`；后端超时 300s 已放宽 |
| 上传 3D 模型失败 | 模型 > 80MB；nginx `client_max_body_size 100m` 已配 |
| 证书过期 | `sudo certbot renew --dry-run` 检查；系统自带 timer 应自动续 |
| 公网能开但很慢 | 上行带宽瓶颈；3D 首次加载 1MB 属正常，后续可给 `/static/` 加 nginx 缓存 |
| 想让厂房局域网网页端也能开 | 把 `PULSE-backend` 任务的参数改成 `--host 0.0.0.0`（或临时前台 `python -m uvicorn api_server:app --host 0.0.0.0 --port 8000`），再在 Windows 防火墙放行 8000 的局域网入站；公网仍然只走隧道，不会直接暴露 |

---

## 12. 安全清单

- [ ] 云安全组只开 22 / 80 / 443 / 7000；**不要**开 18000、8000、3306。
- [ ] frps 监听 7000 有 token；`/etc/frp/frps.toml` 权限 600。
- [ ] 隧道落地端口 18000 只绑 `127.0.0.1`（`proxyBindAddr`）。
- [ ] 本机 uvicorn 只绑 `127.0.0.1`，靠 frpc 出站，不开入站。
- [ ] App 鉴权不开倒车：`mobile_auth_enabled` 保持 true，飞书白名单只加真实用户。
- [ ] `config.json`（含飞书 secret / MySQL 密码）与 `data/` 不进 git（`.gitignore` 已配）。
- [ ] 定期看 `data/audit` 审计日志（登录、配置变更）。

---

## 附：执行顺序（照着做）

1. 云安全组放行 7000 → 2. 云上 `install-frps.sh` 拿 token → 3. 云上 nginx + certbot → 4.（可选）看门狗 → 5. Windows `install-frpc.ps1` + `install-backend-task.ps1` → 6. 手机 App 指向 `https://pulse.ainavi.online` 登录 → 7. 跑第 8 节验收清单。
