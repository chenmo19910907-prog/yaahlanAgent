#!/usr/bin/env bash
# 启动钉钉网关（前台）；生产环境可用 launchd 托管
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"
LOG_DIR="$DIR/logs"
mkdir -p "$LOG_DIR"
echo "日志: $LOG_DIR/gateway.log"
exec "$DIR/run.sh" server.py 2>&1 | tee -a "$LOG_DIR/gateway.log"
