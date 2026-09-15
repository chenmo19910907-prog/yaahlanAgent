"""匹配 user 消息是否命中 online/config/registry.json 已入库的 MOA 能力。"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REGISTRY_PATH = _REPO_ROOT / "online" / "config" / "registry.json"

# 全员只读，不算「管理员专属线上 MOA」
_PUBLIC_ONLINE_MOA_IDS = frozenset({"moa_query_user_by_phone"})

_IGNORE_FLAGS = frozenset(
    {
        "--payload-file",
        "--expr",
        "--online-env",
        "--target-environment",
        "--query-user-by-phone",
    }
)

_NL_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "online_vip_query_current": [
        re.compile(
            r"线上.{0,20}(?:查|查询).{0,32}(?:VIP|vip).{0,16}(?:等级|经验|信息)?",
            re.I,
        ),
        re.compile(r"线上.{0,20}(?:VIP|vip).{0,16}(?:等级|经验)", re.I),
    ],
    "online_family_query_members": [
        re.compile(r"线上.{0,20}(?:查|查询).{0,12}家族.{0,12}\d+.{0,12}成员", re.I),
        re.compile(r"线上.{0,20}家族.{0,12}\d+.{0,12}成员", re.I),
    ],
    "online_family_query_joined_by_user": [
        re.compile(r"线上.{0,20}(?:查|查询).{0,12}用户.{0,12}\d+.{0,20}(?:所属|加入|在).{0,8}家族", re.I),
        re.compile(r"线上.{0,20}(?:查|查询).{0,12}\d+.{0,20}(?:所属|在).{0,8}家族", re.I),
    ],
    "online_family_detail_by_id": [
        re.compile(r"线上.{0,20}(?:查|查询).{0,12}家族.{0,12}\d+.{0,12}(?:详情|详细|信息)", re.I),
    ],
    "online_family_detail_by_user": [
        re.compile(r"线上.{0,20}(?:查|查询).{0,12}用户.{0,12}\d+.{0,20}家族.{0,12}(?:详情|成员|详细)", re.I),
    ],
    "online_id_auth_query": [
        re.compile(r"线上.{0,20}(?:查|查询).{0,24}(?:实名|认证)", re.I),
    ],
    "online_ip_find": [
        re.compile(r"线上.{0,20}(?:查|查询).{0,12}(?:IP|ip).{0,24}(?:归属|地址|地)", re.I),
        re.compile(r"线上.{0,20}IP归属", re.I),
    ],
    "online_user_reg_time_query": [
        re.compile(r"线上.{0,20}(?:查|查询).{0,24}(?:注册时间|注册日期)", re.I),
    ],
    "online_charm_query_current": [
        re.compile(r"线上.{0,20}(?:查|查询).{0,24}(?:魅力等级|魅力值)", re.I),
    ],
    "online_wealth_query_current": [
        re.compile(r"线上.{0,20}(?:查|查询).{0,24}(?:财富等级|财富值)", re.I),
    ],
    "online_diamond_query_account": [
        re.compile(r"线上.{0,20}(?:查|查询).{0,24}(?:钻石|余额|有多少钻)", re.I),
    ],
    "online_user_active_days_query": [
        re.compile(r"线上.{0,20}(?:查|查询).{0,24}(?:登录天数|活跃天数)", re.I),
    ],
    "online_user_app_language_query": [
        re.compile(r"线上.{0,20}(?:查|查询).{0,24}(?:app语言|语言设置|app 语言)", re.I),
    ],
    "online_user_prop_query_own": [
        re.compile(r"线上.{0,20}(?:查|查询).{0,24}(?:装扮|propType|道具)", re.I),
    ],
    "online_user_query_joined_trade_union": [
        re.compile(r"线上.{0,20}(?:查|查询).{0,24}(?:所属公会|在哪个公会|加入的公会)", re.I),
    ],
}


def _read_registry() -> dict[str, Any]:
    with open(_REGISTRY_PATH, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("online registry 必须是 JSON object")
    return data


def _is_online_moa_item(item: dict[str, Any]) -> bool:
    cmd = str(item.get("command") or "")
    category = str(item.get("category") or "")
    item_id = str(item.get("id") or "")
    if item_id == "moa_query_user_by_phone":
        return True
    if "online_execute.py moa" in cmd.replace("\\", "/"):
        return True
    if "MOA" in category.upper():
        return True
    return "moa_execute.py" in cmd and (
        "--线上环境" in cmd or "--online-env" in cmd or "--target-environment prod" in cmd
    )


@lru_cache(maxsize=1)
def online_moa_registry_ids() -> frozenset[str]:
    """已入库的线上 MOA registry id（不含全员手机号查询）。"""
    items = _read_registry().get("items")
    if not isinstance(items, list):
        return frozenset()
    ids: set[str] = set()
    for raw in items:
        if not isinstance(raw, dict):
            continue
        item_id = str(raw.get("id") or "").strip()
        if not item_id or item_id in _PUBLIC_ONLINE_MOA_IDS:
            continue
        if _is_online_moa_item(raw):
            ids.add(item_id)
    return frozenset(ids)


@lru_cache(maxsize=1)
def _online_moa_items() -> tuple[dict[str, Any], ...]:
    items = _read_registry().get("items")
    if not isinstance(items, list):
        return ()
    out: list[dict[str, Any]] = []
    for raw in items:
        if not isinstance(raw, dict):
            continue
        item_id = str(raw.get("id") or "").strip()
        if not item_id or item_id in _PUBLIC_ONLINE_MOA_IDS:
            continue
        if _is_online_moa_item(raw):
            out.append(raw)
    return tuple(out)


def _prompt_keywords(item: dict[str, Any]) -> list[str]:
    keywords: list[str] = []
    name = str(item.get("name") or "")
    if name.upper().startswith("MOA-"):
        keywords.append(name[4:])
    elif name:
        keywords.append(name)
    for prompt in item.get("prompts") or []:
        cleaned = re.sub(r"<[^>]+>", "", str(prompt))
        cleaned = re.sub(r"线上环境", "", cleaned).strip()
        if len(cleaned) >= 2:
            keywords.append(cleaned)
    return keywords


def _command_signals(item: dict[str, Any]) -> tuple[list[str], list[str]]:
    cmd = str(item.get("command") or "")
    templates = re.findall(r"MOA/templates/([^\s\"']+\.json)", cmd)
    flags = [
        flag
        for flag in re.findall(r"--[\w-]+", cmd)
        if flag not in _IGNORE_FLAGS
    ]
    return templates, flags


def _item_matches_text(item: dict[str, Any], text: str) -> bool:
    item_id = str(item.get("id") or "")
    templates, flags = _command_signals(item)
    for tpl in templates:
        stem = tpl.removesuffix(".json")
        if tpl in text or stem in text:
            return True
    for flag in flags:
        if flag in text:
            return True
    cmd = str(item.get("command") or "")
    if cmd and len(cmd) >= 24 and cmd in text:
        return True
    for kw in _prompt_keywords(item):
        if kw and kw in text:
            return True
    for pattern in _NL_PATTERNS.get(item_id, []):
        if pattern.search(text):
            return True
    return False


def match_registered_online_moa(text: str) -> str | None:
    """若 text 命中已入库线上 MOA，返回 registry id；否则 None。"""
    t = (text or "").strip()
    if not t:
        return None
    for item in _online_moa_items():
        if _item_matches_text(item, t):
            return str(item.get("id") or "") or None
    return None


def clear_online_moa_registry_cache() -> None:
    online_moa_registry_ids.cache_clear()
    _online_moa_items.cache_clear()
