#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
列举并读取钉钉目录下全部「版本用例」Excel（文件名含 x.y.z）。

示例：
  python3 scripts/dingtalk_read_folder_workbooks.py --folder-url "https://alidocs.dingtalk.com/i/nodes/XXX"
  python3 scripts/dingtalk_read_folder_workbooks.py --list-only
  python3 scripts/dingtalk_read_folder_workbooks.py --export-dir ~/Documents/cursor-mcp/dingExcel/kb-sync
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
_ROOT = _SCRIPTS.parent
_MCP_PYTHON = _ROOT / ".cursor/skills/dingtalk-doc-read/mcp_dingtalk_doc/venv/bin/python3.13"
if (
    __name__ == "__main__"
    and _MCP_PYTHON.is_file()
    and Path(sys.executable).resolve() != _MCP_PYTHON.resolve()
):
    os.execv(str(_MCP_PYTHON), [str(_MCP_PYTHON), str(Path(__file__).resolve()), *sys.argv[1:]])

if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from dingtalk_kb_source import (  # noqa: E402
    DEFAULT_CONFIG,
    discover_workbooks,
    fetch_workbook_sheets,
    load_json_config,
)


def _nonempty_rows(matrix: list[list]) -> int:
    n = 0
    for row in matrix:
        if not isinstance(row, list):
            continue
        if any(cell is not None and str(cell).strip() for cell in row):
            n += 1
    return n


def main() -> int:
    cfg = load_json_config()
    ap = argparse.ArgumentParser(description="读取钉钉目录下全部版本用例 Excel")
    ap.add_argument(
        "--folder-url",
        default=str(cfg.get("folderUrl") or ""),
        help="钉钉目录 URL（默认 DingTalk/config/kb.json）",
    )
    ap.add_argument("--list-only", action="store_true", help="只列举，不拉取 Sheet 数据")
    ap.add_argument(
        "--export-dir",
        type=Path,
        default=None,
        help="将每个工作簿导出为 JSON（含全部 Sheet 原始矩阵）",
    )
    ap.add_argument("--recursive", action=argparse.BooleanOptionalAction, default=bool(cfg.get("recursive", True)))
    ap.add_argument("--max-documents", type=int, default=int(cfg.get("maxDocuments", 200)))
    ap.add_argument("--max-folder-fetches", type=int, default=int(cfg.get("maxFolderFetches", 80)))
    args = ap.parse_args()

    folder = (args.folder_url or "").strip()
    if not folder:
        raise SystemExit("请提供 --folder-url 或在 DingTalk/config/kb.json 配置 folderUrl")

    print(f"扫描目录: {folder}")
    workbooks = discover_workbooks(
        folder,
        recursive=args.recursive,
        max_documents=args.max_documents,
        max_folder_fetches=args.max_folder_fetches,
    )
    if not workbooks:
        raise SystemExit("未发现版本用例 Excel（目录为空或 Cookie/权限无效）")

    summary: list[dict] = []
    for wb in workbooks:
        item: dict = {
            "version": wb.version_label,
            "name": wb.name,
            "url": wb.url,
            "node_id": wb.node_id,
        }
        if args.list_only:
            summary.append(item)
            print(f"{wb.version_label}\t{wb.name}\t{wb.url}")
            continue

        print(f"\n=== {wb.version_label} · {wb.name} ===")
        sheets = fetch_workbook_sheets(wb.url)
        sheet_info = []
        for sheet_name, matrix in sheets:
            rows = _nonempty_rows(matrix)
            sheet_info.append({"name": sheet_name, "nonempty_rows": rows, "total_rows": len(matrix)})
            print(f"  - {sheet_name}: {rows} 非空行 / {len(matrix)} 行")
        item["sheets"] = sheet_info

        if args.export_dir:
            out_dir = args.export_dir.expanduser()
            out_dir.mkdir(parents=True, exist_ok=True)
            safe = re.sub(r"[^\w\u4e00-\u9fff.\-]+", "_", wb.name)[:80]
            out_path = out_dir / f"{wb.version_label}_{safe}.json"
            payload = {
                **item,
                "data": {name: matrix for name, matrix in sheets},
            }
            out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            item["export_path"] = str(out_path)
            print(f"  已导出: {out_path}")

        summary.append(item)

    if args.export_dir:
        out_dir = args.export_dir.expanduser()
        manifest_path = out_dir / "manifest.json"
        manifest_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\n清单: {manifest_path}")

    print(f"\n共 {len(workbooks)} 个版本表格。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
