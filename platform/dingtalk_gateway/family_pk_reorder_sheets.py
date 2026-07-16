#!/usr/bin/env python3
"""按家族 PK 标准顺序重排钉钉表格 Sheet。"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

GATEWAY_DIR = Path(__file__).resolve().parent
REPO_ROOT = GATEWAY_DIR.parents[1]
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

from alidocs_excel_export import DOC_API, _excel_env, _get_token_and_operator  # noqa: E402
from family_pk_calc_utils import FAMILY_PK_SHEET_ORDER  # noqa: E402
from family_pk_tab_to_workbook import (  # noqa: E402
    DEFAULT_WORKBOOK,
    _string_rows,
    _write_sheet_replace,
)
from mse_workbook_utils import fetch_workbook_sheets_async, node_id  # noqa: E402

import httpx  # noqa: E402


async def _list_sheet_names(
    *,
    token: str,
    operator: str,
    workbook_id: str,
    client: httpx.AsyncClient,
) -> list[str]:
    sheets_url = f"{DOC_API}/workbooks/{workbook_id}/sheets?operatorId={operator}"
    resp = await client.get(sheets_url, headers={"x-acs-dingtalk-access-token": token})
    resp.raise_for_status()
    return [str(item.get("name") or "") for item in resp.json().get("value", [])]


async def _delete_sheet_by_name(
    *,
    token: str,
    operator: str,
    workbook_id: str,
    sheet_name: str,
    client: httpx.AsyncClient,
) -> None:
    sheets_url = f"{DOC_API}/workbooks/{workbook_id}/sheets?operatorId={operator}"
    resp = await client.get(sheets_url, headers={"x-acs-dingtalk-access-token": token})
    resp.raise_for_status()
    sheet_id = None
    for item in resp.json().get("value", []):
        if str(item.get("name") or "") == sheet_name:
            sheet_id = str(item.get("id") or "")
            break
    if not sheet_id:
        return
    delete_url = f"{DOC_API}/workbooks/{workbook_id}/sheets/{sheet_id}?operatorId={operator}"
    del_resp = await client.delete(
        delete_url,
        headers={"x-acs-dingtalk-access-token": token},
    )
    if del_resp.status_code >= 400:
        raise RuntimeError(
            f"删除工作表 {sheet_name} 失败 HTTP {del_resp.status_code}: {del_resp.text[:300]}"
        )


async def _create_sheet_at_index(
    *,
    token: str,
    operator: str,
    workbook_id: str,
    sheet_name: str,
    target_index: int,
    client: httpx.AsyncClient,
) -> None:
    sheets_url = f"{DOC_API}/workbooks/{workbook_id}/sheets?operatorId={operator}"
    create_resp = await client.post(
        sheets_url,
        headers={"x-acs-dingtalk-access-token": token, "Content-Type": "application/json"},
        json={"name": sheet_name, "targetIndex": target_index},
    )
    if create_resp.status_code >= 400:
        raise RuntimeError(
            f"创建工作表 {sheet_name} 失败 HTTP {create_resp.status_code}: {create_resp.text[:300]}"
        )


async def reorder_family_pk_sheets_async(
    workbook_url_or_id: str,
    *,
    sheet_order: list[str] | None = None,
) -> dict[str, Any]:
    """将已存在的标准 Sheet 调整到约定顺序（delete + targetIndex 重建，保留内容）。"""
    order = list(sheet_order or FAMILY_PK_SHEET_ORDER)
    workbook_id = node_id(workbook_url_or_id)
    workbook_url = f"https://alidocs.dingtalk.com/i/nodes/{workbook_id}"

    env = _excel_env()
    token, operator = await _get_token_and_operator(env)
    sheets_data = await fetch_workbook_sheets_async(workbook_url)

    async with httpx.AsyncClient(timeout=120) as client:
        before = await _list_sheet_names(
            token=token, operator=operator, workbook_id=workbook_id, client=client
        )
        existing = [name for name in order if name in sheets_data or name in before]
        if not existing:
            return {
                "workbookUrl": workbook_url,
                "before": before,
                "after": before,
                "moved": [],
                "changed": False,
            }

        prefix_ok = before[: len(existing)] == existing
        if prefix_ok:
            return {
                "workbookUrl": workbook_url,
                "before": before,
                "after": before,
                "moved": [],
                "changed": False,
            }

        data_cache = {
            name: sheets_data.get(name) or [[""]]
            for name in existing
        }
        moved: list[dict[str, Any]] = []
        # 钉钉表须保留至少一个可见 Sheet；用末尾锚点页兜底后再删标准页。
        anchor_name = "_reorder_anchor"
        current_before = await _list_sheet_names(
            token=token, operator=operator, workbook_id=workbook_id, client=client
        )
        if anchor_name in current_before:
            await _delete_sheet_by_name(
                token=token,
                operator=operator,
                workbook_id=workbook_id,
                sheet_name=anchor_name,
                client=client,
            )

        await _create_sheet_at_index(
            token=token,
            operator=operator,
            workbook_id=workbook_id,
            sheet_name=anchor_name,
            target_index=len(current_before),
            client=client,
        )

        for sheet_name in list(existing):
            if sheet_name not in await _list_sheet_names(
                token=token, operator=operator, workbook_id=workbook_id, client=client
            ):
                continue
            await _delete_sheet_by_name(
                token=token,
                operator=operator,
                workbook_id=workbook_id,
                sheet_name=sheet_name,
                client=client,
            )

        # targetIndex=0 每次插在表头；倒序创建可得正序。
        for sheet_name in reversed(existing):
            await _create_sheet_at_index(
                token=token,
                operator=operator,
                workbook_id=workbook_id,
                sheet_name=sheet_name,
                target_index=0,
                client=client,
            )
            await _write_sheet_replace(
                token=token,
                operator=operator,
                workbook_id=workbook_id,
                sheet_name=sheet_name,
                rows=_string_rows(data_cache[sheet_name]),
            )
            moved.append({"sheet": sheet_name, "targetIndex": existing.index(sheet_name)})

        await _delete_sheet_by_name(
            token=token,
            operator=operator,
            workbook_id=workbook_id,
            sheet_name=anchor_name,
            client=client,
        )

        after = await _list_sheet_names(
            token=token, operator=operator, workbook_id=workbook_id, client=client
        )

    return {
        "workbookUrl": workbook_url,
        "before": before,
        "after": after,
        "moved": moved,
        "changed": bool(moved),
        "expectedPrefix": existing,
    }


def reorder_family_pk_sheets(
    workbook_url_or_id: str,
    *,
    sheet_order: list[str] | None = None,
) -> dict[str, Any]:
    return asyncio.run(
        reorder_family_pk_sheets_async(workbook_url_or_id, sheet_order=sheet_order)
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="家族 PK 钉钉表 Sheet 顺序调整")
    parser.add_argument("--workbook", default=DEFAULT_WORKBOOK)
    args = parser.parse_args()
    try:
        summary = reorder_family_pk_sheets(args.workbook.strip())
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
