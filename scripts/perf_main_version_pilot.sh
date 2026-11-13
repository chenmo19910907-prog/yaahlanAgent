#!/usr/bin/env bash
# 主版本性能 case §4 试点：冷启动 + 五底栏 1 轮 + 进/出性能房
# 用法：
#   PERF_SERIAL=9ca11887 PERF_ROOM_ID=54623490 ./scripts/perf_main_version_pilot.sh
# PerfDog 请在本脚本运行前 USB 连好被测机；本脚本只跑 ADB 操作路径，不采 FPS。

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SERIAL="${PERF_SERIAL:-}"
ROOM_ID="${PERF_ROOM_ID:-54623490}"
ADB=(python3 "$ROOT/adb/adb_execute.py")
if [[ -n "$SERIAL" ]]; then
  ADB+=(--serial "$SERIAL")
fi
# 性能试点：不截图、跳过弹窗门禁 uiautomator 偶发失败；底栏片段须 --force-script（游戏/房间等默认走 AI）
MACRO_FLAGS=(--no-capture --no-popup-gate --force-script)

echo "== 设备 =="
"${ADB[@]}" device info | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['device']['manufacturer'], d['device']['model'], d['device']['width'], 'x', d['device']['height']); a=d.get('adaptation',{}); print('calibrated:', a.get('canRunRecordedScripts'), '-', a.get('message','')[:80])"

echo "== §4-1 冷启动进 Game/Home 帧 =="
"${ADB[@]}" macro 冷启动回首页 "${MACRO_FLAGS[@]}"
sleep 10

echo "== §4-2 五底栏往返 1 轮（试点；正式测 5 轮 + 快滑 0.5s） =="
for m in 切换游戏底栏 切换房间底栏 切换消息底栏 切换动态底栏; do
  echo "-- $m"
  "${ADB[@]}" macro "$m" "${MACRO_FLAGS[@]}" || { echo "FAIL: $m"; exit 1; }
  sleep 0.5
done
echo "-- 切换我的底栏（Me 弹窗须测前手工关闭，失败不中断）"
"${ADB[@]}" macro 切换我的底栏 "${MACRO_FLAGS[@]}" || echo "WARN: Me 弹窗门禁，请先关弹窗或 popup analyze --scene me --auto-dismiss"
sleep 0.5
"${ADB[@]}" macro 切换房间底栏 "${MACRO_FLAGS[@]}"
sleep 10

echo "== §4-6 搜索进性能房 ROOM_ID=$ROOM_ID =="
"${ADB[@]}" macro 搜索进房 --text "$ROOM_ID" "${MACRO_FLAGS[@]}"
sleep 10
"${ADB[@]}" activity
sleep 5

echo "== §4-13 退出房间（试点 1 次） =="
"${ADB[@]}" macro 退出房间 "${MACRO_FLAGS[@]}" || echo "WARN: 退出房间失败，请 capture 读图"
sleep 10

echo "== 试点结束；PerfDog 查看 FPS/Jank；正式测见 temporary_testcase/主版本性能case_2026Q4.md =="
