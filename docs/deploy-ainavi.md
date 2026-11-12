# 部署到云服务器（pulse.ainavi.online）

> ⚠️ **本方案已不采用（2026-11-12）**。云服务器只有 2 核 1.9G，跑不动 Ollama，而且 80/443 已被现有 nginx 占用。
> 现行架构：**云 nginx + frps 只做公网入口，后端 / MySQL / Ollama 留在本机**，见 `docs/deploy-frp-local-engine.md`。
> 下文保留作为「全部搬上云」的参考（例如未来换一台能跑模型的服务器）。

目标拓扑：

```
手机 App ── HTTPS ──► Caddy 443 ──► 127.0.0.1:8000 (uvicorn / api_server.py)
                          │
                          └── 自动申请 Let's Encrypt 证书（域名必须已解析到本机）
网页端 ── 局域网 http://内网IP:8000 ──► 同一个服务
```

服务器只开 80/443；8000 只绑 `127.0.0.1`；MySQL / Ollama 不对外网暴露。

---

## 0. 前置条件

- 云服务器：Ubuntu 22.04 / 24.04（Debian 12 同理），已能公网访问 80/443。
- 域名：`pulse.ainavi.online` 的 **A 记录** 指向本机公网 IP（`curl ifconfig.me` 查）。
- 安全组/防火墙：放行 80、443（8000 不要放行）。
- 飞书自建应用：`app_id` / `app_secret`（见第 5 步配置）。

---

## 1. 安装系统依赖

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git caddy
python3 --version   # 需要 3.10+
```

## 2. 拉代码、建运行用户

```bash
sudo useradd --system --create-home --home-dir /home/pulse --shell /usr/sbin/nologin pulse
sudo mkdir -p /opt/pulse && sudo chown pulse:pulse /opt/pulse

# 用 pulse 用户克隆（服务器上建议用只读 deploy key 或 PAT）
sudo -u pulse git clone https://github.com/BREEY05/monitor_system.git /opt/pulse
cd /opt/pulse
```

> 私有仓库：先在 GitHub 生成 Fine-grained token（只读 Contents），clone 时用
> `https://<token>@github.com/BREEY05/monitor_system.git`；后续 `git pull` 同法，或
> `git config credential.helper store` 保存。

## 3. Python 环境与依赖

```bash
sudo -u pulse python3 -m venv /opt/pulse/.venv
sudo -u pulse /opt/pulse/.venv/bin/pip install -U pip
sudo -u pulse /opt/pulse/.venv/bin/pip install -r /opt/pulse/requirements.txt
```

> 国内服务器可加镜像：`-i https://mirrors.aliyun.com/pypi/simple/`。
> 若 LangChain 相关依赖装不上，先确认 Python 版本与 requirements.txt 一致。

## 4. 生成配置（config.json 不入库，需手动创建）

```bash
cd /opt/pulse
sudo -u pulse cp config.example.json config.json
sudo -u pulse python3 - <<'PY'
import json, secrets
p = 'config.json'
c = json.load(open(p, encoding='utf-8'))
# JWT / 会话密钥（务必随机）
c['mobile_public_base_url'] = 'https://pulse.ainavi.online'
c['mobile_auth_enabled'] = True
c['feishu_login_enabled'] = True
# 飞书应用凭据（第 5 步从飞书开放平台复制）
c['feishu_app_id'] = 'cli_xxxxxxxx'
c['feishu_app_secret'] = '填写飞书 app_secret'
# 首期默认 SQLite，够用；要 MySQL 就改 database_backend 为 mysql 并填连接信息
c['database_backend'] = 'sqlite'
json.dump(c, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
print('config.json ok')
PY
```

运行时目录（JWT 密钥、账号、审计、SQLite 都会写这里）：

```bash
sudo -u pulse mkdir -p /opt/pulse/data
sudo -u pulse chmod 700 /opt/pulse/data
```

首次启动会生成管理员账号：`data/mobile_admin_credentials.txt`（用户名 admin + 随机密码），
**登录网页端后请改掉**；它是飞书登录出问题时的兜底入口。

```bash
sudo -u pulse cat /opt/pulse/data/mobile_admin_credentials.txt
```

## 5. 飞书开放平台配置（扫码登录必需）

1. 打开 https://open.feishu.cn/app → 进入你的自建应用。
2. **添加应用能力** → 勾选「网页应用」。
3. **安全设置 → 重定向 URL** 填入（必须完全一致，含协议）：
   ```
   https://pulse.ainavi.online/api/mobile/feishu/callback
   ```
