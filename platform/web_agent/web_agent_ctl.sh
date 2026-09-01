#!/usr/bin/env bash
# Web Agent launchd 管理：安装 / 启停 / 状态 / 日志
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
LABEL="com.yaahlan.web-agent"
PLIST_SRC="$DIR/config/com.yaahlan.web-agent.plist.example"
PLIST_DST="$HOME/Library/LaunchAgents/${LABEL}.plist"
UID_NUM="$(id -u)"
DOMAIN="gui/${UID_NUM}"
SERVICE="${DOMAIN}/${LABEL}"
LOG_DIR="$DIR/data"

usage() {
  cat <<EOF
用法: $0 <install|uninstall|start|stop|restart|status|logs>

  install    安装 launchd 并启动（登录/重启后自启 + 崩溃重启）
  uninstall  停止并移除 launchd
  start      启动服务
  stop       停止服务
  restart    重启服务
  status     查看运行状态
  logs       跟踪 server_watch.log
EOF
}

ensure_logs() {
  mkdir -p "$LOG_DIR"
}

_kill_manual_processes() {
  pkill -f "platform/web_agent/server_watch.py" 2>/dev/null || true
  pkill -f "platform/web_agent/server.py" 2>/dev/null || true
  sleep 0.5
}

install_service() {
  ensure_logs
  _kill_manual_processes
  cp "$PLIST_SRC" "$PLIST_DST"
  launchctl bootout "$DOMAIN" "$PLIST_DST" 2>/dev/null || true
  launchctl bootstrap "$DOMAIN" "$PLIST_DST"
  launchctl enable "$SERVICE" 2>/dev/null || true
  launchctl kickstart -k "$SERVICE"
  echo "[OK] 已安装并启动 $LABEL"
  echo "     plist: $PLIST_DST"
  echo "     日志:  $LOG_DIR/server_watch.log"
  echo "     访问:  http://127.0.0.1:18766/chat.html"
}

uninstall_service() {
  launchctl bootout "$DOMAIN" "$PLIST_DST" 2>/dev/null || true
  rm -f "$PLIST_DST"
  _kill_manual_processes
  echo "[OK] 已卸载 $LABEL"
}

start_service() {
  launchctl kickstart "$SERVICE" 2>/dev/null || {
    launchctl bootstrap "$DOMAIN" "$PLIST_DST" 2>/dev/null || true
    launchctl kickstart "$SERVICE"
  }
  echo "[OK] 已启动 $LABEL"
}

stop_service() {
  launchctl kill SIGTERM "$SERVICE" 2>/dev/null || launchctl bootout "$DOMAIN" "$PLIST_DST" 2>/dev/null || true
  _kill_manual_processes
  echo "[OK] 已停止 $LABEL"
}

restart_service() {
  _kill_manual_processes
  launchctl kickstart -k "$SERVICE" 2>/dev/null || {
    launchctl bootstrap "$DOMAIN" "$PLIST_DST" 2>/dev/null || true
    launchctl kickstart -k "$SERVICE"
  }
  echo "[OK] 已重启 $LABEL"
}

show_status() {
  echo "=== launchd ==="
  launchctl print "$SERVICE" 2>/dev/null | rg -n "state =|pid =|last exit|runs =|path =" || echo "服务未安装或未运行"
  echo
  echo "=== 进程 ==="
  pgrep -fl "platform/web_agent/server_watch.py" || echo "无 server_watch 进程"
  pgrep -fl "platform/web_agent/server.py" || echo "无 server.py 进程"
  echo
  echo "=== 端口 18766 ==="
  lsof -i :18766 2>/dev/null | head -3 || echo "端口未监听"
  echo
  echo "=== 最近日志 ==="
  if [[ -f "$LOG_DIR/server_watch.log" ]]; then
    tail -n 8 "$LOG_DIR/server_watch.log"
  else
    echo "（尚无日志）"
  fi
}

follow_logs() {
  ensure_logs
  touch "$LOG_DIR/server_watch.log" "$LOG_DIR/server_watch.err.log"
  tail -f "$LOG_DIR/server_watch.log"
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
  *) usage; exit 1 ;;
esac
