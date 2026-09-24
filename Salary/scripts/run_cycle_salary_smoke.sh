#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/python.sh
source "${SCRIPT_DIR}/lib/python.sh"
resolve_python

# 固定冒烟集（与 case 表 P0 对齐）
SMOKE_CASES=(
  "cycle_salary_union_prepayment_deduction"
  "cycle_salary_anchor_prepayment_deduction"
  "cycle_salary_union_owner_union_prepayment_deduction"
  "cycle_salary_union_non_owner_double_prepayment_deduction"
  "cycle_salary_regular_anchor_duplicate_same_key_prepayment_behavior"
  "cycle_salary_regular_anchor_moa2_rerun_idempotent_probe"
  "cycle_salary_regular_anchor_extreme_large_prepayment_behavior"
)

build_k_expr() {
  local expr=""
  local name
  for name in "${SMOKE_CASES[@]}"; do
    if [[ -z "${expr}" ]]; then
      expr="${name}"
    else
      expr="${expr} or ${name}"
    fi
  done
  printf "%s" "${expr}"
}

if [[ "${1:-}" == "--list" ]]; then
  printf "Cycle salary smoke cases (%d):\n" "${#SMOKE_CASES[@]}"
  printf " - %s\n" "${SMOKE_CASES[@]}"
  exit 0
fi

ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
TARGET_TEST="business_case/salary/cycle_salary/test_yaahlan_cycle_salary.py"
K_EXPR="$(build_k_expr)"

echo "Running cycle salary smoke set..."
echo "project: ${ROOT_DIR}"
echo "target : ${TARGET_TEST}"
echo "python : ${PYTHON_CMD}"
echo "cases  : ${#SMOKE_CASES[@]}"
echo "filter : ${K_EXPR}"
echo

cd "${ROOT_DIR}"
"${PYTHON_CMD}" -m pytest "${TARGET_TEST}" -k "${K_EXPR}" "$@"
