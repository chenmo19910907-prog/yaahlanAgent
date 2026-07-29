"""快捷入口 bookmarks.json 读写与 legacy localStorage 合并。"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

WEB_AGENT_DIR = Path(__file__).resolve().parent
BOOKMARKS_PATH = WEB_AGENT_DIR / "config" / "bookmarks.json"
BOOKMARKS_BACKUP_DIR = WEB_AGENT_DIR / "data" / "bookmarks_backups"
BOOKMARKS_BACKUP_KEEP = 30


def load_bookmarks(path: Path | None = None) -> dict[str, Any]:
    target = path or BOOKMARKS_PATH
    if not target.is_file():
        return {"categories": []}
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"categories": []}
        categories = data.get("categories")
        if not isinstance(categories, list):
            return {"categories": []}
        return {"categories": categories}
    except (OSError, json.JSONDecodeError):
        return {"categories": []}


def normalize_bookmarks_payload(data: Any) -> dict[str, Any] | None:
    if not isinstance(data, dict):
        return None
    categories_raw = data.get("categories")
    if not isinstance(categories_raw, list):
        return None
    categories: list[dict[str, Any]] = []
    for cat in categories_raw:
        if not isinstance(cat, dict):
            return None
        cat_id = str(cat.get("id") or "").strip()
        cat_label = str(cat.get("label") or cat_id).strip()
        if not cat_id or not cat_label:
            return None
        items_raw = cat.get("items")
        if not isinstance(items_raw, list):
            return None
        items: list[dict[str, Any]] = []
        for item in items_raw:
            if not isinstance(item, dict):
                return None
            item_id = str(item.get("id") or "").strip()
            label = str(item.get("label") or "").strip()
            url = str(item.get("url") or "").strip()
            if not item_id or not label or not url:
                return None
            normalized: dict[str, Any] = {
                "id": item_id,
                "label": label,
                "url": url,
                "icon": str(item.get("icon") or "link").strip() or "link",
            }
            description = str(item.get("description") or "").strip()
            if description:
                normalized["description"] = description
            icon_url = str(item.get("iconUrl") or "").strip()
            if icon_url:
                normalized["iconUrl"] = icon_url
            items.append(normalized)
        categories.append({"id": cat_id, "label": cat_label, "items": items})
    return {"categories": categories}


def _backup_bookmarks_file(target: Path) -> None:
    if not target.is_file():
        return
    BOOKMARKS_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_path = BOOKMARKS_BACKUP_DIR / f"bookmarks_{ts}.json"
    shutil.copy2(target, backup_path)
    backups = sorted(BOOKMARKS_BACKUP_DIR.glob("bookmarks_*.json"))
    overflow = len(backups) - BOOKMARKS_BACKUP_KEEP
    if overflow > 0:
        for old in backups[:overflow]:
            old.unlink(missing_ok=True)


def save_bookmarks(data: dict[str, Any], path: Path | None = None) -> None:
    target = path or BOOKMARKS_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    if target == BOOKMARKS_PATH:
        _backup_bookmarks_file(target)
    target.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _item_urls(data: dict[str, Any]) -> set[str]:
    urls: set[str] = set()
    for cat in data.get("categories") or []:
        if not isinstance(cat, dict):
            continue
        for item in cat.get("items") or []:
            if isinstance(item, dict):
                url = str(item.get("url") or "").strip()
                if url:
                    urls.add(url.rstrip("/"))
    return urls


def _ensure_category(
    data: dict[str, Any],
    category_id: str,
    label: str,
) -> dict[str, Any]:
    categories = data.setdefault("categories", [])
    if not isinstance(categories, list):
        categories = []
        data["categories"] = categories
    for cat in categories:
        if isinstance(cat, dict) and str(cat.get("id") or "") == category_id:
            if not isinstance(cat.get("items"), list):
                cat["items"] = []
            return cat
    created = {"id": category_id, "label": label, "items": []}
    categories.append(created)
    return created


def merge_legacy_bookmarks(
    team_data: dict[str, Any],
    legacy_data: Any,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """将浏览器 localStorage 格式合并进团队 bookmarks，返回 (merged, added_items)。"""
    if not isinstance(legacy_data, dict):
        return team_data, []
    merged = normalize_bookmarks_payload(team_data)
    if merged is None:
        merged = {"categories": []}
    legacy_cats = legacy_data.get("categories")
    legacy_items = legacy_data.get("items")
    if not isinstance(legacy_cats, list):
        legacy_cats = []
    if not isinstance(legacy_items, list):
        legacy_items = []

    label_by_id = {
        str(cat.get("id") or "").strip(): str(cat.get("label") or "").strip()
        for cat in legacy_cats
        if isinstance(cat, dict) and str(cat.get("id") or "").strip()
    }
    seen_urls = _item_urls(merged)
    seen_ids: set[str] = set()
    for cat in merged.get("categories") or []:
        if not isinstance(cat, dict):
            continue
        for item in cat.get("items") or []:
            if isinstance(item, dict) and item.get("id"):
                seen_ids.add(str(item["id"]))

    added: list[dict[str, str]] = []
    for raw in legacy_items:
        if not isinstance(raw, dict):
            continue
        item_id = str(raw.get("id") or "").strip()
        label = str(raw.get("label") or "").strip()
        url = str(raw.get("url") or "").strip()
        if not label or not url:
            continue
        url_key = url.rstrip("/")
        if url_key in seen_urls:
            continue
        if item_id and item_id in seen_ids:
            continue
        category_id = str(raw.get("categoryId") or "mine").strip() or "mine"
        cat_label = label_by_id.get(category_id) or (
            "我的收藏" if category_id == "mine" else category_id
        )
        cat = _ensure_category(merged, category_id, cat_label)
        item = {
            "id": item_id or f"legacy-{len(seen_ids) + len(added) + 1}",
            "label": label,
            "url": url,
            "icon": str(raw.get("icon") or "link").strip() or "link",
        }
        description = str(raw.get("description") or "").strip()
        if description:
            item["description"] = description
        cat["items"].append(item)
        seen_urls.add(url_key)
        if item_id:
            seen_ids.add(item_id)
        added.append({"label": label, "url": url, "category": cat_label})

    normalized = normalize_bookmarks_payload(merged)
    if normalized is None:
        return team_data, []
    return normalized, added
