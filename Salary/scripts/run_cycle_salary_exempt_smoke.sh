#!/usr/bin/env bash
# 主播薪资豁免冒烟：5 条（等级 + 首次正负向 + 跨周期）
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/python.sh
source "${SCRIPT_DIR}/lib/python.sh"
resolve_python

ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SUITE_JSON="${ROOT_DIR}/data/salary/cycle_salary/yaahlan_cycle_salary_exempt_suite.json"
TARGET_TEST="business_case/salary/cycle_salary/test_yaahlan_cycle_salary_exempt.py"

if [[ "${1:-}" == "--list" ]]; then
  "${PYTHON_CMD}" -c "
import json, sys
d = json.load(open(sys.argv[1], encoding='utf-8'))
smoke = d.get('smoke_cases') or []
print('Exempt smoke cases (%d):' % len(smoke))
for x in smoke:
    print(' -', x)
" "${SUITE_JSON}"
  exit 0
fi

cd "${ROOT_DIR}"
export CYCLE_SALARY_SUITE=exempt
export CYCLE_SALARY_EXEMPT_SMOKE=1

echo "Running cycle salary EXEMPT smoke..."
echo "project: ${ROOT_DIR}"
echo "target : ${TARGET_TEST}"
echo "python : ${PYTHON_CMD}"
echo

"${PYTHON_CMD}" -m pytest "${TARGET_TEST}" "$@"
