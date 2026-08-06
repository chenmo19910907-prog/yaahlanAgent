"""钉钉 userId → 姓名解析（会话内已知昵称 + 通讯录 API + 本地缓存）。"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from web_session_store import SessionMeta

logger = logging.getLogger("web-agent")

WEB_AGENT_DIR = Path(__file__).resolve().parent
NAME_CACHE_PATH = WEB_AGENT_DIR / "data" / "dingtalk_user_names.json"
ORG_ROSTER_CACHE_PATH = WEB_AGENT_DIR / "data" / "dingtalk_org_roster.json"
WEB_AUTH_SESSIONS_PATH = WEB_AGENT_DIR / "data" / "web_auth_sessions.json"
MESSAGE_BOARD_PATH = WEB_AGENT_DIR / "data" / "message_board.json"
ORG_ROSTER_TTL_S = 6 * 3600

_lock = threading.Lock()
_cache: dict[str, str] | None = None
_org_roster_cache: dict[str, object] | None = None
_org_roster_refresh_attempt_at: float = 0.0
ORG_ROSTER_RETRY_S = 900
# 共同对话选人列表不展示的系统/占位账号
_COLLABORATOR_EXCLUDED_DISPLAY_NAMES = frozenset({"未知用户", "测试员"})


def _load_cache() -> dict[str, str]:
    global _cache
    if _cache is not None:
        return _cache
    if not NAME_CACHE_PATH.is_file():
        _cache = {}
        return _cache
    try:
        raw = json.loads(NAME_CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        _cache = {}
        return _cache
    if not isinstance(raw, dict):
        _cache = {}
        return _cache
    _cache = {str(k): str(v) for k, v in raw.items() if str(k).strip() and str(v).strip()}
    return _cache


def _save_cache(data: dict[str, str]) -> None:
    global _cache
    NAME_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    NAME_CACHE_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _cache = dict(data)


_CJK_NAME_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]+")


def chinese_display_name(label: str) -> str:
    """中文+英文混排姓名仅保留中文；纯英文或无中文则原样返回。"""
    name = (label or "").strip()
    if not name:
        return name
    parts = _CJK_NAME_RE.findall(name)
    if parts:
        return "".join(parts)
    return name


def _has_cjk(label: str) -> bool:
    return bool(_CJK_NAME_RE.search(label or ""))


def _prefer_staff_label(prev: str, new: str) -> str:
    """合并两候选展示名：优先含中文、更长者。"""
    left = (prev or "").strip()
    right = (new or "").strip()
    if not left:
        return right
    if not right:
        return left
    left_cjk = _has_cjk(left)
    right_cjk = _has_cjk(right)
    if right_cjk and not left_cjk:
        return right
    if left_cjk and not right_cjk:
        return left
    left_pub = chinese_display_name(left)
    right_pub = chinese_display_name(right)
    if len(right_pub) > len(left_pub):
        return right
    if len(left_pub) > len(right_pub):
        return left
    return right


def _merge_staff_label(known: dict[str, str], staff_id: str, display_name: str) -> None:
    uid = (staff_id or "").strip()
    label = (display_name or "").strip()
    if not uid:
        return
    if label == uid:
        return
    prev = known.get(uid, "")
    if not prev:
        known[uid] = label
        return
    if label:
        known[uid] = _prefer_staff_label(prev, label)


def _public_display_name(label: str, staff_id: str = "") -> str:
    """对外展示名：不回落为 staffId 数字编号。"""
    name = chinese_display_name((label or "").strip())
    sid = (staff_id or "").strip()
    if name and name != sid:
        return name
    return "未知用户"


def _staff_user(staff_id: str, label: str) -> dict[str, str]:
    sid = (staff_id or "").strip()
    return {"staffId": sid, "displayName": _public_display_name(label, sid)}


def resolve_staff_display_name(
    staff_id: str,
    *,
    known_labels: dict[str, str] | None = None,
    fallback_label: str = "",
    try_api: bool = False,
) -> str:
    """多元汇总解析 staffId 展示名：known_labels → fallback → 可选 API。"""
    uid = (staff_id or "").strip()
    best = ""
    labels = known_labels or {}
    if uid:
        mapped = (labels.get(uid) or "").strip()
        if mapped:
            best = mapped
    fallback = (fallback_label or "").strip()
    if fallback:
        best = _prefer_staff_label(best, fallback) if best else fallback
    if uid and try_api:
        try:
            api_name = resolve_dingtalk_name(uid, known=labels, try_api=True)
        except Exception:  # noqa: BLE001
            api_name = ""
        if api_name:
            best = _prefer_staff_label(best, api_name) if best else api_name
    return chinese_display_name(best)


def lookup_staff_public_name(
    staff_id: str,
    fallback_label: str = "",
    *,
    sessions: list[SessionMeta] | None = None,
) -> str:
    """按多元汇总返回对外展示名（含未知用户兜底）。"""
    known = collect_all_staff_labels(sessions or [])
    resolved = resolve_staff_display_name(
        staff_id,
        known_labels=known,
        fallback_label=fallback_label,
    )
    return _public_display_name(resolved or fallback_label, staff_id)


def collect_known_labels(sessions: list[SessionMeta]) -> dict[str, str]:
    """从已有会话里汇总 staffId → 钉钉昵称。"""
    known: dict[str, str] = {}
    for meta in sessions:
        if meta.source == "dingtalk":
            uid = (meta.dingtalk_owner_id or "").strip()
            label = (meta.dingtalk_label or "").strip()
        elif meta.source == "web":
            uid = (meta.web_owner_id or "").strip()
            label = (meta.web_owner_label or "").strip()
        else:
            continue
        _merge_staff_label(known, uid, label)
        for collab_id in meta.web_collaborator_ids:
            _merge_staff_label(known, collab_id, "")
    return known


def collect_web_auth_staff_labels() -> dict[str, str]:
    """从网页登录会话落盘汇总 staffId → 展示名。"""
    known: dict[str, str] = {}
    if not WEB_AUTH_SESSIONS_PATH.is_file():
        return known
    try:
        raw = json.loads(WEB_AUTH_SESSIONS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return known
    if not isinstance(raw, dict):
        return known
    for entry in raw.values():
        if not isinstance(entry, dict):
            continue
        _merge_staff_label(
            known,
            str(entry.get("staffId") or ""),
            str(entry.get("displayName") or ""),
        )
    return known


def collect_message_board_staff_labels() -> dict[str, str]:
    """从留言板作者汇总 staffId → 展示名（跳过访客）。"""
    from message_board_store import is_guest_staff_id  # noqa: WPS433

    known: dict[str, str] = {}
    if not MESSAGE_BOARD_PATH.is_file():
        return known
    try:
        raw = json.loads(MESSAGE_BOARD_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return known
    messages = raw.get("messages") if isinstance(raw, dict) else None
    if not isinstance(messages, list):
        return known
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        staff_id = str(msg.get("staffId") or "").strip()
        if not staff_id or is_guest_staff_id(staff_id):
            continue
        _merge_staff_label(known, staff_id, str(msg.get("displayName") or ""))
    return known


def _get_access_token() -> str:
    import sys

    gateway_dir = WEB_AGENT_DIR.parent / "dingtalk_gateway"
    if str(gateway_dir) not in sys.path:
        sys.path.insert(0, str(gateway_dir))
    from alidocs_upload import get_access_token  # noqa: WPS433

    return get_access_token()


def _post_topapi(token: str, api_path: str, payload: dict[str, object]) -> dict[str, object]:
    url = f"https://oapi.dingtalk.com/{api_path}?access_token={token}"
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        raw = json.loads(resp.read().decode("utf-8"))
    if not isinstance(raw, dict):
        raise RuntimeError("钉钉接口返回格式异常")
    return raw


def _fetch_department_ids(token: str, root_dept_id: int = 1) -> list[int]:
    pending = [root_dept_id]
    seen: set[int] = set()
    while pending:
        dept_id = pending.pop(0)
        if dept_id in seen:
            continue
        seen.add(dept_id)
        data = _post_topapi(token, "topapi/v2/department/listsub", {"dept_id": dept_id})
        if int(data.get("errcode") or 0) != 0:
            raise RuntimeError(str(data.get("errmsg") or data.get("sub_msg") or "department list failed"))
        result = data.get("result")
        child_ids: list[int] = []
        if isinstance(result, dict):
            raw_ids = result.get("dept_id_list")
            if isinstance(raw_ids, list):
                child_ids = [int(item) for item in raw_ids if str(item).strip().isdigit()]
        pending.extend(child_id for child_id in child_ids if child_id not in seen)
    return sorted(seen)


def _fetch_users_in_department(token: str, dept_id: int) -> list[dict[str, str]]:
    users: list[dict[str, str]] = []
    cursor = 0
    while True:
        data = _post_topapi(
            token,
            "topapi/v2/user/list",
            {"dept_id": dept_id, "cursor": cursor, "size": 100},
        )
        if int(data.get("errcode") or 0) != 0:
            raise RuntimeError(str(data.get("errmsg") or data.get("sub_msg") or "user list failed"))
        result = data.get("result")
        if not isinstance(result, dict):
            break
        raw_list = result.get("list")
        if isinstance(raw_list, list):
            for item in raw_list:
                if not isinstance(item, dict):
                    continue
                staff_id = str(item.get("userid") or "").strip()
                if not staff_id:
                    continue
                display_name = ""
                for key in ("name", "nickname"):
                    value = str(item.get(key) or "").strip()
                    if value:
                        display_name = value
                        break
                users.append(_staff_user(staff_id, display_name))
        next_cursor = int(result.get("next_cursor") or 0)
        if not result.get("has_more"):
            break
        if next_cursor == cursor:
            break
        cursor = next_cursor
    return users


def fetch_org_roster_from_api() -> list[dict[str, str]]:
    """拉取企业通讯录全员（需应用开通部门/成员读权限）。"""
    token = _get_access_token()
    merged: dict[str, str] = {}
    for dept_id in _fetch_department_ids(token):
        for user in _fetch_users_in_department(token, dept_id):
            _merge_staff_label(merged, user["staffId"], user["displayName"])
    users = [_staff_user(uid, label) for uid, label in merged.items()]
    users.sort(key=lambda item: (item["displayName"], item["staffId"]))
    return users


def _load_org_roster_cache() -> dict[str, object]:
    global _org_roster_cache
    if _org_roster_cache is not None:
        return _org_roster_cache
    if not ORG_ROSTER_CACHE_PATH.is_file():
        _org_roster_cache = {}
        return _org_roster_cache
    try:
        raw = json.loads(ORG_ROSTER_CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        _org_roster_cache = {}
        return _org_roster_cache
    _org_roster_cache = raw if isinstance(raw, dict) else {}
    return _org_roster_cache


def _save_org_roster_cache(users: list[dict[str, str]]) -> None:
    global _org_roster_cache
    payload = {
        "fetched_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "users": users,
    }
    ORG_ROSTER_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    ORG_ROSTER_CACHE_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _org_roster_cache = payload


def load_org_roster(*, refresh: bool = False) -> list[dict[str, str]]:
    """读取企业通讯录缓存；过期或 refresh 时尝试刷新。"""
    global _org_roster_refresh_attempt_at

    cached = _load_org_roster_cache()
    users_raw = cached.get("users")
    users: list[dict[str, str]] = []
    if isinstance(users_raw, list):
        for item in users_raw:
            if not isinstance(item, dict):
                continue
            staff_id = str(item.get("staffId") or "").strip()
            if not staff_id:
                continue
            display_name = _public_display_name(str(item.get("displayName") or ""), staff_id)
            users.append({"staffId": staff_id, "displayName": display_name})

    fetched_at = str(cached.get("fetched_at") or "").strip()
    stale = refresh
    if fetched_at:
        try:
            ts = datetime.fromisoformat(fetched_at.replace("Z", "+00:00")).timestamp()
            stale = stale or (time.time() - ts > ORG_ROSTER_TTL_S)
        except ValueError:
            stale = True
    else:
        stale = not users

    if not stale:
        return users

    now = time.time()
    if not refresh and now - _org_roster_refresh_attempt_at < ORG_ROSTER_RETRY_S:
        return users

    _org_roster_refresh_attempt_at = now
    try:
        fresh = fetch_org_roster_from_api()
    except (RuntimeError, OSError, urllib.error.URLError, ValueError) as exc:
        logger.debug("刷新企业通讯录失败，使用本地缓存: %s", exc)
        if not fetched_at:
            _save_org_roster_cache(users)
        return users

    if fresh:
        _save_org_roster_cache(fresh)
        return fresh
    if not fetched_at:
        _save_org_roster_cache(users)
    return users


def collect_all_staff_labels(
    sessions: list[SessionMeta],
    *,
    try_api_for_ascii: bool = True,
    max_api_lookups: int = 12,
) -> dict[str, str]:
    """汇总所有已知人员：会话、登录、留言板、姓名缓存、企业通讯录。"""
    known = collect_known_labels(sessions)
    known.update(collect_web_auth_staff_labels())
    known.update(collect_message_board_staff_labels())
    with _lock:
        known.update(_load_cache())
    for user in load_org_roster():
        _merge_staff_label(known, user["staffId"], user["displayName"])
    if try_api_for_ascii:
        api_calls = 0
        for uid, label in list(known.items()):
            if api_calls >= max_api_lookups:
                break
            if _has_cjk(label):
                continue
            resolved = resolve_dingtalk_name(uid, known=known, try_api=True)
            api_calls += 1
            if resolved:
                known[uid] = _prefer_staff_label(label, resolved)
    return known


def _fetch_name_from_api(user_id: str) -> str | None:
    """调用钉钉通讯录 API 查询姓名（需应用开通成员信息读权限）。"""
    uid = (user_id or "").strip()
    if not uid:
        return None
    try:
        import sys

        gateway_dir = WEB_AGENT_DIR.parent / "dingtalk_gateway"
        if str(gateway_dir) not in sys.path:
            sys.path.insert(0, str(gateway_dir))
        from alidocs_upload import get_access_token  # noqa: WPS433

        token = get_access_token()
    except Exception as exc:  # noqa: BLE001
        logger.debug("获取钉钉 token 失败，跳过姓名解析 uid=%s: %s", uid[:12], exc)
        return None

    url = f"https://oapi.dingtalk.com/topapi/v2/user/get?access_token={token}"
    payload = json.dumps({"userid": uid, "language": "zh_CN"}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError) as exc:
        logger.debug("钉钉用户查询失败 uid=%s: %s", uid[:12], exc)
        return None

    if int(data.get("errcode") or 0) != 0:
        logger.debug(
            "钉钉用户查询 errcode=%s uid=%s",
            data.get("errcode"),
            uid[:12],
        )
        return None
    result = data.get("result")
    if not isinstance(result, dict):
        return None
    for key in ("name", "nickname", "real_authed_name"):
        value = str(result.get(key) or "").strip()
        if value:
            return value
    return None


def resolve_dingtalk_name(
    user_id: str,
    *,
    known: dict[str, str] | None = None,
    try_api: bool = True,
) -> str:
    """解析 userId 为展示名；优先中文真实姓名，失败则返回空字符串。"""
    uid = (user_id or "").strip()
    if not uid:
        return ""

    with _lock:
        cached = (_load_cache().get(uid) or "").strip()

    known_name = (known or {}).get(uid, "").strip() if known else ""

    best = ""
    for candidate in (cached, known_name):
        if candidate:
            best = _prefer_staff_label(best, candidate) if best else candidate

    if try_api and not _has_cjk(best):
        api_name = (_fetch_name_from_api(uid) or "").strip()
        if api_name:
            best = _prefer_staff_label(best, api_name) if best else api_name

    if best:
        with _lock:
            cache = _load_cache()
            prev = (cache.get(uid) or "").strip()
            merged = _prefer_staff_label(prev, best) if prev else best
            if merged != prev:
                cache[uid] = merged
                _save_cache(cache)
        return best

    return ""


def is_selectable_collaborator(staff_id: str, display_name: str) -> bool:
    """共同对话可选人员：排除占位名与测试账号。"""
    sid = (staff_id or "").strip()
    name = _public_display_name(display_name, sid)
    if name in _COLLABORATOR_EXCLUDED_DISPLAY_NAMES:
        return False
    return bool(sid)


def filter_staff_users(
    users: list[dict[str, str]],
    query: str,
) -> list[dict[str, str]]:
    """按姓名子串过滤（大小写不敏感，不匹配 staffId）。"""
    needle = (query or "").strip().lower()
    if not needle:
        return users
    filtered: list[dict[str, str]] = []
    for user in users:
        display_name = str(user.get("displayName") or "").strip().lower()
        if needle in display_name:
            filtered.append(user)
    return filtered


def list_selectable_staff_users(
    sessions: list[SessionMeta],
    *,
    exclude_staff_id: str = "",
    query: str = "",
) -> list[dict[str, str]]:
    """汇总可选人员（会话/登录/留言板/姓名缓存/企业通讯录），按展示名排序。"""
    known = collect_all_staff_labels(sessions)
    exclude = (exclude_staff_id or "").strip()
    users: list[dict[str, str]] = []
    seen: set[str] = set()
    for uid, label in known.items():
        staff_id = (uid or "").strip()
        if not staff_id or staff_id in seen or staff_id == exclude:
            continue
        user = _staff_user(staff_id, label)
        if not is_selectable_collaborator(user["staffId"], user["displayName"]):
            continue
        seen.add(staff_id)
        users.append(user)
    users.sort(key=lambda item: (item["displayName"], item["staffId"]))
    return filter_staff_users(users, query)


def enrich_session_owner_labels(
    sessions: list[SessionMeta],
    *,
    try_api: bool = True,
    max_api_lookups: int = 8,
) -> int:
    """用多元汇总补全/升级 dingtalk_label；返回更新条数。"""
    known = collect_all_staff_labels(sessions)

    updated = 0
    api_calls = 0
    for meta in sessions:
        if meta.source != "dingtalk":
            continue
        uid = (meta.dingtalk_owner_id or "").strip()
        if not uid:
            continue
        stored = (meta.dingtalk_label or "").strip()
        resolved = (known.get(uid) or "").strip()
        if not resolved and try_api and api_calls < max_api_lookups:
            resolved = resolve_dingtalk_name(uid, known=known, try_api=True)
            api_calls += 1
            if resolved:
                known[uid] = resolved
        if not resolved:
            continue
        best = _prefer_staff_label(stored, resolved) if stored else resolved
        if best and best != stored:
            meta.dingtalk_label = best
            known[uid] = best
            updated += 1

    return updated
