#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从钉钉 alidocs 目录同步版本测试用例 → testcase-kb。

推荐入口：DingTalk/kb_sync_execute.py（本文件为实现代码）
默认读取 DingTalk/config/kb.json 中的 folderUrl（可改为你的用例目录）。

处理顺序（与本地 xlsx 同步一致）：
1) 按版本号升序逐个 Excel
2) 每个工作簿内逐 Sheet 写入
3) 同名功能模块：后处理的较新版本覆盖旧条目
4) 可选跑 kb_optimize_pipeline（去重 / 矛盾合并 / 体例改写）

冲突规则：版本号更大者优先保留（同 xlsx_kb_sync）。
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
_ROOT = _SCRIPTS.parent
_MCP_PYTHON = _ROOT / ".cursor/skills/dingtalk-doc-read/mcp_dingtalk_doc/venv/bin/python3.13"
if not _MCP_PYTHON.is_file():
    _MCP_PYTHON = (
        _ROOT
        / ".cursor/skills/testcase-to-excel/mcp_dingtalk_excel/venv/bin/python3.13"
    )
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
    resolve_folder_url,
)
from xlsx_kb_sync import (  # noqa: E402
    DEFAULT_OUTPUT_DOC_DIR,
    LOCALE_SKIP_RE,
    process_workbook_sheets,
    reset_output_dir,
)

ROOT = _SCRIPTS.parent


def run_optimize_pipeline(output_dir: Path) -> int:
    cmd = [
        sys.executable,
        str(_SCRIPTS / "kb_optimize_pipeline.py"),
        "--root",
        str(output_dir),
    ]
    print(f"\n>>> {' '.join(cmd)}")
    return subprocess.call(cmd, cwd=str(ROOT))


def main() -> int:
    cfg = load_json_config()
    ap = argparse.ArgumentParser(description="钉钉目录 → testcase-kb 同步")
    ap.add_argument(
        "--folder-id",
        default=str(cfg.get("folderId") or ""),
        help="已登记目录 id（见 DingTalk/config/folders.json；默认 yaahlan-testcases）",
    )
    ap.add_argument(
        "--folder-url",
        default="",
        help="钉钉 alidocs 目录 URL（指定时覆盖 --folder-id）",
    )
    ap.add_argument(
        "--workbook-url",
        action="append",
        default=[],
        help="仅同步指定 Excel URL（可重复）；指定后不再扫描目录",
    )
    ap.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DOC_DIR,
        help="testcase-kb 输出目录",
    )
    ap.add_argument("--recursive", action=argparse.BooleanOptionalAction, default=bool(cfg.get("recursive", True)))
    ap.add_argument("--max-documents", type=int, default=int(cfg.get("maxDocuments", 200)))
    ap.add_argument("--max-folder-fetches", type=int, default=int(cfg.get("maxFolderFetches", 80)))
    ap.add_argument("--only-version", type=str, default="", help="仅处理如 2.5.2")
    ap.add_argument("--reset", action="store_true", help="先清空 output-dir 下 *.md")
    ap.add_argument(
        "--no-optimize",
        action="store_true",
        help="同步后不跑 kb_optimize_pipeline",
    )
    ap.add_argument(
        "--list-only",
        action="store_true",
        help="只列举目录内可识别的版本 Excel，不写入",
    )
    args = ap.parse_args()

    if args.reset:
        reset_output_dir(args.output_dir)

    workbooks = []
    if args.workbook_url:
        from dingtalk_kb_source import (
            DingtalkWorkbook,
            parse_version_from_name,
            version_label_from_tuple,
        )

        from dingtalk_kb_source import extract_node_id_from_url, is_case_workbook_name

        try:
            folder_for_lookup, _ = resolve_folder_url(
                folder_id=args.folder_id or None,
                folder_url=args.folder_url or None,
                kb_config=cfg,
            )
        except ValueError:
            folder_for_lookup = ""
        catalog = (
            discover_workbooks(folder_for_lookup, max_documents=500)
            if folder_for_lookup
            else []
        )
        by_id = {w.node_id: w for w in catalog}

        for url in args.workbook_url:
            nid = extract_node_id_from_url(url)
            hit = by_id.get(nid) or next((w for w in catalog if w.url == url), None)
            if hit:
                workbooks.append(hit)
                continue
            name = nid
            if not is_case_workbook_name(name):
                print(f"跳过（非用例表）: {url}", file=sys.stderr)
                continue
            ver = parse_version_from_name(name) or (0, 0, 0)
            vlabel = version_label_from_tuple(ver) if parse_version_from_name(name) else "—"
            workbooks.append(
                DingtalkWorkbook(
                    name=name,
                    url=url,
                    node_id=nid,
                    version_tuple=ver,
                    version_label=vlabel,
                )
            )
        workbooks.sort(key=lambda w: (w.version_tuple, w.name))
    else:
        try:
            folder, folder_entry = resolve_folder_url(
                folder_id=args.folder_id or None,
                folder_url=args.folder_url or None,
                kb_config=cfg,
            )
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        label = folder_entry.get("name") if folder_entry else folder
        print(f"扫描钉钉目录: {label} ({folder})")
        workbooks = discover_workbooks(
            folder,
            recursive=args.recursive,
            max_documents=args.max_documents,
            max_folder_fetches=args.max_folder_fetches,
        )

    if args.only_version:
        t = tuple(int(x) for x in args.only_version.split("."))
        workbooks = [w for w in workbooks if w.version_tuple == t]

    if not workbooks:
        raise SystemExit("未发现可同步的版本用例 Excel（目录为空或节点非表格）")

    print(f"将处理 {len(workbooks)} 个工作簿，输出: {args.output_dir}")
    for w in workbooks:
        print(f"  - {w.version_label}  {w.name}  {w.url}")

    if args.list_only:
        return 0

    # 全局替换输出目录（xlsx_kb_sync 模块级常量）
    import xlsx_kb_sync as xkb

    xkb.DEFAULT_OUTPUT_DOC_DIR = args.output_dir

    ok, fail = 0, 0
    for wb in workbooks:
        if LOCALE_SKIP_RE.search(wb.name):
            print(f"\n=== 跳过整表（土语/俄语专项）: {wb.name} ===")
            continue
        print(f"\n=== 工作簿开始: {wb.name} ({wb.version_label}) ===")
        try:
            sheets = fetch_workbook_sheets(wb.url)
            process_workbook_sheets(wb.name, wb.version_label, sheets)
            print(f"=== 工作簿完成: {wb.name} ===")
            ok += 1
        except Exception as exc:
            fail += 1
            print(f"=== 工作簿失败: {wb.name} ===\n    {exc}", file=sys.stderr)
    print(f"\n同步统计: 成功 {ok}，失败 {fail}，合计 {len(workbooks)}")

    should_optimize = (not args.no_optimize) and bool(cfg.get("runOptimizePipeline", True))
    if should_optimize:
        rc = run_optimize_pipeline(args.output_dir)
        if rc != 0:
            return rc

    print("\n钉钉同步完成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
