#!/usr/bin/env python3
"""生成家族 PK 向上汇报 HTML（单次报告 / 全量扫描 / 建设成果 Hub）。"""

from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from pathlib import Path

REPORT_DIR = Path(__file__).resolve().parent
if str(REPORT_DIR) not in sys.path:
    sys.path.insert(0, str(REPORT_DIR))

from generator import (  # noqa: E402
    EXPORTS_DIR,
    load_summary,
    render_report_html,
    scan_summaries,
    write_all_reports,
    write_hub,
    write_report,
)
from playbook import load_playbook  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="家族 PK 测试自动化 — 向上汇报 HTML")
    parser.add_argument("--json", help="单次 summary JSON，如 .tmp/family_pk_test_result_2026-07-11.json")
    parser.add_argument("--scan-tmp", action="store_true", help="扫描 .tmp/family_pk_test_result_*.json 生成全部报告")
    parser.add_argument("--hub", action="store_true", help="生成建设成果 Showcase 页 index.html（背景+演示+原理）")
    parser.add_argument("--out-dir", default=str(EXPORTS_DIR), help="HTML 输出目录")
    parser.add_argument("--open", action="store_true", help="生成后用浏览器打开")
    parser.add_argument("--stdout", action="store_true", help="将 HTML 输出到 stdout（仅 --json）")
    args = parser.parse_args()

    out_dir = Path(args.out_dir).resolve()

    if args.stdout:
        if not args.json:
            print("--stdout 需要配合 --json", file=sys.stderr)
            return 2
        summary = load_summary(Path(args.json))
        print(render_report_html(summary, load_playbook()))
        return 0

    opened: Path | None = None

    if args.hub or (not args.json and not args.scan_tmp):
        hub_path = write_hub(out_dir=out_dir)
        print(json.dumps({"hub": str(hub_path)}, ensure_ascii=False))
        opened = hub_path

    if args.scan_tmp:
        paths = write_all_reports(out_dir=out_dir)
        if args.hub:
            write_hub(out_dir=out_dir)
        print(json.dumps({"reports": [str(p) for p in paths]}, ensure_ascii=False))
        if paths and not opened:
            opened = paths[0]

    if args.json:
        path = write_report(Path(args.json), out_dir=out_dir)
        print(json.dumps({"report": str(path)}, ensure_ascii=False))
        opened = path
        if args.hub or args.scan_tmp:
            write_hub(out_dir=out_dir)

    if args.open and opened:
        url = opened.as_uri()
        if webbrowser.open(url):
            print(f"opened: {url}", file=sys.stderr)
        else:
            print(f"report: {url}", file=sys.stderr)

    if not args.json and not args.scan_tmp and not args.hub:
        summaries = scan_summaries()
        print(f"hint: found {len(summaries)} summary JSON in .tmp/", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
