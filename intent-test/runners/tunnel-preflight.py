#!/usr/bin/env python3
"""Tunnel 抓包预检：校验定制礼物意图测试数据就绪，并生成/更新 midscene/.env 变量。"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adb.adb.gift_panel_analyze import (  # noqa: E402
    _latest_by_url,
    analyze_gift_panel_from_tunnel,
    parse_customize_gift_subjects,
    parse_gift_tab_list_v3,
)
from adb.adb.popup_analyze import fetch_recent_tunnel_items  # noqa: E402
from adb.adb.tunnel_verify import resolve_momoid  # noqa: E402

MIDSCENE_ENV = ROOT / "midscene" / ".env"
BASE_PROFILE_PATH = ROOT / "intent-test" / "config" / "base-profile.yaml"
GENERATED_DIR = ROOT / "intent-test" / ".generated" / "preflight"

SEARCH_URL_MARKERS = (
    "searchCustomGift",
    "searchcustomgift",
    "customGiftSearch",
    "searchCustom",
    "giftPanel/search",
)

ENV_KEYS = (
    "TEST_TUNNEL_MOMOID",
    "TEST_CUSTOM_GIFT_UID",
    "TEST_CUSTOM_GIFT_UID_PARTIAL",
    "TEST_CUSTOM_GIFT_NICKNAME",
    "TEST_CUSTOM_GIFT_NICKNAME_KEYWORD",
    "TEST_CUSTOM_GIFT_NICKNAME_NOT_FOUND",
    "TEST_CUSTOM_GIFT_GIFT_NAME",
    "TUNNEL_KEYWORD_CUSTOM_GIFT_SEARCH",
)

TUNNEL_KEYWORD_QUERIES = (
    "searchCustomGift",
    "getTotalCustomGiftRankList",
    "getGiftTabListV3",
)

INTENT_REQUIREMENTS: dict[str, list[str]] = {
    "IT-GIFT-UID-001": ["TEST_CUSTOM_GIFT_UID", "TEST_TUNNEL_MOMOID"],
    "IT-GIFT-UID-002": ["TEST_CUSTOM_GIFT_UID", "TEST_TUNNEL_MOMOID"],
    "IT-GIFT-UID-003": ["TEST_CUSTOM_GIFT_UID", "TEST_CUSTOM_GIFT_UID_PARTIAL"],
    "IT-GIFT-NICK-001": ["TEST_CUSTOM_GIFT_NICKNAME", "TEST_TUNNEL_MOMOID"],
    "IT-GIFT-NICK-002": ["TEST_CUSTOM_GIFT_NICKNAME_KEYWORD", "TEST_TUNNEL_MOMOID"],
    "IT-GIFT-NICK-003": ["TEST_CUSTOM_GIFT_NICKNAME_NOT_FOUND"],
    "IT-GIFT-NICK-004": ["TEST_CUSTOM_GIFT_NICKNAME", "TEST_TUNNEL_MOMOID"],
}


def _load_base_profile_env() -> None:
    """从 intent-test/config/base-profile.yaml 注入 env（不覆盖已有变量）。"""
    if not BASE_PROFILE_PATH.is_file():
        return
    try:
        import subprocess

        loader = ROOT / "intent-test" / "runners" / "load-base-profile.mjs"
        proc = subprocess.run(
            ["node", str(loader), "--json"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
        if proc.returncode != 0:
            return
        payload = json.loads(proc.stdout)
        env_map = payload.get("env") if isinstance(payload, dict) else None
        if not isinstance(env_map, dict):
            return
        for key, value in env_map.items():
            if key and key not in os.environ and value is not None:
                os.environ[key] = str(value).strip()
    except (OSError, json.JSONDecodeError, subprocess.SubprocessError, ValueError):
        return


def _load_midscene_env() -> None:
    _load_base_profile_env()
    if not MIDSCENE_ENV.is_file():
        return
    for line in MIDSCENE_ENV.read_text(encoding="utf-8").splitlines():
        trimmed = line.strip()
        if not trimmed or trimmed.startswith("#") or "=" not in trimmed:
            continue
        key, val = trimmed.split("=", 1)
        key = key.strip()
        val = val.strip().split("#", 1)[0].strip()
        if key:
            os.environ[key] = val


def _resolve_momoid_arg(momoid: str | None, account: str | None) -> str:
    if momoid and momoid.strip():
        return momoid.strip()
    env_momoid = os.environ.get("TEST_TUNNEL_MOMOID", "").strip()
    if env_momoid:
        return env_momoid
    return resolve_momoid(momoid=None, account=account)


def _items_by_url_marker(items: list[dict[str, Any]], marker: str) -> list[dict[str, Any]]:
    matched = [x for x in items if marker.lower() in str(x.get("url", "")).lower()]
    return sorted(matched, key=lambda x: str(x.get("time", "")), reverse=True)


def _response_ec_ok(response: Any) -> bool:
    if not isinstance(response, dict):
        return False
    try:
        return int(response.get("ec")) == 200
    except (TypeError, ValueError):
        return False


def _normalize_custom_gift_row(row: dict[str, Any]) -> dict[str, Any] | None:
    uid = str(row.get("ownerUid") or row.get("owner_uid") or row.get("uid") or "").strip()
    nick = str(row.get("ownerNickname") or row.get("owner_nickname") or row.get("nickname") or "").strip()
    gift_name = str(row.get("giftName") or row.get("gift_name") or row.get("name") or "").strip()
    if not uid and not nick and not gift_name:
        return None
    return {
        "ownerUid": uid,
        "ownerNickname": nick,
        "giftId": row.get("giftId") or row.get("gift_id") or row.get("id"),
        "giftName": gift_name or row.get("giftName"),
        "value": row.get("value"),
    }


def _parse_rows_from_response_data(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, dict):
        return []
    rows: list[dict[str, Any]] = []
    list_rows = data.get("list")
    if isinstance(list_rows, list):
        for row in list_rows:
            if not isinstance(row, dict):
                continue
            normalized = _normalize_custom_gift_row(row)
            if normalized:
                rows.append(normalized)
    if rows:
        return rows
    normalized = _normalize_custom_gift_row(data)
    return [normalized] if normalized else []


def _parse_rows_from_item(item: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not item or not isinstance(item.get("response"), dict):
        return []
    if not _response_ec_ok(item["response"]):
        return []
    return _parse_rows_from_response_data(item["response"].get("data"))


def _parse_rank_list(item: dict[str, Any] | None) -> list[dict[str, Any]]:
    return _parse_rows_from_item(item)


def _is_search_url(url: str) -> bool:
    low = url.lower()
    return any(marker.lower() in low for marker in SEARCH_URL_MARKERS)


def _collect_search_hit_rows(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows_out: list[dict[str, Any]] = []
    for item in items:
        if not _is_search_url(str(item.get("url", ""))):
            continue
        for row in _parse_rows_from_item(item):
            rows_out.append(
                {
                    **row,
                    "source": "searchCustomGift",
                    "captureTime": item.get("time"),
                    "tunnelId": item.get("_id"),
                }
            )
    return rows_out


def _collect_rank_rows(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows_out: list[dict[str, Any]] = []
    for item in _items_by_url_marker(items, "getTotalCustomGiftRankList"):
        for row in _parse_rows_from_item(item):
            rows_out.append(
                {
                    **row,
                    "source": "getTotalCustomGiftRankList",
                    "captureTime": item.get("time"),
                    "tunnelId": item.get("_id"),
                }
            )
    return rows_out


def _first_customize_gift_name(tabs: list[dict[str, Any]]) -> str:
    tab = _pick_customize_tab(tabs)
    if not tab:
        return ""
    for gift in tab.get("gifts") or []:
        name = str(gift.get("name") or "").strip()
        if name:
            return name
    return ""


def _merge_tunnel_items(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for group in groups:
        for item in group:
            key = str(item.get("_id") or item.get("url", "")) + str(item.get("time", ""))
            merged[key] = item
    return sorted(merged.values(), key=lambda x: str(x.get("time", "")), reverse=True)


def _fetch_tunnel_keyword_items(
    *,
    momoid: str,
    keyword: str,
    since_seconds: int,
    g_appid: str,
    g_env: str,
) -> list[dict[str, Any]]:
    from adb.adb.tunnel_verify import _ensure_tunnel_import

    list_requests, normalize_request_list, tunnel_success = _ensure_tunnel_import()
    start_time = int(time.time()) - max(1, since_seconds)
    payload = list_requests(
        base_url=os.environ.get("TUNNEL_BASE_URL", "https://tunnel.wemomo.com"),
        momoid=momoid,
        start_time=start_time,
        keyword=keyword,
        g_appid=g_appid,
        g_env=g_env,
    )
    if not tunnel_success(payload.get("ec")):
        return []
    return normalize_request_list(payload)


def _load_tunnel_items(
    *,
    momoid: str,
    since_seconds: int,
    g_appid: str,
    g_env: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    items, meta = fetch_recent_tunnel_items(
        momoid=momoid,
        since_seconds=since_seconds,
        g_appid=g_appid,
        g_env=g_env,
    )
    keyword_groups: list[list[dict[str, Any]]] = []
    markers_present = {marker for marker in TUNNEL_KEYWORD_QUERIES if _items_by_url_marker(items, marker)}
    for keyword in TUNNEL_KEYWORD_QUERIES:
        if keyword in markers_present and meta.get("itemCount", 0) > 0:
            continue
        extra = _fetch_tunnel_keyword_items(
            momoid=momoid,
            keyword=keyword,
            since_seconds=since_seconds,
            g_appid=g_appid,
            g_env=g_env,
        )
        if extra:
            keyword_groups.append(extra)
    if keyword_groups:
        items = _merge_tunnel_items(items, *keyword_groups)
        meta = {**meta, "itemCount": len(items), "keywordSupplement": True}
    return items, meta


def _pick_customize_tab(tabs: list[dict[str, Any]]) -> dict[str, Any] | None:
    for tab in tabs:
        name = str(tab.get("tabName") or tab.get("tab_name") or "")
        if "custom" in name.lower() or "定制" in name:
            return tab
    return None


def _discover_search_keyword(items: list[dict[str, Any]]) -> dict[str, Any]:
    default = os.environ.get("TUNNEL_KEYWORD_CUSTOM_GIFT_SEARCH", "searchCustomGift").strip()
    hits: list[dict[str, Any]] = []
    for item in items:
        url = str(item.get("url", ""))
        low = url.lower()
        if not any(m.lower() in low for m in SEARCH_URL_MARKERS):
            continue
        path = urlparse(url).path
        segment = path.rstrip("/").split("/")[-1] if path else ""
        keyword = segment or default
        hits.append(
            {
                "keyword": keyword,
                "url": url,
                "time": item.get("time"),
                "_id": item.get("_id"),
            }
        )
    if hits:
        return {
            "keyword": hits[0]["keyword"],
            "source": "tunnel_capture",
            "recent": hits[:3],
        }
    return {
        "keyword": default,
        "source": "default_or_env",
        "recent": [],
        "note": "近期抓包未发现搜索接口，请在 App 执行一次 uid/昵称搜索后重跑 preflight",
    }


def _uid_partial(full_uid: str) -> str:
    digits = re.sub(r"\D", "", full_uid)
    if len(digits) < 5:
        raise ValueError(f"uid 过短，无法生成 partial: {full_uid!r}")
    cut = max(4, len(digits) - 3)
    partial = digits[:cut]
    if partial == digits:
        partial = digits[: max(4, len(digits) - 1)]
    return partial


def _nickname_keyword(nickname: str) -> str:
    text = nickname.strip()
    if len(text) <= 2:
        return text
    if len(text) <= 4:
        return text[:2]
    mid = len(text) // 2
    return text[max(0, mid - 1) : mid + 2]


def _nickname_not_found() -> str:
    return f"不存在的昵称preflight{int(time.time()) % 100000}"


def _pick_subject(
    rows: list[dict[str, Any]],
    *,
    exclude_uid: str | None = None,
    require_nickname: bool = True,
) -> dict[str, Any] | None:
    for row in rows:
        uid = str(row.get("ownerUid", "")).strip()
        nick = str(row.get("ownerNickname", "")).strip()
        if require_nickname and (not uid or not nick):
            continue
        if not require_nickname and not uid and not nick:
            continue
        if exclude_uid and uid == exclude_uid:
            continue
        return row
    return None


def _collect_customize_panel_rows(tabs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return parse_customize_gift_subjects(tabs)


def _resolve_nickname_from_tunnel(items: list[dict[str, Any]], uid: str) -> str:
    if not uid:
        return ""
    for item in items:
        url = str(item.get("url", "")).lower()
        if "simpleuserinfo" not in url:
            continue
        req = item.get("request")
        if isinstance(req, dict):
            remote = str(req.get("remoteId") or req.get("remote_id") or "").strip()
            if remote and remote != uid:
                continue
        resp = item.get("response")
        if not isinstance(resp, dict) or not _response_ec_ok(resp):
            continue
        data = resp.get("data")
        if not isinstance(data, dict):
            continue
        for key in ("nickname", "nickName", "ownerNickname", "name"):
            val = str(data.get(key) or "").strip()
            if val:
                return val
        user = data.get("user") or data.get("userInfo")
        if isinstance(user, dict):
            for key in ("nickname", "nickName"):
                val = str(user.get(key) or "").strip()
                if val:
                    return val
    return ""


def _enrich_subject_nickname(
    subject: dict[str, Any] | None,
    *,
    items: list[dict[str, Any]],
    search_rows: list[dict[str, Any]],
    rank_rows: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not subject:
        return None
    nick = str(subject.get("ownerNickname", "")).strip()
    uid = str(subject.get("ownerUid", "")).strip()
    if nick:
        return subject
    for rows in (search_rows, rank_rows):
        for row in rows:
            if str(row.get("ownerUid", "")).strip() == uid:
                found = str(row.get("ownerNickname", "")).strip()
                if found:
                    return {**subject, "ownerNickname": found}
    resolved = _resolve_nickname_from_tunnel(items, uid)
    if resolved:
        return {**subject, "ownerNickname": resolved}
    return subject


def _pick_subject_user(
    search_rows: list[dict[str, Any]],
    rank_rows: list[dict[str, Any]],
    panel_rows: list[dict[str, Any]],
    *,
    items: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    subject = _pick_subject(search_rows)
    if subject:
        subject = {**subject, "dataSource": subject.get("source", "searchCustomGift")}
    elif rank_rows:
        subject = _pick_subject(rank_rows)
        if subject:
            subject = {**subject, "dataSource": subject.get("source", "getTotalCustomGiftRankList")}
    elif panel_rows:
        subject = _pick_subject(panel_rows, require_nickname=False)
        if subject:
            subject = {**subject, "dataSource": subject.get("source", "getGiftTabListV3/customize")}
    if subject and items is not None:
        subject = _enrich_subject_nickname(
            subject,
            items=items,
            search_rows=search_rows,
            rank_rows=rank_rows,
        )
    return subject


def _checklist(
    *,
    tunnel_ok: bool,
    momoid: str,
    heartbeat: dict[str, Any] | None,
    panel: dict[str, Any],
    customize_tab: dict[str, Any] | None,
    panel_rows: list[dict[str, Any]],
    search_rows: list[dict[str, Any]],
    rank_rows: list[dict[str, Any]],
    search_info: dict[str, Any],
    env_vars: dict[str, str],
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []

    def add(check_id: str, label: str, ok: bool, detail: str = "", level: str = "error") -> None:
        checks.append({"id": check_id, "label": label, "ok": ok, "detail": detail, "level": level})

    add("tunnel_auth", "Tunnel Cookie 可用", tunnel_ok, "配置 Tunnel/.env.local 或 MOA/.env.local")
    add("momoid", "momoid 已解析", bool(momoid), momoid or "须 --momoid / TEST_TUNNEL_MOMOID / --account")

    hb_ok = heartbeat is not None
    add(
        "in_room",
        "近期有房内心跳（进房佐证）",
        hb_ok,
        "请在 App 进入语音房并停留数秒" if not hb_ok else str(heartbeat.get("time")),
        level="warn",
    )

    panel_ok = bool(panel.get("apis", {}).get("getGiftTabListV3", {}).get("found"))
    add(
        "gift_panel",
        "近期有 getGiftTabListV3 抓包",
        panel_ok,
        "请在房内打开橙色礼物盒礼物面板" if not panel_ok else "",
    )

    customize_ok = len(panel_rows) > 0 or (
        customize_tab is not None and int(customize_tab.get("giftCount") or 0) > 0
    )
    add(
        "customize_tab",
        "Customize Tab 有线上定制礼物（getGiftTabListV3）",
        customize_ok,
        f"panelRows={len(panel_rows)} giftCount={customize_tab.get('giftCount') if customize_tab else 0}",
    )

    rank_ok = len(rank_rows) > 0
    add(
        "custom_rank",
        "自定义礼物周榜有 ownerUid/ownerNickname",
        rank_ok,
        "可选：切换本周/上周榜以补全昵称" if not rank_ok else f"{len(rank_rows)} 条",
        level="warn",
    )

    search_hit_ok = len(search_rows) > 0
    add(
        "search_hit",
        "定制礼物搜索接口有命中结果",
        search_hit_ok,
        "可选：Customize 内搜索一次以补全昵称"
        if not search_hit_ok
        else f"{len(search_rows)} 条，最近 nick={search_rows[0].get('ownerNickname', '-')}",
        level="info",
    )

    subject_ok = bool(env_vars.get("TEST_CUSTOM_GIFT_UID")) and bool(
        env_vars.get("TEST_CUSTOM_GIFT_NICKNAME")
    )
    uid_ok = bool(env_vars.get("TEST_CUSTOM_GIFT_UID"))
    nick_ok = bool(env_vars.get("TEST_CUSTOM_GIFT_NICKNAME"))
    add(
        "subject_uid",
        "已解析定制礼物 ownerUid（getGiftTabListV3/customize.extra.userId 等）",
        uid_ok,
        f"uid={env_vars.get('TEST_CUSTOM_GIFT_UID') or '-'} "
        f"gift={env_vars.get('TEST_CUSTOM_GIFT_GIFT_NAME') or '-'}",
    )
    add(
        "subject_nickname",
        "已解析定制用户昵称（搜索/周榜/simpleUserInfo）",
        nick_ok,
        f"nick={env_vars.get('TEST_CUSTOM_GIFT_NICKNAME') or '-'}",
        level="warn" if uid_ok and not nick_ok else "error",
    )
    add(
        "subject_user",
        "uid + 昵称 可用于命中类用例",
        subject_ok,
        f"uid={env_vars.get('TEST_CUSTOM_GIFT_UID') or '-'} "
        f"nick={env_vars.get('TEST_CUSTOM_GIFT_NICKNAME') or '-'} "
        f"gift={env_vars.get('TEST_CUSTOM_GIFT_GIFT_NAME') or '-'}",
    )

    search_seen = bool(search_info.get("recent"))
    add(
        "search_api",
        "搜索接口 keyword 已确认",
        True,
        search_info.get("keyword", ""),
        level="warn" if not search_seen else "info",
    )

    return checks


def _intent_readiness(env_vars: dict[str, str], checks: list[dict[str, Any]]) -> dict[str, Any]:
    check_failed = {c["id"] for c in checks if not c["ok"] and c["level"] == "error"}
    out: dict[str, Any] = {}
    for intent_id, keys in INTENT_REQUIREMENTS.items():
        missing = [k for k in keys if not str(env_vars.get(k, "")).strip()]
        ready = not missing
        if "tunnel_auth" in check_failed:
            ready = False
        if intent_id.startswith("IT-GIFT-NICK") and intent_id != "IT-GIFT-NICK-003":
            if "subject_nickname" in check_failed:
                ready = False
        elif intent_id.startswith("IT-GIFT-UID") and intent_id != "IT-GIFT-UID-003":
            if "subject_uid" in check_failed:
                ready = False
            if "customize_tab" in check_failed:
                ready = False
        reason: list[str] = []
        if missing:
            reason.append(f"缺少环境变量: {', '.join(missing)}")
        if intent_id.startswith("IT-GIFT-NICK") and intent_id != "IT-GIFT-NICK-003":
            if "subject_nickname" in check_failed:
                reason.append("无可用定制用户昵称")
        elif intent_id.startswith("IT-GIFT-UID") and intent_id != "IT-GIFT-UID-003":
            if "subject_uid" in check_failed:
                reason.append("无可用定制礼物 uid")
            if "customize_tab" in check_failed:
                reason.append("Customize Tab 无礼物")
        out[intent_id] = {"ready": ready, "reason": "；".join(reason) or "ok"}
    return out


def _patch_env_file(env_vars: dict[str, str]) -> list[str]:
    if not MIDSCENE_ENV.is_file():
        raise FileNotFoundError(f"未找到 {MIDSCENE_ENV}，请先 cp midscene/.env.example .env")

    lines = MIDSCENE_ENV.read_text(encoding="utf-8").splitlines()
    updated_keys: list[str] = []
    seen: set[str] = set()

    new_lines: list[str] = []
    for line in lines:
        if "=" not in line or line.strip().startswith("#"):
            new_lines.append(line)
            continue
        key = line.split("=", 1)[0].strip()
        if key in env_vars:
            new_lines.append(f"{key}={env_vars[key]}")
            updated_keys.append(key)
            seen.add(key)
        else:
            new_lines.append(line)

    missing_keys = [k for k in ENV_KEYS if k not in seen]
    if missing_keys:
        if new_lines and new_lines[-1].strip():
            new_lines.append("")
        new_lines.append("# ---- 意图测试：Tunnel preflight 自动写入 ----")
        for key in missing_keys:
            if key not in env_vars:
                continue
            new_lines.append(f"{key}={env_vars[key]}")
            updated_keys.append(key)

    MIDSCENE_ENV.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    return updated_keys


def run_preflight(
    *,
    momoid: str,
    since_seconds: int = 7200,
    g_appid: str | None = None,
    g_env: str = "alpha",
) -> dict[str, Any]:
    appid = (g_appid or os.environ.get("TUNNEL_G_APPID") or "yaahlan").strip()
    items, meta = _load_tunnel_items(
        momoid=momoid,
        since_seconds=since_seconds,
        g_appid=appid,
        g_env=g_env,
    )
    tunnel_ok = bool(meta.get("tunnelOk"))

    panel = analyze_gift_panel_from_tunnel(
        momoid=momoid,
        since_seconds=since_seconds,
        g_appid=appid,
        g_env=g_env,
    )
    tabs = panel.get("tabsDetail") or []
    customize_tab = _pick_customize_tab(tabs)
    panel_rows = _collect_customize_panel_rows(tabs)

    search_rows = _collect_search_hit_rows(items)
    rank_rows = _collect_rank_rows(items)
    rank_item = _latest_by_url(items, "getTotalCustomGiftRankList")
    search_item = next((x for x in _items_by_url_marker(items, "searchCustomGift") if _is_search_url(str(x.get("url", "")))), None)
    if not search_item:
        for marker in SEARCH_URL_MARKERS:
            search_item = _latest_by_url(items, marker)
            if search_item:
                break

    subject = _pick_subject_user(search_rows, rank_rows, panel_rows, items=items)

    uid = str(subject.get("ownerUid", "")).strip() if subject else ""
    nickname = str(subject.get("ownerNickname", "")).strip() if subject else ""
    gift_name = str(subject.get("giftName", "")).strip() if subject else ""
    if not gift_name and panel_rows:
        gift_name = str(panel_rows[0].get("giftName", "")).strip()

    search_info = _discover_search_keyword(items)
    heartbeat = _latest_by_url(items, "room/heart/heartbeat")

    env_vars: dict[str, str] = {
        "TEST_TUNNEL_MOMOID": momoid,
        "TUNNEL_KEYWORD_CUSTOM_GIFT_SEARCH": str(search_info.get("keyword", "searchCustomGift")),
    }
    if uid:
        env_vars["TEST_CUSTOM_GIFT_UID"] = uid
        env_vars["TEST_CUSTOM_GIFT_UID_PARTIAL"] = _uid_partial(uid)
    if nickname:
        env_vars["TEST_CUSTOM_GIFT_NICKNAME"] = nickname
        env_vars["TEST_CUSTOM_GIFT_NICKNAME_KEYWORD"] = _nickname_keyword(nickname)
    if gift_name:
        env_vars["TEST_CUSTOM_GIFT_GIFT_NAME"] = gift_name
    env_vars["TEST_CUSTOM_GIFT_NICKNAME_NOT_FOUND"] = _nickname_not_found()

    checks = _checklist(
        tunnel_ok=tunnel_ok,
        momoid=momoid,
        heartbeat=heartbeat,
        panel=panel,
        customize_tab=customize_tab,
        panel_rows=panel_rows,
        search_rows=search_rows,
        rank_rows=rank_rows,
        search_info=search_info,
        env_vars=env_vars,
    )
    intents = _intent_readiness(env_vars, checks)
    blocking = [c for c in checks if not c["ok"] and c["level"] == "error"]
    core_ready = tunnel_ok and "subject_uid" not in {c["id"] for c in blocking}
    intent_ready = all(v["ready"] for v in intents.values())
    ready = core_ready and intent_ready

    return {
        "ok": ready,
        "momoid": momoid,
        "sinceSeconds": since_seconds,
        "generatedAt": int(time.time()),
        "tunnelMeta": meta,
        "sources": {
            "getGiftTabListV3": {
                **(panel.get("apis", {}).get("getGiftTabListV3") or {}),
                "customizeRowCount": len(panel_rows),
                "sampleCustomize": panel_rows[0] if panel_rows else None,
            },
            "getTotalCustomGiftRankList": {
                "found": rank_item is not None,
                "time": rank_item.get("time") if rank_item else None,
                "rowCount": len(rank_rows),
            },
            "searchCustomGift": {
                "found": search_item is not None,
                "time": search_item.get("time") if search_item else None,
                "hitCount": len(search_rows),
                "recentHit": search_rows[0] if search_rows else None,
            },
            "searchApi": search_info,
            "heartbeat": {
                "found": heartbeat is not None,
                "time": heartbeat.get("time") if heartbeat else None,
            },
        },
        "customizeTab": {
            "tabName": customize_tab.get("tabName") if customize_tab else None,
            "giftCount": customize_tab.get("giftCount") if customize_tab else 0,
        },
        "subjectUser": subject,
        "env": env_vars,
        "checks": checks,
        "intents": intents,
        "agentHint": (
            "预检优先解析 getGiftTabListV3 Customize Tab：gift.name + extra.userId。"
            "昵称来自搜索/周榜/simpleUserInfo；momoid 须与真机一致，抓包 g_appid 建议 yaahlan。"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Tunnel 抓包预检 + 意图测试数据准备")
    parser.add_argument("--momoid", default=None, help="Tunnel userId（默认 TEST_TUNNEL_MOMOID）")
    parser.add_argument("--account", default=None, help="adb/录制脚本/索引.json testAccounts 键")
    parser.add_argument("--since", type=int, default=7200, help="抓包回溯秒数，默认 7200")
    parser.add_argument("--g-appid", default=os.environ.get("TUNNEL_G_APPID", "yaahlan"))
    parser.add_argument("--g-env", default="alpha")
    parser.add_argument("--out", default=None, help="写入 JSON 报告路径")
    parser.add_argument(
        "--write-env",
        action="store_true",
        help="将 env 变量写入 midscene/.env（仅更新 ENV_KEYS）",
    )
    args = parser.parse_args()

    _load_midscene_env()
    try:
        momoid = _resolve_momoid_arg(args.momoid, args.account)
    except ValueError as exc:
        print(f"[preflight] ✗ {exc}", file=sys.stderr)
        return 2

    report = run_preflight(
        momoid=momoid,
        since_seconds=max(60, args.since),
        g_appid=args.g_appid,
        g_env=args.g_env,
    )

    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = Path(args.out) if args.out else GENERATED_DIR / f"gift-custom-search.{momoid}.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.write_env:
        try:
            updated = _patch_env_file(report["env"])
            report["envWritten"] = updated
            out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as exc:
            print(f"[preflight] ✗ 写入 midscene/.env 失败: {exc}", file=sys.stderr)
            return 1

    status = "✓" if report["ok"] else "✗"
    print(f"[preflight] {status} momoid={momoid} report={out_path}")
    for check in report["checks"]:
        mark = "✓" if check["ok"] else ("!" if check["level"] == "warn" else "✗")
        detail = f" — {check['detail']}" if check.get("detail") else ""
        print(f"  {mark} {check['label']}{detail}")

    ready_count = sum(1 for v in report["intents"].values() if v["ready"])
    total = len(report["intents"])
    print(f"[preflight] 意图就绪 {ready_count}/{total}")
    for intent_id, info in report["intents"].items():
        mark = "✓" if info["ready"] else "✗"
        print(f"  {mark} {intent_id}: {info['reason']}")

    if report.get("envWritten"):
        print(f"[preflight] 已写入 midscene/.env: {', '.join(report['envWritten'])}")

    if report["env"].get("TEST_CUSTOM_GIFT_UID") or report["env"].get("TEST_CUSTOM_GIFT_NICKNAME"):
        print(
            "[preflight] 建议变量: "
            f"UID={report['env'].get('TEST_CUSTOM_GIFT_UID', '-')} "
            f"NICK={report['env'].get('TEST_CUSTOM_GIFT_NICKNAME', '-')} "
            f"GIFT={report['env'].get('TEST_CUSTOM_GIFT_GIFT_NAME', '-')} "
            f"SEARCH={report['env'].get('TUNNEL_KEYWORD_CUSTOM_GIFT_SEARCH', '')}"
        )

    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
