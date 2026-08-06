#!/usr/bin/env python3
"""开发者后台全量家族 → 成员/手机号/族长标记 → 过滤非中东族长 → 钉钉 Sheet2。"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

GATEWAY_DIR = Path(__file__).resolve().parent
REPO_ROOT = GATEWAY_DIR.parents[1]
_ADMIN_DIR = admin_module_dir()
_EXCEL_VENV = (
    REPO_ROOT / ".cursor/skills/testcase-to-excel/mcp_dingtalk_excel/venv/bin/python3.13"
)

if (
    __name__ == "__main__"
    and _EXCEL_VENV.is_file()
    and Path(sys.executable).resolve() != _EXCEL_VENV.resolve()
):
    os.execv(str(_EXCEL_VENV), [str(_EXCEL_VENV), str(Path(__file__).resolve()), *sys.argv[1:]])

if str(GATEWAY_DIR) not in sys.path:
    sys.path.insert(0, str(GATEWAY_DIR))

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
if str(_ADMIN_DIR) not in sys.path:
    sys.path.insert(0, str(_ADMIN_DIR))

from family_pk_tab_to_workbook import (  # noqa: E402
    DEFAULT_SHEET,
    DEFAULT_WORKBOOK,
    build_rows,
    write_family_list_async,
)
from family_pk_calc_utils import rename_family_pk_workbook  # noqa: E402
from admin.env import load_local_env  # noqa: E402

MENA_AREA_CODES = {"MENA", "中东", "中东区"}

load_local_env(str(_ADMIN_DIR))


def _run_json(cmd: list[str]) -> dict[str, Any]:
    proc = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip()[-500:]
        raise RuntimeError(f"命令失败 {' '.join(cmd)}: {tail}")
    text = (proc.stdout or "").strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise RuntimeError(f"未解析到 JSON: {text[:300]}")
    return json.loads(text[start : end + 1])


def list_all_families(*, page_size: int = 100) -> list[dict[str, Any]]:
    offset = 0
    items: list[dict[str, Any]] = []
    while True:
        body = _run_json(
            [
                sys.executable,
                str(admin_execute_path()),
                "--list-all-families",
                "--family-offset",
                str(offset),
                "--family-limit",
                str(page_size),
            ]
        )
        batch = body.get("items") or []
        if not isinstance(batch, list):
            raise RuntimeError("getAllFamilyList 返回 items 格式异常")
        items.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
    return items


def query_owner_area(owner_id: str, *, cache: dict[str, str]) -> str:
    owner = owner_id.strip()
    if not owner:
        return ""
    if owner in cache:
        return cache[owner]
    body = _run_json(
        [
            sys.executable,
            str(admin_execute_path()),
            "--query-user-id",
            owner,
        ]
    )
    area = str(body.get("area") or "").strip()
    cache[owner] = area
    return area


def is_mena_owner(area: str) -> bool:
    text = (area or "").strip()
    if not text:
        return False
    upper = text.upper()
    return upper in MENA_AREA_CODES or text in MENA_AREA_CODES


def filter_mena_families(items: list[dict[str, Any]]) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    kept: list[dict[str, str]] = []
    excluded: list[dict[str, Any]] = []
    area_cache: dict[str, str] = {}
    for item in items:
        fid = str(item.get("familyId") or "").strip()
        fname = str(item.get("familyName") or "").strip()
        owner = str(item.get("familyOwnerId") or "").strip()
        if not fid.isdigit():
            continue
        area = query_owner_area(owner, cache=area_cache)
        if is_mena_owner(area):
            kept.append({"familyId": fid, "familyName": fname})
        else:
            excluded.append(
                {
                    "familyId": fid,
                    "familyName": fname,
                    "familyOwnerId": owner,
                    "ownerArea": area,
                }
            )
    return kept, excluded


def export_admin_families_to_workbook(
    *,
    workbook: str,
    sheet_name: str = DEFAULT_SHEET,
    pk_date: str | None = None,
) -> dict[str, Any]:
    all_items = list_all_families()
    families, excluded = filter_mena_families(all_items)
    if not families:
        raise RuntimeError("过滤后无中东族长家族，请检查族长大区（queryUserDetail.area）")

    rows = build_rows(families=families)
    doc_url = asyncio.run(write_family_list_async(workbook, rows, sheet_name=sheet_name))
    workbook_title = ""
    if pk_date and str(pk_date).strip():
        workbook_title = rename_family_pk_workbook(workbook, str(pk_date).strip())
    out_path = tmp_dir() / "family_pk_admin_families_sheet2.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    summary = {
        "workbookUrl": doc_url,
        "workbookTitle": workbook_title or None,
        "sheetName": sheet_name,
        "totalFamilies": len(all_items),
        "keptFamilies": len(families),
        "excludedFamilies": len(excluded),
        "memberRowCount": max(len(rows) - 1, 0),
        "excluded": excluded[:20],
        "reportPath": str(out_path),
    }
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="开发者后台家族列表 → 钉钉 Sheet2（仅中东族长）")
    parser.add_argument("workbook", nargs="?", default=DEFAULT_WORKBOOK, help="钉钉表格 URL/nodeId")
    parser.add_argument("--sheet-name", default=DEFAULT_SHEET, help="Sheet2 名称")
    parser.add_argument("--pk-date", help="匹配日期 yyyy-MM-dd，重命名钉钉表")
    args = parser.parse_args()
    try:
        summary = export_admin_families_to_workbook(
            workbook=args.workbook.strip(),
            sheet_name=args.sheet_name.strip() or DEFAULT_SHEET,
            pk_date=args.pk_date.strip() if args.pk_date else None,
        )
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
