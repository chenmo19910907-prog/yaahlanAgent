"""MDP Nova 用户列表（userAdmin/queryUserProfileList）请求与响应解析。"""

from __future__ import annotations

import os
import re
from typing import Any

from .client import http_post_json
from .config import defaults
from .gift import mdp_gift_success as mdp_user_admin_success

# MDP 用户列表 banStatus：3=已注销（与 queryUserDetail accountState=-1 一致）
BAN_STATUS_CANCELLED = 3


def parse_user_id_list(raw: str | None) -> list[int]:
    if raw is None or not str(raw).strip():
        return []
    ids: list[int] = []
    for part in re.split(r"[\s,\n]+", str(raw).strip()):
        token = part.strip()
        if not token:
            continue
        try:
            ids.append(int(token))
        except ValueError as e:
            raise ValueError(f"userIdList 含非法 userId: {token!r}") from e
    return ids


def build_query_user_profile_list_body(
    *,
    app_id: int,
    page_no: int,
    page_size: int,
    user_ids: list[int] | None = None,
    nickname: str | None = None,
    phone: str | None = None,
    area_code: str | None = None,
    device_id: str | None = None,
    mmuidv3: str | None = None,
    email: str | None = None,
    area: str | None = None,
    ban_status: str | None = None,
    gender: str | None = None,
    country_code: str | None = None,
    register_type: str | None = None,
) -> dict[str, object]:
    if page_no <= 0:
        raise ValueError("user-list-page-no 必须为正整数")
    if page_size <= 0:
        raise ValueError("user-list-page-size 必须为正整数")

    body: dict[str, object] = {
        "userIdList": user_ids or [],
        "pageNo": page_no,
        "pageSize": page_size,
    }
    optional_fields: dict[str, str | None] = {
        "appId": str(app_id),
        "nickname": nickname,
        "phone": phone,
        "areaCode": area_code,
        "deviceId": device_id,
        "mmuidv3": mmuidv3,
        "email": email,
        "area": area,
        "banStatus": ban_status,
        "gender": gender,
        "countryCode": country_code,
        "registerType": register_type,
    }
    for key, value in optional_fields.items():
        if key == "appId":
            body[key] = app_id
            continue
        text = str(value or "").strip()
        if text:
            body[key] = text
    return body


def _simplify_record(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "userId": row.get("userId"),
        "nickname": row.get("nickname"),
        "genderName": row.get("genderName"),
        "birthday": row.get("birthday"),
        "countryName": row.get("countryName"),
        "area": row.get("area"),
        "areaCode": row.get("areaCode"),
        "phone": row.get("phone"),
        "registerType": row.get("registerType"),
        "registerTime": row.get("registerTime"),
        "lastLoginTime": row.get("lastLoginTime"),
        "banStatus": row.get("banStatus"),
    }


def _normalize_phone_digits(text: str | None) -> str:
    return re.sub(r"\D", "", str(text or ""))


def is_active_profile_list_record(row: dict[str, Any]) -> bool:
    status = row.get("banStatus")
    if status is None:
        return True
    try:
        return int(status) != BAN_STATUS_CANCELLED
    except (TypeError, ValueError):
        return True


def profile_list_phone_matches(
    row: dict[str, Any],
    *,
    phone: str,
    area_code: str | None,
) -> bool:
    raw = str(row.get("phone") or "").strip()
    if not raw:
        return False
    want_mobile = _normalize_phone_digits(phone)
    want_area = _normalize_phone_digits(area_code or "")
    if "|" in raw:
        row_area, row_mobile = raw.split("|", 1)
        row_area = _normalize_phone_digits(row_area)
        row_mobile = _normalize_phone_digits(row_mobile)
    else:
        row_area, row_mobile = "", _normalize_phone_digits(raw)
    if row_mobile != want_mobile:
        return False
    if want_area and row_area and row_area != want_area:
        return False
    return True


