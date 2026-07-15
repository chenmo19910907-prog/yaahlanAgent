#!/usr/bin/env bash
# 不依赖 Hermes 模型的冒烟：KB 推荐 + 意图 catalog + 编译一条意图
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO"

echo "=== 1) Skills 文件 ==="
test -f hermes/skills/yaahlan-gen-testcase/SKILL.md
test -f hermes/skills/yaahlan-intent/SKILL.md
test -f .hermes.md
echo "OK"

echo "=== 2) KB 推荐（注册登录）==="
python3 scripts/suggest_kb_for_module.py 注册登录

echo "=== 3) 意图 catalog ==="
cd intent-test
npm run catalog

echo "=== 4) 编译一条意图（不跑真机）==="
SAMPLE="$(find intents -name '*.yaml' ! -path '*/_fragments/*' ! -path '*/_seed/*' | head -1)"
if [[ -z "$SAMPLE" ]]; then
  echo "WARN: 无可用意图 yaml"
  exit 1
fi
echo "compile: $SAMPLE"
npm run compile -- "$SAMPLE"

echo ""
echo "冒烟通过。接下来任选："
echo "  bash hermes/scripts/setup.sh   # 安装/接入 Hermes"
echo "  cd $REPO && hermes             # /yaahlan-gen-testcase 或 /yaahlan-intent"
