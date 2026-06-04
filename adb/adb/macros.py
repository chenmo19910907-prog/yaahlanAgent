"""已验证 UI 宏：定义见 adb/录制脚本，支持中文名调用。"""

from __future__ import annotations

from typing import Any

import json

from .recorded_scripts import load_fragment, list_catalog, resolve_key


def apply_skip_flags(
    steps: list[dict[str, Any]],
    *,
    skip: set[str],
) -> list[dict[str, Any]]:
    if not skip:
        return steps
    out: list[dict[str, Any]] = []
    for step in steps:
        key = step.get("skip_key")
        if key and key in skip:
            continue
        out.append(step)
    return out


def resolve_macro(
    name: str,
    *,
    text: str | None = None,
) -> dict[str, Any]:
    return load_fragment(name, text=text)


def get_macro(name: str) -> dict[str, Any]:
    return load_fragment(name, text=None)


def list_macros() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in list_catalog():
        if item.get("kind") != "fragment":
            continue
        try:
            spec = load_fragment(str(item["name"]), text=None)
        except ValueError:
            _, _, path = resolve_key(str(item["name"]), kind="fragment")
            spec = json.loads(path.read_text(encoding="utf-8"))
        out.append(
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "description": spec.get("description", ""),
                "capture": spec.get("capture", "end"),
                "stepCount": len(spec.get("steps", [])),
                "params": item.get("params", []),
            }
        )
    return out
