#!/usr/bin/env bash
# 自测：Python 解释器解析、样例报告、钉钉简报 dry-run、发送脚本可用性
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
# shellcheck source=lib/python.sh
source "${SCRIPT_DIR}/lib/python.sh"
resolve_python

echo "=== 1. Python 解释器 ==="
echo "PYTHON_CMD=${PYTHON_CMD}"
"${PYTHON_CMD}" --version

echo ""
echo "=== 2. 模块语法检查 ==="
"${PYTHON_CMD}" -m py_compile \
  "${ROOT_DIR}/utils/salary_report.py" \
  "${ROOT_DIR}/utils/env_utils.py" \
  "${ROOT_DIR}/conftest.py" \
  "${ROOT_DIR}/scripts/send_dingtalk_robot.py" \
  "${ROOT_DIR}/scripts/check_dingtalk_webhook.py" \
  "${ROOT_DIR}/scripts/generate_sample_report.py"

echo ""
echo "=== 3. 样例报告 MD + HTML ==="
cd "${ROOT_DIR}"
"${PYTHON_CMD}" scripts/generate_sample_report.py

echo ""
echo "=== 4. 钉钉简报内容构建（dry-run）==="
DINGTALK_BRIEF_DRY_RUN=1 "${PYTHON_CMD}" - <<'PY'
import os
import sys

sys.path.insert(0, os.getcwd())
from utils.salary_report import build_dingtalk_brief_markdown, send_report_brief_to_dingtalk

results = [
    {"case_name": "case_pass", "case_name_cn": "通过用例", "status": "通过"},
    {
        "case_name": "case_fail",
        "case_name_cn": "失败用例",
        "status": "失败",
        "failure_reason": "表3.salary_coefficient: expected=0.8, actual=0.6",
        "check_rows": [
            {
                "label": "表3.salary_coefficient",
                "expected": 0.8,
                "actual": 0.6,
                "passed": False,
            }
        ],
    },
]
md = build_dingtalk_brief_markdown("/tmp/report.md", results, 2, 70, html_path="/tmp/report.html")
assert "测试报告" in md
assert "Yaahlan" in md
assert "case_fail" in md
assert "| 项目 | 内容 |" in md
assert "| 序号 | 用例名 |" in md
assert "| 用例名 | 直接原因" in md
os.environ.pop("DINGTALK_REPORT_WEBHOOK", None)
os.environ.pop("DINGTALK_WEBHOOK", None)
from utils.salary_report import get_collector
get_collector().reset()
assert send_report_brief_to_dingtalk("/tmp/report.md", results, 2, 70, dry_run=True) is True
get_collector().dingtalk_brief_sent = True
assert send_report_brief_to_dingtalk("/tmp/report.md", results, 2, 70, dry_run=False) is True
from utils.salary_report import _claim_dingtalk_brief_send, _dingtalk_brief_fingerprint, _release_dingtalk_brief_send
fp = _dingtalk_brief_fingerprint("/tmp/report.md", results, 2)
_release_dingtalk_brief_send(".", fp)
assert _claim_dingtalk_brief_send(".", fp) is True
assert _claim_dingtalk_brief_send(".", fp) is False
_release_dingtalk_brief_send(".", fp)
print("build_dingtalk_brief_markdown + dedupe: OK")
PY

echo ""
echo "=== 5. send_dingtalk_robot.py 帮助 ==="
"${PYTHON_CMD}" scripts/send_dingtalk_robot.py --help >/dev/null
echo "send_dingtalk_robot.py --help: OK"

echo ""
echo "=== 6. shell 脚本 python 解析 ==="
for sh in run_cycle_salary_with_report.sh run_cycle_salary_smoke.sh run_cycle_salary_union_receive_owner_regression.sh; do
  (cd "${ROOT_DIR}" && bash -c "source scripts/lib/python.sh && resolve_python && test -n \"\${PYTHON_CMD}\"") || {
    echo "FAIL: ${sh}"
    exit 1
  }
  echo "${sh}: PYTHON_CMD 解析 OK"
done

echo ""
echo "=== 全部自测通过 ==="
