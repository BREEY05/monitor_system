#!/usr/bin/env bash
# PULSE · 云服务器一键安装 frps（公网入口侧）
#
# 作用：
#   1. 下载 frp 最新 release 的 frps 到 /usr/local/bin/frps
#   2. 生成 /etc/frp/frps.toml（随机 token，只开放 18000 一个远端端口）
#   3. 注册并启动 systemd 服务 frps
#
# 用法（root）：
#   sudo bash deploy/frp/install-frps.sh
#
# 之后到云控制台安全组放行 TCP 7000，把打印出来的 token 填到 Windows 的 frpc 配置里。

set -euo pipefail

FRP_ETC=/etc/frp
FRP_BIN=/usr/local/bin/frps
FRP_UNIT=/etc/systemd/system/frps.service
FALLBACK_VERSION=v0.72.0

log()  { printf '\n\033[1;36m[frps]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[frps] %s\033[0m\n' "$*"; }
die()  { printf '\n\033[1;31m[frps] %s\033[0m\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "请用 root 运行：sudo bash deploy/frp/install-frps.sh"
command -v curl >/dev/null 2>&1 || die "缺少 curl：apt-get update && apt-get install -y curl"
command -v systemctl >/dev/null 2>&1 || die "没有 systemd，请手动安装 frps"

case "$(uname -m)" in
  x86_64|amd64)  ARCH=amd64 ;;
  aarch64|arm64) ARCH=arm64 ;;
  *) die "不支持的架构：$(uname -m)" ;;
esac

log "检测最新 frp 版本…"
VERSION="$FALLBACK_VERSION"
if command -v python3 >/dev/null 2>&1; then
  DETECTED=$(curl -fsSL --max-time 10 https://api.github.com/repos/fatedier/frp/releases/latest 2>/dev/null \
    | python3 -c 'import json,sys; print(json.load(sys.stdin).get("tag_name",""))' 2>/dev/null || true)
  if [ -n "$DETECTED" ]; then VERSION="$DETECTED"; fi
fi
VER=$(printf '%s' "$VERSION" | sed 's/^v//')
FNAME="frp_$VER""_linux_$ARCH.tar.gz"
DIRNAME="frp_$VER""_linux_$ARCH"
log "使用版本：$VERSION（linux/$ARCH）"

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
URL="https://github.com/fatedier/frp/releases/download/$VERSION/$FNAME"

log "下载 $URL"
if ! curl -fL --retry 3 --retry-delay 2 --connect-timeout 15 -o "$TMP/frp.tar.gz" "$URL"; then
  cat >&2 <<EOF

下载失败。可以换镜像重试，例如：
  curl -fL -o /tmp/frp.tar.gz 'https://ghfast.top/$URL'
  tar -xzf /tmp/frp.tar.gz -C /tmp
  sudo install -m 0755 /tmp/$DIRNAME/frps /usr/local/bin/frps
然后重新运行本脚本（脚本会跳过下载、直接生成配置）。
EOF
  die "frp 下载失败"
fi

tar -xzf "$TMP/frp.tar.gz" -C "$TMP"
[ -f "$TMP/$DIRNAME/frps" ] || die "压缩包结构异常，未找到 frps"
install -m 0755 "$TMP/$DIRNAME/frps" "$FRP_BIN"

mkdir -p "$FRP_ETC"
TOKEN=""
if [ -f "$FRP_ETC/frps.toml" ]; then
  TOKEN=$(sed -n 's/^auth\.token = "\(.*\)"$/\1/p' "$FRP_ETC/frps.toml" | head -n1)
  log "已存在 $FRP_ETC/frps.toml，保留原配置"
else
  TOKEN=$(openssl rand -hex 24 2>/dev/null || head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n')
  cat > "$FRP_ETC/frps.toml" <<EOF
# PULSE · frps（公网入口侧）—— 由 deploy/frp/install-frps.sh 生成
bindAddr = "0.0.0.0"
bindPort = 7000

auth.method = "token"
auth.token = "$TOKEN"

# 只允许分配 18000 一个远端端口
allowPorts = [{ start = 18000, end = 18000 }]

# 隧道落地端口只监听本机，仅 nginx 可访问
proxyBindAddr = "127.0.0.1"

# 强制客户端走 TLS
transport.tls.force = true

log.to = "console"
log.level = "info"
EOF
  chmod 600 "$FRP_ETC/frps.toml"
  log "已生成 $FRP_ETC/frps.toml"
fi

if [ ! -f "$FRP_UNIT" ]; then
  cat > "$FRP_UNIT" <<'UNIT_EOF'
[Unit]
Description=frp server (PULSE public entry)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/bin/frps -c /etc/frp/frps.toml
Restart=always
RestartSec=3
LimitNOFILE=1048576
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
UNIT_EOF
  log "已写入 $FRP_UNIT"
fi

systemctl daemon-reload
systemctl enable frps >/dev/null 2>&1 || true
systemctl restart frps
sleep 1

if systemctl is-active --quiet frps; then
  log "frps 运行中"
else
  journalctl -u frps -n 30 --no-pager || true
  die "frps 启动失败，请看上面的日志"
fi

PUBLIC_IP=$(curl -fsS --max-time 5 https://api.ipify.org 2>/dev/null || echo "81.70.92.137")

echo
log "监听端口："
ss -lntp 2>/dev/null | grep -E ':7000|:18000' || warn "未看到 7000，请检查防火墙/安全组"
echo
cat <<EOF
────────────────────────────────────────────────────────────
云服务器侧已完成。下面这些信息请抄到 Windows 的 frpc 配置里：

  服务器地址（frps）：$PUBLIC_IP
  控制端口（frps）  ：7000
  鉴权 token        ：$TOKEN
  远端端口（默认）  ：18000（frps 只监听 127.0.0.1，nginx 反代到这里）

还需要做两件事：
  1) 云控制台安全组放行 TCP 7000（80/443 保持现状）
  2) 部署 nginx 站点：
       sudo cp deploy/nginx/pulse.ainavi.online.conf /etc/nginx/sites-available/pulse.ainavi.online
       sudo ln -sf /etc/nginx/sites-available/pulse.ainavi.online /etc/nginx/sites-enabled/
       sudo nginx -t && sudo systemctl reload nginx
     然后签发证书：
       sudo certbot --nginx -d pulse.ainavi.online --redirect

Windows 侧（在你电脑上，管理员 PowerShell）：
  powershell -ExecutionPolicy Bypass -File deploy\frp\install-frpc.ps1 -ServerAddr $PUBLIC_IP -Token $TOKEN
────────────────────────────────────────────────────────────
EOF
