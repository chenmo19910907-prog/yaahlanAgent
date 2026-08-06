#!/usr/bin/env python3
"""MOA getFamilyPkUserList：拉取家族成员贡献榜全量。"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

from repo_paths import (
    admin_execute_path,
    admin_module_dir,
    batch_progress_script,
    get_repo_root,
    gift_execute_path,
    gift_module_dir,
    moa_execute_path,
    moa_module_dir,
    moa_template,
    mse_execute_path,
    mse_module_dir,
    stage_gateway_url,
    tmp_dir,
)
_TEMPLATE = moa_template("家族PK-成员贡献列表.json")
_MAX_PAGES = 100


def normalize_pk_date(pk_date: str) -> str:
    text = pk_date.strip()
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        return text
    raise ValueError(f"pk_date 须为 yyyy-MM-dd: {pk_date!r}")


def _parse_moa_stdout(text: str) -> dict[str, Any]:
    start = text.find("{")
    if start < 0:
        raise RuntimeError("MOA 输出不含 JSON")
    decoder = json.JSONDecoder()
    obj, _ = decoder.raw_decode(text[start:])
    if not isinstance(obj, dict):
        raise RuntimeError("MOA 返回不是 object")
    return obj


def _run_member_list_page(
    *,
    user_id: str,
    family_id: str,
    pk_date: str,
    area: str,
    offset: int,
    limit: int,
    timeout_s: int,
) -> dict[str, Any]:
    proc = subprocess.run(
        [
            sys.executable,
            str(moa_execute_path()),
            "--payload-file",
            str(_TEMPLATE),
            "--family-pk-member-list-user-id",
            user_id,
            "--family-pk-member-list-family-id",
            family_id,
            "--family-pk-member-list-date",
            pk_date,
            "--family-pk-member-list-area",
            area,
            "--family-pk-member-list-offset",
            str(offset),
            "--family-pk-member-list-limit",
            str(limit),
            "--family-pk-member-list-single-page",
            "--timeout-ms",
            str(max(timeout_s, 5) * 1000),
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=max(timeout_s + 10, 30),
        check=False,
    )
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "MOA 调用失败")[-800:]
        raise RuntimeError(tail)
    return _parse_moa_stdout(proc.stdout)


def fetch_family_pk_member_list(
    *,
    user_id: str,
    family_id: str,
    pk_date: str,
    area: str = "MENA",
    limit: int = 20,
    timeout_s: int = 60,
) -> list[dict[str, Any]]:
    """翻页拉取家族成员贡献榜全量 memberList。"""
    user_id = str(user_id).strip()
    family_id = str(family_id).strip()
    pk_date = normalize_pk_date(pk_date)
    area = str(area or "MENA").strip().upper() or "MENA"
    if not user_id or not family_id:
        raise ValueError("user_id 与 family_id 不能为空")

    all_members: list[dict[str, Any]] = []
    offset = 0
    for page in range(_MAX_PAGES):
        summary = _run_member_list_page(
            user_id=user_id,
            family_id=family_id,
            pk_date=pk_date,
            area=area,
            offset=offset,
            limit=limit,
            timeout_s=timeout_s,
        )
        batch = summary.get("memberList") or []
        if not isinstance(batch, list):
            raise RuntimeError("memberList 不是数组")
        all_members.extend(batch)
        if not summary.get("hasNext"):
            break
        next_offset = summary.get("nextOffset")
        offset = int(next_offset) if next_offset is not None else offset + limit
    return all_members
