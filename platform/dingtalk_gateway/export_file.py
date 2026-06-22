#!/usr/bin/env python3
"""本地 CSV/JSON → 钉钉 alidocs 目录（创建在线表格或上传文件）。"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "scripts"))

from export_delivery import load_export_config, node_url  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="导出文件到钉钉 Agent 导出目录")
    parser.add_argument("file", help="本地 csv/json 路径")
    parser.add_argument("--name", help="钉钉中的文件名（默认取源文件名去扩展名）")
    args = parser.parse_args()

    src = Path(args.file).expanduser().resolve()
    if not src.is_file():
        print(f"[FAIL] 文件不存在: {src}", file=sys.stderr)
        return 1

    cfg = load_export_config()
    name = args.name or src.stem
    suffix = src.suffix.lower()

    try:
        if suffix == ".csv":
            from alidocs_excel_export import export_csv_to_folder

            url = export_csv_to_folder(
                src,
                parent_node_id=cfg.node_id,
                workbook_name=name,
            )
        elif suffix == ".json":
            from alidocs_upload import upload_file_to_folder

            url = upload_file_to_folder(
                src,
                parent_node_id=cfg.node_id,
                file_name=src.name,
                convert_to_online_doc=False,
            )
        else:
            from alidocs_upload import upload_file_to_folder

            url = upload_file_to_folder(
                src,
                parent_node_id=cfg.node_id,
                file_name=src.name,
            )
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1

    print(url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
