#!/usr/bin/env bash
# 将本仓库 Hermes Skills 接到 ~/.hermes（external_dirs + yaahlan.repo）
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
CONFIG="$HERMES_HOME/config.yaml"
SKILLS_DIR="$REPO/hermes/skills"

echo "==> repo: $REPO"
echo "==> hermes home: $HERMES_HOME"

if ! command -v hermes >/dev/null 2>&1; then
  echo "Hermes 未安装。正在执行官方安装脚本…"
  curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
  # shellcheck disable=SC1090
  [[ -f "$HOME/.zshrc" ]] && source "$HOME/.zshrc" || true
  [[ -f "$HOME/.bashrc" ]] && source "$HOME/.bashrc" || true
  export PATH="$HOME/.local/bin:$PATH"
fi

if ! command -v hermes >/dev/null 2>&1; then
  echo "ERROR: 仍找不到 hermes，请新开终端后重跑本脚本，或手动 source ~/.zshrc"
  exit 1
fi

mkdir -p "$HERMES_HOME" "$HERMES_HOME/skills/yaahlan"

# 本地 skills 目录做 symlink（最稳），并补全 config.yaml 的 external_dirs
ln -sfn "$SKILLS_DIR/yaahlan-gen-testcase" "$HERMES_HOME/skills/yaahlan/yaahlan-gen-testcase"
ln -sfn "$SKILLS_DIR/yaahlan-intent" "$HERMES_HOME/skills/yaahlan/yaahlan-intent"

python3 - "$CONFIG" "$SKILLS_DIR" "$REPO" <<'PY'
import re
import sys
from pathlib import Path

config_path, skills_dir, repo = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
if not config_path.exists():
    config_path.write_text(
        f"skills:\n  external_dirs:\n    - {skills_dir}\n"
        f"  config:\n    yaahlan.repo: {repo}\n",
        encoding="utf-8",
    )
    print(f"created {config_path}")
    raise SystemExit(0)

text = config_path.read_text(encoding="utf-8")

# Drop mistaken trailing duplicates from older setup.sh
for bad in (
    f"\nskills:\n  external_dirs:\n    - {skills_dir}\n\nskills.config:\n  yaahlan.repo: {repo}\n",
    f"\nskills:\n  external_dirs:\n    - {skills_dir}\n",
    f"\nskills.config:\n  yaahlan.repo: {repo}\n",
):
    if text.endswith(bad) or bad in text[text.rfind("\nskills:") if "\nskills:" in text else 0 :]:
        # only strip exact trailing append from previous buggy setup
        if text.rstrip().endswith(f"yaahlan.repo: {repo}") and text.count("\nskills:") >= 2:
            idx = text.rfind("\nskills:\n  external_dirs:")
            if idx > 0:
                text = text[:idx].rstrip() + "\n"

old_commented = """  # external_dirs:
  #   - ~/.agents/skills
  #   - /home/shared/team-skills
"""
replacement = f"""  external_dirs:
    - {skills_dir}

  config:
    yaahlan.repo: {repo}
"""
if old_commented in text:
    text = text.replace(old_commented, replacement, 1)
elif skills_dir not in text:
    needle = "  creation_nudge_interval:"
    if needle in text:
        # insert after that line
        lines = text.splitlines(keepends=True)
        out = []
        for i, line in enumerate(lines):
            out.append(line)
            if line.startswith("  creation_nudge_interval:"):
                out.append("\n")
                out.append(replacement if not replacement.endswith("\n") else replacement)
                if not replacement.endswith("\n"):
                    out.append("\n")
        text = "".join(out)
    else:
        text = text.rstrip() + "\n\nskills:\n" + replacement
elif "yaahlan.repo:" not in text:
    text = text.rstrip() + f"\n  config:\n    yaahlan.repo: {repo}\n"
else:
    text = re.sub(
        r"(?m)^([ \t]*yaahlan\.repo:).*$",
        rf"\1 {repo}",
        text,
    )

config_path.write_text(text, encoding="utf-8")
print(f"updated {config_path}")
PY

echo "==> skills linked:"
echo "    symlink: $HERMES_HOME/skills/yaahlan/yaahlan-gen-testcase"
echo "    symlink: $HERMES_HOME/skills/yaahlan/yaahlan-intent"
echo "    external_dirs: $SKILLS_DIR"
echo ""
echo "下一步："
echo "  1) hermes model          # 配置模型（若未配置）"
echo "  2) cd $REPO && hermes    # 在仓库根目录启动"
echo "  3) 对话中试: /yaahlan-gen-testcase 根据注册登录 KB 生成 3 条样例用例"
echo "     或: /yaahlan-intent 列出意图目录并编译一条动态意图"
echo ""
echo "不依赖模型的冒烟: bash hermes/scripts/smoke.sh"
