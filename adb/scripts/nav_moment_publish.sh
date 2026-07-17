#!/bin/bash
# 进入动态发布编辑页 — 从动态帧右上角 + 按钮进入
# 用法: ./nav_moment_publish.sh
#
# 前置: 需已在动态帧（Moment tab）；若未在动态帧可先执行 nav_bottom_tabs.sh moment
# 设备: 通过环境变量 ADB_DEVICE 指定，或自动选取已连接设备

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

# + 按钮位置：右上角 (X≈93% 宽度, Y≈7.2% 高度)
# 在 Discover/Follow 顶栏同一行的最右侧
X_PLUS=$(awk "BEGIN {printf \"%d\", $WIDTH * 0.93}")
Y_PLUS=$(awk "BEGIN {printf \"%d\", $HEIGHT * 0.072}")

ACTION="${1:-publish}"

case "$ACTION" in
    publish|enter|+)
        echo "📱 [$DEVICE] 点击动态帧 + 按钮 → ($X_PLUS, $Y_PLUS)"
        $ADB shell input tap "$X_PLUS" "$Y_PLUS"
        ;;
    full)
        # 完整流程：先进动态帧再点 +
        NAV_Y=$(awk "BEGIN {printf \"%d\", $HEIGHT * 0.96}")
        X_MOMENT=$(awk "BEGIN {printf \"%d\", $WIDTH * 0.70}")
        echo "📱 [$DEVICE] 点击 Moment 帧 → ($X_MOMENT, $NAV_Y)"
        $ADB shell input tap "$X_MOMENT" "$NAV_Y"
        sleep 1.5
        echo "📱 [$DEVICE] 点击 + 按钮 → ($X_PLUS, $Y_PLUS)"
        $ADB shell input tap "$X_PLUS" "$Y_PLUS"
        ;;
    info)
        echo "📱 设备: $DEVICE | 分辨率: ${WIDTH}x${HEIGHT}"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "  + 发布按钮 → ($X_PLUS, $Y_PLUS)  [93%W, 7.2%H]"
        echo ""
        echo "用法:"
        echo "  $0           # 点击 + 进入发布编辑页（需已在动态帧）"
        echo "  $0 full      # 先进动态帧再点 +"
        echo "  $0 info      # 显示坐标信息"
        ;;
    *)
        echo "用法: $0 [publish|full|info]"
        echo "  publish/enter/+  点击 + 进入发布编辑页（默认，需已在动态帧）"
        echo "  full             先切动态帧再点 +"
        echo "  info             显示坐标信息"
        exit 1
        ;;
esac
