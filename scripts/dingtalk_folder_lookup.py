#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
在已登记的钉钉目录中按关键词查找子文档链接。

推荐入口：DingTalk/lookup_execute.py

示例：
  python3 DingTalk/lookup_execute.py 2.5.4
  python3 DingTalk/lookup_execute.py --folder-id yaahlan-testcases --list
  python3 DingTalk/lookup_execute.py --name-contains 消息
"""

from __future__ import annotations

import argparse
import json
import os
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

from dingtalk_collect_folder_links import (  # noqa: E402
    DentryLink,
    extract_node_id,
    fetch_children_via_api,
    filter_links,
)
from dingtalk_kb_source import (  # noqa: E402
    extract_node_id_from_url,
    list_registered_folders,
    load_json_config,
    resolve_dingtalk_cookie,
    resolve_folder_url,
)


def _list_folder_links(
    folder_url: str,
    *,
    only_spreadsheet: bool,
    name_contains: str,
) -> list[DentryLink]:
    folder_id = extract_node_id_from_url(folder_url)
    cookie = resolve_dingtalk_cookie()
    import asyncio

    links = asyncio.run(fetch_children_via_api(folder_id, cookie=cookie))
    return filter_links(
        links,
        only_spreadsheet=only_spreadsheet,
        name_contains=name_contains,
    )


def _print_links(links: list[DentryLink], *, as_json: bool) -> None:
    links = sorted(links, key=lambda l: l.name)
    if as_json:
        payload = [
            {
                "name": l.name,
                "node_id": l.node_id,
                "url": l.url,
                "kind": l.kind,
                "extension": l.extension,
            }
            for l in links
        ]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    for l in links:
        print(f"{l.name}\t{l.url}")


def main() -> int:
    cfg = load_json_config()
    ap = argparse.ArgumentParser(
        description="在已登记钉钉目录中查找子文档链接（默认 Yaahlan 测试用例目录）"
    )
    ap.add_argument(
        "keyword",
        nargs="?",
        default="",
        help="文件名关键词（如 2.5.4、消息）；省略且未 --list 时打印登记目录",
    )
    ap.add_argument(
        "--folder-id",
        default=str(cfg.get("folderId") or "yaahlan-testcases"),
        help="已登记目录 id（见 DingTalk/config/folders.json）",
    )
    ap.add_argument("--folder-url", default="", help="直接指定目录 URL（覆盖 --folder-id）")
    ap.add_argument("--list", action="store_true", help="列举目录下全部匹配项（不填 keyword 时列出全部表格）")
    ap.add_argument("--all-kinds", action="store_true", help="包含文件夹等非表格项（默认仅表格/用例）")
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    ap.add_argument("--show-folders", action="store_true", help="仅打印已登记目录清单")
    args = ap.parse_args()

    if args.show_folders or (not args.keyword.strip() and not args.list and not args.folder_url):
        folders = list_registered_folders()
        if not folders:
            raise SystemExit("DingTalk/config/folders.json 尚无登记目录")
        for f in folders:
            fid = str(f.get("id") or "")
            name = str(f.get("name") or "")
            url = str(f.get("folderUrl") or "")
            default = " [默认]" if f.get("default") else ""
            print(f"{fid}{default}\t{name}\t{url}")
        print(f"\n共 {len(folders)} 个登记目录", file=sys.stderr)
        return 0

    folder_url, entry = resolve_folder_url(
        folder_id=args.folder_id,
        folder_url=args.folder_url or None,
        kb_config=cfg,
    )
    folder_name = str((entry or {}).get("name") or extract_node_id(folder_url))
    only_spreadsheet = not args.all_kinds
    keyword = args.keyword.strip()

    if args.list or not keyword:
        links = _list_folder_links(
            folder_url,
            only_spreadsheet=only_spreadsheet,
            name_contains=keyword,
        )
    else:
        links = _list_folder_links(
            folder_url,
            only_spreadsheet=only_spreadsheet,
            name_contains=keyword,
        )
        if not links:
            links = _list_folder_links(
                folder_url,
                only_spreadsheet=only_spreadsheet,
                name_contains="",
            )
            kw = keyword.lower()
            links = [l for l in links if kw in l.name.lower()]

    if not links:
        scope = "表格" if only_spreadsheet else "文档"
        hint = f"关键词「{keyword}」" if keyword else "当前目录"
        raise SystemExit(f"未找到匹配{scope}：{hint}（目录: {folder_name}）")

    _print_links(links, as_json=args.json)
    print(
        f"\n目录: {folder_name} ({folder_url})\n共 {len(links)} 个匹配",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
