"""工具台能力目录左侧分组树（catalog_nav.json）读写与校验。"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

WEB_AGENT_DIR = Path(__file__).resolve().parent
CATALOG_NAV_PATH = WEB_AGENT_DIR / "config" / "catalog_nav.json"
CATALOG_NAV_BACKUP_DIR = WEB_AGENT_DIR / "data" / "catalog_nav_backups"
CATALOG_NAV_BACKUP_KEEP = 30
MAX_FOLDER_DEPTH = 12


def load_catalog_nav(path: Path | None = None) -> dict[str, Any]:
    target = path or CATALOG_NAV_PATH
    if not target.is_file():
        return {"version": 1, "collapsed": [], "tree": []}
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"version": 1, "collapsed": [], "tree": []}
        tree = data.get("tree")
        collapsed = data.get("collapsed")
        if not isinstance(tree, list):
            tree = []
        if not isinstance(collapsed, list):
            collapsed = []
        return {"version": 1, "collapsed": [str(x) for x in collapsed if str(x).strip()], "tree": tree}
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "collapsed": [], "tree": []}


def build_default_nav_tree(modules: list[dict[str, Any]], *, include_playbook: bool) -> list[dict[str, Any]]:
    tree: list[dict[str, Any]] = [{"kind": "all"}]
    if include_playbook:
        tree.append({"kind": "playbook"})
    for mod in modules:
        if not isinstance(mod, dict):
            continue
        module_id = str(mod.get("id") or "").strip()
        if module_id:
            tree.append({"kind": "module", "moduleId": module_id})
    return tree


def _collect_module_ids(nodes: list[Any]) -> set[str]:
    found: set[str] = set()
    for node in nodes:
        if not isinstance(node, dict):
            continue
        kind = str(node.get("kind") or "").strip()
        if kind == "module":
            mid = str(node.get("moduleId") or "").strip()
            if mid:
                found.add(mid)
        elif kind == "folder":
            children = node.get("children")
            if isinstance(children, list):
                found |= _collect_module_ids(children)
    return found


def reconcile_nav_tree(
    tree: list[Any],
    modules: list[dict[str, Any]],
    *,
    include_playbook: bool,
) -> list[dict[str, Any]]:
    """校验并保留用户目录树；移除已不存在的 module 叶子（不在树尾追加新 module）。"""
    valid_ids = {
        str(mod.get("id") or "").strip()
        for mod in modules
        if isinstance(mod, dict) and str(mod.get("id") or "").strip()
    }

    def walk(nodes: list[Any]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for raw in nodes:
            if not isinstance(raw, dict):
                continue
            kind = str(raw.get("kind") or "").strip()
            if kind == "all":
                out.append({"kind": "all"})
            elif kind == "playbook":
                if include_playbook:
                    children_raw = raw.get("children")
                    if not isinstance(children_raw, list):
                        children_raw = []
                    children = walk(children_raw)
                    entry: dict[str, Any] = {"kind": "playbook"}
                    nav_label = str(raw.get("navLabel") or "").strip()
                    if nav_label:
                        entry["navLabel"] = nav_label
                    if children:
                        entry["children"] = children
                    out.append(entry)
            elif kind == "module":
                mid = str(raw.get("moduleId") or "").strip()
                if mid and mid in valid_ids:
                    children_raw = raw.get("children")
                    if not isinstance(children_raw, list):
                        children_raw = []
                    children = walk(children_raw)
                    entry: dict[str, Any] = {"kind": "module", "moduleId": mid}
                    nav_label = str(raw.get("navLabel") or "").strip()
                    if nav_label:
                        entry["navLabel"] = nav_label
                    if children:
                        entry["children"] = children
                    out.append(entry)
            elif kind == "folder":
                folder_id = str(raw.get("id") or "").strip()
                label = str(raw.get("label") or "").strip()
                children_raw = raw.get("children")
                if not folder_id or not label:
                    continue
                if not isinstance(children_raw, list):
                    children_raw = []
                children = walk(children_raw)
                entry: dict[str, Any] = {
                    "kind": "folder",
                    "id": folder_id,
                    "label": label,
                    "children": children,
                }
                if raw.get("subfolder") is True:
                    entry["subfolder"] = True
                out.append(entry)
        return out

    merged = walk(tree)
    if not merged:
        merged = build_default_nav_tree(modules, include_playbook=include_playbook)
        return merged

    has_all = any(n.get("kind") == "all" for n in merged)
    if not has_all:
        merged.insert(0, {"kind": "all"})

    return merged


def _normalize_nodes(raw_nodes: Any, depth: int = 0) -> list[dict[str, Any]] | None:
    if not isinstance(raw_nodes, list):
        return None
    if depth > MAX_FOLDER_DEPTH:
        return None
    out: list[dict[str, Any]] = []
    for raw in raw_nodes:
        if not isinstance(raw, dict):
            return None
        kind = str(raw.get("kind") or "").strip()
        if kind == "all":
            out.append({"kind": "all"})
        elif kind == "playbook":
            children_raw = raw.get("children")
            if not isinstance(children_raw, list):
                children_raw = []
            children = _normalize_nodes(children_raw, depth + 1)
            if children is None:
                return None
            entry: dict[str, Any] = {"kind": "playbook"}
            nav_label = str(raw.get("navLabel") or "").strip()
            if nav_label:
                entry["navLabel"] = nav_label
            if children:
                entry["children"] = children
            out.append(entry)
        elif kind == "module":
            module_id = str(raw.get("moduleId") or "").strip()
            if not module_id:
                return None
            children_raw = raw.get("children")
            if not isinstance(children_raw, list):
                children_raw = []
            children = _normalize_nodes(children_raw, depth + 1)
            if children is None:
                return None
            entry: dict[str, Any] = {"kind": "module", "moduleId": module_id}
            nav_label = str(raw.get("navLabel") or "").strip()
            if nav_label:
                entry["navLabel"] = nav_label
            if children:
                entry["children"] = children
            out.append(entry)
        elif kind == "folder":
            folder_id = str(raw.get("id") or "").strip()
            label = str(raw.get("label") or "").strip()
            children_raw = raw.get("children")
            if not folder_id or not label:
                return None
            if not isinstance(children_raw, list):
                children_raw = []
            children = _normalize_nodes(children_raw, depth + 1)
            if children is None:
                return None
            entry: dict[str, Any] = {
                "kind": "folder",
                "id": folder_id,
                "label": label,
                "children": children,
            }
            if raw.get("subfolder") is True:
                entry["subfolder"] = True
            out.append(entry)
        else:
            return None
    return out


def normalize_catalog_nav_payload(data: Any) -> dict[str, Any] | None:
    if not isinstance(data, dict):
        return None
    tree_raw = data.get("tree")
    tree = _normalize_nodes(tree_raw, 0)
    if tree is None:
        return None
    collapsed_raw = data.get("collapsed")
    collapsed: list[str] = []
    if isinstance(collapsed_raw, list):
        for item in collapsed_raw:
            cid = str(item or "").strip()
            if cid:
                collapsed.append(cid)
    return {"version": 1, "collapsed": collapsed, "tree": tree}


def _backup_catalog_nav_file(target: Path) -> None:
    if not target.is_file():
        return
    CATALOG_NAV_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_path = CATALOG_NAV_BACKUP_DIR / f"catalog_nav_{ts}.json"
    shutil.copy2(target, backup_path)
    backups = sorted(CATALOG_NAV_BACKUP_DIR.glob("catalog_nav_*.json"))
    overflow = len(backups) - CATALOG_NAV_BACKUP_KEEP
    if overflow > 0:
        for old in backups[:overflow]:
            old.unlink(missing_ok=True)


def save_catalog_nav(data: dict[str, Any], path: Path | None = None) -> None:
    target = path or CATALOG_NAV_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    if target == CATALOG_NAV_PATH:
        _backup_catalog_nav_file(target)
    target.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def folder_ids_in_tree(nodes: Any) -> set[str]:
    out: set[str] = set()
    if not isinstance(nodes, list):
        return out
    for raw in nodes:
        if not isinstance(raw, dict):
            continue
        kind = str(raw.get("kind") or "").strip()
        if kind == "folder":
            folder_id = str(raw.get("id") or "").strip()
            if folder_id:
                out.add(folder_id)
        children = raw.get("children")
        if isinstance(children, list):
            out |= folder_ids_in_tree(children)
    return out


def nav_tree_removed_folder_ids(old_tree: Any, new_tree: Any) -> set[str]:
    return folder_ids_in_tree(old_tree) - folder_ids_in_tree(new_tree)


def catalog_nav_for_response(
    modules: list[dict[str, Any]],
    *,
    include_playbook: bool,
) -> dict[str, Any]:
    stored = load_catalog_nav()
    tree = stored.get("tree") or []
    if not isinstance(tree, list) or not tree:
        tree = build_default_nav_tree(modules, include_playbook=include_playbook)
    else:
        tree = reconcile_nav_tree(tree, modules, include_playbook=include_playbook)
    collapsed = stored.get("collapsed") if isinstance(stored.get("collapsed"), list) else []
    return {"version": 1, "collapsed": [str(x) for x in collapsed if str(x).strip()], "tree": tree}
