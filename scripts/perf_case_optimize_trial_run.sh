#!/usr/bin/env bash
# case优化 · 试跑：跳过 E 列【需补图】场景 03/09/23，缩短静置/滑动手势，跑完写钉钉 F 列。
#
# 用法：
#   PERF_SERIAL=<adb> PERF_ROOM_ID=54623490 ./scripts/perf_case_optimize_trial_run.sh
#
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPORT="${ROOT}/.tmp/perf_case优化_full_report.txt"
LOG="${ROOT}/.tmp/perf_case优化_trial_run.log"

export PERF_SKIP_NEED_IMAGE=1
# 试跑加速（正式 PerfDog 测勿用）
export PERF_IDLE_SEC="${PERF_IDLE_SEC:-10}"
export PERF_SOAK_IN_ROOM_SEC="${PERF_SOAK_IN_ROOM_SEC:-30}"
export PERF_SWIPE_30S_N="${PERF_SWIPE_30S_N:-12}"
export PERF_ROOM_LOOP="${PERF_ROOM_LOOP:-3}"
export PERF_PROFILE_LOOP="${PERF_PROFILE_LOOP:-5}"
export PERF_CHAT_LOOP="${PERF_CHAT_LOOP:-5}"
export PERF_SUB_TAB_ROUNDS="${PERF_SUB_TAB_ROUNDS:-3}"
export PERF_FIVE_TAB_ROUNDS="${PERF_FIVE_TAB_ROUNDS:-5}"
export PERF_PULL_REFRESH_N="${PERF_PULL_REFRESH_N:-5}"
export PERF_LIKE_N="${PERF_LIKE_N:-5}"

mkdir -p "${ROOT}/.tmp"

if ! python3 "${ROOT}/adb/adb_execute.py" devices 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); sys.exit(0 if d.get('devices') else 1)"; then
  echo "[trial] 无 ADB 设备，跳过真机；仅写钉钉 F 列（需补图跳过 + 其余未执行）" | tee "$LOG"
  python3 "${ROOT}/scripts/perf_case_optimize_write_f.py" --mark-image-skip-only
  exit 2
fi

set +e
"${ROOT}/scripts/perf_automation_full.sh" 2>&1 | tee "$LOG"
run_rc=${PIPESTATUS[0]}
set -e

python3 "${ROOT}/scripts/perf_case_optimize_write_f.py" --report "$REPORT"
exit "$run_rc"
