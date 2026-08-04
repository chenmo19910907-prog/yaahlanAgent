"""大R用户管理后台（yaahlan-admin /admin/big-rich/*）。"""

from __future__ import annotations

import calendar
import re
from datetime import date, datetime, timedelta
from typing import Any

from .client import admin_success, http_post_json
from .config import defaults

ENDPOINTS: dict[str, str] = {
    "page_list": "/admin/big-rich/pageList",
    "export_list": "/admin/big-rich/exportList",
    "vip_change_page": "/admin/big-rich/vip-change/page",
    "vip_change_export": "/admin/big-rich/vip-change/export",
    "daily_vip4_page": "/admin/big-rich/daily-vip4/page",
    "daily_vip4_export": "/admin/big-rich/daily-vip4/export",
    "detail_disburse_scene": "/admin/big-rich/detail/disburseScene",
    "detail_gift_top50": "/admin/big-rich/detail/giftTop50",
    "detail_recv_top50": "/admin/big-rich/detail/recvTop50",
    "detail_game_top": "/admin/big-rich/detail/gameTop",
    "detail_recharge_top20": "/admin/big-rich/detail/rechargeTop20",
}

QUERY_PERIOD_TYPE: dict[str, int] = {
    "WEEK_PERIOD": 1,
    "WEEK_SUMMARY": 2,
    "MONTH_PERIOD": 3,
    "MONTH_SUMMARY": 4,
    "FIXED_PERIOD": 5,
}

USER_TYPE_VIP = 2
USER_TYPE_RECHARGE = 1

VIP_CHANGE_UP = "UP"
VIP_CHANGE_DOWN = "DOWN"

PAGE_LIST_COLUMNS = (
    "userId",
    "nickname",
    "rechargeUsd",
    "rechargeCoin",
    "nonGameDisburseCoin",
    "gameBetCoin",
    "vipLevel",
    "wealthLevel",
    "country",
    "selfGiftCoin",
    "lastRechargeTime",
    "lastOnlineTime",
    "registerTime",
)


def big_rich_config() -> dict[str, Any]:
    cfg = defaults("big_rich")
    paths = cfg.get("paths")
    if isinstance(paths, dict):
        merged = dict(ENDPOINTS)
        merged.update({k: str(v) for k, v in paths.items() if v})
        cfg = dict(cfg)
        cfg["paths"] = merged
    else:
        cfg = dict(cfg)
        cfg["paths"] = dict(ENDPOINTS)
    return cfg


def build_big_rich_url(base_url: str, endpoint: str) -> str:
    cfg = big_rich_config()
    paths = cfg["paths"]
    if endpoint not in paths:
        raise ValueError(f"未知 endpoint: {endpoint}，可选: {', '.join(sorted(paths))}")
    prefix = str(cfg.get("apiPrefix") or "").rstrip("/")
    path = str(paths[endpoint])
    if not path.startswith("/"):
        path = f"/{path}"
    if prefix:
        return f"{base_url.rstrip('/')}{prefix}{path}"
    return f"{base_url.rstrip('/')}{path}"


def normalize_yyyymmdd(value: str | date | datetime | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.strftime("%Y%m%d")
    if isinstance(value, date):
        return value.strftime("%Y%m%d")
    text = str(value).strip()
    if not text:
        return None
    digits = re.sub(r"\D", "", text)
    if len(digits) != 8:
        raise ValueError(f"日期须为 YYYYMMDD 或 YYYY-MM-DD: {value!r}")
    return digits


def month_summary_range(reference: date | None = None) -> tuple[str, str]:
    ref = reference or date.today()
    start = ref.replace(day=1)
    end = ref
    return normalize_yyyymmdd(start) or "", normalize_yyyymmdd(end) or ""


def parse_yyyymmdd(value: str | date | datetime | None) -> date:
    normalized = normalize_yyyymmdd(value)
    if not normalized:
        raise ValueError("日期不能为空")
    return datetime.strptime(normalized, "%Y%m%d").date()


def encode_date_field(value: str | date | datetime | None, *, as_int: bool = True) -> str | int:
    normalized = normalize_yyyymmdd(value)
    if not normalized:
        raise ValueError("日期不能为空")
    return int(normalized) if as_int else normalized


def _last_day_of_month(d: date) -> date:
    return date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])


def _subtract_months(d: date, months: int) -> date:
    month_index = d.month - 1 - months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _iso_week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _iso_week_end(d: date) -> date:
    return _iso_week_start(d) + timedelta(days=6)


