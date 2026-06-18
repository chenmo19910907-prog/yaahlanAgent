"""用例加载与校验。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .paths import cases_dir


def resolve_case_path(case_ref: str) -> Path:
    ref = (case_ref or "").strip()
    if not ref:
        raise ValueError("请指定用例 id 或路径")

    direct = Path(ref)
    if direct.is_file():
        return direct

    candidate = cases_dir() / f"{ref}.json"
    if candidate.is_file():
        return candidate

    matches = list(cases_dir().rglob(f"*{ref}*.json"))
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise ValueError(f"用例 id 不唯一: {ref}")
    raise FileNotFoundError(f"找不到用例: {ref}")


def load_case(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("用例 JSON 须为 object")
    return data


def case_flow_steps(case: dict[str, Any]) -> list[str]:
    """自然语言步骤列表：优先 flow[]，兼容旧 steps[].note。"""
    flow = case.get("flow")
    if isinstance(flow, list):
        return [str(item).strip() for item in flow if str(item).strip()]

    steps = case.get("steps")
    if isinstance(steps, list):
        out: list[str] = []
        for step in steps:
            if isinstance(step, str) and step.strip():
                out.append(step.strip())
            elif isinstance(step, dict):
                note = str(step.get("note") or step.get("target") or "").strip()
                if note:
                    out.append(note)
        return out
    return []
