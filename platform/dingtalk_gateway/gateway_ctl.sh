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
用法: $0 <install|uninstall|start|stop|restart|status|logs|health>

  install    安装 launchd 并启动（开机自启 + 崩溃重启）
  uninstall  停止并移除 launchd
  start      启动服务
  stop       停止服务
  restart    重启服务
  status     查看运行状态
  logs       跟踪 gateway.log
  health     Bridge / MOA / 凭证健康检查
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
  launchctl kickstart -k "$SERVICE"
  echo "[OK] 已重启 $LABEL"
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
  status) show_status ;;
  logs) follow_logs ;;
  health) run_health ;;
  *) usage; exit 1 ;;
esac
