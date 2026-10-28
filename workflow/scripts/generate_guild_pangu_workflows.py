#!/usr/bin/env python3
"""公会盘古：登记统一工作流 + 刷新 registry / 使用方法。"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "workflow"))

from workflow.paths import REGISTRY_PATH, WORKFLOWS_DIR  # noqa: E402
from workflow.record import save_workflow, upsert_registry_item  # noqa: E402

UNIFIED_ID = "guild_pangu_shift_config"
LEGACY_PREFIX = "guild_pangu_0"
LEGACY_IDS = [f"guild_pangu_{i:02d}_" for i in range(1, 10)]


def _read_registry() -> dict[str, Any]:
    with REGISTRY_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write_registry(data: dict[str, Any]) -> None:
    with REGISTRY_PATH.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _remove_legacy_registry_items() -> None:
    data = _read_registry()
    items = data.get("items") or []
    kept = []
    for item in items:
        if not isinstance(item, dict):
            continue
        rid = str(item.get("id") or "")
        if rid.startswith("guild_pangu_") and rid != "guild_pangu_shift_config":
            continue
        kept.append(item)
    data["items"] = kept
    _write_registry(data)


def main() -> int:
    wf_path = WORKFLOWS_DIR / f"{UNIFIED_ID}.json"
    with wf_path.open("r", encoding="utf-8") as f:
        wf = json.load(f)
    save_workflow(wf, register=True)
    _remove_legacy_registry_items()
    upsert_registry_item(
        {
            "id": "guild_pangu_shift_config",
            "name": "公会盘古时间偏移配置",
            "category": "公会常用盘古配置工具（workflow）",
            "description": wf.get("description") or "",
            "prompts": [
                "公会盘古 场景=<scenario> whiteUsers=<whiteUsers> fixedTimeSec=<fixedTimeSec> expireTimeSec=<expireTimeSec> shiftTime=<shiftTime> 保存发布",
            ],
            "command": (
                "python3 workflow/workflow_execute.py run guild_pangu_shift_config "
                "--scenario <scenario> --white-users <whiteUsers> "
                "--fixed-time-sec <fixedTimeSec> --expire-time-sec <expireTimeSec> --shift-time <shiftTime>"
            ),
        }
    )

    subprocess = __import__("subprocess")
    env = dict(__import__("os").environ)
    env["PYTHONPATH"] = str(REPO / "platform") + (
        ":" + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )
    subprocess.run(
        [sys.executable, str(REPO / "workflow/scripts/generate_index.py")],
        cwd=str(REPO),
        env=env,
        check=False,
    )
    print("已登记统一公会盘古工作流 guild_pangu_shift_config")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
