"""MDP Nova 用户列表（userAdmin/queryUserProfileList）请求与响应解析。"""

from __future__ import annotations

import os
import re
from typing import Any

from .client import http_post_json
from .config import defaults
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
            seen.add(uid_str)
            selected.append(uid_str)
            if len(selected) >= count:
                return selected
    return selected
