#!/usr/bin/env bash
# 用仓库 venv 启动 Web Agent（含 cursor-sdk / httpx）
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$DIR/../.." && pwd)"
pick_python() {
  for CAND in \
    "$DIR/../dingtalk_gateway/.venv/bin/python3" \
    "$REPO_ROOT/.venv/bin/python3"; do
    if [[ -x "$CAND" ]] && "$CAND" -c "import cursor_sdk" >/dev/null 2>&1; then
      echo "$CAND"
      return 0
    fi
  done
  for CAND in \
    "$DIR/../dingtalk_gateway/.venv/bin/python3" \
    "$REPO_ROOT/.venv/bin/python3"; do
    if [[ -x "$CAND" ]]; then
      echo "$CAND"
      return 0
    fi
  done
  return 1
}
PY="$(pick_python || true)"
if [[ -n "${PY:-}" ]]; then
  exec "$PY" "$DIR/server.py" "${1:---serve}" "${@:2}"
fi
exec python3 "$DIR/server.py" "${1:---serve}" "${@:2}"
