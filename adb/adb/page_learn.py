"""App 页面学习：扫描底栏各帧可点入口，结合知识库沉淀片段。"""

from __future__ import annotations

import json
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from .actions import keyevent, swipe, tap
from .activity import get_foreground_activity
from .device import display_size, run_adb
from .fragment_locator import locator_fields_from_probe
from .recorded_scripts import list_catalog, load_test_accounts, scripts_root
from .project_paths import moa_template, repo_root
from .ui_locator import find_element_at_point, probe_locator_at_point
from .vip_grant import dispatch_vip_try

TabName = Literal["game", "room", "msg", "moment", "me"]
TabFilter = TabName | Literal["all"]

TAB_META: dict[TabName, dict[str, Any]] = {
    "game": {
        "module": "游戏",
        "label": "Game",
        "tap_pct": [0.1, 0.956],
        "resourceId": "tab_game",
    },
    "room": {
        "module": "房间",
        "label": "Room",
        "tap_pct": [0.3, 0.956],
        "resourceId": "tab_room",
    },
    "msg": {
        "module": "消息",
        "label": "Message",
        "tap_pct": [0.5, 0.956],
        "resourceId": "tab_msg",
    },
    "moment": {
        "module": "动态",
        "label": "Moment",
        "tap_pct": [0.7, 0.956],
        "resourceId": "tab_feed",
    },
    "me": {
        "module": "个人主页",
        "label": "Me",
        "tap_pct": [0.9, 0.956],
        "resourceId": "tab_profile",
    },
}

_SKIP_TEXT = frozenset({"Game", "Room", "Message", "Moment", "Me", "Dev"})
_VIP_TEXT_RE = re.compile(r"VIP\s*(\d+)|Active\s+VIP(\d+)", re.I)
_CLICKABLE_RIDS = frozenset(
    {"check_in", "cl_visitor", "friend_ll", "follow_ll", "fans_ll"}
)

CATALOG_PATH = scripts_root() / "页面地图.json"


@dataclass
class PageEntry:
    tab: TabName
    module: str
    label: str
    resourceId: str
    tap_pct: list[float]
    scrollDown: int = 0
    clickable: bool = True
    accessibilityId: str = ""
    bounds: str = ""
    uiText: str = ""
    className: str = ""
    locatorLearnedAt: str = ""
    activity: dict[str, Any] | None = None
    uiSample: str = ""
    vipRequired: int | None = None
    fragmentId: str | None = None
    kbRef: list[str] = field(default_factory=list)
    probed: bool = False


def entry_from_dict(raw: dict[str, Any]) -> PageEntry:
    fields = PageEntry.__dataclass_fields__
    return PageEntry(**{k: raw[k] for k in raw if k in fields})


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def apply_probe_to_entry(
    entry: PageEntry,
    probe: dict[str, Any] | None,
    *,
    stamp: bool = True,
) -> PageEntry:
    """将点击处探测到的元素属性合并进页面地图条目。"""
    if not probe:
        return entry
    fields = locator_fields_from_probe(probe)
    if fields.get("resourceId"):
        entry.resourceId = fields["resourceId"]
    if fields.get("accessibilityId"):
        entry.accessibilityId = fields["accessibilityId"]
    if fields.get("bounds"):
        entry.bounds = fields["bounds"]
    if fields.get("uiText"):
        entry.uiText = fields["uiText"]
    if fields.get("className"):
        entry.className = fields["className"]
    if fields.get("tap_pct"):
        entry.tap_pct = list(fields["tap_pct"])
    if "clickable" in fields:
        entry.clickable = bool(fields["clickable"])
    label = (
        fields.get("uiText")
        or fields.get("accessibilityId")
        or fields.get("resourceId")
        or entry.label
    )
    if label and (not entry.label or entry.label == entry.resourceId):
        entry.label = str(label)
    if stamp:
        entry.locatorLearnedAt = _utc_now()
    return entry


def entry_to_tap_step(entry: PageEntry) -> dict[str, Any]:
    """将页面地图条目转为片段 tap 步骤（优先元素属性，坐标作 fallback）。"""
    step: dict[str, Any] = {"tap_pct": list(entry.tap_pct)}
    if entry.resourceId:
        step["resourceId"] = entry.resourceId
    if entry.accessibilityId:
        step["accessibilityId"] = entry.accessibilityId
    if entry.bounds:
        step["bounds"] = entry.bounds
    if entry.uiText:
        step["uiText"] = entry.uiText
    if entry.className:
        step["className"] = entry.className
    if entry.resourceId or entry.accessibilityId:
        step["fallback_tap_pct"] = list(entry.tap_pct)
    if entry.label:
        step["note"] = entry.label
    if entry.locatorLearnedAt:
        step["locatorLearnedAt"] = entry.locatorLearnedAt
    return step


