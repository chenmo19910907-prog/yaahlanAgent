#!/usr/bin/env bash
# 用仓库 venv 启动 Web Agent（含 cursor-sdk / httpx）
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$DIR/../.." && pwd)"
for CAND in \
  "$REPO_ROOT/.venv/bin/python3" \
  "$DIR/../dingtalk_gateway/.venv/bin/python3"; do
  if [[ -x "$CAND" ]]; then
    exec "$CAND" "$DIR/server.py" "${1:---serve}" "${@:2}"
  fi
done
exec python3 "$DIR/server.py" "${1:---serve}" "${@:2}"
