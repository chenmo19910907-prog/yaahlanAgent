"""线上 MOA 成功操作后钉钉通知超级管理员。"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger("web-agent")


def _notify_disabled() -> bool:
    return os.environ.get("ONLINE_MOA_NOTIFY_DISABLE", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def build_online_moa_alert_message(entry: dict) -> str:
    operator = str(entry.get("operatorName") or entry.get("operatorStaffId") or "未知").strip()
    operation = str(entry.get("operation") or "MOA 操作").strip()
    account = str(entry.get("accountSummary") or "").strip()
    iface = str(entry.get("moaInterface") or "").strip()
    params = str(entry.get("paramsSummary") or "").strip()
    result = str(entry.get("resultSummary") or "").strip()
    count = int(entry.get("callCount") or 1)
    batch = f"（合并 {count} 次）" if count > 1 else ""

    lines = [
        "【线上 MOA 操作提醒】",
        "",
        f"操作：{operation}{batch}",
        f"操作人：{operator}",
    ]
    if account:
        lines.append(f"账号：线上 · {account}" if not account.startswith("线上") else f"账号：{account}")
    if iface:
        lines.append(f"接口：{iface}")
    if params:
        lines.append(f"参数：{params}")
    if result:
        lines.append(f"结果：{result}")
    return "\n".join(lines)


def notify_super_admins_online_moa(
    entry: dict,
    *,
    operator_staff_id: str = "",
) -> int:
    """向全部可通知的超管发钉钉私聊；返回成功发送人数。失败静默。"""
    if _notify_disabled():
        return 0
    if str(entry.get("source") or "moa").strip().lower() != "moa":
        return 0
    env = str(entry.get("environment") or "").strip().lower()
    if env not in ("online", "prod", "production"):
        return 0

    try:
        from web_admin_grants import list_super_admin_staff_ids
        from web_admin_notify import _can_notify_staff, send_robot_private_text
    except Exception as exc:  # noqa: BLE001
        logger.warning("线上 MOA 通知依赖加载失败: %s", exc)
        return 0

    text = build_online_moa_alert_message(entry)
    operator = (operator_staff_id or str(entry.get("operatorStaffId") or "")).strip()
    sent = 0
    for admin_id in list_super_admin_staff_ids():
        if not _can_notify_staff(admin_id):
            continue
        if admin_id == operator:
            continue
        try:
            send_robot_private_text(admin_id, text)
            sent += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "线上 MOA 钉钉通知失败 admin=%s…: %s",
                admin_id[:12],
                exc,
            )
    if sent:
        logger.info(
            "线上 MOA 已通知超管 %s 人 operation=%s",
            sent,
            str(entry.get("operation") or "")[:60],
        )
    return sent


def maybe_notify_online_moa_after_record(
    entry: dict,
    *,
    operator_staff_id: str,
    is_new_entry: bool,
    previous_call_count: int = 0,
) -> None:
    """新记录或批量合并第 2 次时通知一次（避免 N 次重复）。"""
    call_count = int(entry.get("callCount") or 1)
    if is_new_entry:
        notify_super_admins_online_moa(entry, operator_staff_id=operator_staff_id)
        return
    if call_count >= 2 and previous_call_count < 2:
        notify_super_admins_online_moa(entry, operator_staff_id=operator_staff_id)
