#!/usr/bin/env bash
# 用 dingtalk_gateway venv 启动 Web Agent（含 cursor-sdk / httpx）
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$DIR/../dingtalk_gateway/.venv/bin/python3"
exec "$VENV" "$DIR/server.py" "${1:---serve}" "${@:2}"
