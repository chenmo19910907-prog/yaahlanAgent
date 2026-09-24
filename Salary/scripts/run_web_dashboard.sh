#!/usr/bin/env bash
# 启动 Yaahlan 算薪测试可视化后台（FastAPI MVP）
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/python.sh
source "${SCRIPT_DIR}/lib/python.sh"
resolve_python

ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${ROOT_DIR}"

if [[ -f "${ROOT_DIR}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${ROOT_DIR}/.env"
  set +a
fi

PORT="${DASHBOARD_PORT:-8088}"
echo "启动测试后台: http://127.0.0.1:${PORT}"
echo "本机可直接访问；内网部署请在 .env 配置 DASHBOARD_TOKEN"
exec "${PYTHON_CMD}" -m uvicorn web.main:app --host 0.0.0.0 --port "${PORT}"
