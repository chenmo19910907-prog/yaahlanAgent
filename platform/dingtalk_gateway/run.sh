#!/usr/bin/env bash
# 统一用 venv 启动网关脚本
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
exec "$DIR/.venv/bin/python3" "$DIR/${1:-server.py}" "${@:2}"
