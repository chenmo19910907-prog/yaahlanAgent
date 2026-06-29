"""MDP Nova 用户列表（userAdmin/queryUserProfileList）请求与响应解析。"""

from __future__ import annotations

import re
from typing import Any

from .gift import mdp_gift_success as mdp_user_admin_success


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
        "registerType": row.get("registerType"),
        "registerTime": row.get("registerTime"),
        "lastLoginTime": row.get("lastLoginTime"),
        "banStatus": row.get("banStatus"),
    }


def parse_query_user_profile_list_summary(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise RuntimeError("无法解析用户列表 data（不是 object）")

    page_info = data.get("pageInfo")
    if not isinstance(page_info, dict):
        page_info = {}

    raw_records = data.get("records")
    if not isinstance(raw_records, list):
        raise RuntimeError("无法解析用户列表 records（不是 array）")

    records = [_simplify_record(row) for row in raw_records if isinstance(row, dict)]
    return {
        "pageNo": page_info.get("pageNo"),
        "pageSize": page_info.get("pageSize"),
        "totalCount": page_info.get("totalCount"),
        "totalPage": page_info.get("totalPage"),
        "returnedCount": len(records),
        "records": records,
    }
