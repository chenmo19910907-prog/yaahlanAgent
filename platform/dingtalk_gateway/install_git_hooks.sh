#!/usr/bin/env bash
# 将 platform/dingtalk_gateway/hooks/* 安装到仓库 .git/hooks/（post-push → 推送后静默重启网关）
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(git -C "$DIR" rev-parse --show-toplevel)"
HOOKS_SRC="$DIR/hooks"
HOOKS_DST="$REPO_ROOT/.git/hooks"

mkdir -p "$HOOKS_DST"

for hook in post-push; do
  src="$HOOKS_SRC/$hook"
  dst="$HOOKS_DST/$hook"
  if [[ ! -f "$src" ]]; then
    echo "[SKIP] 未找到 $src" >&2
    continue
  fi
  cp "$src" "$dst"
  chmod +x "$dst"
  echo "[OK] 已安装 $dst"
done

echo "推送含 platform/dingtalk_gateway/ 变更时将自动执行 gateway_ctl.sh silent-restart"
