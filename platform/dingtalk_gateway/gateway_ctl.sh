#!/usr/bin/env bash
# 钉钉网关 launchd 管理：安装 / 启停 / 状态 / 日志
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
LABEL="com.yaahlan.dingtalk-gateway"
PLIST_SRC="$DIR/config/com.yaahlan.dingtalk-gateway.plist.example"
PLIST_DST="$HOME/Library/LaunchAgents/${LABEL}.plist"
UID_NUM="$(id -u)"
DOMAIN="gui/${UID_NUM}"
SERVICE="${DOMAIN}/${LABEL}"
LOG_DIR="$DIR/logs"

usage() {
  cat <<EOF
用法: $0 <install|uninstall|start|stop|restart|silent-restart|status|logs|health|health-deep>

  install         安装 launchd 并启动（开机自启 + 崩溃重启）
  uninstall       停止并移除 launchd
  start           启动服务
  stop            停止服务
  restart         重启服务（推送启停通知）
  silent-restart  重启服务（不推送启停通知）
  status     查看运行状态
  logs       跟踪 gateway.log
  health     Bridge / MOA / 各 Cookie·Token 有效性检查
  health-deep  同上，且 server 未运行时做 SDK pong
EOF
}

ensure_logs() {
  mkdir -p "$LOG_DIR"
}

install_service() {
  ensure_logs
  pkill -f "dingtalk_gateway/bot_echo.py" 2>/dev/null || true
  pkill -f "dingtalk_gateway/start_gateway.sh" 2>/dev/null || true
  cp "$PLIST_SRC" "$PLIST_DST"
  launchctl bootout "$DOMAIN" "$PLIST_DST" 2>/dev/null || true
  launchctl bootstrap "$DOMAIN" "$PLIST_DST"
  launchctl enable "$SERVICE" 2>/dev/null || true
  launchctl kickstart -k "$SERVICE"
  echo "[OK] 已安装并启动 $LABEL"
  echo "     plist: $PLIST_DST"
  echo "     日志:  $LOG_DIR/gateway.log"
}

uninstall_service() {
  launchctl bootout "$DOMAIN" "$PLIST_DST" 2>/dev/null || true
  rm -f "$PLIST_DST"
  echo "[OK] 已卸载 $LABEL"
}

start_service() {
  launchctl kickstart "$SERVICE"
  echo "[OK] 已启动 $LABEL"
}

stop_service() {
  launchctl kill SIGTERM "$SERVICE" 2>/dev/null || launchctl bootout "$DOMAIN" "$PLIST_DST" 2>/dev/null || true
  echo "[OK] 已停止 $LABEL"
}

restart_service() {
  pkill -f "dingtalk_gateway/bot_echo.py" 2>/dev/null || true
  launchctl kickstart -k "$SERVICE" 2>/dev/null || {
    launchctl bootstrap "$DOMAIN" "$PLIST_DST" 2>/dev/null || true
    launchctl kickstart -k "$SERVICE"
  }
  echo "[OK] 已重启 $LABEL"
}

_wait_gateway_up() {
  local i
  for i in $(seq 1 24); do
    if pgrep -f "dingtalk_gateway/server.py" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.25
  done
  return 1
}

silent_restart_service() {
  ensure_logs
  mkdir -p "$DIR/data"
  date -u +"%Y-%m-%dT%H:%M:%SZ" > "$DIR/data/silent_restart.flag"
  # 必须经 launchd -k 杀进程并拉起；单靠 pkill 可能杀不掉 launchd 托管的旧实例
  launchctl kickstart -k "$SERVICE" 2>/dev/null || {
    pkill -9 -f "dingtalk_gateway/server.py" 2>/dev/null || true
    pkill -9 -f "dingtalk_gateway/bot_echo.py" 2>/dev/null || true
    sleep 0.5
    launchctl bootstrap "$DOMAIN" "$PLIST_DST" 2>/dev/null || true
    launchctl kickstart -k "$SERVICE"
  }
  if ! _wait_gateway_up; then
    echo "[FAIL] 静默重启后未检测到 server.py 进程" >&2
    exit 1
  fi
  echo "[OK] 已静默重启 ${LABEL} (未推送启停通知)"
}

show_status() {
  echo "=== launchd ==="
  launchctl print "$SERVICE" 2>/dev/null | rg -n "state =|pid =|last exit|runs =|path =" || echo "服务未安装或未运行"
  echo
  echo "=== 进程 ==="
  pgrep -fl "dingtalk_gateway/server.py" || echo "无 server.py 进程"
  echo
  echo "=== 最近日志 ==="
  if [[ -f "$LOG_DIR/gateway.log" ]]; then
    tail -n 8 "$LOG_DIR/gateway.log"
  else
    echo "（尚无日志）"
  fi
}

follow_logs() {
  ensure_logs
  touch "$LOG_DIR/gateway.log" "$LOG_DIR/gateway.err.log"
  tail -f "$LOG_DIR/gateway.log"
}

run_health() {
  "$DIR/run.sh" health_check.py
}

cmd="${1:-}"
case "$cmd" in
  install) install_service ;;
  uninstall) uninstall_service ;;
  start) start_service ;;
  stop) stop_service ;;
  restart) restart_service ;;
  silent-restart) silent_restart_service ;;
  status) show_status ;;
  logs) follow_logs ;;
  health) run_health ;;
  health-deep) "$DIR/run.sh" health_check.py --deep ;;
  *) usage; exit 1 ;;
esac
