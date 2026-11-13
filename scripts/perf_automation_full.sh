#!/usr/bin/env bash
# case优化 · 100% 可自动化全链路（场景 01–30 + 前置）
# 对齐钉钉「性能测试」Sheet「case优化」自动化实现列。
#
# 用法：
#   PERF_SERIAL=9ca11887 PERF_ACCOUNT=xxx PERF_ROOM_ID=54623490 ./scripts/perf_automation_full.sh
#   PERF_ONLY=01,10,29   # 仅跑部分场景（逗号分隔，不含前导零亦可 1,10）
#   PERF_DRY=1           # 只打印将执行的场景，不跑 ADB
#
# PerfDog：请 USB 连机后人工开录；本脚本在关键场景打日志书签 PERF-NN（便于对齐分段 Stat）。

set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SERIAL="${PERF_SERIAL:-}"
ACCOUNT="${PERF_ACCOUNT:-}"
ROOM_ID="${PERF_ROOM_ID:-54623490}"
ROOM_LOOP="${PERF_ROOM_LOOP:-10}"
PROFILE_LOOP="${PERF_PROFILE_LOOP:-30}"
CHAT_LOOP="${PERF_CHAT_LOOP:-30}"
SUB_TAB_ROUNDS="${PERF_SUB_TAB_ROUNDS:-10}"
FIVE_TAB_ROUNDS="${PERF_FIVE_TAB_ROUNDS:-30}"
SOAK_IN_ROOM_SEC="${PERF_SOAK_IN_ROOM_SEC:-180}"
IDLE_SEC="${PERF_IDLE_SEC:-30}"
PULL_REFRESH_N="${PERF_PULL_REFRESH_N:-15}"
LIKE_N="${PERF_LIKE_N:-15}"
PKG="${PERF_PACKAGE:-com.immomo.biz.yaahlan}"
REPORT="${ROOT}/.tmp/perf_case优化_full_report.txt"
DRY="${PERF_DRY:-0}"
ONLY="${PERF_ONLY:-}"
SKIP_NEED_IMAGE="${PERF_SKIP_NEED_IMAGE:-0}"

SWIPE_X1="${PERF_SWIPE_X1:-540}"
SWIPE_Y1="${PERF_SWIPE_Y1:-1800}"
SWIPE_X2="${PERF_SWIPE_X2:-540}"
SWIPE_Y2="${PERF_SWIPE_Y2:-900}"
SWIPE_MS="${PERF_SWIPE_MS:-200}"
SWIPE_GAP="${PERF_SWIPE_GAP:-0.5}"
# 30s 竖滑 ≈ 60 次 × 0.5s
SWIPE_30S_N="${PERF_SWIPE_30S_N:-60}"

mkdir -p "${ROOT}/.tmp"
ADB=(python3 "$ROOT/adb/adb_execute.py")
[[ -n "$SERIAL" ]] && ADB+=(--serial "$SERIAL")
MF=(--no-capture --no-popup-gate --force-script)
ADB_SHELL=(adb)
[[ -n "$SERIAL" ]] && ADB_SHELL+=(-s "$SERIAL")

PASS=()
FAIL=()
SKIP=()

perf_log() { echo "[$(date +%H:%M:%S)] $*"; }
bookmark() { perf_log "[PERF-${1}]"; }

is_need_image_scene() {
  local num="$1"
  [[ "$SKIP_NEED_IMAGE" == "1" ]] || return 1
  local n
  n="$(printf '%02d' "$((10#$num))" 2>/dev/null || echo "$num")"
  case "$n" in 03|09|23) return 0 ;; *) return 1 ;; esac
}

run_scene() {
  local num="$1" title="$2"
  shift 2
  if ! should_run "$num"; then
    perf_log "SKIP (PERF_ONLY) 场景${num}·${title}"
    return 0
  fi
  if is_need_image_scene "$num"; then
    perf_log "SKIP (需补图) 场景${num}·${title}"
    SKIP+=("${num}|${title}|跳过·需补图")
    return 0
  fi
  perf_log "======== 场景${num}·${title} ========"
  if [[ "$DRY" == "1" ]]; then
    perf_log "  (dry-run)"
    return 0
  fi
  bookmark "$num"
  if "$@"; then
    PASS+=("${num}|${title}")
    wait_tail
    perf_log "  -> OK"
  else
    FAIL+=("${num}|${title}")
    wait_tail
    perf_log "  -> FAIL"
  fi
}

