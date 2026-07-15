#!/usr/bin/env bash
# 从 midscene/.env 同步火山方舟到 Hermes（custom:volcengine-ark）
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
export PATH="$HOME/.local/bin:$PATH"

python3 - "$REPO" <<'PY'
from pathlib import Path
import re
import sys

repo = Path(sys.argv[1])
mid = repo / "midscene" / ".env"
hermes_env = Path.home() / ".hermes" / ".env"
cfg = Path.home() / ".hermes" / "config.yaml"

if not mid.exists():
    raise SystemExit(f"缺少 {mid}，请先配置 midscene/.env")

env = {}
for line in mid.read_text(encoding="utf-8").splitlines():
    s = line.strip()
    if not s or s.startswith("#") or "=" not in s:
        continue
    k, v = s.split("=", 1)
    env[k] = v.strip().strip('"').strip("'")

base_url = env.get("MIDSCENE_MODEL_BASE_URL", "").rstrip("/")
api_key = env.get("MIDSCENE_MODEL_API_KEY", "")
model = env.get("MIDSCENE_MODEL_NAME", "")
if not (base_url and api_key and model):
    raise SystemExit("midscene/.env 需含 MIDSCENE_MODEL_BASE_URL / API_KEY / NAME")

print(f"sync → base_url={base_url}")
print(f"sync → model={model}")

text = hermes_env.read_text(encoding="utf-8") if hermes_env.exists() else ""

def upsert_env(src: str, key: str, value: str) -> str:
    pattern = re.compile(rf"(?m)^(?:#\s*)?{re.escape(key)}=.*$")
    line = f"{key}={value}"
    if pattern.search(src):
        return pattern.sub(line, src, count=1)
    if not src.endswith("\n"):
        src += "\n"
    return src + f"\n# Synced from midscene/.env\n{line}\n"

text = upsert_env(text, "VOLCENGINE_ARK_API_KEY", api_key)
text = upsert_env(text, "OPENAI_API_KEY", api_key)
hermes_env.write_text(text, encoding="utf-8")

cfg_text = cfg.read_text(encoding="utf-8")
cfg_text = re.sub(r'(?m)^(  default:\s*)"[^"]*"', rf'\1"{model}"', cfg_text, count=1)
cfg_text = re.sub(r'(?m)^(  provider:\s*)"[^"]*"', r'\1"custom:volcengine-ark"', cfg_text, count=1)
cfg_text = re.sub(r'(?m)^(  base_url:\s*)"[^"]*"', rf'\1"{base_url}"', cfg_text, count=1)

block = (
    "# Yaahlan: Volcengine Ark (synced from midscene/.env)\n"
    "custom_providers:\n"
    "  - name: volcengine-ark\n"
    f"    base_url: {base_url}\n"
    "    key_env: VOLCENGINE_ARK_API_KEY\n"
)

if "name: volcengine-ark" in cfg_text:
    cfg_text = re.sub(
        r"(?ms)^# Yaahlan: Volcengine Ark.*?(?=^# =+|^[a-z_]+:|\Z)",
        block + "\n",
        cfg_text,
        count=1,
    )
    # also refresh base_url inside existing entry
    cfg_text = re.sub(
        r"(?m)(name: volcengine-ark\n\s*base_url:\s*).*",
        rf"\1{base_url}",
        cfg_text,
        count=1,
    )
elif "custom_providers:" in cfg_text:
    cfg_text = cfg_text.replace(
        "custom_providers:",
        "custom_providers:\n  - name: volcengine-ark\n"
        f"    base_url: {base_url}\n"
        "    key_env: VOLCENGINE_ARK_API_KEY\n",
        1,
    )
else:
    marker = "# =============================================================================\n# Agent Behavior"
    cfg_text = cfg_text.replace(marker, block + "\n" + marker, 1) if marker in cfg_text else cfg_text.rstrip() + "\n" + block

cfg.write_text(cfg_text, encoding="utf-8")
print(f"updated {hermes_env}")
print(f"updated {cfg}")
print("provider=custom:volcengine-ark")
PY

echo ""
echo "冒烟："
cd "$REPO"
MODEL="$(python3 -c "import pathlib; d={}; 
[d.update({l.split('=',1)[0]:l.split('=',1)[1].strip()}) for l in pathlib.Path('midscene/.env').read_text().splitlines() if l.strip() and not l.startswith('#') and '=' in l];
print(d.get('MIDSCENE_MODEL_NAME',''))")"
hermes chat -Q -q "只回复：ok" --provider custom:volcengine-ark -m "$MODEL" 2>&1 | tail -8
