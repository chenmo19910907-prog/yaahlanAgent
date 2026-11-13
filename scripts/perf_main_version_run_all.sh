#!/usr/bin/env bash
# §4 主路径：尽可能用 ADB macro 跑一遍，统计 pass/fail/manual
# PERF_SERIAL=9ca11887 PERF_ROOM_ID=54623490 ./scripts/perf_main_version_run_all.sh

set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SERIAL="${PERF_SERIAL:-}"
ROOM_ID="${PERF_ROOM_ID:-54623490}"
TAB_ROUNDS="${PERF_TAB_ROUNDS:-2}"
SWIPE_N="${PERF_SWIPE_N:-8}"
REPORT="${ROOT}/.tmp/perf_run_all_report.txt"
mkdir -p "${ROOT}/.tmp"

ADB=(python3 "$ROOT/adb/adb_execute.py")
[[ -n "$SERIAL" ]] && ADB+=(--serial "$SERIAL")
MF=(--no-capture --no-popup-gate --force-script)
ADB_SHELL=(adb)
[[ -n "$SERIAL" ]] && ADB_SHELL+=(-s "$SERIAL")

PASS=()
FAIL=()
MANUAL=()

log() { echo "[$(date +%H:%M:%S)] $*"; }

run_case() {
  local id="$1" title="$2"
  shift 2
  log "CASE $id $title"
  if "$@"; then
    PASS+=("$id|$title")
    log "  -> OK"
  else
    FAIL+=("$id|$title")
    log "  -> FAIL"
  fi
}

manual_case() {
  MANUAL+=("$1|$2|$3")
  log "CASE $1 $2 -> MANUAL ($3)"
}

do_macro() {
  "${ADB[@]}" macro "$1" "${MF[@]}" "${@:2}" >/dev/null 2>&1
}

do_swipe_v() {
  local n="$1" i
  for ((i=0; i<n; i++)); do
    "${ADB_SHELL[@]}" shell input swipe 540 1800 540 900 200 >/dev/null 2>&1 || return 1
    sleep 0.5
  done
}

back() { "${ADB_SHELL[@]}" shell input keyevent 4 >/dev/null 2>&1; sleep 1; }
wait_perf() { sleep "${1:-5}"; }

case1() { do_macro 冷启动回首页; }
case2() {
  local r m
  for ((r=0; r<TAB_ROUNDS; r++)); do
    for m in 切换游戏底栏 切换房间底栏 切换消息底栏 切换动态底栏 切换我的底栏; do
      do_macro "$m" || return 1
      sleep 0.5
    done
  done
}
case3() { do_macro 切换游戏底栏 && do_swipe_v "$SWIPE_N"; }
case4() {
  do_macro 切换房间底栏 || return 1
  do_macro 房间帧进入财富榜 || return 1
  back; back
  do_macro 房间帧进入财富榜 || return 1
  back; back
}
case5() {
  do_macro 切换房间底栏 || return 1
  do_macro 房间帧切换Hot分类 || return 1
  do_swipe_v "$SWIPE_N"
}
case6() {
  do_macro 切换房间底栏 || return 1
  do_macro 搜索进房 --text "$ROOM_ID" || return 1
  wait_perf 5
  do_macro 退出房间 || return 1
  wait_perf 3
  do_macro 搜索进房 --text "$ROOM_ID" || return 1
  wait_perf 5
}
case7a() { do_macro 房内RoomFunction打开PKATM && back && back; }
case7b() { do_macro 房内RoomFunction打开PopularityChallenge && back && back; }
case7c() { do_macro 房内RoomFunction打开TruthOrDare && back && back; }
case8() { do_macro 房内RoomFunction打开PK && back && back; }
case9() { do_macro 房内RoomFunction打开BGM && sleep 10 && back; }
case10() { do_macro 打开礼物面板; }
case13() { do_macro 退出房间; }
case14() {
  do_macro 切换房间底栏 || return 1
  do_macro 房间帧切换Hot分类 || return 1
  do_macro 房间帧点击首个房间卡片 || return 1
  wait_perf 5
}
case15() {
  do_macro 房内打开在线用户列表 || return 1
  do_macro 房内在线列表切换MembersTab || return 1
  do_swipe_v "$SWIPE_N"
  back
}
case16() {
  do_macro 房内打开在线用户列表 || return 1
  do_swipe_v "$SWIPE_N"
  back
}
case17() { do_macro 退出房间; }
case18() {
  do_macro 切换消息底栏 || return 1
  do_macro 消息帧进入家族群聊 || return 1
  back
}
case19() { do_macro 切换动态底栏 && do_swipe_v "$SWIPE_N"; }
case20() {
  do_macro 切换我的底栏 || return 1
  do_macro 关闭Me页弹窗 || true
  do_macro 我的页进入MyRelationship || return 1
  back
  do_macro 我的页进入MyRelationship || return 1
  back
}
case24() {
  do_macro 切换我的底栏 || return 1
  do_macro 我的页进入个人资料详情 || return 1
  back; back
}
case27() {
  do_macro 切换我的底栏 || return 1
  do_macro 我的页进入ViewedMe || return 1
  back
}
case28a() {
  do_macro 切换我的底栏 || return 1
  do_macro 我的页进入Level || return 1; back
  do_macro 我的页进入Level || return 1; back
}
case28b() {
  do_macro 我的页进入OutfitStore || return 1; back
  do_macro 我的页进入OutfitStore || return 1; back
}
case29() {
  "${ADB_SHELL[@]}" shell input keyevent 3
  sleep 5
  "${ADB_SHELL[@]}" shell monkey -p com.immomo.biz.yaahlan -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1
}

