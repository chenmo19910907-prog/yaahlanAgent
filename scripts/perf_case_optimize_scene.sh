#!/usr/bin/env bash
# 单场景试跑：./scripts/perf_case_optimize_scene.sh 11
# 其余参数原样传给 perf_automation_full.sh（环境变量 PERF_*）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCENE="${1:-}"
if [[ -z "$SCENE" ]]; then
  echo "用法: $0 <场景号 01-30>" >&2
  exit 1
fi
export PERF_ONLY="$SCENE"
exec "$ROOT/scripts/perf_automation_full.sh"