4. **权限管理** → 开通 `contact:user.base:readonly`（读取登录用户 open_id / 姓名 / 头像）。
5. **版本管理与发布** → 创建版本 → 申请发布；把需要使用 App 的同事加进「可用范围」。
6. 把 `app_id` / `app_secret` 写进 `config.json`（第 4 步）。
7. 首个扫码登录的人会**自动成为管理员**（写入 `feishu_login_allowed_open_ids`）；
   其他人扫码若提示「未授权」，用管理员账号在网页端 → 移动端/飞书登录设置里把对方 open_id 加入白名单
   （接口：`GET/POST /api/mobile/feishu/allowlist`，需要 admin token）。

> 审核期间可用管理员账号密码登录 App 调试：登录页展开「管理员账号登录」。

## 6. 启动后端（systemd）

```bash
sudo cp /opt/pulse/deploy/pulse.service /etc/systemd/system/pulse.service
sudo systemctl daemon-reload
sudo systemctl enable --now pulse
sudo systemctl status pulse --no-pager
journalctl -u pulse -n 50 --no-pager
```

本机自测：

```bash
curl -s http://127.0.0.1:8000/api/mobile/ping
# {"ok":true,"server":{...}}
```

## 7. 配 Caddy（自动 HTTPS）

```bash
sudo cp /opt/pulse/deploy/Caddyfile /etc/caddy/Caddyfile
sudo mkdir -p /var/log/caddy && sudo chown caddy:caddy /var/log/caddy
sudo caddy validate --config /etc/caddy/Caddyfile   # 语法检查
sudo systemctl reload caddy
sudo systemctl status caddy --no-pager
```

验证（首次签发证书约 10–30s）：

```bash
curl -sI https://pulse.ainavi.online/api/mobile/ping | head -5
curl -s https://pulse.ainavi.online/api/mobile/ping
```

看到 `200` 与 JSON 即成功；证书可在 `/var/lib/caddy/.local/share/caddy/certificates` 下确认。

## 8. 验收清单

| 检查 | 命令 / 方式 | 期望 |
|---|---|---|
| 健康检查 | `curl -s https://pulse.ainavi.online/api/mobile/ping` | `ok:true` |
| 登录接口保护 | `curl -s -o /dev/null -w "%{http_code}" https://pulse.ainavi.online/api/settings` | `401`（未带 token） |
| 飞书扫码 | App 登录页 →「使用飞书登录」 | 授权后返回 App 并进入首页 |
| 数字孪生 | 设备页 → 地图卡「数字孪生」 | WebView 里出现 3D 车间 |
| AI 对话 | AI 页输入问题 | 8–15s 返回带工具轨迹的结论 |
| 报警 | 网页端设置阈值低于当前值触发 | App 前台弹提示 + 飞书收到消息 |
| 网页端 | 厂区局域网访问 `http://内网IP:8000` | 正常（不影响公网 App） |

## 9. App 指向正式服务器

App 登录页「服务器」填 `https://pulse.ainavi.online`（默认值就是这个），
不需要再改代码；APK 已支持 HTTPS 与局域网 http 调试。

## 10. 更新部署

```bash
cd /opt/pulse
sudo -u pulse git pull --ff-only
sudo -u pulse /opt/pulse/.venv/bin/pip install -r requirements.txt   # 依赖有变化时
sudo systemctl restart pulse
```

## 11. 可选：Ollama（本地大模型）

不用 Ollama、改用云端 API 时：`agent_api_backend` 改为 `openai` 并填 `agent_api_url/model/key`。

本地跑 Ollama：

```bash
curl -fsSL https://ollama.com/install.sh | sh
sudo systemctl enable --now ollama
ollama pull qwen3.5:0.8b
```

Ollama 默认只监听 127.0.0.1:11434，保持默认即可（后端同机访问）。
`config.json` 里 `ollama_enabled: true`、`ollama_model: "qwen3.5:0.8b"`。
注意 CPU 机器上单次问答约 10–30s，建议至少 4 核 8G。

## 12. 常见问题

| 现象 | 原因 / 处理 |
|---|---|
| Caddy 申请证书失败 | 域名未解析到本机 / 80 端口未放行 / 证书签发频率限制，看 `journalctl -u caddy -n 50` |
| `/api/mobile/ping` 502 | 后端没起来：`systemctl status pulse`；或 8000 被占用 |
| App 登录后立刻退出 | 服务器 `data/mobile_auth.json` 被删导致 JWT 密钥变化；重新扫码登录即可 |
| 飞书扫码停在浏览器 | 回调 URL 与飞书后台不一致，或 `mobile_public_base_url` 不是 `https://pulse.ainavi.online` |
| 3D 模型不显示 | 仓库不含 `static/uploads/`（模型不入库），在网页端设置页重新上传 GLB |
| 上传模型报 413 | Caddy `request_body max_size` 已设 100MB，确认改的是生效配置并 reload |
| AI 很慢 | 关闭 thinking 已在代码里；仍慢则换云端 API 或加 CPU |
