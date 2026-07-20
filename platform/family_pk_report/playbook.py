"""从 workflow registry 读取家族 PK 数据测试 playbook。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = REPO_ROOT / "workflow" / "config" / "registry.json"
PLAYBOOK_ID = "family_pk_data_test"


def load_playbook() -> dict[str, Any]:
    with open(REGISTRY_PATH, encoding="utf-8") as f:
        data = json.load(f)
    for item in data.get("playbooks") or []:
        if isinstance(item, dict) and item.get("id") == PLAYBOOK_ID:
            return item
    raise KeyError(f"playbook not found: {PLAYBOOK_ID}")


def step_status_key(order: int) -> str | None:
    mapping = {
        1: "param",
        2: "families",
        3: "tier",
        4: "match",
        5: "reward",
        6: "dispatch",
    }
    return mapping.get(order)
