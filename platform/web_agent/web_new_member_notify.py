"""Agent 新成员：Web / 钉钉机器人首次使用时钉钉通知超级管理员。"""

from __future__ import annotations

import fcntl
import json
import logging
import os
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

logger = logging.getLogger("web-agent")

WEB_AGENT_DIR = Path(__file__).resolve().parent
DATA_DIR = WEB_AGENT_DIR / "data"
KNOWN_USERS_PATH = DATA_DIR / "known_agent_users.json"
LOCK_PATH = DATA_DIR / ".known_agent_users.lock"

_thread_lock = threading.Lock()
_bootstrap_done = False


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@contextmanager
def _exclusive_known_users() -> Iterator[None]:
    with _thread_lock:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(LOCK_PATH), os.O_CREAT | os.O_RDWR)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)


def _load_known_unlocked() -> dict[str, str]:
    if not KNOWN_USERS_PATH.is_file():
        return {}
    try:
        data = json.loads(KNOWN_USERS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    raw = data.get("users")
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for staff_id, stamp in raw.items():
        uid = str(staff_id or "").strip()
        if uid:
            out[uid] = str(stamp or "").strip() or "legacy"
    return out


def _save_known_unlocked(users: dict[str, str]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"users": dict(users)}
    KNOWN_USERS_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _collect_legacy_staff_ids() -> set[str]:
    ids: set[str] = set()
    try:
        from dingtalk_user_lookup import collect_web_auth_staff_labels

        ids.update(collect_web_auth_staff_labels().keys())
    except Exception as exc:  # noqa: BLE001
        logger.debug("bootstrap 读取登录用户失败: %s", exc)

    try:
        from web_session_store import _session_owner_staff_id, get_session_store

        for meta in get_session_store().list_sessions(
            enrich_names=False,
            sync_derived_meta=False,
            readonly=True,
        ):
            uid = _session_owner_staff_id(meta).strip()
            if uid:
                ids.add(uid)
    except Exception as exc:  # noqa: BLE001
        logger.debug("bootstrap 读取会话归属失败: %s", exc)

    ids.update(_staff_ids_from_dingtalk_conversations())
    return ids


def _staff_ids_from_dingtalk_conversations() -> set[str]:
    path = WEB_AGENT_DIR.parent / "dingtalk_gateway" / "data" / "conversations.json"
    if not path.is_file():
        return set()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    if not isinstance(raw, dict):
        return set()
    out: set[str] = set()
    for key in raw:
        k = str(key or "").strip()
        uid = ""
        if k.startswith("dm:"):
            uid = k[3:].strip()
        elif ":user:" in k:
            uid = k.rsplit(":", 1)[-1].strip()
        if uid:
            out.add(uid)
    return out


def _ensure_bootstrap_locked() -> None:
    global _bootstrap_done
    if _bootstrap_done:
        return
    known = _load_known_unlocked()
    if known:
        _bootstrap_done = True
        return
    legacy = _collect_legacy_staff_ids()
    if legacy:
        stamp = _utc_now_iso()
        for uid in legacy:
            known[uid] = stamp
        _save_known_unlocked(known)
        logger.info("已知 Agent 用户 bootstrap %s 人（不通知）", len(legacy))
    _bootstrap_done = True


def build_new_member_message(*, display_name: str, staff_id: str) -> str:
    name = (display_name or "").strip() or (staff_id or "").strip() or "新用户"
    return f"【新成员】{name} 加入了 Web Agent"


def _notify_super_admins(*, display_name: str, staff_id: str) -> int:
    from web_admin_grants import list_super_admin_staff_ids
    from web_admin_notify import _can_notify_staff, send_robot_private_text

    text = build_new_member_message(display_name=display_name, staff_id=staff_id)
    uid = (staff_id or "").strip()
    sent = 0
    for admin_id in list_super_admin_staff_ids():
        if not _can_notify_staff(admin_id):
            continue
        if admin_id == uid:
            continue
        try:
            send_robot_private_text(admin_id, text)
            sent += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "新成员钉钉通知失败 admin=%s…: %s",
                admin_id[:12],
                exc,
            )
    if sent:
        logger.info("新成员已通知超管 %s 人 staff=%s…", sent, uid[:12])
    return sent


def maybe_notify_new_member(
    *,
    staff_id: str,
    display_name: str = "",
) -> bool:
    """
    首次使用该 Agent 的用户加入时通知超管。
    返回 True 表示本次为新成员且已尝试通知。
    """
    uid = (staff_id or "").strip()
    if not uid:
        return False

    from web_admin_notify import _can_notify_staff

    if not _can_notify_staff(uid):
        return False

    should_notify = False
    with _exclusive_known_users():
        _ensure_bootstrap_locked()
        known = _load_known_unlocked()
        if uid in known:
            return False
        known[uid] = _utc_now_iso()
        _save_known_unlocked(known)
        should_notify = True

    if should_notify:
        _notify_super_admins(display_name=display_name, staff_id=uid)
    return should_notify


def spawn_maybe_notify_new_member(staff_id: str, display_name: str = "") -> None:
    """后台线程触发新成员通知，供 Web / 钉钉网关共用。"""
    uid = (staff_id or "").strip()
    if not uid:
        return
    name = (display_name or "").strip()

    def work() -> None:
        try:
            maybe_notify_new_member(staff_id=uid, display_name=name)
        except Exception as exc:  # noqa: BLE001
            logger.warning("新成员通知异常 staff=%s…: %s", uid[:12], exc)

    threading.Thread(
        target=work,
        daemon=True,
        name=f"agent-new-member-{uid[:8]}",
    ).start()
