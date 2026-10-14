"""工具台能力目录左侧分组树（catalog_nav.json）读写与校验。"""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

WEB_AGENT_DIR = Path(__file__).resolve().parent
CATALOG_NAV_PATH = WEB_AGENT_DIR / "config" / "catalog_nav.json"
CATALOG_NAV_BACKUP_DIR = WEB_AGENT_DIR / "data" / "catalog_nav_backups"
CATALOG_NAV_BACKUP_KEEP = 30
MAX_FOLDER_DEPTH = 12

_CATEGORY_PREFIX_RE = re.compile(r"^([^（(]+)")


def _legacy_split_module_id(category_full_name: str) -> str:
    """category 未命中 top_level_rules 时，catalog 曾用括号前语义 slug 作一级 moduleId。"""
    match = _CATEGORY_PREFIX_RE.match(category_full_name.strip())
    cat_label = (match.group(1).strip() if match else category_full_name.strip()) or "未分类"
    slug = re.sub(r"[\s/]+", "-", cat_label.strip())
    slug = re.sub(r"[^\w\u4e00-\u9fff-]", "", slug, flags=re.UNICODE)
    return slug.lower() or "other"


def _build_cap_lookup(modules: list[dict[str, Any]]) -> dict[str, tuple[str, int]]:
    """legacy moduleId / 完整 category 名 / cap label → (moduleId, catIndex)。"""
    lookup: dict[str, tuple[str, int]] = {}
    for mod in modules:
        if not isinstance(mod, dict):
            continue
        mid = str(mod.get("id") or "").strip()
        if not mid:
            continue
        categories = mod.get("categories")
        if not isinstance(categories, list):
            continue
        for cat_index, cat in enumerate(categories):
            if not isinstance(cat, dict):
                continue
            name = str(cat.get("name") or "").strip()
            if not name:
                continue
            lookup[name] = (mid, cat_index)
            legacy = _legacy_split_module_id(name)
            if legacy:
                lookup[legacy] = (mid, cat_index)
    return lookup


def _cap_needs_remap(
    cap: dict[str, Any],
    *,
    valid_ids: set[str],
    cat_counts: dict[str, int],
) -> bool:
    mid = str(cap.get("moduleId") or "").strip()
    cat_raw = cap.get("catIndex")
    try:
        cat_index = int(cat_raw)
    except (TypeError, ValueError):
        return True
    if mid not in valid_ids or cat_index < 0:
        return True
    return cat_index >= cat_counts.get(mid, 0)


