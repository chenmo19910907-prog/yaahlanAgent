#!/usr/bin/env python3
"""从 MSE 读取 familyFundConfig → 更新钉钉参数表。"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
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

from alidocs_excel_export import _excel_env, _get_token_and_operator  # noqa: E402
from family_fund_calc_utils import (  # noqa: E402
    FAMILY_FUND_APP_KEY,
    FAMILY_FUND_CONFIG_KEY,
    FAMILY_FUND_NAMESPACE,
    rename_family_fund_workbook_async,
)
from family_fund_json_to_workbook import build_param_sheet_rows  # noqa: E402
from mse_config_export import _fetch_mse_config  # noqa: E402
from mse_sync_to_workbook import _write_sheet  # noqa: E402
from mse_workbook_utils import (  # noqa: E402
    fetch_workbook_sheets_async,
    node_id,
    reconcile_param_sheet_rows,
    resolve_param_sheet_name,
)

PARAM_SHEET = "参数表"


async def sync_family_fund_mse_to_workbook_async(
    workbook_url_or_id: str,
    *,
    param_sheet: str | None = None,
    mode: str = "merge",
    week_monday: str | None = None,
) -> str:
    workbook_id = node_id(workbook_url_or_id)
    url = f"https://alidocs.dingtalk.com/i/nodes/{workbook_id}"

    fetched = _fetch_mse_config(
        namespace=FAMILY_FUND_NAMESPACE,
        config_key=FAMILY_FUND_CONFIG_KEY,
        app_key=FAMILY_FUND_APP_KEY,
    )
    config = fetched["configValue"]
    item = fetched["meta"]
    meta = {
        "nameSpace": str(item.get("nameSpace") or FAMILY_FUND_NAMESPACE),
        "configKey": str(item.get("configKey") or FAMILY_FUND_CONFIG_KEY),
        "configDesc": str(item.get("configDesc") or "家族基金"),
        "modified": str(item.get("modified") or ""),
        "appKey": FAMILY_FUND_APP_KEY,
    }

    sheets = await fetch_workbook_sheets_async(url)
    sheet_name = resolve_param_sheet_name(sheets, preferred=param_sheet)
    existing = sheets.get(sheet_name) or []
    fresh_rows = build_param_sheet_rows(config=config, meta=meta)

    if mode == "rebuild" or len(existing) < 3:
        param_rows = fresh_rows
    else:
        param_rows = reconcile_param_sheet_rows(existing, fresh_rows, applied=fresh_rows)

    env = _excel_env()
    token, operator = await _get_token_and_operator(env)
    await _write_sheet(
        token=token,
        operator=operator,
        workbook_id=workbook_id,
        sheet_name=sheet_name,
        rows=param_rows,
    )
    if week_monday and str(week_monday).strip():
        try:
            await rename_family_fund_workbook_async(url, str(week_monday).strip())
        except (OSError, RuntimeError, ValueError) as exc:
            print(
                f"WARN: 重命名 {week_monday}家族基金数据测试 失败: {exc}；参数表已写入",
                file=sys.stderr,
            )
    return url


def sync_family_fund_mse_to_workbook(workbook_url_or_id: str, **kwargs: Any) -> str:
    return asyncio.run(sync_family_fund_mse_to_workbook_async(workbook_url_or_id, **kwargs))


def main() -> int:
    parser = argparse.ArgumentParser(description="familyFundConfig MSE → 钉钉参数表")
    parser.add_argument("workbook", help="钉钉表格 URL 或 nodeId")
    parser.add_argument("--param-sheet", default="")
    parser.add_argument("--mode", choices=("merge", "rebuild"), default="merge")
    parser.add_argument("--week-monday", help="周期周一 yyyy-MM-dd，用于重命名钉钉表")
    args = parser.parse_args()
    try:
        url = sync_family_fund_mse_to_workbook(
            args.workbook.strip(),
            param_sheet=args.param_sheet.strip() or None,
            mode=args.mode.strip(),
            week_monday=args.week_monday.strip() if args.week_monday else None,
        )
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1
    print(url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
