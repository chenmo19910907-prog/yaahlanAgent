"""测试账号占用检测：登录前用 Tunnel 判断账号是否正在被其他会话使用。"""

from __future__ import annotations

import time
from typing import Any

from .account_sweep import (
    _ensure_logout,
    resolve_momoid_for_phone,
    sweep_one_account,
)
from .ai_operate import AiOperateRequired
from .device import require_device
from .popup_analyze import fetch_recent_tunnel_items
from .recorded_scripts import load_test_accounts
from .screenshot import screenshot_dir

# 近 N 秒内有下列接口流量 → 视为「账号在用」（其他设备/会话正在操作）
DEFAULT_ACTIVITY_KEYWORDS: tuple[str, ...] = (
    "room/heart/heartbeat",
    "room/enter/",
    "simpleuserinfo",
    "personalhomepageuserinfo",
    "sign/signinlist",
    "gift/send",
    "feed/publish",
    "getuserconfigs",
)


def _normalize_keyword(keyword: str) -> str:
    return keyword.strip().lower()


def _url_matches_activity(url: str, keywords: tuple[str, ...]) -> str | None:
    low = url.lower()
    for key in keywords:
        if _normalize_keyword(key) in low:
            return key
    return None


def _account_entry(key: str, entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "account": key,
        "phone": str(entry.get("phone", "")).strip(),
        "userId": str(entry.get("userId", "")).strip() or None,
        "role": entry.get("role"),
    }


def list_index_account_candidates() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for key, entry in load_test_accounts().items():
        if isinstance(entry, dict):
            row = _account_entry(str(key), entry)
            if row["phone"]:
                out.append(row)
    return out


def resolve_candidate(
    *,
    account: str | None = None,
    phone: str | None = None,
) -> dict[str, Any]:
    if account and str(account).strip():
        key = str(account).strip()
        entry = load_test_accounts().get(key)
        if not isinstance(entry, dict):
            known = "、".join(sorted(load_test_accounts().keys())) or "（无）"
            raise ValueError(f"未知 account {key!r}，可选: {known}")
        row = _account_entry(key, entry)
        if not row["phone"]:
            raise ValueError(f"testAccounts.{key} 缺少 phone")
        return row
    if phone and str(phone).strip():
        mobile = str(phone).strip()
        for key, entry in load_test_accounts().items():
            if isinstance(entry, dict) and str(entry.get("phone", "")).strip() == mobile:
                return _account_entry(str(key), entry)
        momoid, source = resolve_momoid_for_phone(mobile)
        return {
            "account": None,
            "phone": mobile,
            "userId": momoid,
            "momoidSource": source,
        }
    raise ValueError("须指定 --account 或 --text（手机号）")


def check_account_in_use(
    *,
    user_id: str,
    since_seconds: int = 300,
    activity_keywords: tuple[str, ...] = DEFAULT_ACTIVITY_KEYWORDS,
    g_appid: str = "All",
    g_env: str = "alpha",
) -> dict[str, Any]:
    uid = str(user_id).strip()
    if not uid:
        raise ValueError("userId 不能为空")

    items, meta = fetch_recent_tunnel_items(
        momoid=uid,
        since_seconds=max(30, since_seconds),
        g_appid=g_appid,
        g_env=g_env,
    )
    hits: list[dict[str, Any]] = []
    for item in items:
        url = str(item.get("url", ""))
        matched = _url_matches_activity(url, activity_keywords)
        if matched:
            hits.append(
                {
                    "time": item.get("time"),
                    "url": url,
                    "keyword": matched,
                    "method": item.get("method"),
                    "status": item.get("status"),
                }
            )
    hits.sort(key=lambda x: str(x.get("time", "")), reverse=True)
    in_use = len(hits) > 0
    return {
        "userId": uid,
        "sinceSeconds": since_seconds,
        "tunnelOk": bool(meta.get("tunnelOk")),
        "tunnelItemCount": meta.get("itemCount", 0),
        "activityHitCount": len(hits),
        "inUse": in_use,
        "idle": not in_use,
        "activityKeywords": list(activity_keywords),
        "recentHits": hits[:8],
        "lastHit": hits[0] if hits else None,
        "reason": (
            f"近 {since_seconds}s 内有 {len(hits)} 条活跃接口"
            if in_use
            else f"近 {since_seconds}s 内无活跃接口（Tunnel 共 {meta.get('itemCount', 0)} 条）"
        ),
    }