def remap_legacy_nav_caps(
    tree: list[Any],
    modules: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """将误挂 legacy moduleId（如 admin公会）的 cap 归并到合并后的一级模块，并丢弃无效索引。"""
    valid_ids = {
        str(mod.get("id") or "").strip()
        for mod in modules
        if isinstance(mod, dict) and str(mod.get("id") or "").strip()
    }
    cat_counts: dict[str, int] = {}
    for mod in modules:
        if not isinstance(mod, dict):
            continue
        mid = str(mod.get("id") or "").strip()
        if not mid:
            continue
        categories = mod.get("categories")
        cat_counts[mid] = len(categories) if isinstance(categories, list) else 0

    lookup = _build_cap_lookup(modules)

    def resolve_cap(raw: dict[str, Any]) -> dict[str, Any] | None:
        if str(raw.get("kind") or "").strip() != "cap":
            return None
        if not _cap_needs_remap(raw, valid_ids=valid_ids, cat_counts=cat_counts):
            return dict(raw)
        label = str(raw.get("label") or "").strip()
        legacy_mid = str(raw.get("moduleId") or "").strip()
        target: tuple[str, int] | None = None
        if label and label in lookup:
            target = lookup[label]
        elif legacy_mid in lookup:
            target = lookup[legacy_mid]
        if not target:
            return None
        mid, cat_index = target
        entry: dict[str, Any] = {"kind": "cap", "moduleId": mid, "catIndex": cat_index}
        if label:
            entry["label"] = label
        return entry

    def walk(nodes: list[Any]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for raw in nodes:
            if not isinstance(raw, dict):
                continue
            kind = str(raw.get("kind") or "").strip()
            if kind == "cap":
                fixed = resolve_cap(raw)
                if fixed:
                    out.append(fixed)
                continue
            if kind == "module":
                mid = str(raw.get("moduleId") or "").strip()
                children_raw = raw.get("children")
                if not isinstance(children_raw, list):
                    children_raw = []
                children = walk(children_raw)
                if mid in valid_ids:
                    entry: dict[str, Any] = {"kind": "module", "moduleId": mid}
                    nav_label = str(raw.get("navLabel") or "").strip()
                    if nav_label:
                        entry["navLabel"] = nav_label
                    if children:
                        entry["children"] = children
                    out.append(entry)
                else:
                    out.extend(children)
                continue
            if kind == "folder":
                folder_id = str(raw.get("id") or "").strip()
                label = str(raw.get("label") or "").strip()
                children_raw = raw.get("children")
                if not folder_id or not label:
                    continue
                if not isinstance(children_raw, list):
                    children_raw = []
                children = walk(children_raw)
                entry = {
                    "kind": "folder",
                    "id": folder_id,
                    "label": label,
                    "children": children,
                }
                if raw.get("subfolder") is True:
                    entry["subfolder"] = True
                out.append(entry)
                continue
            if kind in ("all", "playbook", "playbookItem"):
                entry = dict(raw)
                children_raw = raw.get("children")
                if isinstance(children_raw, list) and children_raw:
                    entry["children"] = walk(children_raw)
                out.append(entry)
        return out

    return walk(tree)


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
    """目录树中已出现的一级模块 id（含 module 节点与 cap 引用的 moduleId）。"""
    found: set[str] = set()
    for node in nodes:
        if not isinstance(node, dict):
            continue
        kind = str(node.get("kind") or "").strip()
        if kind == "module":
            mid = str(node.get("moduleId") or "").strip()
            if mid:
                found.add(mid)
        elif kind == "cap":
            mid = str(node.get("moduleId") or "").strip()
            if mid:
                found.add(mid)
        children = node.get("children")
        if isinstance(children, list):
            found |= _collect_module_ids(children)
    return found


def _module_ids_with_children(nodes: list[Any]) -> set[str]:
    """树中至少有一处带 children 的 module 节点（含 cap 子节点）。"""
    found: set[str] = set()
    for node in nodes:
        if not isinstance(node, dict):
            continue
        kind = str(node.get("kind") or "").strip()
        children = node.get("children")
        if not isinstance(children, list):
            children = []
        if kind == "module":
            mid = str(node.get("moduleId") or "").strip()
            if mid and children:
                found.add(mid)
        if children:
            found |= _module_ids_with_children(children)
    return found


def _module_ids_referenced_by_caps(nodes: list[Any]) -> set[str]:
    """任意 cap 节点引用的 moduleId（能力已挂到其它分组下）。"""
    found: set[str] = set()
    for node in nodes:
        if not isinstance(node, dict):
            continue
        if str(node.get("kind") or "").strip() == "cap":
            mid = str(node.get("moduleId") or "").strip()
            if mid:
                found.add(mid)
        children = node.get("children")
        if isinstance(children, list):
            found |= _module_ids_referenced_by_caps(children)
    return found


def _prune_duplicate_empty_modules(nodes: list[Any]) -> list[dict[str, Any]]:
    """同一 moduleId 在树中已有带内容的节点时，去掉无 children 的重复 module 空壳。"""
    rich_ids = _module_ids_with_children(nodes) | _module_ids_referenced_by_caps(nodes)

    def walk(raw_nodes: list[Any]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for raw in raw_nodes:
            if not isinstance(raw, dict):
                continue
            kind = str(raw.get("kind") or "").strip()
            if kind == "module":
                mid = str(raw.get("moduleId") or "").strip()
                children_raw = raw.get("children")
                if not isinstance(children_raw, list):
                    children_raw = []
                if mid and not children_raw and mid in rich_ids:
                    continue
                children = walk(children_raw)
                entry: dict[str, Any] = {"kind": "module", "moduleId": mid}
                nav_label = str(raw.get("navLabel") or "").strip()
                if nav_label:
                    entry["navLabel"] = nav_label
                if children:
                    entry["children"] = children
                out.append(entry)
            elif kind in ("folder", "playbook"):
                children_raw = raw.get("children")
                if not isinstance(children_raw, list):
                    children_raw = []
                children = walk(children_raw)
                entry = dict(raw)
                entry["children"] = children
                out.append(entry)
            else:
                out.append(dict(raw))
        return out

    return walk(nodes)


def _tree_has_playbook(nodes: list[Any]) -> bool:
    for node in nodes:
        if not isinstance(node, dict):
            continue
        if str(node.get("kind") or "").strip() == "playbook":
            return True
        children = node.get("children")
        if isinstance(children, list) and _tree_has_playbook(children):
            return True
    return False


def reconcile_nav_tree(
    tree: list[Any],
    modules: list[dict[str, Any]],
    *,
    include_playbook: bool,
) -> list[dict[str, Any]]:
    """校验并保留用户目录树；移除已不存在的 module；在根级补登记后新增的一级模块。"""
    tree = remap_legacy_nav_caps(tree, modules)
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
            elif kind == "cap":
                mid = str(raw.get("moduleId") or "").strip()
                if mid not in valid_ids:
                    continue
                cat_raw = raw.get("catIndex")
                if isinstance(cat_raw, bool):
                    continue
                try:
                    cat_index = int(cat_raw)
                except (TypeError, ValueError):
                    continue
                if cat_index < 0:
                    continue
                entry = {"kind": "cap", "moduleId": mid, "catIndex": cat_index}
                cap_label = str(raw.get("label") or "").strip()
                if cap_label:
                    entry["label"] = cap_label
                out.append(entry)
            elif kind == "playbookItem":
                playbook_id = str(raw.get("playbookId") or "").strip()
                if not playbook_id:
                    continue
                children_raw = raw.get("children")
                if not isinstance(children_raw, list):
                    children_raw = []
                children = [
                    c for c in walk(children_raw)
                    if isinstance(c, dict) and str(c.get("kind") or "") != "pbStep"
                ]
                entry: dict[str, Any] = {
                    "kind": "playbookItem",
                    "playbookId": playbook_id,
                }
                nav_label = str(raw.get("navLabel") or "").strip()
                if nav_label:
                    entry["navLabel"] = nav_label
                if children:
                    entry["children"] = children
                out.append(entry)
            elif kind == "pbStep":
                continue
        return out

    merged = walk(tree)
    merged = _prune_duplicate_empty_modules(merged)
    if not merged:
        merged = build_default_nav_tree(modules, include_playbook=include_playbook)
        return merged

    has_all = any(n.get("kind") == "all" for n in merged)
    if not has_all:
        merged.insert(0, {"kind": "all"})

    present_ids = _collect_module_ids(merged)
    for mod in modules:
        if not isinstance(mod, dict):
            continue
        mid = str(mod.get("id") or "").strip()
        if mid and mid in valid_ids and mid not in present_ids:
            merged.append({"kind": "module", "moduleId": mid})
            present_ids.add(mid)

    if include_playbook and not _tree_has_playbook(merged):
        insert_at = 1 if merged and merged[0].get("kind") == "all" else 0
        merged.insert(insert_at, {"kind": "playbook"})

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
        elif kind == "cap":
            module_id = str(raw.get("moduleId") or "").strip()
            if not module_id:
                return None
            cat_raw = raw.get("catIndex")
            if isinstance(cat_raw, bool):
                return None
            try:
                cat_index = int(cat_raw)
            except (TypeError, ValueError):
                return None
            if cat_index < 0:
                return None
            entry = {"kind": "cap", "moduleId": module_id, "catIndex": cat_index}
            cap_label = str(raw.get("label") or "").strip()
            if cap_label:
                entry["label"] = cap_label
            out.append(entry)
        elif kind == "playbookItem":
            playbook_id = str(raw.get("playbookId") or "").strip()
            if not playbook_id:
                return None
            children_raw = raw.get("children")
            if not isinstance(children_raw, list):
                children_raw = []
            children_norm = _normalize_nodes(children_raw, depth + 1)
            if children_norm is None:
                return None
            children = [
                c for c in children_norm
                if isinstance(c, dict) and str(c.get("kind") or "") != "pbStep"
            ]
            entry: dict[str, Any] = {
                "kind": "playbookItem",
                "playbookId": playbook_id,
            }
            nav_label = str(raw.get("navLabel") or "").strip()
            if nav_label:
                entry["navLabel"] = nav_label
            if children:
                entry["children"] = children
            out.append(entry)
        elif kind == "pbStep":
            continue
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