def _dump_ui_xml(serial: str) -> str:
    run_adb(["shell", "uiautomator", "dump", "/sdcard/ui.xml"], serial=serial, check=True)
    proc = run_adb(["shell", "cat", "/sdcard/ui.xml"], serial=serial, check=True)
    raw = proc.stdout.decode("utf-8", errors="replace")
    return re.sub(r"\sxmlns[^=]*=\"[^\"]*\"", "", raw)


def _ui_texts(xml_text: str) -> str:
    return " ".join(re.findall(r'text="([^"]+)"', xml_text))


def _parse_nodes(xml_text: str, *, width: int, height: int) -> list[dict[str, Any]]:
    root = ET.fromstring(xml_text)
    nodes: list[dict[str, Any]] = []

    def walk(node: ET.Element) -> None:
        attrs = node.attrib
        text = (attrs.get("text") or "").strip()
        desc = (attrs.get("content-desc") or "").strip()
        rid = (attrs.get("resource-id") or "").split("/")[-1]
        clickable = attrs.get("clickable") == "true"
        bounds = attrs.get("bounds") or ""
        match = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds)
        if match:
            x1, y1, x2, y2 = map(int, match.groups())
            label = text or desc
            nodes.append(
                {
                    "text": text,
                    "desc": desc,
                    "label": label,
                    "resourceId": rid,
                    "accessibilityId": desc,
                    "uiText": text,
                    "className": (attrs.get("class") or "").strip(),
                    "bounds": bounds,
                    "clickable": clickable,
                    "x1": x1,
                    "y1": y1,
                    "x2": x2,
                    "y2": y2,
                    "tap_pct": [
                        round((x1 + x2) / 2 / width, 3),
                        round((y1 + y2) / 2 / height, 3),
                    ],
                }
            )
        for child in node:
            walk(child)

    walk(root)
    return nodes


def switch_tab(serial: str, tab: TabName) -> None:
    width, height = display_size(serial)
    px, py = TAB_META[tab]["tap_pct"]
    tap(x=int(px * width), y=int(py * height), serial=serial)
    time.sleep(0.8)


def scroll_tab(
    serial: str,
    direction: Literal["up", "down"],
    *,
    times: int = 1,
) -> None:
    width, height = display_size(serial)
    cx = width // 2
    for _ in range(times):
        if direction == "down":
            swipe(
                x1=cx,
                y1=int(height * 0.73),
                x2=cx,
                y2=int(height * 0.38),
                duration_ms=350,
                serial=serial,
            )
        else:
            swipe(
                x1=cx,
                y1=int(height * 0.38),
                x2=cx,
                y2=int(height * 0.73),
                duration_ms=300,
                serial=serial,
            )
        time.sleep(0.35)


def scan_tab_entries(
    serial: str,
    tab: TabName,
    *,
    scroll_passes: int = 6,
    y_min: int = 200,
    y_max: int = 2100,
) -> list[PageEntry]:
    """扫描某底栏帧内可见/可滚动入口（不点击）。"""
    width, height = display_size(serial)
    meta = TAB_META[tab]
    switch_tab(serial, tab)
    scroll_tab(serial, "up", times=4)

    seen: dict[tuple[str, str], PageEntry] = {}
    for scroll_idx in range(scroll_passes):
        xml_text = _dump_ui_xml(serial)
        nodes = _parse_nodes(xml_text, width=width, height=height)
        for node in nodes:
            y1 = node["y1"]
            if y1 < y_min or y1 > y_max:
                continue
            label = node["label"]
            rid = node["resourceId"]
            if not label and not rid:
                continue
            if label in _SKIP_TEXT:
                continue
            if label.isdigit() and len(label) <= 3:
                continue
            if rid.startswith("tab_"):
                continue
            if (
                not node["clickable"]
                and not rid.endswith("_layout")
                and rid not in _CLICKABLE_RIDS
            ):
                continue
            key = (label or rid, rid)
            cx = (node["x1"] + node["x2"]) // 2
            cy = (node["y1"] + node["y2"]) // 2
            probe = find_element_at_point(
                xml_text, cx, cy, width=width, height=height
            )
            entry = PageEntry(
                tab=tab,
                module=meta["module"],
                label=label or rid,
                resourceId=rid,
                tap_pct=node["tap_pct"],
                scrollDown=scroll_idx,
                clickable=node["clickable"],
                accessibilityId=node.get("accessibilityId") or "",
                bounds=node.get("bounds") or "",
                uiText=node.get("uiText") or "",
                className=node.get("className") or "",
            )
            apply_probe_to_entry(entry, probe, stamp=True)
            if key not in seen or y1 < seen[key].tap_pct[1] * height:
                seen[key] = entry
        scroll_tab(serial, "down", times=1)

    return sorted(seen.values(), key=lambda e: (e.scrollDown, e.tap_pct[1]))


