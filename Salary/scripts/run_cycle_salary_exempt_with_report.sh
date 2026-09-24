#!/usr/bin/env bash
# 主播薪资豁免专项：全量套件 + Markdown/HTML 报告 + 钉钉简报（若已配置）
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/python.sh
source "${SCRIPT_DIR}/lib/python.sh"
resolve_python

ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
TARGET_TEST="business_case/salary/cycle_salary/test_yaahlan_cycle_salary_exempt.py"

cd "${ROOT_DIR}"
export GENERATE_SALARY_REPORT=1
export CYCLE_SALARY_SUITE=exempt
unset CYCLE_SALARY_EXEMPT_SMOKE

echo "Running cycle salary EXEMPT suite (full)..."
echo "project: ${ROOT_DIR}"
echo "target : ${TARGET_TEST}"
echo "python : ${PYTHON_CMD}"
echo

"${PYTHON_CMD}" -m pytest "${TARGET_TEST}" --salary-report --salary-report-suite=exempt "$@"
