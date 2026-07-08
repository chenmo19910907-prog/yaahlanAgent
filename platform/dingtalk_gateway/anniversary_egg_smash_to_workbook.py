#!/usr/bin/env python3
"""3周年砸金蛋测试记录追加写入钉钉 Sheet。"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from family_pk_tab_to_workbook import _ensure_sheet, _string_rows, _write_sheet_replace
from mse_sync_to_workbook import _sheet_cell
from mse_workbook_utils import fetch_workbook_sheets_async, node_id

DEFAULT_SHEET = "砸金蛋测试记录"

HEADER = [
    "砸蛋时间",
    "砸蛋账号",
    "砸蛋房间",
    "本次砸蛋次数",
    "房间内砸蛋次数",
    "用户砸蛋次数",
    "平台砸蛋次数",
    "砸蛋时金蛋等级",
    "当前用户总奖励",
    "当次奖励摘要",
    "当次奖励JSON",
    "记录写入时间",
]


def _format_server_time(value: Any) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, (int, float)):
        ts = float(value)
        if ts > 1e12:
            ts /= 1000.0
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    text = str(value).strip()
    if text.isdigit() and len(text) >= 10:
        ts = int(text)
        if ts > 1e12:
            ts //= 1000
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    return text


def _reward_summary(rewards: Any) -> str:
    if not isinstance(rewards, list) or not rewards:
        return ""
    parts: list[str] = []
    for item in rewards:
        if not isinstance(item, dict):
            continue
        name = item.get("name") or item.get("giftName") or item.get("type") or "奖励"
        num = item.get("num") or item.get("count") or item.get("amount") or 1
        parts.append(f"{name}×{num}")
    return "；".join(parts)


def record_to_row(
    smash_result: dict[str, Any],
    *,
    fallback_user_id: str = "",
    fallback_room_id: str = "",
    fallback_smash_count: int | None = None,
) -> list[str]:
    user_id = str(smash_result.get("userId") or fallback_user_id or "").strip()
    room_id = str(smash_result.get("roomId") or fallback_room_id or "").strip()
    server_time = _format_server_time(
        smash_result.get("serverTime")
        or smash_result.get("timestamp")
        or smash_result.get("smashTime")
    )
    smash_count = smash_result.get("smashCount")
    if smash_count is None:
        smash_count = fallback_smash_count
    rewards = smash_result.get("rewards")
    recorded_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    return [
        _sheet_cell(server_time),
        _sheet_cell(user_id),
        _sheet_cell(room_id),
        _sheet_cell(smash_count),
        _sheet_cell(smash_result.get("roomSmashCount")),
        _sheet_cell(smash_result.get("userSmashCount")),
        _sheet_cell(smash_result.get("platformSmashCount")),
        _sheet_cell(smash_result.get("eggLevel")),
        _sheet_cell(smash_result.get("userTotalReward")),
        _sheet_cell(_reward_summary(rewards)),
        _sheet_cell(json.dumps(rewards, ensure_ascii=False) if rewards is not None else ""),
        _sheet_cell(recorded_at),
    ]


def _rows_match_header(first_row: list[Any]) -> bool:
    if not first_row:
        return False
    cells = [str(c or "").strip() for c in first_row[: len(HEADER)]]
    return cells == HEADER


async def append_smash_record_async(
    workbook_url_or_id: str,
    row: list[str],
    *,
    sheet_name: str = DEFAULT_SHEET,
) -> str:
    from alidocs_excel_export import _excel_env, _get_token_and_operator

    import httpx

    workbook_id = node_id(workbook_url_or_id)
    url = f"https://alidocs.dingtalk.com/i/nodes/{workbook_id}"
    env = _excel_env()
    token, operator = await _get_token_and_operator(env)

    async with httpx.AsyncClient(timeout=120) as client:
        await _ensure_sheet(
            token=token,
            operator=operator,
            workbook_id=workbook_id,
            sheet_name=sheet_name,
            client=client,
        )

    sheets = await fetch_workbook_sheets_async(url)
    existing = sheets.get(sheet_name) or []
    if existing and _rows_match_header(existing[0]):
        data_rows = existing[1:]
        all_matrix = [HEADER] + data_rows + [row]
    elif existing:
        all_matrix = [HEADER] + existing + [row]
    else:
        all_matrix = [HEADER, row]

    str_rows = _string_rows(all_matrix)
    await _write_sheet_replace(
        token=token,
        operator=operator,
        workbook_id=workbook_id,
        sheet_name=sheet_name,
        rows=str_rows,
    )
    return url


def append_smash_record(
    workbook_url_or_id: str,
    row: list[str],
    *,
    sheet_name: str = DEFAULT_SHEET,
) -> str:
    return asyncio.run(
        append_smash_record_async(workbook_url_or_id, row, sheet_name=sheet_name)
    )