def scan_all_tabs(
    serial: str,
    *,
    tabs: list[TabName] | None = None,
    scroll_passes: int = 6,
) -> list[PageEntry]:
    chosen = tabs or list(TAB_META.keys())
    all_entries: list[PageEntry] = []
    for tab in chosen:
        all_entries.extend(scan_tab_entries(serial, tab, scroll_passes=scroll_passes))
    return all_entries


def detect_vip_level(ui_text: str) -> int | None:
    match = _VIP_TEXT_RE.search(ui_text)
    if match:
        return int(next(g for g in match.groups() if g))
    if any(token in ui_text for token in ("Activate Now", "Active VIP", "Unlock")):
        return 1
    return None


def _resolve_user_id(account: str) -> str | None:
    acct = load_test_accounts().get(account)
    if not isinstance(acct, dict):
        return None
    uid = str(acct.get("userId", "")).strip()
    return uid or None


def _tap_entry(serial: str, entry: PageEntry) -> None:
    width, height = display_size(serial)
    switch_tab(serial, entry.tab)
    scroll_tab(serial, "up", times=4)
    scroll_tab(serial, "down", times=entry.scrollDown)
    probe = probe_locator_at_point(
        serial=serial,
        x=int(entry.tap_pct[0] * width),
        y=int(entry.tap_pct[1] * height),
        width=width,
        height=height,
    )
    apply_probe_to_entry(entry, probe, stamp=True)
    tap(
        x=int(entry.tap_pct[0] * width),
        y=int(entry.tap_pct[1] * height),
        serial=serial,
    )
    time.sleep(1.2)


def _back_after_probe(serial: str, activity: dict[str, Any] | None) -> None:
    hint = str((activity or {}).get("hint", ""))
    if hint == "in_room":
        width, height = display_size(serial)
        tap(x=int(width * 0.94), y=int(height * 0.053), serial=serial)
        time.sleep(0.6)
        tap(x=int(width * 0.875), y=int(height * 0.145), serial=serial)
        time.sleep(0.6)
        tap(x=int(width * 0.284), y=int(height * 0.588), serial=serial)
        time.sleep(0.8)
        return
    backs = 2 if hint in ("webview", "visitor", "unknown") else 1
    for _ in range(backs):
        keyevent(code=4, serial=serial)
        time.sleep(0.55)


def probe_entry(
    serial: str,
    entry: PageEntry,
    *,
    user_id: str | None = None,
    auto_vip: bool = True,
) -> PageEntry:
    """点击单个入口并记录 activity；遇 VIP 门控可 MOA 下发体验卡后重试。"""
    _tap_entry(serial, entry)
    xml = _dump_ui_xml(serial)
    ui_text = _ui_texts(xml)
    activity = get_foreground_activity(serial=serial)
    vip_level = detect_vip_level(ui_text)

    if vip_level and auto_vip and user_id:
        dispatch_vip_try(user_id, vip_level)
        tpl = moa_template("VIP-下发体验卡.json")
        entry.kbRef.append(str(tpl.relative_to(repo_root())))
        _back_after_probe(serial, activity)
        _tap_entry(serial, entry)
        xml = _dump_ui_xml(serial)
        ui_text = _ui_texts(xml)
        activity = get_foreground_activity(serial=serial)

    entry.activity = activity
    entry.uiSample = ui_text[:240]
    entry.vipRequired = vip_level
    entry.probed = True
    return entry