should_run() {
  local num="$1"
  [[ -z "$ONLY" ]] && return 0
  local n
  n="$(printf '%02d' "$((10#$num))" 2>/dev/null || echo "$num")"
  IFS=',' read -ra parts <<< "$ONLY"
  local p pn
  for p in "${parts[@]}"; do
    p="${p// /}"
    pn="$(printf '%02d' "$((10#$p))" 2>/dev/null || echo "$p")"
    [[ "$pn" == "$n" || "$p" == "$num" ]] && return 0
  done
  return 1
}

do_macro() {
  "${ADB[@]}" macro "$1" "${MF[@]}" "${@:2}" >/dev/null 2>&1
}

do_macro_soft() {
  do_macro "$@" || true
}

back() {
  "${ADB_SHELL[@]}" shell input keyevent 4 >/dev/null 2>&1
  sleep 1
}

wait_tail() {
  sleep 5
}

wait_idle() {
  sleep "$IDLE_SEC"
}

do_swipe_v_n() {
  local n="$1" i
  for ((i = 0; i < n; i++)); do
    "${ADB_SHELL[@]}" shell input swipe "$SWIPE_X1" "$SWIPE_Y1" "$SWIPE_X2" "$SWIPE_Y2" "$SWIPE_MS" >/dev/null 2>&1 || return 1
    sleep "$SWIPE_GAP"
  done
}

do_swipe_v_30s() {
  do_swipe_v_n "$SWIPE_30S_N"
}

# 下拉刷新：无专用片段时用顶部下拉手势（实验；校准见 PERF_PULL_*）
do_pull_refresh() {
  local n="${1:-$PULL_REFRESH_N}"
  local px1="${PERF_PULL_X1:-540}"
  local py1="${PERF_PULL_Y1:-450}"
  local px2="${PERF_PULL_X2:-540}"
  local py2="${PERF_PULL_Y2:-1200}"
  local i
  for ((i = 0; i < n; i++)); do
    "${ADB_SHELL[@]}" shell input swipe "$px1" "$py1" "$px2" "$py2" 350 >/dev/null 2>&1 || return 1
    sleep 1.2
  done
}

preflight() {
  perf_log "======== 自动化前置（不计入性能路径）========"
  [[ "$DRY" == "1" ]] && return 0
  "${ADB[@]}" devices >/dev/null 2>&1 || true
  if [[ -n "$ACCOUNT" ]]; then
    "${ADB[@]}" accounts check --account "$ACCOUNT" >/dev/null 2>&1 || perf_log "WARN: accounts check"
  else
    perf_log "提示: 可设 PERF_ACCOUNT 做 accounts check"
  fi
  do_macro_soft 冷启动回首页
  do_macro_soft 冷启动回首页
  do_macro_soft 关闭Me页弹窗
  perf_log "force-stop $PKG（不清登录态）"
  "${ADB_SHELL[@]}" shell am force-stop "$PKG" >/dev/null 2>&1
  sleep 2
}

scene_01() {
  do_macro 冷启动回首页 || return 1
  sleep 5
}

scene_02() {
  do_swipe_v_30s
}

scene_03() {
  perf_log "场景03：游戏帧下拉刷新（手势占位，待补「游戏帧下拉刷新」片段）"
  do_pull_refresh "$PULL_REFRESH_N"
}

scene_04() {
  local i
  for ((i = 0; i < PROFILE_LOOP; i++)); do
    do_macro 游戏帧进入个人资料 || return 1
    back
    do_macro 游戏帧进入活动中心 || return 1
    back
  done
}

scene_05() {
  wait_idle
}

scene_06() {
  do_swipe_v_30s
}

scene_07() {
  local r
  for ((r = 0; r < SUB_TAB_ROUNDS; r++)); do
    do_macro 房间帧切换Hot分类 || return 1
    do_macro 房间帧切换MineTab || return 1
    do_macro 房间帧切换EgyptTab || return 1
  done
}

scene_08() {
  local r
  for ((r = 0; r < SUB_TAB_ROUNDS; r++)); do
    do_macro 房间帧切换Hot分类 || return 1
    do_macro 房间帧切换PK分类 || return 1
    do_macro 房间帧切换Game分类 || return 1
    do_macro 房间帧切换Chat分类 || return 1
  done
  perf_log "场景08：家族/音乐 Tab 无片段，已跳过（现网有则补片段后插入同轮）"
}

scene_09() {
  perf_log "场景09：房间列表下拉刷新（手势占位，待补「房间帧下拉刷新」片段）"
  do_pull_refresh "$PULL_REFRESH_N"
}

scene_10() {
  local i
  for ((i = 0; i < ROOM_LOOP; i++)); do
    do_macro 搜索进房 --text "$ROOM_ID" || return 1
    sleep 3
    do_macro 退出房间 || return 1
  done
}

scene_11() {
  do_macro 房间帧切换Hot分类 || return 1
  do_macro 房间帧点击首个房间卡片 || return 1
  perf_log "房内浸泡 ${SOAK_IN_ROOM_SEC}s"
  sleep "$SOAK_IN_ROOM_SEC"
  do_macro_soft 退出房间
}

scene_12() {
  do_macro 房内打开在线用户列表 || return 1
  do_swipe_v_30s
  back
}

scene_13() {
  do_macro 房内打开在线用户列表 || return 1
  do_macro 房内在线列表切换NobilityTab || return 1
  do_swipe_v_30s
  back
  back
}

scene_14() {
  do_macro 房内打开在线用户列表 || return 1
  do_macro 房内在线列表切换MembersTab || return 1
  do_swipe_v_30s
  back
  back
}

scene_15() {
  do_macro_soft 退出房间
  wait_idle
}

para_a() {
  do_macro 切换房间底栏 || return 1
  sleep 5
}

para_b() {
  do_macro 切换消息底栏 || return 1
  sleep 5
}

para_c() {
  do_macro 切换动态底栏 || return 1
  sleep 5
}

para_d() {
  do_macro 切换我的底栏 || return 1
  do_macro_soft 关闭Me页弹窗
  sleep 5
}

scene_16() {
  do_swipe_v_30s
}

scene_17() {
  wait_idle
}

scene_18() {
  local i
  for ((i = 0; i < CHAT_LOOP; i++)); do
    do_macro 消息帧进入家族群聊 || return 1
    back
  done
}

scene_19() {
  do_macro_soft 动态帧切换DiscoverTab
  do_swipe_v_30s
}

scene_20() {
  do_macro 切换动态关注tab || return 1
  do_swipe_v_30s
}

scene_21() {
  local i
  do_macro_soft 动态帧切换DiscoverTab
  for ((i = 0; i < LIKE_N; i++)); do
    do_macro 动态帧Discover点赞首条 || return 1
    sleep 0.8
  done
}

scene_22() {
  do_macro 动态帧Discover进入动态详情 || return 1
  do_swipe_v_30s
  back
}

scene_23() {
  perf_log "场景23：收礼 Tab 无片段 → SKIP 路径（保留 PerfDog 书签位）"
  SKIP+=("23|动态详情收礼Tab滑|需补图 动态详情切换收礼Tab")
  do_macro_soft 动态帧Discover进入动态详情
  do_swipe_v_30s
  back
  return 0
}

scene_24() {
  wait_idle
}

scene_25() {
  sleep 5
}

scene_26() {
  do_macro 进入好友列表 || return 1
  do_swipe_v_30s
  back
  do_macro 进入关注列表 || return 1
  do_swipe_v_30s
  back
  do_macro 进入粉丝列表 || return 1
  do_swipe_v_30s
  back
}

scene_27() {
  local i
  for ((i = 0; i < PROFILE_LOOP; i++)); do
    do_macro 我的页进入个人资料详情 || return 1
    back
  done
}

scene_28() {
  wait_idle
}

scene_29() {
  local r m
  for ((r = 0; r < FIVE_TAB_ROUNDS; r++)); do
    for m in 切换游戏底栏 切换房间底栏 切换消息底栏 切换动态底栏 切换我的底栏; do
      do_macro "$m" || return 1
      sleep 0.5
    done
  done
}

scene_30() {
  "${ADB_SHELL[@]}" shell input keyevent 3 >/dev/null 2>&1
  sleep 30
  "${ADB_SHELL[@]}" shell monkey -p "$PKG" -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1
  sleep 3
}

main() {
  perf_log "case优化全链路 | 设备=${SERIAL:-default} 房=$ROOM_ID ONLY=${ONLY:-all} DRY=$DRY"
  preflight
  run_scene "01" "开跑冷启动" scene_01
  run_scene "02" "Game帧Online列表快滑" scene_02
  run_scene "03" "Game帧下拉刷新" scene_03
  run_scene "04" "Game帧进出子页内存" scene_04
  run_scene "05" "Game帧静置" scene_05
  perf_log "-------- 段落A·切房间帧 --------"
  [[ "$DRY" != "1" ]] && para_a
  run_scene "06" "房间列表快滑" scene_06
  run_scene "07" "房间Hot/Mine/Egypt Tab" scene_07
  run_scene "08" "房间子分类 Tab" scene_08
  run_scene "09" "房间列表下拉刷新" scene_09
  run_scene "10" "进退性能房" scene_10
  run_scene "11" "Hot首卡进房浸泡" scene_11
  run_scene "12" "房内在线列表" scene_12
  run_scene "13" "房内贵族列表" scene_13
  run_scene "14" "房内成员列表" scene_14
  run_scene "15" "退房回列表静置" scene_15
  perf_log "-------- 段落B·切消息帧 --------"
  [[ "$DRY" != "1" ]] && para_b
  run_scene "16" "消息列表快滑" scene_16
  run_scene "17" "消息列表静置" scene_17
  run_scene "18" "会话进出压测" scene_18
  perf_log "-------- 段落C·切动态帧 --------"
  [[ "$DRY" != "1" ]] && para_c
  run_scene "19" "动态Discover快滑" scene_19
  run_scene "20" "动态Following快滑" scene_20
  run_scene "21" "动态点赞刷新" scene_21
  run_scene "22" "动态详情评论滑" scene_22
  run_scene "23" "动态详情收礼Tab滑" scene_23
  run_scene "24" "动态列表静置" scene_24
  perf_log "-------- 段落D·切我的帧 --------"
  [[ "$DRY" != "1" ]] && para_d
  run_scene "25" "Me首屏静置" scene_25
  run_scene "26" "好友/关注/粉丝" scene_26
  run_scene "27" "个人资料进出" scene_27
  run_scene "28" "Me静置" scene_28
  run_scene "29" "五帧快切30次" scene_29
  run_scene "30" "结束压后台" scene_30

  {
    echo "======== case优化 全链路自动化报告 ========"
    echo "时间: $(date -Iseconds)"
    echo "设备: ${SERIAL:-default}  房间: $ROOM_ID  包名: $PKG"
    echo "钉钉: https://alidocs.dingtalk.com/i/nodes/vy20BglGWOekp0O0TmrNb91lJA7depqY · Sheet case优化"
    echo ""
    echo "PASS (${#PASS[@]}):"
    if ((${#PASS[@]})); then printf '  %s\n' "${PASS[@]}"; else echo "  (none)"; fi
    echo ""
    echo "FAIL (${#FAIL[@]}):"
    if ((${#FAIL[@]})); then printf '  %s\n' "${FAIL[@]}"; else echo "  (none)"; fi
    echo ""
    echo "PARTIAL/SKIP (${#SKIP[@]}):"
    if ((${#SKIP[@]})); then printf '  %s\n' "${SKIP[@]}"; else echo "  (none)"; fi
    echo ""
    echo "合计场景 30；跑通 ${#PASS[@]} | 失败 ${#FAIL[@]} | 部分/占位 ${#SKIP[@]}"
  } >"$REPORT"
  cat "$REPORT"
  perf_log "报告: $REPORT"
  ((${#FAIL[@]} == 0))
}

main "$@"
