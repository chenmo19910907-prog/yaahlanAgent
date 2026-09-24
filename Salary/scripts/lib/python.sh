# 解析可用的 Python 解释器：优先 Salary/.venv，其次 python3 / python
resolve_python() {
  local root
  root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
  if [[ -x "${root}/.venv/bin/python3" ]]; then
    PYTHON_CMD="${root}/.venv/bin/python3"
  elif command -v python3 >/dev/null 2>&1; then
    PYTHON_CMD=python3
  elif command -v python >/dev/null 2>&1; then
    PYTHON_CMD=python
  else
    echo "错误: 未找到 python3 或 python，请先安装 Python 3.9+" >&2
    exit 127
  fi
}