def load_catalog(*, path: Path | None = None) -> list[PageEntry]:
    target = path or CATALOG_PATH
    if not target.is_file():
        return []
    data = json.loads(target.read_text(encoding="utf-8"))
    entries = data.get("entries", [])
    if not isinstance(entries, list):
        return []
    return [entry_from_dict(item) for item in entries if isinstance(item, dict)]


def save_catalog(entries: list[PageEntry], *, path: Path | None = None) -> Path:
    target = path or CATALOG_PATH
    payload = {
        "title": "Yaahlan App 页面地图（自动扫描）",
        "note": "learn scan 列入口并探测 resourceId/accessibilityId/bounds；learn probe 补 activity。落片段可用 entry_to_tap_step。",
        "tabs": {k: v["module"] for k, v in TAB_META.items()},
        "entries": [asdict(e) for e in entries],
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def merge_catalog(
    existing: list[PageEntry],
    scanned: list[PageEntry],
) -> list[PageEntry]:
    """保留已 probe 的 activity，合并新 scan 坐标。"""
    probed_by_key = {
        (e.label, e.resourceId, e.tab): e
        for e in existing
        if e.probed
    }
    merged: list[PageEntry] = []
    for entry in scanned:
        key = (entry.label, entry.resourceId, entry.tab)
        old = probed_by_key.get(key)
        if old:
            entry.activity = old.activity
            entry.uiSample = old.uiSample
            entry.vipRequired = old.vipRequired
            entry.kbRef = list(old.kbRef)
            entry.probed = True
            entry.fragmentId = old.fragmentId
            for attr in (
                "accessibilityId",
                "bounds",
                "uiText",
                "className",
                "locatorLearnedAt",
            ):
                if not getattr(entry, attr) and getattr(old, attr):
                    setattr(entry, attr, getattr(old, attr))
        merged.append(entry)
    return merged


def existing_fragment_ids() -> set[str]:
    return {item["id"] for item in list_catalog() if item.get("kind") == "fragment"}


def _tabs_from_filter(tab: TabFilter) -> list[TabName] | None:
    if tab == "all":
        return None
    return [tab]


def run_scan(
    serial: str,
    *,
    tab: TabFilter = "all",
    scroll_passes: int = 6,
) -> dict[str, Any]:
    tabs = _tabs_from_filter(tab)
    scanned = scan_all_tabs(serial, tabs=tabs, scroll_passes=scroll_passes)
    existing = load_catalog()
    if tabs is None:
        merged = merge_catalog(existing, scanned)
    else:
        other = [e for e in existing if e.tab not in tabs]
        merged = other + merge_catalog(
            [e for e in existing if e.tab in tabs],
            scanned,
        )
    path = save_catalog(merged)
    return {
        "ok": True,
        "catalog": str(path),
        "count": len(merged),
        "scanned": len(scanned),
        "tabs": list(TAB_META.keys()) if tabs is None else tabs,
    }


def run_probe(
    serial: str,
    *,
    tab: TabFilter = "all",
    account: str = "familyLeader",
    limit: int = 20,
    auto_vip: bool = True,
    rescan: bool = False,
    scroll_passes: int = 6,
) -> dict[str, Any]:
    tabs = _tabs_from_filter(tab)
    if rescan or not CATALOG_PATH.is_file():
        run_scan(serial, tab=tab, scroll_passes=scroll_passes)

    entries = load_catalog()
    user_id = _resolve_user_id(account)
    tab_filter = None if tab == "all" else tab
    probed_count = 0
    results: list[dict[str, Any]] = []

    for entry in entries:
        if probed_count >= limit:
            break
        if entry.probed:
            continue
        if tab_filter and entry.tab != tab_filter:
            continue
        if tabs and entry.tab not in tabs:
            continue

        probe_entry(serial, entry, user_id=user_id, auto_vip=auto_vip)
        _back_after_probe(serial, entry.activity)
        probed_count += 1
        results.append(
            {
                "label": entry.label,
                "tab": entry.tab,
                "activity": (entry.activity or {}).get("shortName"),
                "hint": (entry.activity or {}).get("hint"),
            }
        )

    save_catalog(entries)
    return {
        "ok": True,
        "probed": probed_count,
        "catalog": str(CATALOG_PATH),
        "results": results,
        "remaining": sum(
            1
            for e in entries
            if not e.probed and (tab_filter is None or e.tab == tab_filter)
        ),
    }