def compute_old_period_dates(
    query_period_type: str | int,
    new_start: date,
    new_end: date,
    *,
    reference: date | None = None,
) -> tuple[date, date]:
    if isinstance(query_period_type, int):
        period_name = next(
            (name for name, code in QUERY_PERIOD_TYPE.items() if code == query_period_type),
            "MONTH_SUMMARY",
        )
    else:
        period_name = str(query_period_type).upper()

    ref = reference or new_end

    if period_name == "FIXED_PERIOD":
        span_days = (new_end - new_start).days
        old_end = new_start - timedelta(days=1)
        old_start = old_end - timedelta(days=span_days)
        return old_start, old_end

    if period_name == "MONTH_SUMMARY":
        prev_end = new_start - timedelta(days=1)
        return prev_end.replace(day=1), prev_end

    if period_name == "MONTH_PERIOD":
        prev_ref = _subtract_months(ref, 1)
        end_day = min(new_end.day, calendar.monthrange(prev_ref.year, prev_ref.month)[1])
        return prev_ref.replace(day=1), prev_ref.replace(day=end_day)

    if period_name == "WEEK_PERIOD":
        prev_week = ref - timedelta(days=7)
        prev_week_start = _iso_week_start(prev_week)
        return prev_week_start, prev_week_start + timedelta(days=new_end.weekday())

    # WEEK_SUMMARY 及默认
    prev_week_end = _iso_week_end(ref - timedelta(days=7))
    return _iso_week_start(prev_week_end), prev_week_end


def build_page_list_body(
    *,
    user_type: int = USER_TYPE_VIP,
    user_id: str = "",
    country: str = "",
    query_period_type: str | int = "MONTH_SUMMARY",
    new_start_date: str | date | None = None,
    new_end_date: str | date | None = None,
    old_start_date: str | date | None = None,
    old_end_date: str | date | None = None,
    order_by: str = "rechargeUsd",
    sort: str = "desc",
    index: int = 0,
    limit: int = 20,
) -> dict[str, Any]:
    cfg = big_rich_config()
    if isinstance(query_period_type, str):
        period = QUERY_PERIOD_TYPE.get(query_period_type.upper())
        if period is None:
            raise ValueError(f"未知 queryPeriodType: {query_period_type}")
    else:
        period = int(query_period_type)

    if new_start_date is None or new_end_date is None:
        start, end = month_summary_range()
        new_start_date = new_start_date or start
        new_end_date = new_end_date or end

    new_start = parse_yyyymmdd(new_start_date)
    new_end = parse_yyyymmdd(new_end_date)
    period_name = next((name for name, code in QUERY_PERIOD_TYPE.items() if code == period), "MONTH_SUMMARY")

    if old_start_date and old_end_date:
        old_start = parse_yyyymmdd(old_start_date)
        old_end = parse_yyyymmdd(old_end_date)
    else:
        old_start, old_end = compute_old_period_dates(period_name, new_start, new_end)

    body: dict[str, Any] = {
        "userType": int(user_type),
        "queryPeriodType": period,
        "newStartDate": encode_date_field(new_start),
        "newEndDate": encode_date_field(new_end),
        "oldStartDate": encode_date_field(old_start),
        "oldEndDate": encode_date_field(old_end),
        "orderBy": order_by,
        "sort": sort,
        "index": int(index),
        "limit": int(limit),
    }
    uid = str(user_id or "").strip()
    if uid:
        body["userId"] = uid
    country_text = str(country or "").strip()
    if country_text:
        body["country"] = country_text
    default_limit = cfg.get("defaultLimit")
    if limit == 20 and default_limit is not None:
        body["limit"] = int(default_limit)
    return body


def build_user_detail_body(
    user_id: str,
    *,
    start_date: str | date | None = None,
    end_date: str | date | None = None,
) -> dict[str, Any]:
    uid = str(user_id).strip()
    if not uid:
        raise ValueError("userId 不能为空")
    if start_date is None or end_date is None:
        start, end = month_summary_range()
        start_date = start_date or start
        end_date = end_date or end
    return {
        "userId": uid,
        "startDate": normalize_yyyymmdd(start_date),
        "endDate": normalize_yyyymmdd(end_date),
    }


