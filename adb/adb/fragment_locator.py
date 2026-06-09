"""片段定位器学习：运行中探测点击处元素属性并回写片段 JSON。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .ui_locator import is_coordinate_locator_kind


def locator_fields_from_probe(probe: dict[str, Any]) -> dict[str, Any]:
    """从 uiautomator 探测结果提取可写入片段 / 页面地图的定位字段。"""
    rid = str(probe.get("resourceIdShort") or "").strip()
    if not rid:
        full = str(probe.get("resourceId") or "").strip()
        rid = full.split("/")[-1] if full else ""
    desc = str(probe.get("accessibilityId") or "").strip()
    text = str(probe.get("text") or "").strip()
    bounds = str(probe.get("bounds") or "").strip()
    class_name = str(probe.get("className") or "").strip()

    out: dict[str, Any] = {}
    if rid:
        out["resourceId"] = rid
    if desc:
        out["accessibilityId"] = desc
    if bounds:
        out["bounds"] = bounds
    if text:
        out["uiText"] = text
    if class_name:
        out["className"] = class_name
    if probe.get("tap_pct"):
        out["tap_pct"] = probe["tap_pct"]
    if probe.get("clickable") is not None:
        out["clickable"] = bool(probe.get("clickable"))
    return out


def merge_probe_into_step(
    step: dict[str, Any],
    probe: dict[str, Any],
    *,
    used_locator_kind: str | None,
) -> tuple[dict[str, Any], bool]:
    """将探测到的元素属性合并进步骤；返回 (新步骤, 是否有变更)。"""
    if step.get("learn_locators") is False:
        return step, False

    rid = str(probe.get("resourceIdShort") or "").strip()
    desc = str(probe.get("accessibilityId") or "").strip()
    text = str(probe.get("text") or "").strip()
    bounds = str(probe.get("bounds") or "").strip()

    if not rid and not desc:
        return step, False

    out = dict(step)
    changed = False

    if rid and out.get("resourceId") != rid:
        out["resourceId"] = rid
        changed = True
    if desc and out.get("accessibilityId") != desc:
        out["accessibilityId"] = desc
        changed = True
    if bounds and out.get("bounds") != bounds:
        out["bounds"] = bounds
        changed = True
    if text and out.get("uiText") != text:
        out["uiText"] = text
        changed = True
    class_name = str(probe.get("className") or "").strip()
    if class_name and out.get("className") != class_name:
        out["className"] = class_name
        changed = True

    if is_coordinate_locator_kind(used_locator_kind):
        if "tap_pct" in out and "fallback_tap_pct" not in out:
            out["fallback_tap_pct"] = out["tap_pct"]
            changed = True
        elif probe.get("tap_pct") and "fallback_tap_pct" not in out:
            out["fallback_tap_pct"] = probe["tap_pct"]
            changed = True
        if "tap" in out and "fallback_tap" not in out:
            out["fallback_tap"] = out["tap"]
            changed = True
        elif probe.get("tap") and "fallback_tap" not in out:
            out["fallback_tap"] = probe["tap"]
            changed = True

    learned_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if out.get("locatorLearnedAt") != learned_at:
        out["locatorLearnedAt"] = learned_at
        changed = True

    return out, changed


def persist_fragment_locator_updates(
    path: Path,
    updates: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    """将 step 索引 → 字段补丁 写回片段 JSON 文件。"""
    if not updates:
        return {"ok": True, "changed": False, "path": str(path), "changedSteps": []}

    spec = json.loads(path.read_text(encoding="utf-8"))
    steps = spec.get("steps")
    if not isinstance(steps, list):
        raise ValueError(f"{path} 缺少 steps 数组")

    changed_indices: list[int] = []
    for index in sorted(updates):
        if index < 0 or index >= len(steps):
            continue
        step = steps[index]
        if not isinstance(step, dict):
            continue
        patch = updates[index]
        if not patch:
            continue
        merged = dict(step)
        merged.update(patch)
        if merged != step:
            steps[index] = merged
            changed_indices.append(index)

    if not changed_indices:
        return {
            "ok": True,
            "changed": False,
            "path": str(path),
            "changedSteps": [],
        }

    path.write_text(
        json.dumps(spec, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "ok": True,
        "changed": True,
        "path": str(path),
        "changedSteps": changed_indices,
        "fragmentId": spec.get("id"),
        "fragmentName": spec.get("name"),
    }


def build_locator_patch(
    step: dict[str, Any],
    probe: dict[str, Any],
    *,
    used_locator_kind: str | None,
) -> dict[str, Any] | None:
    merged, changed = merge_probe_into_step(
        step, probe, used_locator_kind=used_locator_kind
    )
    if not changed:
        return None
    patch: dict[str, Any] = {}
    for key in (
        "resourceId",
        "accessibilityId",
        "bounds",
        "uiText",
        "className",
        "fallback_tap_pct",
        "fallback_tap",
        "locatorLearnedAt",
    ):
        if key in merged and merged.get(key) != step.get(key):
            patch[key] = merged[key]
    return patch or None
