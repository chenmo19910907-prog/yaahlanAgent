#!/bin/bash
# 五底栏快捷导航 — 基于相对位置点击
# 用法: ./nav_bottom_tabs.sh <tab名>
#   tab名: game | room | message | moment | me
#
# 设备: 通过环境变量 ADB_DEVICE 指定，或自动选取已连接设备
# 适配: 自动获取屏幕分辨率并按比例计算坐标

set -euo pipefail

DEVICE="${ADB_DEVICE:-}"
if [ -z "$DEVICE" ]; then
    DEVICE=$(adb devices | grep -w device | head -1 | awk '{print $1}')
fi

if [ -z "$DEVICE" ]; then
    echo "❌ 未找到已连接的 ADB 设备" >&2
    exit 1
fi

ADB="adb -s $DEVICE"

# 获取屏幕分辨率
RESOLUTION=$($ADB shell wm size | grep -oE '[0-9]+x[0-9]+' | tail -1)
WIDTH=$(echo "$RESOLUTION" | cut -d'x' -f1)
HEIGHT=$(echo "$RESOLUTION" | cut -d'x' -f2)

# 底栏 Y 坐标：屏幕高度 96%（底部导航栏中心）
NAV_Y=$(awk "BEGIN {printf \"%d\", $HEIGHT * 0.96}")

# 五底栏 X 坐标（均匀五等分，取每段中心）
# Game=10% | Room=30% | Message=50% | Moment=70% | Me=90%
X_GAME=$(awk "BEGIN {printf \"%d\", $WIDTH * 0.10}")
X_ROOM=$(awk "BEGIN {printf \"%d\", $WIDTH * 0.30}")
X_MESSAGE=$(awk "BEGIN {printf \"%d\", $WIDTH * 0.50}")
X_MOMENT=$(awk "BEGIN {printf \"%d\", $WIDTH * 0.70}")
X_ME=$(awk "BEGIN {printf \"%d\", $WIDTH * 0.90}")

TAB="${1:-}"

case "$TAB" in
    game|Game|GAME)
        echo "📱 [$DEVICE] 点击 Game 帧 → ($X_GAME, $NAV_Y)"
        $ADB shell input tap "$X_GAME" "$NAV_Y"
        ;;
    room|Room|ROOM)
        echo "📱 [$DEVICE] 点击 Room 帧 → ($X_ROOM, $NAV_Y)"
        $ADB shell input tap "$X_ROOM" "$NAV_Y"
        ;;
    message|Message|MESSAGE|msg)
        echo "📱 [$DEVICE] 点击 Message 帧 → ($X_MESSAGE, $NAV_Y)"
        $ADB shell input tap "$X_MESSAGE" "$NAV_Y"
        ;;
    moment|Moment|MOMENT)
        echo "📱 [$DEVICE] 点击 Moment 帧 → ($X_MOMENT, $NAV_Y)"
        $ADB shell input tap "$X_MOMENT" "$NAV_Y"
        ;;
    me|Me|ME)
        echo "📱 [$DEVICE] 点击 Me 帧 → ($X_ME, $NAV_Y)"
        $ADB shell input tap "$X_ME" "$NAV_Y"
        ;;
    all|info)
        echo "📱 设备: $DEVICE | 分辨率: ${WIDTH}x${HEIGHT}"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "  Game    → ($X_GAME, $NAV_Y)   [10%]"
        echo "  Room    → ($X_ROOM, $NAV_Y)   [30%]"
        echo "  Message → ($X_MESSAGE, $NAV_Y)   [50%]"
        echo "  Moment  → ($X_MOMENT, $NAV_Y)   [70%]"
        echo "  Me      → ($X_ME, $NAV_Y)   [90%]"
        ;;
    *)
        echo "用法: $0 <game|room|message|moment|me|all>"
        echo "  all/info  显示所有 tab 坐标信息"
        exit 1
        ;;
esac
