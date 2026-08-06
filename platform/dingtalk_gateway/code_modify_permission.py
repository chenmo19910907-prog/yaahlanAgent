"""钉钉网关：谁可以通过机器人修改 Cursor/网关代码逻辑。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

GATEWAY_DIR = Path(__file__).resolve().parent
ALLOWLIST_PATH = GATEWAY_DIR / "config" / "code_modify_allowlist.json"
ALLOWLIST_LOCAL_PATH = GATEWAY_DIR / "config" / "code_modify_allowlist.local.json"

# 延迟导入，避免与 moa_registry_guard 循环依赖
def _looks_like_moa_registry_intent(text: str) -> bool:
    from moa_registry_guard import looks_like_moa_registry_intent

    return looks_like_moa_registry_intent(text)

CODE_PATH_RE = re.compile(
    r"(dingtalk[_-]?gateway|platform/dingtalk|\bgateway\b|\.cursor/|gateway_prompt|cursor_runner|"
    r"registry\.json|SKILL\.md|command_router|code_modify|bridge_manager|"
    r"export_delivery|reply_formatter|natural_language)",
    re.I,
)
CODE_ACTION_RE = re.compile(
    r"(改|修改|实现|新增|增加|加上|写入|重构|修复|fix|refactor|commit|提交代码|"
    r"代码逻辑|pull.?request|merge.?request|\bMR\b|\bPR\b)",
    re.I,
)
CODE_INTENT_RE = re.compile(
    r"((机器人|网关|Agent|cursor).{0,24}(改|修改|实现|增加|能力|权限|逻辑))|"
    r"((改|修改|实现|增加|权限).{0,24}(机器人|网关|Agent|cursor|代码))",
    re.I,
)
OPS_EXCLUDE_RE = re.compile(
    r"(接单|VIP|vip|经验值?|注销|风控|公会|客服.*状态|升级|抓包|查询|导出|"
    r"生成测试用例|测试用例|用户信息|房间|榜单|MOA|Admin|Tunnel|线上环境)",
    re.I,
)


@dataclass(frozen=True)
class CodeModifyAllowlist:
    allowed_staff_ids: frozenset[str]
    allowed_sender_ids: frozenset[str]
    deny_message: str


def _normalize_ids(raw: object) -> list[str]:
    if not isinstance(raw, list):
        return []
    ids: list[str] = []
    for item in raw:
        text = str(item or "").strip()
        if text:
            ids.append(text)
    return ids


@lru_cache(maxsize=1)
def load_code_modify_allowlist() -> CodeModifyAllowlist:
    data: dict[str, object] = {}
    if ALLOWLIST_PATH.is_file():
        data.update(json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8")))
    if ALLOWLIST_LOCAL_PATH.is_file():
        data.update(json.loads(ALLOWLIST_LOCAL_PATH.read_text(encoding="utf-8")))

    staff_ids = _normalize_ids(data.get("allowedStaffIds"))
    sender_ids = _normalize_ids(data.get("allowedSenderIds"))
    deny_message = str(data.get("denyMessage") or "").strip() or (
        "你没有修改代码逻辑的权限。请联系管理员开通。"
    )
    return CodeModifyAllowlist(
        allowed_staff_ids=frozenset(staff_ids),
        allowed_sender_ids=frozenset(sender_ids),
        deny_message=deny_message,
    )


def reload_code_modify_allowlist() -> CodeModifyAllowlist:
    load_code_modify_allowlist.cache_clear()
    return load_code_modify_allowlist()


def is_code_modify_allowed(
    *,
    sender_staff_id: str | None,
    sender_id: str | None,
) -> bool:
    cfg = load_code_modify_allowlist()
    staff = (sender_staff_id or "").strip()
    sender = (sender_id or "").strip()
    if staff and staff in cfg.allowed_staff_ids:
        return True
    if sender and sender in cfg.allowed_sender_ids:
        return True
    return False


def is_moa_registry_open_to_all() -> bool:
    """MOA 能力入库对全员开放，不受代码修改白名单限制。"""
    return True


def allow_moa_registry_in_readonly(*, code_modify_allowed: bool) -> bool:
    """只读账号是否允许 MOA 能力入库（与网关代码修改权限解耦）。"""
    if code_modify_allowed:
        return False
    return is_moa_registry_open_to_all()


def looks_like_code_modify_request(prompt: str) -> bool:
    text = (prompt or "").strip()
    if not text:
        return False
    if is_moa_registry_open_to_all() and _looks_like_moa_registry_intent(text):
        return False
    if OPS_EXCLUDE_RE.search(text) and not CODE_PATH_RE.search(text):
        return False
    if CODE_PATH_RE.search(text) and CODE_ACTION_RE.search(text):
        return True
    if CODE_INTENT_RE.search(text):
        return True
    return False


def code_modify_denial_message() -> str:
    return load_code_modify_allowlist().deny_message


def get_admin_notify_staff_ids() -> list[str]:
    """管理员审批通知接收人（环境变量优先，否则白名单全部）。"""
    import os

    from env_loader import load_env_local

    load_env_local()
    raw = os.environ.get("WEB_AGENT_ADMIN_NOTIFY_STAFF_ID", "").strip()
    if raw:
        ids = [part.strip() for part in raw.split(",") if part.strip()]
        if ids:
            return ids
    cfg = load_code_modify_allowlist()
    return sorted(cfg.allowed_staff_ids)


def add_staff_to_local_allowlist(staff_id: str) -> bool:
    """追加 staffId 到 local allowlist；已存在则返回 False。"""
    uid = (staff_id or "").strip()
    if not uid:
        raise ValueError("staff_id 不能为空")
    cfg = load_code_modify_allowlist()
    if uid in cfg.allowed_staff_ids:
        return False

    local_data: dict[str, object] = {}
    if ALLOWLIST_LOCAL_PATH.is_file():
        local_data = json.loads(ALLOWLIST_LOCAL_PATH.read_text(encoding="utf-8"))
        if not isinstance(local_data, dict):
            local_data = {}

    existing = _normalize_ids(local_data.get("allowedStaffIds"))
    if uid in existing:
        reload_code_modify_allowlist()
        return False

    existing.append(uid)
    local_data["allowedStaffIds"] = existing
    ALLOWLIST_LOCAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    ALLOWLIST_LOCAL_PATH.write_text(
        json.dumps(local_data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    reload_code_modify_allowlist()
    return True
