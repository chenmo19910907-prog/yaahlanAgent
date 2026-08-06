#!/usr/bin/env python3
"""兼容入口：贡献榜验收已合并至「用户发钻测试」，本脚本转调 member_reward。"""

from __future__ import annotations

import argparse
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

from family_pk_member_reward_to_workbook import (  # noqa: E402
    DEFAULT_SHEET,
    export_user_reward_contrib_verify_to_workbook,
)
from family_pk_tab_to_workbook import DEFAULT_WORKBOOK  # noqa: E402


def export_contrib_verify_to_workbook(
    *,
    workbook: str,
    pk_date: str,
    user_id: str,
    seed_report: Path | None,
    sheet_name: str,
    area: str,
) -> dict[str, Any]:
    summary = export_user_reward_contrib_verify_to_workbook(
        workbook=workbook,
        pk_date=pk_date,
        user_id=user_id,
        seed_report=seed_report,
        sheet_name=sheet_name or DEFAULT_SHEET,
        area=area,
    )
    contrib = summary.get("contribVerify") or {}
    out_path = tmp_dir() / f"family_pk_contrib_verify_{pk_date}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(contrib, ensure_ascii=False, indent=2), encoding="utf-8")
    contrib["workbookUrl"] = summary.get("workbookUrl")
    contrib["workbookTitle"] = summary.get("workbookTitle")
    contrib["sheetName"] = summary.get("sheetName")
    contrib["reportPath"] = str(out_path)
    return contrib


def main() -> int:
    parser = argparse.ArgumentParser(
        description="（已合并）贡献榜验收 → 写入「用户发钻测试」"
    )
    parser.add_argument("--workbook", default=DEFAULT_WORKBOOK)
    parser.add_argument("--pk-date", required=True)
    parser.add_argument(
        "--user-id",
        "--momoid",
        dest="user_id",
        default="100486375",
    )
    parser.add_argument("--seed-report", type=Path)
    parser.add_argument(
        "--sheet-name",
        default=DEFAULT_SHEET,
        help="默认写入「用户发钻测试」",
    )
    parser.add_argument("--area", default="MENA")
    args = parser.parse_args()

    try:
        summary = export_contrib_verify_to_workbook(
            workbook=args.workbook.strip(),
            pk_date=args.pk_date.strip(),
            user_id=str(args.user_id).strip(),
            seed_report=args.seed_report,
            sheet_name=args.sheet_name.strip() or DEFAULT_SHEET,
            area=str(args.area).strip().upper() or "MENA",
        )
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary.get("allPass") else 2


if __name__ == "__main__":
    raise SystemExit(main())
