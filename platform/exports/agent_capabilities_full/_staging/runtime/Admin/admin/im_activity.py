"""活动 IM 配置（cms/activity/addIm、getImList）。"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from .client import http_post_json
from .config import defaults
from .guild import anchor_success

# 消息类型 → API 字段 sendType（后台「消息类型」下拉，0~5）
IM_MESSAGE_TYPES: dict[int, str] = {
    0: "活动通知下发",
    1: "活动奖励下发",
    2: "游戏官方消息",
    3: "主播官方消息",
    4: "Yaahlan助手消息",
    5: "客服消息",
}

# 下发类型 → API 字段 type（后台「下发类型」）
IM_DELIVERY_TYPES: dict[int, str] = {
    0: "活动下发（非定时下发）",
    1: "非定时下发",
    2: "定时任务下发（定时下发）",
    5: "Yaahlan小助手定时任务下发",
}

# 选择「定时任务下发」时，type 固定为 2
IM_SCHEDULED_DELIVERY_TYPE = 2

# 下发用户 userType（与后台下拉一致：任务 12/13=30天→2，任务 15=7天→1）
IM_USER_TYPES: dict[int, str] = {
    1: "近7天活跃用户",
    2: "近30天活跃用户",
    3: "白名单用户",
}

# 六种消息类型默认双语文案（英 + 阿）
IM_MESSAGE_TYPE_BILINGUAL: dict[int, dict[str, str]] = {
    0: {
        "en": "[IM smoke] Activity notification / 30-day active / MENA",
        "ar": "[اختبار IM] إشعار النشاط / نشط 30 يوم / MENA",
    },
    1: {
        "en": "[IM smoke] Activity reward / 30-day active / MENA",
        "ar": "[اختبار IM] مكافأة النشاط / نشط 30 يوم / MENA",
    },
    2: {
        "en": "[IM smoke] Official game message / 30-day active / MENA",
        "ar": "[اختبار IM] رسالة رسمية للعبة / نشط 30 يوم / MENA",
    },
    3: {
        "en": "[IM smoke] Official streamer message / 30-day active / MENA",
        "ar": "[اختبار IM] رسالة رسمية للمضيف / نشط 30 يوم / MENA",
    },
    4: {
        "en": "[IM smoke] Yaahlan assistant message / 30-day active / MENA",
        "ar": "[اختبار IM] رسالة مساعد Yaahlan / نشط 30 يوم / MENA",
    },
    5: {
        "en": "[IM smoke] Customer service message / 30-day active / MENA",
        "ar": "[اختبار IM] رسالة خدمة العملاء / نشط 30 يوم / MENA",
    },
}


def build_add_im_payload(
    *,
    name: str,
    msg_type: int,
    user_type: int = 2,
    delivery_type: int = IM_SCHEDULED_DELIVERY_TYPE,
    send_time_ms: int,
    area: str = "MENA",
    msg_en: str | None = None,
    msg_ar: str | None = None,
    image_en: str = "",
    image_ar: str = "",
    task_id: str = "",
    goto_url: str = "",
    bg_color: str = "",
    white_list: str = "",
) -> dict[str, Any]:
    if msg_type not in IM_MESSAGE_TYPES:
        raise ValueError(f"未知消息类型 sendType={msg_type}，支持: {sorted(IM_MESSAGE_TYPES)}")
    if user_type not in IM_USER_TYPES:
        raise ValueError(f"未知下发用户 userType={user_type}，支持: {sorted(IM_USER_TYPES)}")
    if delivery_type not in IM_DELIVERY_TYPES:
        raise ValueError(
            f"未知下发类型 type={delivery_type}，当前支持: {sorted(IM_DELIVERY_TYPES)}"
        )

    label = IM_MESSAGE_TYPES[msg_type]
    bilingual = IM_MESSAGE_TYPE_BILINGUAL.get(msg_type, {})
    if msg_en is None:
        content_en = bilingual.get("en") or f"[IM smoke] {label} / {IM_USER_TYPES[user_type]} / {area}"
    else:
        content_en = msg_en
    if msg_ar is None:
        content_ar = bilingual.get("ar") or f"[اختبار IM] {label} / {IM_USER_TYPES[user_type]} / {area}"
    else:
        content_ar = msg_ar
    return {
        "id": task_id,
        "name": name,
        "msgContent": {"en": content_en, "ar": content_ar},
        "userFilterType": 0,
        "type": delivery_type,
        "userType": user_type,
        "whiteList": white_list,
        "filePath": "",
        "fileName": "",
        "userCount": "",
        "image": {"ar": image_ar, "en": image_en},
        "gotoUrl": goto_url,
        "sendTime": send_time_ms,
        "sendType": msg_type,
        "bgColor": bg_color,
        "area": area,
    }


def add_im_task(payload: dict[str, Any], *, timeout_s: float = 30.0) -> dict[str, Any]:
    cfg = defaults("add_im")
    base_url = str(cfg.get("baseUrl") or "https://melon-gateway-alpha-stage.immomo.com").rstrip("/")
    path = str(cfg.get("path") or "/yaahlan/cms/activity/addIm")
    resp = http_post_json(f"{base_url}{path}", payload, timeout_s=timeout_s)
    if not anchor_success(resp):
        raise RuntimeError(f"addIm 失败: ec={resp.get('ec')}, em={resp.get('em')}")
    return resp


IM_SEND_STATUS_LABELS: dict[int, str] = {
    0: "等待中",
    1: "已下发",
}


def _normalize_im_task(row: dict[str, Any]) -> dict[str, Any]:
    delivery_type = row.get("type")
    message_type = row.get("sendType")
    send_status = row.get("sendStatus")

    try:
        delivery_type_int = int(delivery_type)
    except (TypeError, ValueError):
        delivery_type_int = delivery_type

    try:
        message_type_int = int(message_type)
    except (TypeError, ValueError):
        message_type_int = message_type

    try:
        send_status_int = int(send_status)
    except (TypeError, ValueError):
        send_status_int = send_status

    send_time_ms = row.get("sendTime")
    send_time_local = None
    try:
        send_time_local = datetime.fromtimestamp(int(send_time_ms) / 1000).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    except (TypeError, ValueError, OSError):
        pass

    return {
        "id": row.get("id"),
        "name": row.get("name"),
        "area": row.get("area"),
        "deliveryType": delivery_type_int,
        "deliveryTypeLabel": IM_DELIVERY_TYPES.get(delivery_type_int)
        if isinstance(delivery_type_int, int)
        else None,
        "messageType": message_type_int,
        "messageTypeLabel": IM_MESSAGE_TYPES.get(message_type_int)
        if isinstance(message_type_int, int)
        else None,
        "userType": row.get("userType"),
        "userTypeLabel": IM_USER_TYPES.get(int(row.get("userType")))
        if str(row.get("userType") or "").isdigit()
        else None,
        "sendStatus": send_status_int,
        "sendStatusLabel": IM_SEND_STATUS_LABELS.get(send_status_int)
        if isinstance(send_status_int, int)
        else None,
        "sendNum": row.get("sendNum"),
        "sendTimeMs": send_time_ms,
        "sendTimeLocal": send_time_local,
        "msgContent": row.get("msgContent"),
        "image": row.get("image"),
        "gotoUrl": row.get("gotoUrl"),
        "bgColor": row.get("bgColor"),
        "whiteList": row.get("whiteList"),
        "senderCsId": row.get("senderCsId"),
    }


def fetch_im_list(*, area: str = "MENA", timeout_s: float = 30.0) -> dict[str, Any]:
    cfg = defaults("query_im_list")
    base_url = str(cfg.get("baseUrl") or "https://melon-gateway-alpha-stage.immomo.com").rstrip("/")
    path = str(cfg.get("path") or "/yaahlan/cms/activity/getImList")
    resp = http_post_json(f"{base_url}{path}", {"area": area}, timeout_s=timeout_s)
    if not anchor_success(resp):
        raise RuntimeError(f"getImList 失败: ec={resp.get('ec')}, em={resp.get('em')}")
    return resp


def parse_im_list_summary(
    data: Any,
    *,
    area: str | None = None,
    task_id: str | None = None,
    task_name: str | None = None,
    name_contains: str | None = None,
) -> dict[str, Any]:
    if not isinstance(data, list):
        raise RuntimeError("无法解析 IM 任务列表 data（不是 array）")

    tasks = [_normalize_im_task(row) for row in data if isinstance(row, dict)]

    def _match(task: dict[str, Any]) -> bool:
        if task_id and str(task.get("id") or "").strip() != str(task_id).strip():
            return False
        if task_name:
            if str(task.get("name") or "").strip() != str(task_name).strip():
                return False
        if name_contains:
            needle = str(name_contains).strip().lower()
            haystack = str(task.get("name") or "").strip().lower()
            if needle and needle not in haystack:
                return False
        return True

    filtered = [task for task in tasks if _match(task)]
    filtered.sort(key=lambda item: int(item.get("id") or 0), reverse=True)

    return {
        "area": area,
        "totalTasks": len(tasks),
        "returnedCount": len(filtered),
        "taskIdFilter": str(task_id).strip() if task_id else None,
        "taskNameFilter": str(task_name).strip() if task_name else None,
        "nameContainsFilter": str(name_contains).strip() if name_contains else None,
        "fieldMapping": {
            "type": "下发类型",
            "sendType": "消息类型",
        },
        "tasks": filtered,
    }


def delete_im_task(*, task_id: int, area: str = "MENA", timeout_s: float = 30.0) -> dict[str, Any]:
    cfg = defaults("delete_im")
    base_url = str(cfg.get("baseUrl") or "https://melon-gateway-alpha-stage.immomo.com").rstrip("/")
    path = str(cfg.get("path") or "/yaahlan/cms/activity/deleteIm")
    resp = http_post_json(
        f"{base_url}{path}",
        {"id": int(task_id), "area": area},
        timeout_s=timeout_s,
    )
    if not anchor_success(resp):
        raise RuntimeError(f"deleteIm 失败: id={task_id}, ec={resp.get('ec')}, em={resp.get('em')}")
    return resp


def delete_im_tasks_above_id(
    *,
    min_exclusive_id: int,
    area: str = "MENA",
    dry_run: bool = False,
    timeout_s: float = 30.0,
) -> dict[str, Any]:
    """删除指定分区内 id 大于 min_exclusive_id 的全部 IM 任务。"""
    if min_exclusive_id < 0:
        raise ValueError("min_exclusive_id 不能为负数")

    list_resp = fetch_im_list(area=area, timeout_s=timeout_s)
    rows = list_resp.get("data")
    if not isinstance(rows, list):
        raise RuntimeError("getImList data 不是 array")

    targets: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            task_id = int(row.get("id"))
        except (TypeError, ValueError):
            continue
        if task_id > min_exclusive_id:
            targets.append(_normalize_im_task(row))

    targets.sort(key=lambda item: int(item.get("id") or 0))

    results: list[dict[str, Any]] = []
    for task in targets:
        task_id = int(task["id"])
        entry: dict[str, Any] = {
            "id": task_id,
            "name": task.get("name"),
            "area": area,
        }
        if dry_run:
            entry["status"] = "dry_run"
            results.append(entry)
            continue
        try:
            delete_im_task(task_id=task_id, area=area, timeout_s=timeout_s)
        except RuntimeError as exc:
            entry["status"] = "failed"
            entry["error"] = str(exc)
            results.append(entry)
            continue
        entry["status"] = "deleted"
        results.append(entry)

    deleted = [item for item in results if item.get("status") == "deleted"]
    failed = [item for item in results if item.get("status") == "failed"]
    return {
        "area": area,
        "minExclusiveId": min_exclusive_id,
        "matchedCount": len(targets),
        "deletedCount": len(deleted),
        "failedCount": len(failed),
        "dryRun": dry_run,
        "results": results,
    }


def schedule_im_message_type_smoke(
    *,
    area: str = "MENA",
    user_type: int = 2,
    start_offset_minutes: int = 1,
    interval_minutes: int = 1,
    name_prefix: str = "im-type-smoke",
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    """为 6 种消息类型各创建一条定时 IM 任务，sendTime 依次递增 interval_minutes。"""
    if start_offset_minutes < 1:
        raise ValueError("start_offset_minutes 至少为 1，避免任务立即过期")
    if interval_minutes < 1:
        raise ValueError("interval_minutes 至少为 1")

    now_ms = int(time.time() * 1000)
    minute_ms = 60_000
    run_tag = datetime.now().strftime("%m%d-%H%M")
    results: list[dict[str, Any]] = []

    for index, msg_type in enumerate(sorted(IM_MESSAGE_TYPES)):
        offset_min = start_offset_minutes + index * interval_minutes
        send_time_ms = now_ms + offset_min * minute_ms
        msg_label = IM_MESSAGE_TYPES[msg_type]
        name = f"{name_prefix}-{run_tag}-t{msg_type}-{msg_label}"
        payload = build_add_im_payload(
            name=name,
            msg_type=msg_type,
            user_type=user_type,
            delivery_type=IM_SCHEDULED_DELIVERY_TYPE,
            send_time_ms=send_time_ms,
            area=area,
        )
        entry: dict[str, Any] = {
            "index": index + 1,
            "deliveryType": IM_SCHEDULED_DELIVERY_TYPE,
            "deliveryTypeLabel": IM_DELIVERY_TYPES[IM_SCHEDULED_DELIVERY_TYPE],
            "messageType": msg_type,
            "messageTypeLabel": msg_label,
            "userType": user_type,
            "userTypeLabel": IM_USER_TYPES[user_type],
            "area": area,
            "name": name,
            "sendTimeMs": send_time_ms,
            "sendTimeLocal": datetime.fromtimestamp(send_time_ms / 1000).strftime("%Y-%m-%d %H:%M:%S"),
            "payload": payload,
        }
        if dry_run:
            entry["status"] = "dry_run"
            results.append(entry)
            continue

        try:
            resp = add_im_task(payload)
        except RuntimeError as exc:
            entry["status"] = "failed"
            entry["error"] = str(exc)
            results.append(entry)
            continue

        entry["status"] = "created"
        entry["response"] = resp
        results.append(entry)

    return results


def summarize_schedule_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    created = [r for r in results if r.get("status") == "created"]
    failed = [r for r in results if r.get("status") == "failed"]
    return {
        "total": len(results),
        "created": len(created),
        "failed": len(failed),
        "dryRun": all(r.get("status") == "dry_run" for r in results),
        "fieldMapping": {
            "type": "下发类型（定时任务下发固定 2）",
            "sendType": "消息类型（0~5）",
        },
        "tasks": [
            {
                "name": r.get("name"),
                "deliveryType": r.get("deliveryType"),
                "deliveryTypeLabel": r.get("deliveryTypeLabel"),
                "messageType": r.get("messageType"),
                "messageTypeLabel": r.get("messageTypeLabel"),
                "payloadType": (r.get("payload") or {}).get("type"),
                "payloadSendType": (r.get("payload") or {}).get("sendType"),
                "msgContent": (r.get("payload") or {}).get("msgContent"),
                "sendTimeLocal": r.get("sendTimeLocal"),
                "status": r.get("status"),
                "error": r.get("error"),
            }
            for r in results
        ],
    }