def filter_phone_lookup_records(
    records: list[dict[str, Any]],
    *,
    phone: str | None,
    area_code: str | None,
    active_only: bool,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    phone_text = str(phone or "").strip()
    if not phone_text:
        return records, {"rawReturnedCount": len(records), "excludedCancelledCount": 0}

    filtered: list[dict[str, Any]] = []
    excluded_cancelled = 0
    for row in records:
        if not profile_list_phone_matches(row, phone=phone_text, area_code=area_code):
            continue
        if active_only and not is_active_profile_list_record(row):
            excluded_cancelled += 1
            continue
        filtered.append(row)
    return filtered, {
        "rawReturnedCount": len(records),
        "excludedCancelledCount": excluded_cancelled,
    }


def parse_query_user_profile_list_summary(
    data: Any,
    *,
    filter_phone: str | None = None,
    filter_area_code: str | None = None,
    active_only: bool = False,
) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise RuntimeError("无法解析用户列表 data（不是 object）")

    page_info = data.get("pageInfo")
    if not isinstance(page_info, dict):
        page_info = {}

    raw_records = data.get("records")
    if not isinstance(raw_records, list):
        raise RuntimeError("无法解析用户列表 records（不是 array）")

    records = [_simplify_record(row) for row in raw_records if isinstance(row, dict)]
    filter_stats: dict[str, int] = {}
    if str(filter_phone or "").strip():
        records, filter_stats = filter_phone_lookup_records(
            records,
            phone=filter_phone,
            area_code=filter_area_code,
            active_only=active_only,
        )

    summary: dict[str, Any] = {
        "pageNo": page_info.get("pageNo"),
        "pageSize": page_info.get("pageSize"),
        "totalCount": page_info.get("totalCount"),
        "totalPage": page_info.get("totalPage"),
        "returnedCount": len(records),
        "records": records,
    }
    if filter_stats:
        summary.update(filter_stats)
        if len(records) == 1:
            summary["userId"] = records[0].get("userId")
    return summary


def _resolve_mdp_base_url(cfg: dict[str, Any]) -> str:
    base_url = (
        os.environ.get("MDP_ADMIN_BASE_URL")
        or cfg.get("baseUrl")
        or ""
    ).strip().rstrip("/")
    if not base_url:
        raise ValueError("缺少 MDP Admin 域名：请设置 MDP_ADMIN_BASE_URL 或 config.json 中 query_user_profile_list.baseUrl")
    return base_url


def fetch_user_profile_list(body: dict[str, object], *, timeout_s: float = 30.0) -> dict[str, Any]:
    cfg = defaults("query_user_profile_list")
    base_url = _resolve_mdp_base_url(cfg)
    path = str(cfg.get("path", "/userAdmin/queryUserProfileList"))
    url = f"{base_url}{path}"
    resp = http_post_json(url, body, timeout_s=timeout_s, auth="mdp_nova")
    if not mdp_user_admin_success(resp.get("ec")):
        raise RuntimeError(f"queryUserProfileList 失败: ec={resp.get('ec')}, em={resp.get('em')}")
    return parse_query_user_profile_list_summary(resp.get("data"))


def parse_exclude_user_ids(raw: str | None) -> set[str]:
    if raw is None or not str(raw).strip():
        return set()
    return {token.strip() for token in re.split(r"[\s,\n]+", str(raw).strip()) if token.strip()}


def has_user_info(record: dict[str, Any]) -> bool:
    """判断用户列表记录是否包含有效用户信息（有昵称即视为有资料）。"""
    nickname = str(record.get("nickname") or "").strip()
    return bool(nickname)


def pick_friend_candidates_from_user_list(
    *,
    target_user_id: str,
    count: int,
    exclude: set[str] | None = None,
    page_start: int = 1,
    page_size: int = 50,
    max_pages: int = 50,
    app_id: int = 2005,
    nickname: str | None = None,
    phone: str | None = None,
    area_code: str | None = None,
    device_id: str | None = None,
    mmuidv3: str | None = None,
    email: str | None = None,
    area: str | None = None,
    ban_status: str | None = None,
    gender: str | None = None,
    country_code: str | None = None,
    register_type: str | None = None,
    require_user_info: bool = True,
) -> list[str]:
    if count <= 0:
        raise ValueError("count 必须为正整数")
    if page_start <= 0:
        raise ValueError("page_start 必须为正整数")
    if page_size <= 0:
        raise ValueError("page_size 必须为正整数")
    if max_pages <= 0:
        raise ValueError("max_pages 必须为正整数")

    blocked = set(exclude or set())
    blocked.add(str(target_user_id).strip())

    selected: list[str] = []
    seen: set[str] = set()
    for page_no in range(page_start, page_start + max_pages):
        body = build_query_user_profile_list_body(
            app_id=app_id,
            page_no=page_no,
            page_size=page_size,
            nickname=nickname,
            phone=phone,
            area_code=area_code,
            device_id=device_id,
            mmuidv3=mmuidv3,
            email=email,
            area=area,
            ban_status=ban_status,
            gender=gender,
            country_code=country_code,
            register_type=register_type,
        )
        summary = fetch_user_profile_list(body)
        records = summary.get("records") or []
        if not records:
            break
        for row in records:
            if not isinstance(row, dict):
                continue
            uid = row.get("userId")
            if uid is None:
                continue
            uid_str = str(uid).strip()
            if not uid_str or uid_str in blocked or uid_str in seen:
                continue
            if require_user_info and not has_user_info(row):
                continue
            seen.add(uid_str)
            selected.append(uid_str)
            if len(selected) >= count:
                return selected
    return selected
