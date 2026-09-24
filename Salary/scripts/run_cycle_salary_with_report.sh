#!/usr/bin/env bash
# 执行半月结算薪用例并生成 Markdown + HTML 测试报告，结束后发送钉钉简报（若已配置 Webhook）
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/python.sh
source "${SCRIPT_DIR}/lib/python.sh"
resolve_python

ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
TARGET_TEST="business_case/salary/cycle_salary/test_yaahlan_cycle_salary.py"

cd "${ROOT_DIR}"
export GENERATE_SALARY_REPORT=1
"${PYTHON_CMD}" -m pytest "${TARGET_TEST}" --salary-report "$@"
