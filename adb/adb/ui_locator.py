"""UI 元素定位：uiautomator dump → Resource-ID / Accessibility-ID / XPath → 点击坐标。"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any, Literal

from .coords import pct_to_pixel
from .device import display_size, run_adb

LocatorKind = Literal[
    "resourceId",
    "accessibilityId",
    "xpath",
    "tap_pct",
    "tap",
]


class LocatorNotFoundError(ValueError):
    """所有定位策略均未命中。"""


def dump_ui_xml(*, serial: str) -> str:
    run_adb(["shell", "uiautomator", "dump", "/sdcard/ui.xml"], serial=serial, check=True)
    proc = run_adb(["shell", "cat", "/sdcard/ui.xml"], serial=serial, check=True)
    raw = proc.stdout.decode("utf-8", errors="replace")
    return re.sub(r"\sxmlns[^=]*=\"[^\"]*\"", "", raw)


def _short_resource_id(resource_id: str) -> str:
    rid = str(resource_id or "").strip()
    if not rid:
        return ""
    return rid.split("/")[-1]


def _resource_id_matches(node_rid: str, target: str) -> bool:
    target = str(target).strip()
    if not target:
        return False
    node_short = _short_resource_id(node_rid)
    target_short = _short_resource_id(target)
    return node_rid == target or node_short == target_short or node_short == target


def _bounds_center(bounds: str) -> tuple[int, int] | None:
    match = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds or "")
    if not match:
        return None
    x1, y1, x2, y2 = map(int, match.groups())
    return (x1 + x2) // 2, (y1 + y2) // 2


def _node_info(node: ET.Element) -> dict[str, Any]:
    attrs = node.attrib
    bounds = attrs.get("bounds") or ""
    center = _bounds_center(bounds)
    return {
        "resourceId": attrs.get("resource-id") or "",
        "resourceIdShort": _short_resource_id(attrs.get("resource-id") or ""),
        "accessibilityId": (attrs.get("content-desc") or "").strip(),
        "text": (attrs.get("text") or "").strip(),
        "className": (attrs.get("class") or "").strip(),
        "clickable": attrs.get("clickable") == "true",
        "bounds": bounds,
        "center": center,
    }


def find_by_resource_id(
    xml_text: str,
    resource_id: str,
    *,
    prefer_clickable: bool = True,
    index: int = 0,
) -> dict[str, Any] | None:
    root = ET.fromstring(xml_text)
    matches: list[dict[str, Any]] = []

    def walk(node: ET.Element) -> None:
        info = _node_info(node)
        if _resource_id_matches(info["resourceId"], resource_id) and info["center"]:
            matches.append(info)
        for child in node:
            walk(child)

    walk(root)
    if prefer_clickable:
        clickable = [m for m in matches if m["clickable"]]
        if clickable:
            matches = clickable
    if not matches or index >= len(matches):
        return None
    hit = matches[index]
    x, y = hit["center"]
    return {**hit, "x": x, "y": y, "locatorKind": "resourceId", "locatorValue": resource_id}


def find_by_accessibility_id(
    xml_text: str,
    accessibility_id: str,
    *,
    prefer_clickable: bool = True,
    index: int = 0,
    match_text: bool = False,
) -> dict[str, Any] | None:
    target = str(accessibility_id).strip()
    if not target:
        return None
    root = ET.fromstring(xml_text)
    matches: list[dict[str, Any]] = []

    def walk(node: ET.Element) -> None:
        info = _node_info(node)
        desc = info["accessibilityId"]
        text = info["text"]
        hit = desc == target or (match_text and text == target)
        if hit and info["center"]:
            matches.append(info)
        for child in node:
            walk(child)

    walk(root)
    if prefer_clickable:
        clickable = [m for m in matches if m["clickable"]]
        if clickable:
            matches = clickable
    if not matches or index >= len(matches):
        return None
    hit = matches[index]
    x, y = hit["center"]
    return {
        **hit,
        "x": x,
        "y": y,
        "locatorKind": "accessibilityId",
        "locatorValue": target,
    }


def find_by_xpath(
    xml_text: str,
    xpath: str,
    *,
    index: int = 0,
) -> dict[str, Any] | None:
    expr = str(xpath).strip()
    if not expr:
        return None
    root = ET.fromstring(xml_text)
    try:
        nodes = root.findall(expr)
    except ET.ParseError as exc:
        raise ValueError(f"无效 XPath: {expr}") from exc
    candidates: list[dict[str, Any]] = []
    for node in nodes:
        info = _node_info(node)
        if info["center"]:
            candidates.append(info)
    if not candidates or index >= len(candidates):
        return None
    hit = candidates[index]
    x, y = hit["center"]
    return {**hit, "x": x, "y": y, "locatorKind": "xpath", "locatorValue": expr}


def _normalize_strategy(raw: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError(f"定位策略须为 object: {raw}")
    out = dict(raw)
    if "accessibility_id" in out and "accessibilityId" not in out:
        out["accessibilityId"] = out.pop("accessibility_id")
    if "contentDesc" in out and "accessibilityId" not in out:
        out["accessibilityId"] = out.pop("contentDesc")
    if "content-desc" in out and "accessibilityId" not in out:
        out["accessibilityId"] = out.pop("content-desc")
    if "resource_id" in out and "resourceId" not in out:
        out["resourceId"] = out.pop("resource_id")
    return out


def build_strategy_chain(step: dict[str, Any]) -> list[dict[str, Any]]:
    """从片段步骤解析定位策略链（按优先级顺序尝试）。"""
    if "tap_locate" in step:
        raw_chain = step["tap_locate"]
        if not isinstance(raw_chain, list) or not raw_chain:
            raise ValueError("tap_locate 须为非空数组")
        return [_normalize_strategy(item) for item in raw_chain]

    chain: list[dict[str, Any]] = []
    for key in ("resourceId", "accessibilityId", "xpath"):
        if step.get(key):
            chain.append({key: step[key], "index": step.get("index", 0)})
    if "tap_pct" in step:
        chain.append({"tap_pct": step["tap_pct"]})
    if "tap" in step:
        chain.append({"tap": step["tap"]})
    if "fallback_tap_pct" in step:
        chain.append({"tap_pct": step["fallback_tap_pct"]})
    if "fallback_tap" in step:
        chain.append({"tap": step["fallback_tap"]})
    return chain


def _resolve_static_tap(
    strategy: dict[str, Any],
    *,
    width: int,
    height: int,
    mirror_x: bool,
) -> dict[str, Any]:
    from .rtl import mirror_x_pct, mirror_x_pixel

    if "tap_pct" in strategy:
        pct = strategy["tap_pct"]
        if not isinstance(pct, (list, tuple)) or len(pct) != 2:
            raise ValueError(f"tap_pct 须为 [x, y]: {strategy}")
        x_pct, y_pct = float(pct[0]), float(pct[1])
        if mirror_x:
            x_pct = mirror_x_pct(x_pct)
        x, y = pct_to_pixel(width, height, x_pct, y_pct)
        return {
            "x": x,
            "y": y,
            "locatorKind": "tap_pct",
            "locatorValue": [x_pct, y_pct],
        }
    if "tap" in strategy:
        xy = strategy["tap"]
        if not isinstance(xy, (list, tuple)) or len(xy) != 2:
            raise ValueError(f"tap 须为 [x, y]: {strategy}")
        x, y = int(xy[0]), int(xy[1])
        if mirror_x:
            x = mirror_x_pixel(x, width=width)
        return {"x": x, "y": y, "locatorKind": "tap", "locatorValue": [x, y]}
    raise ValueError(f"静态坐标策略缺少 tap/tap_pct: {strategy}")


def resolve_tap_from_step(
    step: dict[str, Any],
    *,
    serial: str,
    width: int,
    height: int,
    mirror_x: bool = False,
    prefer_clickable: bool = True,
) -> dict[str, Any]:
    """
    按策略链解析点击坐标。
    支持：tap_locate 数组，或 resourceId/accessibilityId/xpath + fallback_tap(_pct)。
    """
    strategies = build_strategy_chain(step)
    if not strategies:
        raise LocatorNotFoundError("步骤未提供任何定位策略")

    attempts: list[dict[str, Any]] = []
    xml_text: str | None = None
    index = int(step.get("index", 0))

    for strategy in strategies:
        try:
            if "resourceId" in strategy:
                if xml_text is None:
                    xml_text = dump_ui_xml(serial=serial)
                hit = find_by_resource_id(
                    xml_text,
                    str(strategy["resourceId"]),
                    prefer_clickable=prefer_clickable,
                    index=int(strategy.get("index", index)),
                )
                if hit:
                    if mirror_x:
                        from .rtl import mirror_x_pixel

                        hit["x"] = mirror_x_pixel(hit["x"], width=width)
                        hit["rtlMirrored"] = True
                    attempts.append({"ok": True, **hit})
                    return {**hit, "attempts": attempts}
                attempts.append(
                    {
                        "ok": False,
                        "locatorKind": "resourceId",
                        "locatorValue": strategy["resourceId"],
                    }
                )
                continue

            if "accessibilityId" in strategy:
                if xml_text is None:
                    xml_text = dump_ui_xml(serial=serial)
                hit = find_by_accessibility_id(
                    xml_text,
                    str(strategy["accessibilityId"]),
                    prefer_clickable=prefer_clickable,
                    index=int(strategy.get("index", index)),
                    match_text=bool(strategy.get("matchText", False)),
                )
                if hit:
                    if mirror_x:
                        from .rtl import mirror_x_pixel

                        hit["x"] = mirror_x_pixel(hit["x"], width=width)
                        hit["rtlMirrored"] = True
                    attempts.append({"ok": True, **hit})
                    return {**hit, "attempts": attempts}
                attempts.append(
                    {
                        "ok": False,
                        "locatorKind": "accessibilityId",
                        "locatorValue": strategy["accessibilityId"],
                    }
                )
                continue

            if "xpath" in strategy:
                if xml_text is None:
                    xml_text = dump_ui_xml(serial=serial)
                hit = find_by_xpath(
                    xml_text,
                    str(strategy["xpath"]),
                    index=int(strategy.get("index", index)),
                )
                if hit:
                    if mirror_x:
                        from .rtl import mirror_x_pixel

                        hit["x"] = mirror_x_pixel(hit["x"], width=width)
                        hit["rtlMirrored"] = True
                    attempts.append({"ok": True, **hit})
                    return {**hit, "attempts": attempts}
                attempts.append(
                    {
                        "ok": False,
                        "locatorKind": "xpath",
                        "locatorValue": strategy["xpath"],
                    }
                )
                continue

            static = _resolve_static_tap(
                strategy, width=width, height=height, mirror_x=mirror_x
            )
            attempts.append({"ok": True, **static})
            return {**static, "attempts": attempts}
        except ValueError as exc:
            attempts.append({"ok": False, "error": str(exc), "strategy": strategy})

    raise LocatorNotFoundError(
        f"所有定位策略均未命中: {attempts}"
    )


def find_element_at_point(
    xml_text: str,
    x: int,
    y: int,
    *,
    width: int | None = None,
    height: int | None = None,
    prefer_clickable: bool = True,
    max_area_ratio: float = 0.35,
) -> dict[str, Any] | None:
    """在 uiautomator dump 中查找包含点击点的最合适节点（偏小、可点、有 id）。"""
    root = ET.fromstring(xml_text)
    hits: list[dict[str, Any]] = []
    screen_area = (width or 1080) * (height or 2340)
    max_area = int(screen_area * max_area_ratio)

    def walk(node: ET.Element) -> None:
        info = _node_info(node)
        bounds = info.get("bounds") or ""
        match = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds)
        if not match:
            for child in node:
                walk(child)
            return
        x1, y1, x2, y2 = map(int, match.groups())
        if x1 <= x <= x2 and y1 <= y <= y2:
            area = max(1, (x2 - x1) * (y2 - y1))
            if area <= max_area:
                cx, cy = info["center"] or (x, y)
                rid = str(info.get("resourceIdShort") or "").strip()
                desc = str(info.get("accessibilityId") or "").strip()
                text = str(info.get("text") or "").strip()
                hits.append(
                    {
                        **info,
                        "area": area,
                        "x": cx,
                        "y": cy,
                        "hasId": bool(rid or desc or text),
                    }
                )
        for child in node:
            walk(child)

    walk(root)
    if not hits:
        # 放宽面积上限再试（底栏等区域可能被父布局包裹）
        max_area = int(screen_area * 0.85)

        def walk_relaxed(node: ET.Element) -> None:
            info = _node_info(node)
            bounds = info.get("bounds") or ""
            match = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds)
            if not match:
                for child in node:
                    walk_relaxed(child)
                return
            x1, y1, x2, y2 = map(int, match.groups())
            if x1 <= x <= x2 and y1 <= y <= y2:
                area = max(1, (x2 - x1) * (y2 - y1))
                if area <= max_area:
                    cx, cy = info["center"] or (x, y)
                    rid = str(info.get("resourceIdShort") or "").strip()
                    desc = str(info.get("accessibilityId") or "").strip()
                    text = str(info.get("text") or "").strip()
                    hits.append(
                        {
                            **info,
                            "area": area,
                            "x": cx,
                            "y": cy,
                            "hasId": bool(rid or desc or text),
                        }
                    )
            for child in node:
                walk_relaxed(child)

        walk_relaxed(root)
    if not hits:
        return None

    def score(h: dict[str, Any]) -> tuple[int, int, int, int]:
        clickable_rank = 0 if (not prefer_clickable or h.get("clickable")) else 1
        id_rank = 0 if h.get("hasId") else 1
        tab_rank = 0 if str(h.get("resourceIdShort", "")).startswith("tab_") else 1
        return (clickable_rank, id_rank, tab_rank, int(h["area"]))

    hits.sort(key=score)
    best = hits[0]
    rid = str(best.get("resourceIdShort") or "").strip()
    desc = str(best.get("accessibilityId") or "").strip()
    if not rid and not desc and not best.get("text"):
        return None
    return {
        **best,
        "locatorKind": "at_point",
        "locatorValue": [x, y],
    }


def probe_locator_at_point(
    *,
    serial: str,
    x: int,
    y: int,
    width: int | None = None,
    height: int | None = None,
) -> dict[str, Any] | None:
    if width is None or height is None:
        width, height = display_size(serial)
    xml_text = dump_ui_xml(serial=serial)
    hit = find_element_at_point(xml_text, x, y, width=width, height=height)
    if not hit:
        return None
    x_pct = round(x / width, 3)
    y_pct = round(y / height, 3)
    hit["tap_pct"] = [x_pct, y_pct]
    hit["tap"] = [x, y]
    return hit


def is_coordinate_locator_kind(kind: str | None) -> bool:
    return kind in ("tap_pct", "tap", "at_point", None)


def is_locator_step(step: dict[str, Any]) -> bool:
    if "tap_locate" in step:
        return True
    if any(step.get(k) for k in ("resourceId", "accessibilityId", "xpath")):
        return True
    if "tap" in step or "tap_pct" in step:
        return True
    if "fallback_tap" in step or "fallback_tap_pct" in step:
        return True
    return False
