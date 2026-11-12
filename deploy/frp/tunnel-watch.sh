#!/usr/bin/env bash
# PULSE · 隧道看门狗（跑在云服务器上，每分钟一次）
#
# 探测 http://127.0.0.1:18000/api/mobile/ping（= 隧道落地端口 = 你电脑上的后端）
# 状态发生变化时发飞书告警；平时静默。
#
# 安装见 docs/deploy-frp-local-engine.md「五、云服务器：隧道告警」

set -uo pipefail

ENV_FILE=/etc/pulse-watch.env
if [ -f "$ENV_FILE" ]; then
  # shellcheck disable=SC1090
  . "$ENV_FILE"
fi

HEALTH_URL="$HEALTH_URL"
[ -z "$HEALTH_URL" ] && HEALTH_URL="http://127.0.0.1:18000/api/mobile/ping"
FEISHU_WEBHOOK="$FEISHU_WEBHOOK"
STATE_DIR="$STATE_DIR"
[ -z "$STATE_DIR" ] && STATE_DIR=/var/lib/pulse-watch

mkdir -p "$STATE_DIR" 2>/dev/null || true
STATE_FILE="$STATE_DIR/state"

if [ -f "$STATE_FILE" ]; then
  PREV=$(cat "$STATE_FILE" 2>/dev/null || echo unknown)
else
  PREV=unknown
fi

if curl -fsS --max-time 6 "$HEALTH_URL" >/dev/null 2>&1; then
  CUR=up
else
  CUR=down
fi

logger -t pulse-watch "probe=$CUR prev=$PREV" 2>/dev/null || true

[ "$CUR" = "$PREV" ] && exit 0
printf '%s\n' "$CUR" > "$STATE_FILE"

NOW=$(date '+%Y-%m-%d %H:%M:%S %Z')

send_feishu() {
  local text="$1"
  [ -z "$FEISHU_WEBHOOK" ] && return 0
  python3 - "$FEISHU_WEBHOOK" "$text" <<'PY' >/dev/null 2>&1 || true
import json, sys, urllib.request
hook, text = sys.argv[1], sys.argv[2]
body = json.dumps({"msg_type": "text", "content": {"text": text}}).encode("utf-8")
req = urllib.request.Request(hook, data=body, headers={"Content-Type": "application/json"})
urllib.request.urlopen(req, timeout=8).read()
PY
}

if [ "$CUR" = "down" ]; then
  if [ "$PREV" = "unknown" ]; then
    send_feishu "⚠️ PULSE 隧道首次探测失败
时间：$NOW
公网入口正常，但拿不到本机后端响应。
请检查：电脑是否开机 / frpc 计划任务 / 本机 8000 端口。"
  else
    send_feishu "⚠️ PULSE 本地引擎离线
时间：$NOW
公网入口仍在线，但隧道或本机后端不可达，App 与网页会看到「本地引擎离线」页。
请检查：电脑是否开机/休眠、frpc 计划任务、uvicorn 是否在 127.0.0.1:8000。"
  fi
else
  if [ "$PREV" = "down" ]; then
    send_feishu "✅ PULSE 本地引擎已恢复
时间：$NOW
公网访问已恢复：https://pulse.ainavi.online"
  fi
fi
