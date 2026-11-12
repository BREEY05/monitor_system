#!/usr/bin/env bash
# PULSE 部署前环境体检（只读，不改任何东西）
# 用法：bash deploy/server-audit.sh     或   sudo bash deploy/server-audit.sh
set +e
echo "===== 1. 系统 ====="
uname -srm
. /etc/os-release 2>/dev/null && echo "$PRETTY_NAME"
echo "内核/发行版如上；虚拟化: $(systemd-detect-virt 2>/dev/null || echo unknown)"
echo "当前用户: $(whoami)  sudo可用: $(sudo -n true 2>/dev/null && echo yes || echo no)"

echo
echo "===== 2. 资源 ====="
echo "CPU 核数: $(nproc)   内存:"; free -h | sed -n '1,2p'
echo "磁盘:"; df -h / | tail -1

echo
echo "===== 3. 网络 ====="
echo "网卡:"; ip -4 -o addr show scope global 2>/dev/null | awk '{print "  " $2 " " $4}'
echo "公网出口 IP: $(curl -s --max-time 6 https://ifconfig.me || curl -s --max-time 6 https://api.ipify.org || echo 获取失败)"
echo "域名解析: pulse.ainavi.online -> $(getent hosts pulse.ainavi.online | awk '{print $1}' | paste -sd, -)"
echo "          ainavi.online       -> $(getent hosts ainavi.online | awk '{print $1}' | paste -sd, -)"

echo
echo "===== 4. 端口占用（80/443/8000/3306/11434/22）====="
ss -lntp 2>/dev/null | awk 'NR==1 || $4 ~ /:(80|443|8000|3306|11434|22)$/'

echo
echo "===== 5. 已装组件 ====="
for c in python3 git caddy nginx mysql mysqld docker ollama node; do
  if command -v $c >/dev/null 2>&1; then
    printf "  %-8s %s\n" "$c" "$(command -v $c)"
  else
    printf "  %-8s 未安装\n" "$c"
  fi
done
python3 -V 2>&1 | sed 's/^/  python3 版本: /'
git --version 2>&1 | sed 's/^/  /'
caddy version 2>/dev/null | sed 's/^/  caddy: /'
nginx -v 2>&1 | sed 's/^/  /'

echo
echo "===== 6. 服务状态 ====="
for s in caddy nginx mysql mysqld docker ollama pulse ssh; do
  st=$(systemctl is-active $s 2>/dev/null)
  en=$(systemctl is-enabled $s 2>/dev/null)
  [ -n "$st" ] && echo "  $s: $st (enabled=$en)"
done

echo
echo "===== 7. 防火墙 ====="
if command -v ufw >/dev/null 2>&1; then echo "ufw:"; sudo ufw status 2>/dev/null || ufw status 2>/dev/null; fi
if command -v firewall-cmd >/dev/null 2>&1; then echo "firewalld:"; sudo firewall-cmd --list-all 2>/dev/null; fi
if command -v iptables >/dev/null 2>&1; then echo "iptables INPUT:"; sudo iptables -S INPUT 2>/dev/null | head -12; fi

echo
echo "===== 8. 现有站点 / 反代 ====="
[ -d /opt ] && ls -1 /opt 2>/dev/null | sed 's/^/  \/opt\//'
[ -d /www/wwwroot ] && echo "  检测到宝塔目录 /www/wwwroot:" && ls -1 /www/wwwroot 2>/dev/null | sed 's/^/    /'
[ -f /etc/caddy/Caddyfile ] && echo "--- /etc/caddy/Caddyfile (前 30 行) ---" && head -30 /etc/caddy/Caddyfile
[ -d /etc/nginx/sites-enabled ] && echo "--- nginx sites-enabled ---" && ls -1 /etc/nginx/sites-enabled 2>/dev/null

echo
echo "===== 9. 外部可达性（本机自测）====="
for u in https://pulse.ainavi.online/api/mobile/ping http://127.0.0.1:8000/api/mobile/ping; do
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 8 "$u")
  echo "  $u -> HTTP $code"
done

echo
echo "===== 体检结束，把这整段输出发回即可 ====="