log "设备 ${SERIAL:-default} 房间 $ROOM_ID"

run_case "1" "冷启动" case1
wait_perf 8
run_case "2" "五底栏${TAB_ROUNDS}轮" case2
run_case "3" "Game列表快滑" case3
run_case "4" "财富榜往返×2" case4
run_case "5" "Hot+滑动" case5
run_case "6" "进房${ROOM_ID}×2" case6
run_case "7a" "PK ATM" case7a
run_case "7b" "Popularity Challenge" case7b
run_case "7c" "Truth or Dare" case7c
run_case "8" "Room PK" case8
run_case "9" "BGM 10s" case9
run_case "10" "打开礼物面板" case10
back
manual_case "11" "送Rose×10" "须手工"
manual_case "12" "Love Carriage×10" "须手工"
manual_case "12a" "礼物Tab" "须手工"
run_case "13" "退出性能房" case13
wait_perf 5
run_case "14" "Hot首卡进房" case14
run_case "15" "成员列表滑" case15
run_case "16" "在线列表滑" case16
run_case "17" "退出当前房" case17
run_case "18" "家族群聊入口" case18
run_case "19" "动态列表滑" case19
run_case "20" "MyRelationship×2" case20
manual_case "21" "好友列表滑" "须手工"
manual_case "22" "Following滑" "须手工"
manual_case "23" "Followers滑" "须手工"
run_case "24" "个人资料详情" case24
manual_case "25" "编辑资料" "须手工"
manual_case "26" "CP/挚友空间" "须手工"
run_case "27" "Visitors" case27
run_case "28a" "Level×2" case28a
run_case "28b" "OutfitStore×2" case28b
run_case "29" "压后台5s" case29
manual_case "30" "浸泡A 3min" "须手工"
manual_case "31" "浸泡B 5min" "须手工"

{
  echo "======== 主版本性能 §4 自动化跑批 ========"
  echo "时间: $(date -Iseconds)"
  echo "设备: ${SERIAL:-default}  房间: $ROOM_ID"
  echo ""
  echo "PASS (${#PASS[@]}):"
  printf '  %s\n' "${PASS[@]}"
  echo ""
  echo "FAIL (${#FAIL[@]}):"
  printf '  %s\n' "${FAIL[@]}"
  echo ""
  echo "MANUAL (${#MANUAL[@]}):"
  printf '  %s\n' "${MANUAL[@]}"
  echo ""
  auto=$(( ${#PASS[@]} + ${#FAIL[@]} ))
  echo "§4 主路径 31 条：已自动尝试 ${auto} 条（含 7a/b/c 拆分）"
  echo "  跑通: ${#PASS[@]}  |  失败: ${#FAIL[@]}  |  仅手工: ${#MANUAL[@]}"
} | tee "$REPORT"
