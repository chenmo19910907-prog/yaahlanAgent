"""记录已通过 moa_execute 试跑验收的模板；sync_registry 默认仅入库已验收模板。"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from .paths import moa_dir


def _verified_path() -> str:
    return os.path.join(moa_dir(), "config", "trial_verified_templates.json")


def _read() -> dict[str, str]:
    path = _verified_path()
    if not os.path.isfile(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"{path} 必须是 JSON object")
    out: dict[str, str] = {}
    for key, val in data.items():
        if isinstance(key, str) and key.strip() and isinstance(val, str):
            out[key.strip()] = val.strip()
    return out


def _write(data: dict[str, str]) -> None:
    path = _verified_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(dict(sorted(data.items())), f, ensure_ascii=False, indent=2)
        f.write("\n")


def is_template_trial_verified(template_file: str) -> bool:
    fname = os.path.basename(str(template_file or "").strip())
    if not fname.endswith(".json"):
        return False
    return fname in _read()


def mark_template_trial_verified(template_file: str) -> None:
    fname = os.path.basename(str(template_file or "").strip())
    if not fname.endswith(".json"):
        raise ValueError("template_file 须为 MOA/templates 下的 .json 文件名或路径")
    data = _read()
    data[fname] = datetime.now(timezone.utc).isoformat()
    _write(data)


def list_trial_verified_templates() -> list[str]:
    return sorted(_read().keys())
