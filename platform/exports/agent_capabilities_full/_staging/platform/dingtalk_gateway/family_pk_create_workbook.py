#!/usr/bin/env python3
"""新建家族 PK 测试钉钉表格（含各步骤 Sheet 占位）。"""

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
_FOLDER_CONFIG = GATEWAY_DIR / "config" / "family_pk_workbook_folder.json"

if (
    __name__ == "__main__"
    and _EXCEL_VENV.is_file()
    and Path(sys.executable).resolve() != _EXCEL_VENV.resolve()
):
    os.execv(str(_EXCEL_VENV), [str(_EXCEL_VENV), str(Path(__file__).resolve()), *sys.argv[1:]])

if str(GATEWAY_DIR) not in sys.path:
    sys.path.insert(0, str(GATEWAY_DIR))

from alidocs_excel_export import (  # noqa: E402
    ALIDOCS_NODE,
    _create_workbook,
    _excel_env,
    _get_token_and_operator,
    _get_workspace_id,
)
from family_pk_calc_utils import family_pk_workbook_title, FAMILY_PK_SHEET_ORDER  # noqa: E402
from family_pk_tab_to_workbook import (  # noqa: E402
    DEFAULT_WORKBOOK_SHEET,
    _delete_sheet,
    _ensure_sheet,
)

import httpx  # noqa: E402

DEFAULT_SHEETS = list(FAMILY_PK_SHEET_ORDER)


def _normalize_date(text: str) -> str:
    value = text.strip()
    if len(value) == 10 and value[4] == "-" and value[7] == "-":
        return value
    raise ValueError(f"日期须为 yyyy-MM-dd: {text!r}")


def load_parent_folder_config() -> dict[str, str]:
    if not _FOLDER_CONFIG.is_file():
        raise RuntimeError(f"缺少目录配置: {_FOLDER_CONFIG}")
    data = json.loads(_FOLDER_CONFIG.read_text(encoding="utf-8"))
    node_id = str(data.get("nodeId") or "").strip()
    if not node_id:
        raise RuntimeError(f"{_FOLDER_CONFIG} 缺少 nodeId")
    return {
        "nodeId": node_id,
        "spaceId": str(data.get("spaceId") or "").strip(),
        "folderUrl": str(data.get("folderUrl") or ALIDOCS_NODE.format(node_id=node_id)),
        "name": str(data.get("name") or "家族PK测试表目录"),
    }


def _resolve_workspace_id(parent_node_id: str, *, space_id: str = "") -> str:
    if space_id:
        return space_id
    if str(REPO_ROOT / "scripts") not in sys.path:
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from mcp_paths import resolve_dingtalk_cookie  # noqa: PLC0415

    try:
        return _get_workspace_id(parent_node_id, resolve_dingtalk_cookie())
    except OSError as exc:
        if "401" in str(exc):
            raise RuntimeError(
                "钉钉 alidocs Cookie 已过期，无法读取父目录 spaceId。"
                "请刷新 DINGTALK_COOKIE（~/.dingtalk_doc_cookie 或 .cursor/.mcp.secrets.json），"
                f"或在 {_FOLDER_CONFIG.name} 填写 spaceId"
            ) from exc
        raise


async def create_family_pk_workbook_async(
    *,
    pk_date: str,
    parent_node_id: str | None = None,
    sheets: list[str] | None = None,
) -> dict[str, Any]:
    pk_date = _normalize_date(pk_date)
    folder = load_parent_folder_config()
    parent = (parent_node_id or folder["nodeId"]).strip()
    title = family_pk_workbook_title(pk_date)
    sheet_names = list(sheets or DEFAULT_SHEETS)

    env = _excel_env()
    token, operator = await _get_token_and_operator(env)
    workspace_id = _resolve_workspace_id(parent, space_id=folder.get("spaceId") or "")
    workbook_id = await _create_workbook(
        token=token,
        operator=operator,
        workspace_id=workspace_id,
        parent_node_id=parent,
        name=title,
    )
    async with httpx.AsyncClient(timeout=120) as client:
        for name in sheet_names:
            await _ensure_sheet(
                token=token,
                operator=operator,
                workbook_id=workbook_id,
                sheet_name=name,
                client=client,
            )
        # 钉钉新建 WORKBOOK 自带默认 Sheet1；自定义 Sheet 建好后删掉，避免多一页空表。
        if sheet_names and DEFAULT_WORKBOOK_SHEET not in sheet_names:
            await _delete_sheet(
                token=token,
                operator=operator,
                workbook_id=workbook_id,
                sheet_name=DEFAULT_WORKBOOK_SHEET,
                client=client,
            )
    workbook_url = ALIDOCS_NODE.format(node_id=workbook_id)
    from family_pk_reorder_sheets import reorder_family_pk_sheets_async  # noqa: E402

    sheet_order = await reorder_family_pk_sheets_async(workbook_url)
    return {
        "pkDate": pk_date,
        "workbookTitle": title,
        "workbookId": workbook_id,
        "workbookUrl": workbook_url,
        "parentNodeId": parent,
        "parentFolderUrl": folder["folderUrl"],
        "sheets": sheet_names,
        "sheetOrder": sheet_order,
    }


def create_family_pk_workbook(
    *,
    pk_date: str,
    parent_node_id: str | None = None,
    sheets: list[str] | None = None,
) -> dict[str, Any]:
    return asyncio.run(
        create_family_pk_workbook_async(
            pk_date=pk_date,
            parent_node_id=parent_node_id,
            sheets=sheets,
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="新建家族PK测试钉钉表格")
    parser.add_argument("--pk-date", required=True, help="匹配日期 yyyy-MM-dd，用于表名")
    parser.add_argument("--parent-node-id", help="父目录 nodeId（默认读 family_pk_workbook_folder.json）")
    args = parser.parse_args()
    try:
        summary = create_family_pk_workbook(
            pk_date=args.pk_date.strip(),
            parent_node_id=args.parent_node_id.strip() if args.parent_node_id else None,
        )
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
