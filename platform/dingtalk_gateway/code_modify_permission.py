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


def looks_like_code_modify_request(prompt: str) -> bool:
    text = (prompt or "").strip()
    if not text:
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
