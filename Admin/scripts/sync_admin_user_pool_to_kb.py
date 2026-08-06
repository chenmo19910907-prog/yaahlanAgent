#!/usr/bin/env python3
"""从测试开发后台抓取 userId 写入 testcase-kb 备用池（支持活跃/非活跃分库）。"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "Admin" / "scripts"))

from admin_project_paths import (  # noqa: E402
    admin_module_dir,
    admin_user_pool_paths,
    online_test_accounts_path,
    test_devices_json_path,
    testcase_kb_root,
)

KB_PATH, INACTIVE_KB_PATH, ACTIVE_KB_PATH = admin_user_pool_paths()
UNLIMITED_TARGET = 10**9
TEST_DEVICES_PATH = test_devices_json_path()
ONLINE_ACCOUNTS_PATH = online_test_accounts_path()
_KB_ROOT = testcase_kb_root()
sys.path.insert(0, str(REPO_ROOT / "platform"))

from project.loader import stage_gateway_url  # noqa: E402

ANCHOR_LIST_URL = stage_gateway_url(
    "anchorList", "/yaahlan/cms/anchor/anchorList/anchorList"
)
GUILD_LIST_URL = stage_gateway_url(
    "guildList", "/yaahlan/cms/anchor/tradeUnionList/tradeUnionPageList"
)
USER_KEY_DEFAULT = "cidwuF5xkEMvaZMDWWu8BtHbg==:user:32274159141215328"

sys.path.insert(0, str(admin_module_dir()))

from admin.client import http_get_json, http_post_json  # noqa: E402
from admin.config import defaults  # noqa: E402
from admin.custom_gift import gateway_success, parse_custom_gift_list_summary  # noqa: E402
from admin.env import load_local_env  # noqa: E402
from admin.guild import parse_query_trade_union_summary  # noqa: E402
from admin.user import (  # noqa: E402
    parse_history_user_list_by_device_summary,
    parse_user_detail_summary,
)
from admin.user_list import (  # noqa: E402
    build_query_user_profile_list_body,
    fetch_user_profile_list,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _parse_utc_time(text: str | None) -> datetime | None:
    if not text:
        return None
    value = str(text).strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S UTC").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


class ActivityChecker:
    """按 queryUserDetail.lastOnLineTime 判断近 N 天是否活跃。"""

    def __init__(self, *, active_within_days: int) -> None:
        if active_within_days <= 0:
            raise ValueError("active_within_days 必须为正整数")
        self.active_within_days = active_within_days
        self.cutoff = datetime.now(timezone.utc) - timedelta(days=active_within_days)
        self._cache: dict[str, bool] = {}
        detail_cfg = defaults("query_user_detail")
        self._detail_path = str(detail_cfg.get("path", "/admin/user/queryUserDetail"))
        self._detail_base = str(
            detail_cfg.get("baseUrl") or "https://yaahlan-admin-alpha.wemomo.com"
        ).rstrip("/")

    def is_active(self, user_id: str) -> bool:
        uid = str(user_id or "").strip()
        if not uid:
            return True
        if uid in self._cache:
            return self._cache[uid]
        url = f"{self._detail_base}{self._detail_path}"
        resp = http_post_json(url, {"userId": uid}, timeout_s=20.0)
        if resp.get("ec") != 200:
            raise RuntimeError(
                f"查询用户详情失败: userId={uid} ec={resp.get('ec')} em={resp.get('em')}"
            )
        summary = parse_user_detail_summary(resp.get("data"))
        last_online = _parse_utc_time(str(summary.get("lastOnLineTime") or ""))
        active = bool(last_online and last_online >= self.cutoff)
        self._cache[uid] = active
        return active

    def is_inactive_candidate(self, user_id: str) -> bool:
        return not self.is_active(user_id)


class AreaChecker:
    """按 queryUserDetail.area 判断是否属于指定大区。"""

    def __init__(self, *, keep_area: str) -> None:
        value = str(keep_area or "").strip().upper()
        if not value:
            raise ValueError("keep_area 不能为空")
        self.keep_area = value
        self._cache: dict[str, str | None] = {}
        detail_cfg = defaults("query_user_detail")
        self._detail_path = str(detail_cfg.get("path", "/admin/user/queryUserDetail"))
        self._detail_base = str(
            detail_cfg.get("baseUrl") or "https://yaahlan-admin-alpha.wemomo.com"
        ).rstrip("/")

    def user_area(self, user_id: str) -> str | None:
        uid = str(user_id or "").strip()
        if not uid:
            return None
        if uid in self._cache:
            return self._cache[uid]
        url = f"{self._detail_base}{self._detail_path}"
        resp = http_post_json(url, {"userId": uid}, timeout_s=20.0)
        if resp.get("ec") != 200:
            raise RuntimeError(
                f"查询用户详情失败: userId={uid} ec={resp.get('ec')} em={resp.get('em')}"
            )
        summary = parse_user_detail_summary(resp.get("data"))
        area = str(summary.get("area") or "").strip().upper() or None
        self._cache[uid] = area
        return area

    def is_target_area(self, user_id: str) -> bool:
        return self.user_area(user_id) == self.keep_area


def filter_users_by_area(
    user_ids: list[str],
    *,
    checker: AreaChecker,
    user_key: str,
    report_progress: bool,
    progress_offset: int,
    progress_total: int,
) -> tuple[list[str], list[str]]:
    kept: list[str] = []
    removed: list[str] = []
    for index, uid in enumerate(user_ids, start=1):
        if checker.is_target_area(uid):
            kept.append(uid)
        else:
            removed.append(uid)
        if report_progress and progress_total >= 3:
            _report_progress(
                user_key=user_key,
                current=progress_offset + index,
                total=progress_total,
                detail=(
                    f"大区过滤 {index}/{len(user_ids)} · "
                    f"保留 {checker.keep_area} {len(kept)} · 剔除 {len(removed)}"
                ),
            )
    return kept, removed


def filter_out_active_users(
    user_ids: list[str],
    *,
    checker: ActivityChecker,
    user_key: str,
    report_progress: bool,
    progress_offset: int,
    progress_total: int,
) -> tuple[list[str], list[str], int]:
    kept: list[str] = []
    removed_active: list[str] = []
    for index, uid in enumerate(user_ids, start=1):
        if checker.is_inactive_candidate(uid):
            kept.append(uid)
        else:
            removed_active.append(uid)
        if report_progress and progress_total >= 3:
            _report_progress(
                user_key=user_key,
                current=progress_offset + index,
                total=progress_total,
                detail=f"活跃过滤 {index}/{len(user_ids)} · 保留 {len(kept)}",
            )
    return kept, removed_active, len(removed_active)


def classify_users_by_activity(
    user_ids: list[str],
    *,
    checker: ActivityChecker,
    user_key: str,
    report_progress: bool,
    progress_offset: int,
    progress_total: int,
) -> tuple[list[str], list[str]]:
    inactive_ids: list[str] = []
    active_ids: list[str] = []
    for index, uid in enumerate(user_ids, start=1):
        if checker.is_active(uid):
            active_ids.append(uid)
        else:
            inactive_ids.append(uid)
        if report_progress and progress_total >= 3:
            _report_progress(
                user_key=user_key,
                current=progress_offset + index,
                total=progress_total,
                detail=(
                    f"活跃分类 {index}/{len(user_ids)} · "
                    f"活跃 {len(active_ids)} · 非活跃 {len(inactive_ids)}"
                ),
            )
    return inactive_ids, active_ids


def dedupe_preserve_order(user_ids: list[str]) -> tuple[list[str], int]:
    seen: set[str] = set()
    ordered: list[str] = []
    removed = 0
    for raw in user_ids:
        uid = str(raw or "").strip()
        if not uid:
            continue
        if uid in seen:
            removed += 1
            continue
        seen.add(uid)
        ordered.append(uid)
    return ordered, removed


def _load_existing_pool(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _load_existing_user_ids(path: Path) -> list[str]:
    payload = _load_existing_pool(path)
    raw_ids = payload.get("userIds")
    if not isinstance(raw_ids, list):
        return []
    return [str(uid).strip() for uid in raw_ids if str(uid or "").strip()]


def _append_unique(
    selected: list[str],
    seen: set[str],
    candidates: list[str],
    *,
    target_count: int,
    checker: ActivityChecker | None = None,
    blocked: set[str] | None = None,
) -> int:
    added = 0
    deny = blocked or set()
    for raw in candidates:
        uid = str(raw or "").strip()
        if not uid or uid in seen or uid in deny:
            continue
        if checker is not None and not checker.is_inactive_candidate(uid):
            deny.add(uid)
            continue
        seen.add(uid)
        selected.append(uid)
        added += 1
        if len(selected) >= target_count:
            break
    return added


def _load_mmuidv3_list(path: Path) -> list[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    devices = payload.get("devices") if isinstance(payload, dict) else None
    if not isinstance(devices, list):
        raise RuntimeError(f"无法解析设备列表: {path}")
    seen: set[str] = set()
    ordered: list[str] = []
    for row in devices:
        if not isinstance(row, dict):
            continue
        mmuidv3 = str(row.get("mmuidv3") or "").strip()
        if not mmuidv3 or mmuidv3 in seen:
            continue
        seen.add(mmuidv3)
        ordered.append(mmuidv3)
    return ordered


def _report_progress(
    *,
    user_key: str,
    current: int,
    total: int,
    detail: str = "",
    result_text: str = "",
) -> None:
    if total < 3:
        return
    cmd = [
        sys.executable,
        str(REPO_ROOT / "platform" / "dingtalk_gateway" / "batch_progress_report.py"),
        "--user-key",
        user_key,
        "--current",
        str(current),
        "--total",
        str(total),
        "--label",
        "抓取用户ID",
    ]
    if detail:
        cmd.extend(["--detail", detail])
    if result_text:
        cmd.extend(["--result-text", result_text])
    subprocess.run(cmd, cwd=str(REPO_ROOT), check=False)


def fetch_from_mdp_user_list(
    *,
    target_count: int,
    page_size: int,
    seen: set[str],
    checker: ActivityChecker | None = None,
    blocked: set[str] | None = None,
) -> tuple[list[str], dict[str, Any]]:
    selected: list[str] = []
    meta: dict[str, Any] = {
        "name": "userAdmin/queryUserProfileList",
        "pageSize": page_size,
        "pagesFetched": 0,
        "totalCount": None,
        "addedCount": 0,
    }
    page_no = 1
    while len(selected) < target_count:
        body = build_query_user_profile_list_body(app_id=2005, page_no=page_no, page_size=page_size)
        summary = fetch_user_profile_list(body)
        meta["pagesFetched"] = page_no
        if meta["totalCount"] is None:
            meta["totalCount"] = summary.get("totalCount")
        records = summary.get("records") or []
        if not records:
            break
        batch: list[str] = []
        for row in records:
            if isinstance(row, dict):
                uid = str(row.get("userId") or "").strip()
                if uid:
                    batch.append(uid)
        added = _append_unique(
            selected,
            seen,
            batch,
            target_count=target_count,
            checker=checker,
            blocked=blocked,
        )
        meta["addedCount"] = int(meta["addedCount"]) + added
        if len(selected) >= target_count:
            break
        if len(records) < page_size:
            break
        page_no += 1
    return selected, meta


def fetch_from_device_history(
    *,
    mmuidv3_list: list[str],
    target_count: int,
    page_size: int,
    seen: set[str],
    user_key: str,
    report_progress: bool,
    progress_offset: int = 0,
    progress_total: int = 0,
    checker: ActivityChecker | None = None,
    blocked: set[str] | None = None,
) -> tuple[list[str], dict[str, Any]]:
    cfg = defaults("query_history_user_list_by_device_id")
    base_url = str(cfg.get("baseUrl") or "https://yaahlan-admin-alpha.wemomo.com").rstrip("/")
    path = str(cfg.get("path", "/yaahlan/backend/deviceHistory/queryHistoryUserListByDeviceId"))

    selected: list[str] = []
    devices_used = 0
    total_devices = len(mmuidv3_list)
    batch_total = progress_total or total_devices

    for index, mmuidv3 in enumerate(mmuidv3_list, start=1):
        page = 1
        while len(selected) < target_count:
            url = f"{base_url}{path}"
            resp = http_post_json(
                url,
                {"mmuidv3": mmuidv3, "page": page, "pageSize": page_size},
                timeout_s=30.0,
            )
            if resp.get("ec") != 200:
                raise RuntimeError(
                    f"设备历史账号查询失败: ec={resp.get('ec')} em={resp.get('em')} mmuidv3={mmuidv3[:12]}..."
                )
            summary = parse_history_user_list_by_device_summary(resp.get("data"))
            items = summary.get("items") or []
            if not items:
                break
            batch = [
                str(row.get("userId") or "").strip()
                for row in items
                if isinstance(row, dict) and str(row.get("userId") or "").strip()
            ]
            _append_unique(
                selected,
                seen,
                batch,
                target_count=target_count,
                checker=checker,
                blocked=blocked,
            )
            if len(items) < page_size:
                break
            page += 1

        devices_used = index
        if report_progress and batch_total >= 3:
            _report_progress(
                user_key=user_key,
                current=progress_offset + index,
                total=batch_total,
                detail=f"设备历史 {index}/{total_devices} · 本轮新增 {len(selected)}",
            )
        if len(selected) >= target_count:
            break

    meta = {
        "name": "deviceHistory/queryHistoryUserListByDeviceId",
        "deviceSource": str(TEST_DEVICES_PATH.relative_to(REPO_ROOT)),
        "devicesScanned": devices_used,
        "devicesAvailable": total_devices,
        "pageSize": page_size,
        "addedCount": len(selected),
    }
    return selected, meta


def fetch_from_anchor_management(
    *,
    target_count: int,
    page_size: int,
    seen: set[str],
    user_key: str,
    report_progress: bool,
    progress_offset: int = 0,
    progress_total: int = 0,
    checker: ActivityChecker | None = None,
    blocked: set[str] | None = None,
) -> tuple[list[str], dict[str, Any]]:
    selected: list[str] = []
    offset = 0
    pages_fetched = 0
    while len(selected) < target_count:
        resp = http_post_json(
            ANCHOR_LIST_URL,
            {"offset": offset, "limit": page_size, "area": "MENA"},
            timeout_s=30.0,
        )
        if resp.get("ec") != 200:
            raise RuntimeError(f"主播管理列表失败: ec={resp.get('ec')} em={resp.get('em')}")
        data = resp.get("data") or {}
        batch_rows = data.get("list") or []
        if not isinstance(batch_rows, list) or not batch_rows:
            break
        batch = [
            str(row.get("userId") or "").strip()
            for row in batch_rows
            if isinstance(row, dict) and str(row.get("userId") or "").strip()
        ]
        _append_unique(
            selected,
            seen,
            batch,
            target_count=target_count,
            checker=checker,
            blocked=blocked,
        )
        pages_fetched += 1
        if report_progress and progress_total >= 3:
            _report_progress(
                user_key=user_key,
                current=progress_offset + pages_fetched,
                total=progress_total,
                detail=f"主播管理 第 {pages_fetched} 页 · 本轮新增 {len(selected)}",
            )
        if len(selected) >= target_count:
            break
        if not data.get("has_next"):
            break
        next_offset = data.get("next_offset")
        if next_offset is None:
            break
        offset = int(next_offset)

    meta = {
        "name": "cms/anchor/anchorList/anchorList",
        "pagesFetched": pages_fetched,
        "pageSize": page_size,
        "addedCount": len(selected),
    }
    return selected, meta


def fetch_from_guild_management(
    *,
    target_count: int,
    page_size: int,
    seen: set[str],
    user_key: str,
    report_progress: bool,
    progress_offset: int = 0,
    progress_total: int = 0,
    checker: ActivityChecker | None = None,
    blocked: set[str] | None = None,
) -> tuple[list[str], dict[str, Any]]:
    selected: list[str] = []
    page = 1
    pages_fetched = 0
    while len(selected) < target_count:
        resp = http_post_json(
            GUILD_LIST_URL,
            {
                "tradeName": "",
                "tradeId": "",
                "tradeUid": "",
                "page": page,
                "pageSize": page_size,
                "area": "MENA",
            },
            timeout_s=30.0,
        )
        if resp.get("ec") != 200:
            raise RuntimeError(f"公会管理列表失败: ec={resp.get('ec')} em={resp.get('em')}")
        summary = parse_query_trade_union_summary(resp.get("data"))
        items = summary.get("items") or []
        if not items:
            break
        batch: list[str] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            leader = str(item.get("tradeUid") or "").strip()
            if leader:
                batch.append(leader)
            for child in item.get("childUnions") or []:
                if not isinstance(child, dict):
                    continue
                child_leader = str(child.get("tradeUid") or "").strip()
                if child_leader:
                    batch.append(child_leader)
        _append_unique(
            selected,
            seen,
            batch,
            target_count=target_count,
            checker=checker,
            blocked=blocked,
        )
        pages_fetched += 1
        if report_progress and progress_total >= 3:
            _report_progress(
                user_key=user_key,
                current=progress_offset + pages_fetched,
                total=progress_total,
                detail=f"公会管理 第 {pages_fetched} 页 · 本轮新增 {len(selected)}",
            )
        if len(selected) >= target_count:
            break
        if len(items) < page_size:
            break
        page += 1

    meta = {
        "name": "cms/anchor/tradeUnionList/tradeUnionPageList",
        "pagesFetched": pages_fetched,
        "pageSize": page_size,
        "addedCount": len(selected),
    }
    return selected, meta


def fetch_from_supplement_sources(
    *,
    target_count: int,
    seen: set[str],
    checker: ActivityChecker | None = None,
    blocked: set[str] | None = None,
) -> tuple[list[str], dict[str, Any]]:
    selected: list[str] = []
    breakdown: dict[str, int] = {}

    cfg = defaults("vip5_custom_gift_list")
    base_url = (
        os.environ.get("ADMIN_GATEWAY_BASE_URL") or str(cfg.get("baseUrl") or "")
    ).strip().rstrip("/")
    if base_url:
        path = str(cfg.get("path", "/yaahlan/backend/vip5UserConfig/getListConfig"))
        url = f"{base_url}{path}?{urllib.parse.urlencode({'perPage': 500})}"
        resp = http_get_json(url, timeout_s=30.0)
        if gateway_success(resp.get("status")):
            summary = parse_custom_gift_list_summary(resp.get("data"))
            batch = [
                str(item.get("userId") or "").strip()
                for item in (summary.get("items") or [])
                if isinstance(item, dict) and str(item.get("userId") or "").strip()
            ]
            added = _append_unique(
                selected,
                seen,
                batch,
                target_count=target_count,
                checker=checker,
                blocked=blocked,
            )
            breakdown["vip5CustomGiftList"] = added

    if len(selected) < target_count and base_url:
        resp = http_post_json(
            f"{base_url}/yaahlan/backend/family/getAllFamilyList",
            {"offset": 0, "limit": 500},
            timeout_s=30.0,
        )
        if resp.get("ec") == 200:
            raw_list = (resp.get("data") or {}).get("list") or []
            batch = [
                str(row.get("familyOwnerId") or "").strip()
                for row in raw_list
                if isinstance(row, dict) and str(row.get("familyOwnerId") or "").strip()
            ]
            before = len(selected)
            _append_unique(
                selected,
                seen,
                batch,
                target_count=target_count,
                checker=checker,
                blocked=blocked,
            )
            breakdown["familyOwnerList"] = len(selected) - before

    if len(selected) < target_count and ONLINE_ACCOUNTS_PATH.is_file():
        payload = json.loads(ONLINE_ACCOUNTS_PATH.read_text(encoding="utf-8"))
        batch = [
            str(row.get("userId") or "").strip()
            for row in (payload.get("accounts") or [])
            if isinstance(row, dict) and str(row.get("userId") or "").strip()
        ]
        before = len(selected)
        _append_unique(
            selected,
            seen,
            batch,
            target_count=target_count,
            checker=checker,
            blocked=blocked,
        )
        breakdown["onlineTestAccounts"] = len(selected) - before

    meta = {
        "name": "supplement/customGift+family+onlineAccounts",
        "breakdown": breakdown,
        "addedCount": len(selected),
    }
    return selected, meta


def _pool_sources_lines(sources: list[dict[str, Any]]) -> list[str]:
    source_lines: list[str] = []
    for item in sources:
        if not isinstance(item, dict):
            continue
        name = item.get("name") or "-"
        extra = []
        for key in (
            "pagesFetched",
            "devicesScanned",
            "devicesAvailable",
            "totalCount",
            "addedCount",
        ):
            if item.get(key) is not None:
                extra.append(f"{key}={item[key]}")
        breakdown = item.get("breakdown")
        if isinstance(breakdown, dict) and breakdown:
            extra.append(
                "breakdown="
                + ",".join(f"{k}:{v}" for k, v in breakdown.items())
            )
        suffix = f" ({', '.join(extra)})" if extra else ""
        source_lines.append(f"- {name}{suffix}")
    return source_lines


def build_pool_payload(
    *,
    kb_path: str,
    description: str,
    user_ids: list[str],
    primary_source: str,
    sources: list[dict[str, Any]],
    dedupe_removed: int,
    active_within_days: int | None = None,
    pool_kind: str | None = None,
    mdp_login_hint: str = "",
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "kbPath": kb_path,
        "description": description,
        "primarySource": primary_source,
        "sources": sources,
        "dedupeRemoved": dedupe_removed,
        "syncedAt": _utc_now(),
        "count": len(user_ids),
        "userIds": user_ids,
    }
    if active_within_days:
        payload["activeWithinDays"] = active_within_days
    if pool_kind:
        payload["poolKind"] = pool_kind
    if mdp_login_hint:
        payload["mdpLoginHint"] = mdp_login_hint
    return payload


def build_result_markdown(payload: dict[str, Any]) -> str:
    source_lines = _pool_sources_lines(payload.get("sources") or [])
    lines = [
        "## 备用 userId 池同步完成",
        "",
        f"- 目标数量：**{payload.get('targetCount')}**",
        f"- 实际入库：**{payload.get('count')}**",
        f"- 去重移除：**{payload.get('dedupeRemoved', 0)}**",
        f"- 近 {payload.get('activeFilterDays', '-')} 天活跃剔除：**{payload.get('activeRemoved', 0)}**",
        f"- 主来源：`{payload.get('primarySource')}`",
        f"- 同步时间：{payload.get('syncedAt')}",
        f"- 知识库：`testcase-kb/admin_user_pool.json`",
        "",
        "### 数据来源",
        *source_lines,
        "",
        "### 用法",
        "- 读取 JSON 的 `userIds`，按需取前 N 个",
        "- 刷新：`python3 Admin/scripts/sync_admin_user_pool_to_kb.py --count 1000`",
    ]
    if payload.get("mdpLoginHint"):
        lines.extend(["", f"> ⚠️ {payload['mdpLoginHint']}"])
    return "\n".join(lines)


def build_split_result_markdown(
    *,
    inactive_payload: dict[str, Any],
    active_payload: dict[str, Any],
    total_collected: int,
    dedupe_removed: int,
) -> str:
    source_lines = _pool_sources_lines(inactive_payload.get("sources") or [])
    lines = [
        "## 设备账号池同步完成（活跃 / 非活跃分库）",
        "",
        f"- 抓取去重后总数：**{total_collected}**",
        f"- 去重移除：**{dedupe_removed}**",
        f"- 非活跃入库：**{inactive_payload.get('count')}**",
        f"- 活跃入库：**{active_payload.get('count')}**",
        f"- 活跃判定：近 **{inactive_payload.get('activeWithinDays', '-')}** 天内有登录",
        f"- 同步时间：{inactive_payload.get('syncedAt')}",
        "",
        "### 知识库",
        f"- 非活跃：`{inactive_payload.get('kbPath')}`",
        f"- 活跃：`{active_payload.get('kbPath')}`",
        f"- 兼容别名（非活跃）：`testcase-kb/admin_user_pool.json`",
        "",
        "### 数据来源",
        *source_lines,
        "",
        "### 用法",
        "- 需要空闲测试号 → 读 `admin_user_pool_inactive.json` 的 `userIds`",
        "- 需要近期在线号 → 读 `admin_user_pool_active.json` 的 `userIds`",
        "- 刷新：`python3 Admin/scripts/sync_admin_user_pool_to_kb.py --split-active-inactive --active-within-days 30`",
    ]
    hint = inactive_payload.get("mdpLoginHint") or active_payload.get("mdpLoginHint")
    if hint:
        lines.extend(["", f"> ⚠️ {hint}"])
    return "\n".join(lines)


def _estimate_refill_progress_total(*, mmuidv3_count: int, page_size: int) -> int:
    anchor_pages = max(1, (120 + page_size - 1) // page_size)
    guild_pages = max(1, (70 + page_size - 1) // page_size)
    return mmuidv3_count + anchor_pages + guild_pages + 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="从开发后台抓取 userId 写入 testcase-kb 备用池")
    parser.add_argument("--count", type=int, default=1000, help="目标 userId 数量（默认 1000）")
    parser.add_argument("--page-size", type=int, default=50, help="分页 pageSize（默认 50）")
    parser.add_argument(
        "--exclude-active-within-days",
        type=int,
        default=0,
        help="剔除近 N 天内 lastOnLineTime 有登录的 userId（0=不过滤）",
    )
    parser.add_argument(
        "--split-active-inactive",
        action="store_true",
        help="按活跃度分写入活跃/非活跃两个知识库（抓取全部设备账号，不按 count 截断）",
    )
    parser.add_argument(
        "--active-within-days",
        type=int,
        default=30,
        help="--split-active-inactive 时判定活跃的近 N 天（默认 30）",
    )
    parser.add_argument(
        "--filter-keep-area",
        default="",
        help="仅保留指定大区账号并写回活跃/非活跃知识库（如 MENA）；剔除其它大区",
    )
    parser.add_argument(
        "--source",
        choices=("auto", "mdp", "device-history"),
        default="auto",
        help="数据来源：auto=多源抓取并去重补全（默认 auto）",
    )
    parser.add_argument(
        "--merge-existing",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="合并已有 admin_user_pool.json 后再去重补抓（默认开启）",
    )
    parser.add_argument("--user-key", default=USER_KEY_DEFAULT, help="钉钉批量进度 user_key")
    parser.add_argument("--dry-run", action="store_true", help="只抓取不写知识库")
    parser.add_argument("--no-progress", action="store_true", help="不上报钉钉批量进度")
    return parser


def _write_pool_file(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_area_filter_result_markdown(
    *,
    keep_area: str,
    inactive_before: int,
    inactive_after: int,
    active_before: int,
    active_after: int,
    removed_total: int,
    removed_by_area: dict[str, int],
    synced_at: str,
) -> str:
    area_lines = [
        f"| {area or '未知'} | {count} |"
        for area, count in sorted(removed_by_area.items(), key=lambda item: (-item[1], item[0]))
    ]
    return "\n".join(
        [
            "## 账号池大区过滤完成",
            "",
            f"- 保留大区：**{keep_area}**（中东）",
            f"- 非活跃池：{inactive_before} → **{inactive_after}**",
            f"- 活跃池：{active_before} → **{active_after}**",
            f"- 合计剔除：**{removed_total}**",
            f"- 同步时间：{synced_at}",
            "",
            "### 剔除分布（按大区）",
            "| 大区 | 数量 |",
            "| --- | ---: |",
            *area_lines,
            "",
            "### 知识库",
            "- 非活跃：`testcase-kb/admin_user_pool_inactive.json`",
            "- 活跃：`testcase-kb/admin_user_pool_active.json`",
            "- 兼容别名（非活跃）：`testcase-kb/admin_user_pool.json`",
        ]
    )


def _run_filter_keep_area(args: argparse.Namespace) -> int:
    keep_area = str(args.filter_keep_area or "").strip().upper()
    if not keep_area:
        print("filter-keep-area 不能为空", file=sys.stderr)
        return 2

    report_progress = not args.no_progress
    pool_files = [
        ("inactive", INACTIVE_KB_PATH),
        ("active", ACTIVE_KB_PATH),
    ]
    pools: dict[str, dict[str, Any]] = {}
    for kind, path in pool_files:
        payload = _load_existing_pool(path)
        if not payload:
            print(f"知识库不存在或为空: {path}", file=sys.stderr)
            return 1
        pools[kind] = payload

    inactive_before = int(pools["inactive"].get("count") or len(pools["inactive"].get("userIds") or []))
    active_before = int(pools["active"].get("count") or len(pools["active"].get("userIds") or []))

    all_ids, _ = dedupe_preserve_order(
        list(pools["inactive"].get("userIds") or []) + list(pools["active"].get("userIds") or [])
    )
    if not all_ids:
        print("知识库中无 userId", file=sys.stderr)
        return 1

    checker = AreaChecker(keep_area=keep_area)
    progress_total = len(all_ids)
    if report_progress and progress_total >= 3:
        _report_progress(
            user_key=args.user_key,
            current=0,
            total=progress_total,
            detail=f"开始大区过滤 · 共 {progress_total} 个 · 保留 {keep_area}",
        )

    mena_ids, removed_ids = filter_users_by_area(
        all_ids,
        checker=checker,
        user_key=args.user_key,
        report_progress=report_progress,
        progress_offset=0,
        progress_total=progress_total,
    )
    mena_set = set(mena_ids)
    removed_by_area: dict[str, int] = {}
    for uid in removed_ids:
        area = checker.user_area(uid) or "未知"
        removed_by_area[area] = removed_by_area.get(area, 0) + 1

    synced_at = _utc_now()
    inactive_ids = [
        uid for uid in pools["inactive"].get("userIds") or [] if uid in mena_set
    ]
    active_ids = [
        uid for uid in pools["active"].get("userIds") or [] if uid in mena_set
    ]

    for kind, ids in (("inactive", inactive_ids), ("active", active_ids)):
        payload = pools[kind]
        payload["userIds"] = ids
        payload["count"] = len(ids)
        payload["syncedAt"] = synced_at
        payload["keepArea"] = keep_area
        payload["areaRemoved"] = (inactive_before if kind == "inactive" else active_before) - len(ids)

    if not args.dry_run:
        _write_pool_file(INACTIVE_KB_PATH, pools["inactive"])
        _write_pool_file(ACTIVE_KB_PATH, pools["active"])
        legacy_payload = dict(pools["inactive"])
        legacy_payload["kbPath"] = str(KB_PATH.relative_to(REPO_ROOT))
        legacy_payload["description"] = (
            "测试环境备用 userId 池（非活跃）；兼容旧路径，等同 admin_user_pool_inactive.json"
        )
        _write_pool_file(KB_PATH, legacy_payload)

    result_md = build_area_filter_result_markdown(
        keep_area=keep_area,
        inactive_before=inactive_before,
        inactive_after=len(inactive_ids),
        active_before=active_before,
        active_after=len(active_ids),
        removed_total=len(removed_ids),
        removed_by_area=removed_by_area,
        synced_at=synced_at,
    )
    if report_progress and progress_total >= 3:
        _report_progress(
            user_key=args.user_key,
            current=progress_total,
            total=progress_total,
            detail=f"完成 · 保留 {len(mena_ids)} · 剔除 {len(removed_ids)}",
            result_text=result_md,
        )

    print(
        json.dumps(
            {
                "keepArea": keep_area,
                "inactiveBefore": inactive_before,
                "inactiveAfter": len(inactive_ids),
                "activeBefore": active_before,
                "activeAfter": len(active_ids),
                "removedTotal": len(removed_ids),
                "removedByArea": removed_by_area,
            },
            ensure_ascii=False,
        )
    )
    return 0


def _run_split_active_inactive(args: argparse.Namespace) -> int:
    if args.active_within_days <= 0:
        print("split 模式下 active-within-days 必须为正整数", file=sys.stderr)
        return 2

    report_progress = not args.no_progress
    seed_ids: list[str] = []
    if args.merge_existing:
        seed_ids.extend(_load_existing_user_ids(INACTIVE_KB_PATH))
        seed_ids.extend(_load_existing_user_ids(ACTIVE_KB_PATH))
        seed_ids.extend(_load_existing_user_ids(KB_PATH))

    user_ids, dedupe_removed = dedupe_preserve_order(seed_ids)
    mmuidv3_list = _load_mmuidv3_list(TEST_DEVICES_PATH) if TEST_DEVICES_PATH.is_file() else []
    if not mmuidv3_list:
        print("test_devices.json 中无可用 mmuidv3", file=sys.stderr)
        return 1

    refill_total = _estimate_refill_progress_total(
        mmuidv3_count=len(mmuidv3_list),
        page_size=args.page_size,
    )
    progress_current = 0
    checker = ActivityChecker(active_within_days=args.active_within_days)

    if report_progress and refill_total >= 3:
        _report_progress(
            user_key=args.user_key,
            current=0,
            total=refill_total,
            detail=f"开始抓取全部设备账号（已有 {len(user_ids)} 个）",
        )

    seen: set[str] = set(user_ids)
    sources: list[dict[str, Any]] = []
    primary_source = ""
    mdp_login_hint = ""
    target_count = UNLIMITED_TARGET

    if args.source in ("auto", "mdp"):
        try:
            batch, mdp_meta = fetch_from_mdp_user_list(
                target_count=target_count,
                page_size=args.page_size,
                seen=seen,
            )
            user_ids.extend(batch)
            sources.append(mdp_meta)
            primary_source = mdp_meta["name"]
        except RuntimeError as exc:
            if args.source == "mdp":
                print(str(exc), file=sys.stderr)
                return 1
            mdp_login_hint = (
                "MDP 用户列表 Token 失效（ec=20000 请先登录），"
                "已改用设备历史 / 公会管理 / 主播管理等接口补抓；"
                "如需 ops-admin 用户列表，请更新 Admin/.env.local 中 MDP_AEGIS_TOKEN / MDP_CLOUD_AEGIS_TOKEN"
            )

    if args.source in ("auto", "device-history"):
        batch, device_meta = fetch_from_device_history(
            mmuidv3_list=mmuidv3_list,
            target_count=target_count,
            page_size=args.page_size,
            seen=seen,
            user_key=args.user_key,
            report_progress=report_progress,
            progress_offset=progress_current,
            progress_total=refill_total,
        )
        user_ids.extend(batch)
        progress_current += int(device_meta.get("devicesScanned") or 0)
        sources.append(device_meta)
        if not primary_source:
            primary_source = device_meta["name"]

    if args.source == "auto":
        batch, anchor_meta = fetch_from_anchor_management(
            target_count=target_count,
            page_size=args.page_size,
            seen=seen,
            user_key=args.user_key,
            report_progress=report_progress,
            progress_offset=progress_current,
            progress_total=refill_total,
        )
        user_ids.extend(batch)
        progress_current += int(anchor_meta.get("pagesFetched") or 0)
        sources.append(anchor_meta)
        if not primary_source:
            primary_source = anchor_meta["name"]

        batch, guild_meta = fetch_from_guild_management(
            target_count=target_count,
            page_size=args.page_size,
            seen=seen,
            user_key=args.user_key,
            report_progress=report_progress,
            progress_offset=progress_current,
            progress_total=refill_total,
        )
        user_ids.extend(batch)
        progress_current += int(guild_meta.get("pagesFetched") or 0)
        sources.append(guild_meta)
        if not primary_source:
            primary_source = guild_meta["name"]

        batch, supplement_meta = fetch_from_supplement_sources(
            target_count=target_count,
            seen=seen,
        )
        user_ids.extend(batch)
        progress_current += 1
        if report_progress and refill_total >= 3:
            _report_progress(
                user_key=args.user_key,
                current=min(refill_total, progress_current),
                total=refill_total,
                detail=f"补充来源 · 累计 {len(user_ids)}",
            )
        sources.append(supplement_meta)
        if not primary_source:
            primary_source = supplement_meta["name"]

    user_ids, final_dedupe_removed = dedupe_preserve_order(user_ids)
    dedupe_removed += final_dedupe_removed
    if not user_ids:
        print("未收集到任何 userId", file=sys.stderr)
        return 1

    classify_total = len(user_ids)
    progress_total = classify_total
    if report_progress and progress_total >= 3:
        _report_progress(
            user_key=args.user_key,
            current=0,
            total=progress_total,
            detail=f"开始活跃分类（共 {classify_total} 个）",
        )

    inactive_ids, active_ids = classify_users_by_activity(
        user_ids,
        checker=checker,
        user_key=args.user_key,
        report_progress=report_progress,
        progress_offset=0,
        progress_total=progress_total,
    )

    inactive_payload = build_pool_payload(
        kb_path=str(INACTIVE_KB_PATH.relative_to(REPO_ROOT)),
        description="测试环境非活跃 userId 池；近 N 天无登录记录",
        user_ids=inactive_ids,
        primary_source=primary_source,
        sources=sources,
        dedupe_removed=dedupe_removed,
        active_within_days=args.active_within_days,
        pool_kind="inactive",
        mdp_login_hint=mdp_login_hint,
    )
    active_payload = build_pool_payload(
        kb_path=str(ACTIVE_KB_PATH.relative_to(REPO_ROOT)),
        description="测试环境活跃 userId 池；近 N 天内有登录记录",
        user_ids=active_ids,
        primary_source=primary_source,
        sources=sources,
        dedupe_removed=dedupe_removed,
        active_within_days=args.active_within_days,
        pool_kind="active",
        mdp_login_hint=mdp_login_hint,
    )

    if not args.dry_run:
        _write_pool_file(INACTIVE_KB_PATH, inactive_payload)
        _write_pool_file(ACTIVE_KB_PATH, active_payload)
        legacy_payload = dict(inactive_payload)
        legacy_payload["kbPath"] = str(KB_PATH.relative_to(REPO_ROOT))
        legacy_payload["description"] = (
            "测试环境备用 userId 池（非活跃）；兼容旧路径，等同 admin_user_pool_inactive.json"
        )
        _write_pool_file(KB_PATH, legacy_payload)

    result_md = build_split_result_markdown(
        inactive_payload=inactive_payload,
        active_payload=active_payload,
        total_collected=len(user_ids),
        dedupe_removed=dedupe_removed,
    )
    if report_progress and progress_total >= 3:
        _report_progress(
            user_key=args.user_key,
            current=progress_total,
            total=progress_total,
            detail=(
                f"完成 · 非活跃 {len(inactive_ids)} · 活跃 {len(active_ids)}"
            ),
            result_text=result_md,
        )

    print(
        json.dumps(
            {
                "totalCollected": len(user_ids),
                "inactiveCount": len(inactive_ids),
                "activeCount": len(active_ids),
                "dedupeRemoved": dedupe_removed,
                "inactiveKbPath": inactive_payload["kbPath"],
                "activeKbPath": active_payload["kbPath"],
            },
            ensure_ascii=False,
        )
    )
    return 0


def main() -> int:
    args = build_parser().parse_args()
    if args.count <= 0:
        print("count 必须为正整数", file=sys.stderr)
        return 2

    load_local_env(str(ADMIN_DIR))

    if args.filter_keep_area:
        return _run_filter_keep_area(args)

    if args.split_active_inactive:
        return _run_split_active_inactive(args)

    seed_ids: list[str] = []
    existing_pool: dict[str, Any] = {}
    if args.merge_existing:
        existing_pool = _load_existing_pool(KB_PATH)
        seed_ids.extend(_load_existing_user_ids(KB_PATH))

    user_ids, dedupe_removed = dedupe_preserve_order(seed_ids)
    active_removed = 0
    blocked: set[str] = set()
    checker: ActivityChecker | None = None
    report_progress = not args.no_progress

    mmuidv3_list = _load_mmuidv3_list(TEST_DEVICES_PATH) if TEST_DEVICES_PATH.is_file() else []
    refill_total = _estimate_refill_progress_total(
        mmuidv3_count=len(mmuidv3_list),
        page_size=args.page_size,
    )
    filter_total = len(user_ids) if args.exclude_active_within_days > 0 else 0
    progress_total = filter_total + refill_total
    progress_current = 0

    if args.exclude_active_within_days > 0:
        checker = ActivityChecker(active_within_days=args.exclude_active_within_days)
        if report_progress and progress_total >= 3:
            _report_progress(
                user_key=args.user_key,
                current=0,
                total=progress_total,
                detail=f"开始过滤近 {args.exclude_active_within_days} 天活跃用户",
            )
        user_ids, removed_active_ids, active_removed = filter_out_active_users(
            user_ids,
            checker=checker,
            user_key=args.user_key,
            report_progress=report_progress,
            progress_offset=0,
            progress_total=progress_total,
        )
        blocked.update(removed_active_ids)
        progress_current = filter_total
    elif report_progress and progress_total >= 3:
        _report_progress(
            user_key=args.user_key,
            current=0,
            total=progress_total,
            detail=f"去重后已有 {len(user_ids)} 个",
        )

    seen: set[str] = set(user_ids)
    seen.update(blocked)
    sources: list[dict[str, Any]] = []
    primary_source = ""
    mdp_login_hint = ""

    def _need_more() -> int:
        return max(0, args.count - len(user_ids))

    use_mdp = args.source in ("auto", "mdp")
    if use_mdp and _need_more() > 0:
        try:
            batch, mdp_meta = fetch_from_mdp_user_list(
                target_count=_need_more(),
                page_size=args.page_size,
                seen=seen,
                checker=checker,
                blocked=blocked,
            )
            user_ids.extend(batch)
            sources.append(mdp_meta)
            primary_source = mdp_meta["name"]
        except RuntimeError as exc:
            if args.source == "mdp":
                print(str(exc), file=sys.stderr)
                return 1
            mdp_login_hint = (
                "MDP 用户列表 Token 失效（ec=20000 请先登录），"
                "已改用设备历史 / 公会管理 / 主播管理等接口补抓；"
                "如需 ops-admin 用户列表，请更新 Admin/.env.local 中 MDP_AEGIS_TOKEN / MDP_CLOUD_AEGIS_TOKEN"
            )

    if _need_more() > 0 and args.source in ("auto", "device-history"):
        if not mmuidv3_list:
            print("test_devices.json 中无可用 mmuidv3", file=sys.stderr)
            return 1
        batch, device_meta = fetch_from_device_history(
            mmuidv3_list=mmuidv3_list,
            target_count=_need_more(),
            page_size=args.page_size,
            seen=seen,
            user_key=args.user_key,
            report_progress=report_progress,
            progress_offset=progress_current,
            progress_total=progress_total,
            checker=checker,
            blocked=blocked,
        )
        user_ids.extend(batch)
        progress_current += int(device_meta.get("devicesScanned") or 0)
        sources.append(device_meta)
        if not primary_source:
            primary_source = device_meta["name"]

    if _need_more() > 0 and args.source == "auto":
        batch, anchor_meta = fetch_from_anchor_management(
            target_count=_need_more(),
            page_size=args.page_size,
            seen=seen,
            user_key=args.user_key,
            report_progress=report_progress,
            progress_offset=progress_current,
            progress_total=progress_total,
            checker=checker,
            blocked=blocked,
        )
        user_ids.extend(batch)
        progress_current += int(anchor_meta.get("pagesFetched") or 0)
        sources.append(anchor_meta)
        if not primary_source:
            primary_source = anchor_meta["name"]

    if _need_more() > 0 and args.source == "auto":
        batch, guild_meta = fetch_from_guild_management(
            target_count=_need_more(),
            page_size=args.page_size,
            seen=seen,
            user_key=args.user_key,
            report_progress=report_progress,
            progress_offset=progress_current,
            progress_total=progress_total,
            checker=checker,
            blocked=blocked,
        )
        user_ids.extend(batch)
        progress_current += int(guild_meta.get("pagesFetched") or 0)
        sources.append(guild_meta)
        if not primary_source:
            primary_source = guild_meta["name"]

    if _need_more() > 0 and args.source == "auto":
        batch, supplement_meta = fetch_from_supplement_sources(
            target_count=_need_more(),
            seen=seen,
            checker=checker,
            blocked=blocked,
        )
        user_ids.extend(batch)
        progress_current += 1
        if report_progress and progress_total >= 3:
            _report_progress(
                user_key=args.user_key,
                current=min(progress_total, progress_current),
                total=progress_total,
                detail=f"补充来源 · 累计 {len(user_ids)}",
            )
        sources.append(supplement_meta)
        if not primary_source:
            primary_source = supplement_meta["name"]

    user_ids, final_dedupe_removed = dedupe_preserve_order(user_ids)
    dedupe_removed += final_dedupe_removed

    if len(user_ids) < args.count:
        print(
            f"仅收集到 {len(user_ids)} 个 userId，未达到目标 {args.count}",
            file=sys.stderr,
        )
        return 1

    user_ids = user_ids[: args.count]
    if not primary_source:
        primary_source = str(existing_pool.get("primarySource") or "")
    if not sources and isinstance(existing_pool.get("sources"), list):
        sources = [item for item in existing_pool["sources"] if isinstance(item, dict)]

    payload: dict[str, Any] = {
        "kbPath": "testcase-kb/admin_user_pool.json",
        "description": "测试环境备用 userId 池；按需读取 userIds 前 N 个使用（多源抓取、全局去重、可剔除近期活跃用户）",
        "primarySource": primary_source,
        "sources": sources,
        "targetCount": args.count,
        "dedupeRemoved": dedupe_removed,
        "syncedAt": _utc_now(),
        "count": len(user_ids),
        "userIds": user_ids,
    }
    if args.exclude_active_within_days > 0:
        payload["activeFilterDays"] = args.exclude_active_within_days
        payload["activeRemoved"] = active_removed
    if mdp_login_hint:
        payload["mdpLoginHint"] = mdp_login_hint

    if not args.dry_run:
        KB_PATH.parent.mkdir(parents=True, exist_ok=True)
        KB_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    result_md = build_result_markdown(payload)
    if report_progress and progress_total >= 3:
        _report_progress(
            user_key=args.user_key,
            current=progress_total,
            total=progress_total,
            detail=f"完成 · 入库 {len(user_ids)}",
            result_text=result_md,
        )

    print(
        json.dumps(
            {
                "count": payload["count"],
                "dedupeRemoved": payload["dedupeRemoved"],
                "activeRemoved": payload.get("activeRemoved", 0),
                "kbPath": payload["kbPath"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