def build_vip_change_body(
    *,
    week_anchor_date: str | date | None = None,
    change_type: str = VIP_CHANGE_DOWN,
    index: int = 0,
    limit: int = 20,
) -> dict[str, Any]:
    if week_anchor_date is None:
        today = date.today()
        monday = today - timedelta(days=today.weekday())
        week_anchor_date = monday
    change = str(change_type or VIP_CHANGE_DOWN).strip().upper()
    if change not in (VIP_CHANGE_UP, VIP_CHANGE_DOWN):
        raise ValueError("changeType 须为 UP 或 DOWN")
    return {
        "weekAnchorDate": normalize_yyyymmdd(week_anchor_date),
        "changeType": change,
        "index": int(index),
        "limit": int(limit),
    }


def build_daily_vip4_body(
    *,
    start_date: str | date | None = None,
    end_date: str | date | None = None,
    index: int = 0,
    limit: int = 20,
) -> dict[str, Any]:
    if start_date is None:
        start_date = date.today() - timedelta(days=1)
    if end_date is None:
        end_date = start_date
    return {
        "startDate": normalize_yyyymmdd(start_date),
        "endDate": normalize_yyyymmdd(end_date),
        "index": int(index),
        "limit": int(limit),
    }


def post_big_rich(
    base_url: str,
    endpoint: str,
    body: dict[str, Any],
    *,
    timeout_s: float = 15.0,
    auth: str = "yaahlan",
) -> dict[str, Any]:
    url = build_big_rich_url(base_url, endpoint)
    resp = http_post_json(url, body, timeout_s=timeout_s, auth=auth)
    if not admin_success(resp.get("ec")):
        raise RuntimeError(
            f"大R接口失败 endpoint={endpoint} ec={resp.get('ec')} em={resp.get('em')}"
        )
    return resp


def extract_page_rows(resp: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    data = resp.get("data")
    if not isinstance(data, dict):
        return [], 0
    rows = data.get("data")
    items = [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []
    total_raw = data.get("totalCount", 0)
    try:
        total = int(total_raw)
    except (TypeError, ValueError):
        total = len(items)
    return items, total


def parse_page_list_summary(resp: dict[str, Any]) -> dict[str, Any]:
    rows, total = extract_page_rows(resp)
    return {
        "totalCount": total,
        "returned": len(rows),
        "userIds": [str(row.get("userId")) for row in rows if row.get("userId") is not None],
        "rows": rows,
    }


def parse_detail_bundle(results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {"sections": {}}
    for key, resp in results.items():
        data = resp.get("data")
        if isinstance(data, dict):
            summary["sections"][key] = data
        else:
            summary["sections"][key] = data
    disburse = summary["sections"].get("disburseScene")
    if isinstance(disburse, dict):
        summary["totalRechargeCoin"] = disburse.get("totalRechargeCoin")
        summary["totalDispatchCoin"] = disburse.get("totalDispatchCoin")
        summary["totalConsumeCoin"] = disburse.get("totalConsumeCoin")
    game = summary["sections"].get("gameTop")
    if isinstance(game, dict):
        summary["totalGameProfit"] = game.get("totalProfit")
    return summary


def verify_sort_monotonic(rows: list[dict[str, Any]], field: str, *, descending: bool) -> list[str]:
    issues: list[str] = []
    values: list[float] = []
    for row in rows:
        raw = row.get(field)
        if raw is None:
            continue
        try:
            values.append(float(raw))
        except (TypeError, ValueError):
            issues.append(f"字段 {field} 非数值: {raw!r}")
            return issues
    for idx in range(len(values) - 1):
        left, right = values[idx], values[idx + 1]
        if descending and left < right:
            issues.append(f"降序违反 idx={idx}: {left} < {right}")
        if not descending and left > right:
            issues.append(f"升序违反 idx={idx}: {left} > {right}")
    return issues


def verify_search_hit(rows: list[dict[str, Any]], user_id: str) -> list[str]:
    uid = str(user_id).strip()
    if not uid:
        return []
    if not rows:
        return [f"搜索 userId={uid} 无结果"]
    if len(rows) > 1:
        return [f"搜索 userId={uid} 返回 {len(rows)} 条，期望 1 条"]
    found = str(rows[0].get("userId") or "")
    if found != uid:
        return [f"搜索 userId={uid} 首条为 {found}"]
    return []


def verify_page_list_columns(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return []
    sample = rows[0]
    missing = [col for col in PAGE_LIST_COLUMNS if col not in sample]
    if missing:
        return [f"列表缺少字段: {', '.join(missing)}"]
    return []
