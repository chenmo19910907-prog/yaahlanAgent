"""配置加载。"""

from __future__ import annotations

import json
import os
from typing import Any

_CONFIG_CACHE: dict[str, Any] | None = None


def _base_dir() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_config() -> dict[str, Any]:
    global _CONFIG_CACHE
    if _CONFIG_CACHE is not None:
        return _CONFIG_CACHE
    path = os.path.join(_base_dir(), "config.json")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("Risk/config.json 必须是 object")
    _CONFIG_CACHE = data
    return data


def defaults() -> dict[str, Any]:
    raw = load_config().get("defaults")
    if not isinstance(raw, dict):
        return {}
    return raw


def max_elements_per_request() -> int:
    value = defaults().get("max_elements_per_request", 5)
    try:
        limit = int(value)
    except (TypeError, ValueError) as e:
        raise ValueError(f"max_elements_per_request 无效: {value}") from e
    if limit <= 0:
        raise ValueError("max_elements_per_request 必须为正整数")
    return limit


def max_elements_for_request(menu_key: str | None = None) -> int:
    if menu_key:
        try:
            event_cfg = menu_event_by_key(menu_key)
            if "max_elements_per_request" in event_cfg:
                return int(event_cfg["max_elements_per_request"])
        except ValueError:
            pass
    return max_elements_per_request()


def chunk_elements(elements: list[str], chunk_size: int | None = None) -> list[list[str]]:
    size = chunk_size or max_elements_per_request()
    if size <= 0:
        raise ValueError("chunk_size 必须为正整数")
    return [elements[i : i + size] for i in range(0, len(elements), size)]


def menu_event_by_key(key: str) -> dict[str, Any]:
    menus = load_config().get("menu_events")
    if not isinstance(menus, dict):
        raise ValueError("Risk/config.json 缺少 menu_events")
    item = menus.get(key)
    if not isinstance(item, dict):
        raise ValueError(f"未找到 menu_events.{key}，可用: {sorted(menus)}")
    return item


def resolve_menu_operate_body(
    *,
    menu_event: str | None,
    menu_key: str | None,
    menu_type: str | None,
    dimension: str | None,
    elements: list[str],
    action: str,
    reason: str,
    token: str | None,
) -> dict[str, Any]:
    cfg = defaults()
    event_cfg: dict[str, Any] = {}
    if menu_key:
        event_cfg = menu_event_by_key(menu_key)

    resolved_event = menu_event or event_cfg.get("menu_event") or event_cfg.get("id")
    if not resolved_event:
        raise ValueError("必须提供 --menu-event 或 --menu-key")

    resolved_type = (menu_type or event_cfg.get("menu_type") or cfg.get("menu_type") or "").strip()
    resolved_dimension = (dimension or event_cfg.get("dimension") or cfg.get("dimension") or "").strip()
    if not resolved_type:
        raise ValueError("必须提供 --menu-type 或在 config/menu_key 中配置 menu_type")
    if not resolved_dimension:
        raise ValueError("必须提供 --dimension 或在 config/menu_key 中配置 dimension")
    if not elements:
        raise ValueError("必须提供 --elements 或 --element-file")

    limit = max_elements_per_request()
    if len(elements) > limit:
        raise ValueError(
            f"单次最多 {limit} 个 elements，当前 {len(elements)} 个；"
            "请减少数量或去掉 --strict-limit 以自动分批"
        )

    resolved_token = token or event_cfg.get("token") or cfg.get("token") or os.environ.get("SEC_RISK_TOKEN")
    if not resolved_token:
        raise ValueError("必须提供 --token 或配置 SEC_RISK_TOKEN / config.defaults.token")

    action = action.strip().lower()
    if action not in {"add", "delete", "remove", "del"}:
        raise ValueError(f"不支持的 action: {action}，支持: add, delete")

    if action in {"remove", "del"}:
        action = "delete"

    return {
        "menu_event": str(resolved_event).strip(),
        "menu_type": resolved_type,
        "dimension": resolved_dimension,
        "elements": elements,
        "action": action,
        "reason": reason.strip() or "测试",
        "token": str(resolved_token).strip(),
    }
