#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/python.sh
source "${SCRIPT_DIR}/lib/python.sh"
resolve_python

# 定向回归：payment_type=1 && is_trade_owner=1（公会收-会长）
TARGET_CASES=(
  "cycle_salary_union_prepayment_deduction"
  "cycle_salary_union_receive_double_prepayment_deduction"
  "cycle_salary_union_receive_owner_union_prepayment_trade_id_mismatch"
  "cycle_salary_union_receive_owner_double_prepayment_period_isolation"
  "cycle_salary_union_receive_owner_zero_double_prepayment_no_effect"
  "cycle_salary_union_receive_owner_mixed_interference"
)

build_k_expr() {
  local expr=""
  local name
  for name in "${TARGET_CASES[@]}"; do
    if [[ -z "${expr}" ]]; then
      expr="${name}"
    else
      expr="${expr} or ${name}"
    fi
  done
  printf "%s" "${expr}"
}

if [[ "${1:-}" == "--list" ]]; then
  printf "Union-receive owner regression cases (%d):\n" "${#TARGET_CASES[@]}"
  printf " - %s\n" "${TARGET_CASES[@]}"
  exit 0
fi

ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
TARGET_TEST="business_case/salary/cycle_salary/test_yaahlan_cycle_salary.py"
K_EXPR="$(build_k_expr)"

echo "Running union-receive owner regression set..."
echo "project: ${ROOT_DIR}"
echo "target : ${TARGET_TEST}"
echo "python : ${PYTHON_CMD}"
echo "cases  : ${#TARGET_CASES[@]}"
echo "filter : ${K_EXPR}"
echo

cd "${ROOT_DIR}"
"${PYTHON_CMD}" -m pytest "${TARGET_TEST}" -k "${K_EXPR}" "$@"