def check_account(
    *,
    account: str | None = None,
    phone: str | None = None,
    since_seconds: int = 300,
    activity_keywords: tuple[str, ...] = DEFAULT_ACTIVITY_KEYWORDS,
) -> dict[str, Any]:
    cand = resolve_candidate(account=account, phone=phone)
    uid = cand.get("userId")
    if not uid:
        momoid, source = resolve_momoid_for_phone(str(cand["phone"]))
        uid = momoid
        cand["userId"] = uid
        cand["momoidSource"] = source
    if not uid:
        return {
            **cand,
            "ok": False,
            "inUse": None,
            "idle": None,
            "error": "无法解析 userId（索引/MOA 均失败），无法检测占用",
        }
    usage = check_account_in_use(
        user_id=uid,
        since_seconds=since_seconds,
        activity_keywords=activity_keywords,
    )
    return {
        "action": "accountsCheck",
        "ok": True,
        **cand,
        **usage,
    }


def pick_idle_account(
    *,
    candidates: list[dict[str, Any]] | None = None,
    preferred: str | None = None,
    since_seconds: int = 300,
    activity_keywords: tuple[str, ...] = DEFAULT_ACTIVITY_KEYWORDS,
) -> dict[str, Any]:
    pool = list(candidates or list_index_account_candidates())
    if preferred and str(preferred).strip():
        key = str(preferred).strip()
        preferred_rows = [c for c in pool if c.get("account") == key]
        others = [c for c in pool if c.get("account") != key]
        pool = preferred_rows + others

    checked: list[dict[str, Any]] = []
    picked: dict[str, Any] | None = None
    skipped_in_use: list[str] = []

    for cand in pool:
        phone = str(cand.get("phone", "")).strip()
        if not phone:
            continue
        uid = cand.get("userId")
        if not uid:
            uid, source = resolve_momoid_for_phone(phone)
            cand = {**cand, "userId": uid, "momoidSource": source}
        if not uid:
            checked.append({**cand, "checkOk": False, "error": "无 userId"})
            continue
        usage = check_account_in_use(
            user_id=str(uid),
            since_seconds=since_seconds,
            activity_keywords=activity_keywords,
        )
        row = {**cand, **usage, "checkOk": True}
        checked.append(row)
        label = str(cand.get("account") or phone)
        if usage.get("inUse"):
            skipped_in_use.append(label)
            continue
        picked = row
        break

    return {
        "action": "accountsPick",
        "ok": picked is not None,
        "sinceSeconds": since_seconds,
        "picked": picked,
        "skippedInUse": skipped_in_use,
        "candidates": checked,
        "agentHint": (
            f"选用 {picked.get('account') or picked.get('phone')}（{picked.get('phone')}）"
            if picked
            else f"候选账号均在用：{', '.join(skipped_in_use) or '（无）'}；扩大 --phones 范围或加大 --since"
        ),
    }


def login_idle_account(
    *,
    serial: str | None = None,
    preferred: str | None = None,
    candidates: list[dict[str, Any]] | None = None,
    since_seconds: int = 300,
    check_me: bool = False,
    tunnel_wait: int = 25,
) -> dict[str, Any]:
    serial = serial or require_device(None)
    shot_dir = screenshot_dir(None)

    pick = pick_idle_account(
        candidates=candidates,
        preferred=preferred,
        since_seconds=since_seconds,
    )
    if not pick.get("ok") or not pick.get("picked"):
        return {
            "action": "accountsLoginIdle",
            "ok": False,
            "pick": pick,
            "agentHint": pick.get("agentHint"),
        }

    picked = pick["picked"]
    phone = str(picked["phone"]).strip()

    try:
        _ensure_logout(serial, shot_dir, 2)
    except AiOperateRequired as exc:
        return {
            "action": "accountsLoginIdle",
            "ok": False,
            "pick": pick,
            "requiresAiVision": True,
            "aiPayload": exc.payload,
            "agentHint": "须先退出到登录页：ai prepare --goal logout → 读图点 Log out",
        }

    login_result = sweep_one_account(
        phone,
        serial=serial,
        shot_dir=shot_dir,
        check_me=check_me,
        tunnel_wait=tunnel_wait,
    )
    return {
        "action": "accountsLoginIdle",
        "ok": bool(login_result.get("ok")),
        "pick": pick,
        "phone": phone,
        "account": picked.get("account"),
        "userId": picked.get("userId"),
        "login": login_result,
        "agentHint": login_result.get("agentHint") or pick.get("agentHint"),
    }


def check_all_index_accounts(*, since_seconds: int = 300) -> dict[str, Any]:
    rows = []
    for cand in list_index_account_candidates():
        rows.append(
            check_account(
                account=cand.get("account"),
                since_seconds=since_seconds,
            )
        )
    idle = [r for r in rows if r.get("idle")]
    in_use = [r for r in rows if r.get("inUse")]
    return {
        "action": "accountsCheckAll",
        "sinceSeconds": since_seconds,
        "total": len(rows),
        "idleCount": len(idle),
        "inUseCount": len(in_use),
        "idleAccounts": [
            r.get("account") or r.get("phone") for r in idle
        ],
        "inUseAccounts": [
            r.get("account") or r.get("phone") for r in in_use
        ],
        "results": rows,
    }
