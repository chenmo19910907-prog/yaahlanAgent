"""批量操作项数上限：非管理员单任务最多 1000 项，管理员不限。"""

from __future__ import annotations

import os
import re

from admin_permission import is_admin
from task_chain_estimate import _count_batch_items

# 与 batch_progress.BATCH_MIN_ITEMS 一致（勿从 batch_progress 导入，避免循环依赖）
_BATCH_MIN_ITEMS = 3

NON_ADMIN_MAX_BATCH_ITEMS = 1000

_USER_KEY_STAFF_RE = re.compile(r":user:([^:]+)$")
_PHONE_RANGE_CLI_RE = re.compile(
    r"--phone-start\s+(\d+)\s+.*--phone-end\s+(\d+)",
    re.I | re.S,
)
_PHONE_RANGE_NL_RE = re.compile(
    r"(\d{11})\s*(?:到|至|~|—|-)\s*(\d{11})",
)

_POLICY_EXCLUDE_RE = re.compile(
    r"(应该|需要|希望|要求|限制|开通|授权|增加|添加|修改|设置).{0,16}(上限|批量|1000)|"
    r"批量操作.{0,12}(上限|限制|1000)|"
    r"非管理员.{0,12}1000|"
    r"管理员不限制",
    re.I,
)

_DENY_TEMPLATE = (
    "批量操作项数为 {total}，超过非管理员单任务上限 {limit}。"
    "请拆成多个任务，或在用户头像信息中打开「管理员列表」申请管理员。"
)


def non_admin_max_batch_items() -> int:
    return NON_ADMIN_MAX_BATCH_ITEMS


def batch_operation_denial_message(*, total: int, limit: int | None = None) -> str:
    cap = limit if limit is not None else NON_ADMIN_MAX_BATCH_ITEMS
    return _DENY_TEMPLATE.format(total=int(total), limit=int(cap))


def _phone_range_count(start: str, end: str) -> int:
    try:
        a = int(start)
        b = int(end)
    except ValueError:
        return 0
    if a > b:
        a, b = b, a
    if b - a > 50_000_000:
        return 0
    return b - a + 1


def estimate_batch_item_count(prompt: str) -> int:
    """从用户问题粗估批量项数（与 task_chain_estimate 一致，并补充号段）。"""
    text = (prompt or "").strip()
    if not text:
        return 1

    best = _count_batch_items(text)
    for pattern in (_PHONE_RANGE_CLI_RE, _PHONE_RANGE_NL_RE):
        for m in pattern.finditer(text):
            n = _phone_range_count(m.group(1), m.group(2))
            if n > best:
                best = n
    return max(1, best)


def is_batch_over_non_admin_limit(total: int, *, is_admin_user: bool) -> bool:
    if is_admin_user:
        return False
    try:
        n = int(total)
    except (TypeError, ValueError):
        return False
    return n > NON_ADMIN_MAX_BATCH_ITEMS


def resolve_batch_operation_denial(
    prompt: str,
    *,
    is_admin_user: bool,
) -> str | None:
    """任务开始前：根据问题文本预估批量项数并拒绝超限。"""
    if is_admin_user:
        return None
    text = (prompt or "").strip()
    if not text or _POLICY_EXCLUDE_RE.search(text):
        return None
    total = estimate_batch_item_count(text)
    if total < _BATCH_MIN_ITEMS:
        return None
    if total > NON_ADMIN_MAX_BATCH_ITEMS:
        return batch_operation_denial_message(total=total)
    return None


def _staff_from_user_key(user_key: str) -> str:
    key = (user_key or "").strip()
    m = _USER_KEY_STAFF_RE.search(key)
    if m:
        return m.group(1).strip()
    return ""


def _hydrate_caller_staff_id() -> str:
    staff = (os.environ.get("WEB_AGENT_CALLER_STAFF_ID") or "").strip()
    if staff:
        return staff
    staff = (os.environ.get("DINGTALK_SENDER_STAFF_ID") or "").strip()
    if staff:
        return staff
    try:
        import sys
        from pathlib import Path

        web_agent_dir = Path(__file__).resolve().parents[1] / "web_agent"
        if str(web_agent_dir) not in sys.path:
            sys.path.insert(0, str(web_agent_dir))
        from web_agent_audit_context import hydrate_audit_env_from_store  # noqa: WPS433

        hydrate_audit_env_from_store()
    except (ImportError, OSError, ValueError):
        return ""
    return (os.environ.get("WEB_AGENT_CALLER_STAFF_ID") or "").strip()


def resolve_is_admin_for_batch_limit(
    *,
    user_key: str = "",
    sender_staff_id: str | None = None,
    sender_id: str | None = None,
) -> bool:
    staff = (sender_staff_id or "").strip() or _staff_from_user_key(user_key)
    if not staff:
        staff = _hydrate_caller_staff_id()
    return is_admin(
        sender_staff_id=staff or None,
        sender_id=sender_id,
        staff_id=staff or None,
    )


def assert_batch_total_allowed(
    total: int,
    *,
    user_key: str = "",
    sender_staff_id: str | None = None,
    sender_id: str | None = None,
) -> None:
    """进度上报 / 脚本写入时校验 total（管理员不限）。"""
    try:
        n = int(total)
    except (TypeError, ValueError):
        raise ValueError("批量 total 无效") from None
    if n <= NON_ADMIN_MAX_BATCH_ITEMS:
        return
    admin_user = resolve_is_admin_for_batch_limit(
        user_key=user_key,
        sender_staff_id=sender_staff_id,
        sender_id=sender_id,
    )
    if admin_user:
        return
    raise ValueError(batch_operation_denial_message(total=n))
