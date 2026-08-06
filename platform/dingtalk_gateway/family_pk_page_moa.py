#!/usr/bin/env python3
"""MOA getFamilyPkPage：直接拉取家族 PK 页面数据（pkList 等）。"""

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
_TEMPLATE = moa_template("家族PK-请求页面.json")


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


def _extract_page_data(resp: dict[str, Any]) -> dict[str, Any]:
    outer_ec = resp.get("ec")
    if outer_ec not in (0, 200, "0", "200"):
        raise RuntimeError(f"MOA 外层失败: ec={outer_ec}, em={resp.get('em')}")
    inner = resp.get("result")
    if not isinstance(inner, dict):
        raise RuntimeError("MOA 缺少 result")
    inner_ec = inner.get("ec")
    if inner_ec not in (0, "0"):
        raise RuntimeError(f"MOA 业务失败: ec={inner_ec}, em={inner.get('em')}")
    payload = inner.get("result")
    if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
        return payload["data"]
    if isinstance(payload, dict):
        return payload
    raise RuntimeError("getFamilyPkPage 返回缺少 data")


def fetch_family_pk_page_data(
    *,
    user_id: str,
    pk_date: str,
    area: str = "MENA",
    timeout_s: int = 60,
) -> dict[str, Any]:
    """调用 MOA getFamilyPkPage，返回 data（含 pkList）。"""
    user_id = str(user_id).strip()
    pk_date = normalize_pk_date(pk_date)
    area = str(area or "MENA").strip().upper() or "MENA"
    if not user_id:
        raise ValueError("user_id 不能为空")

    proc = subprocess.run(
        [
            sys.executable,
            str(moa_execute_path()),
            "--payload-file",
            str(_TEMPLATE),
            "--family-pk-page-user-id",
            user_id,
            "--family-pk-page-date",
            pk_date,
            "--family-pk-page-area",
            area,
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
    resp = _parse_moa_stdout(proc.stdout)
    data = _extract_page_data(resp)
    if not isinstance(data.get("pkList"), list):
        raise RuntimeError("getFamilyPkPage 返回缺少 pkList")
    data["_requestDate"] = pk_date
    data["_userId"] = user_id
    return data


def _family_name(info: dict[str, Any]) -> str:
    return str(info.get("name") or info.get("familyName") or "").strip()


def parse_moa_pk_pairs(pk_list: list[Any]) -> dict[str, Any]:
    """解析 MOA getFamilyPkPage.pkList：每行一侧家族 + 对手，校验配对无重复。"""
    entries: list[dict[str, Any]] = []
    seen_families: dict[str, int] = {}
    duplicate_errors: list[str] = []

    for index, pair in enumerate(pk_list, start=1):
        if not isinstance(pair, dict):
            continue
        fa_info = pair.get("familyInfo") or {}
        opp = pair.get("opponentFamily")
        fa = str(fa_info.get("familyId") or "").strip()
        if not fa.isdigit():
            continue
        fan = _family_name(fa_info)
        fb = ""
        fbn = ""
        bye = True
        if isinstance(opp, dict) and str(opp.get("familyId") or "").strip().isdigit():
            fb = str(opp.get("familyId")).strip()
            fbn = _family_name(opp)
            bye = False

        for fid, label in ((fa, "家族"), (fb, "对手") if fb else (None, None)):
            if not fid:
                continue
            if fid in seen_families:
                duplicate_errors.append(
                    f"{fid} 重复出现（MOA序 {seen_families[fid]} 与 {index}）"
                )
            else:
                seen_families[fid] = index

        entries.append(
            {
                "index": index,
                "familyId": fa,
                "familyName": fan,
                "opponentId": fb,
                "opponentName": fbn,
                "bye": bye,
            }
        )

    pair_count = sum(1 for item in entries if not item["bye"])
    bye_count = sum(1 for item in entries if item["bye"])
    unique_family_count = len(seen_families)
    return {
        "entries": entries,
        "entryCount": len(entries),
        "pairCount": pair_count,
        "byeCount": bye_count,
        "uniqueFamilyCount": unique_family_count,
        "pairConsistent": not duplicate_errors,
        "duplicateErrors": duplicate_errors,
    }
