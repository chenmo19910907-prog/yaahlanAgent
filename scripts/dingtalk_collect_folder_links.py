#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
列举钉钉 alidocs 目录下全部子文档链接。

默认使用与浏览器相同的 Box API（/box/api/v2/dentry/list），Cookie 有效时无需开浏览器。
可选 --playwright：启动 Chromium 打开目录页并拦截同一 API（用于 Cookie 失效时对照）。

推荐入口：DingTalk/collect_execute.py（本文件为实现代码）

示例：
  python3 DingTalk/collect_execute.py --only-spreadsheet
  python3 DingTalk/collect_execute.py --output ~/Documents/cursor-mcp/dingExcel/folder-links.json
  python3 DingTalk/collect_execute.py --playwright --headed
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
_SCRIPTS = Path(__file__).resolve().parent
_ROOT = _SCRIPTS.parent
_MCP_PYTHON = _ROOT / ".cursor/skills/dingtalk-doc-read/mcp_dingtalk_doc/venv/bin/python3.13"
_PW_PYTHON = _SCRIPTS / ".venv-playwright/bin/python3"
if (
    __name__ == "__main__"
    and "--playwright" in sys.argv
    and _PW_PYTHON.is_file()
    and Path(sys.executable).resolve() != _PW_PYTHON.resolve()
):
    os.execv(str(_PW_PYTHON), [str(_PW_PYTHON), str(Path(__file__).resolve()), *sys.argv[1:]])
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
    load_json_config,
    resolve_dingtalk_cookie,
    resolve_folder_url,
)

BASE_URL = "https://alidocs.dingtalk.com"
LIST_API = f"{BASE_URL}/box/api/v2/dentry/list"
NODE_ID_RE = re.compile(r"/i/nodes/([^?/#]+)")
SPREADSHEET_EXT = frozenset({"axls", "xlsx", "xls", "able", "sheet"})


@dataclass
class DentryLink:
    name: str
    node_id: str
    url: str
    kind: str  # folder | document | other
    extension: str = ""
    dentry_type: str = ""
    updated_time: Optional[int] = None


def extract_node_id(url_or_id: str) -> str:
    text = (url_or_id or "").strip()
    if text.startswith("http"):
        m = NODE_ID_RE.search(text)
        if not m:
            raise ValueError(f"无法从 URL 解析 node_id: {text}")
        return m.group(1)
    return text


def _xsrf_from_cookie(cookie: str) -> str:
    m = re.search(r"XSRF-TOKEN=([^;]+)", cookie)
    return m.group(1) if m else ""


def _infer_kind(entry: Dict[str, Any]) -> str:
    dtype = str(entry.get("dentryType") or "").lower()
    if dtype == "folder" or entry.get("hasChildren"):
        return "folder"
    return "document"


def _entry_to_link(entry: Dict[str, Any]) -> DentryLink:
    nid = str(entry.get("dentryUuid") or entry.get("nodeUuid") or "").strip()
    name = str(entry.get("name") or "").strip()
    ext = str(entry.get("extension") or "").strip().lower()
    if not ext and "." in name:
        ext = name.rsplit(".", 1)[-1].lower()
    return DentryLink(
        name=name,
        node_id=nid,
        url=f"{BASE_URL}/i/nodes/{nid}",
        kind=_infer_kind(entry),
        extension=ext,
        dentry_type=str(entry.get("dentryType") or ""),
        updated_time=entry.get("updatedTime") or entry.get("contentUpdatedTime"),
    )


async def fetch_children_via_api(
    folder_node_id: str,
    *,
    cookie: str,
    page_size: int = 100,
    max_pages: int = 50,
) -> List[DentryLink]:
    import httpx

    headers = {
        "cookie": cookie,
        "user-agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
        "accept": "application/json, text/plain, */*",
        "referer": f"{BASE_URL}/i/nodes/{folder_node_id}",
        "x-xsrf-token": _xsrf_from_cookie(cookie),
    }
    found: List[DentryLink] = []
    load_more_id: Optional[str] = None

    async with httpx.AsyncClient(verify=False, timeout=60.0) as client:
        for page in range(1, max_pages + 1):
            params: Dict[str, Any] = {
                "dentryUuid": folder_node_id,
                "orderType": "SORT_KEY",
                "sortType": "desc",
                "listDentrySource": "2",
                "pageSize": page_size,
            }
            if load_more_id:
                params["loadMoreId"] = load_more_id

            response = await client.get(LIST_API, headers=headers, params=params)
            if response.status_code in (401, 403):
                raise RuntimeError("钉钉 Cookie 无效或已过期，请更新 DINGTALK_COOKIE")
            response.raise_for_status()
            payload = response.json()
            if not payload.get("isSuccess", True) and payload.get("status") not in (200, None):
                raise RuntimeError(f"目录列表 API 失败: {payload}")

            data = payload.get("data") or {}
            children = data.get("children") or []
            for entry in children:
                if isinstance(entry, dict) and entry.get("dentryUuid"):
                    found.append(_entry_to_link(entry))

            has_more = bool(data.get("hasMore"))
            load_more_id = data.get("loadMoreId")
            if not children or not has_more:
                break

    return found


def _parse_cookie_for_playwright(cookie_str: str) -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    for part in cookie_str.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name, value = part.split("=", 1)
        items.append(
            {
                "name": name.strip(),
                "value": value.strip(),
                "domain": ".dingtalk.com",
                "path": "/",
            }
        )
    return items


async def fetch_children_via_playwright(
    folder_node_id: str,
    *,
    cookie: str,
    headed: bool = False,
    scroll_rounds: int = 20,
) -> List[DentryLink]:
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise RuntimeError(
            "未安装 Playwright。请执行：\n"
            "  cd scripts && python3 -m venv .venv-playwright\n"
            "  .venv-playwright/bin/pip install playwright\n"
            "  .venv-playwright/bin/python -m playwright install chromium"
        ) from exc

    url = f"{BASE_URL}/i/nodes/{folder_node_id}"
    captured: List[Dict[str, Any]] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=not headed)
        context = await browser.new_context(locale="zh-CN")
        await context.add_cookies(_parse_cookie_for_playwright(cookie))
        page = await context.new_page()

        async def on_response(resp) -> None:
            if "/box/api/v2/dentry/list" not in resp.url:
                return
            if resp.status != 200:
                return
            try:
                body = await resp.json()
            except Exception:
                return
            data = body.get("data") or {}
            for entry in data.get("children") or []:
                if isinstance(entry, dict):
                    captured.append(entry)

        page.on("response", on_response)
        await page.goto(url, wait_until="domcontentloaded", timeout=90000)
        await page.wait_for_timeout(5000)
        for _ in range(scroll_rounds):
            await page.mouse.wheel(0, 2500)
            await page.wait_for_timeout(400)
        await page.wait_for_timeout(2000)
        await browser.close()

    dedup: Dict[str, DentryLink] = {}
    for entry in captured:
        link = _entry_to_link(entry)
        if link.node_id:
            dedup[link.node_id] = link
    return list(dedup.values())


def filter_links(
    links: List[DentryLink],
    *,
    only_spreadsheet: bool,
    name_contains: str,
) -> List[DentryLink]:
    out = links
    if only_spreadsheet:
        out = [
            l
            for l in out
            if l.extension in SPREADSHEET_EXT
            or l.name.lower().endswith((".axls", ".xlsx", ".xls", ".able"))
            or "用例" in l.name
        ]
    if name_contains:
        kw = name_contains.strip()
        out = [l for l in out if kw in l.name]
    return out


def write_output(path: Path, links: List[DentryLink], fmt: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "json":
        payload = [asdict(l) for l in links]
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return
    if fmt == "csv":
        lines = ["name,node_id,url,kind,extension"]
        for l in links:
            row = [
                l.name.replace('"', '""'),
                l.node_id,
                l.url,
                l.kind,
                l.extension,
            ]
            lines.append(",".join(f'"{c}"' if "," in c or '"' in c else c for c in row))
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return
    raise ValueError(f"未知输出格式: {fmt}")


def main() -> int:
    cfg = load_json_config()
    ap = argparse.ArgumentParser(description="列举钉钉目录下子文档链接")
    ap.add_argument(
        "--folder-id",
        default=str(cfg.get("folderId") or ""),
        help="已登记目录 id（见 DingTalk/config/folders.json；默认 yaahlan-testcases）",
    )
    ap.add_argument(
        "--folder-url",
        default="",
        help="目录 URL 或 node_id（指定时覆盖 --folder-id）",
    )
    ap.add_argument(
        "--output",
        type=Path,
        default=None,
        help="导出路径（.json 或 .csv）；不指定则打印到 stdout",
    )
    ap.add_argument("--only-spreadsheet", action="store_true", help="仅表格/用例文档")
    ap.add_argument("--name-contains", default="", help="按文件名过滤（子串）")
    ap.add_argument(
        "--playwright",
        action="store_true",
        help="用 Chromium 打开目录页并拦截 list API（较慢，用于对照）",
    )
    ap.add_argument("--headed", action="store_true", help="Playwright 有界面模式")
    ap.add_argument("--page-size", type=int, default=100)
    args = ap.parse_args()

    try:
        folder, folder_entry = resolve_folder_url(
            folder_id=args.folder_id or None,
            folder_url=args.folder_url or None,
            kb_config=cfg,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    folder_id = extract_node_id(folder)
    if folder_entry:
        print(
            f"目录: {folder_entry.get('name')} ({folder_entry.get('id')})",
            file=sys.stderr,
        )
    cookie = resolve_dingtalk_cookie()

    if args.playwright:
        links = asyncio.run(
            fetch_children_via_playwright(
                folder_id,
                cookie=cookie,
                headed=args.headed,
            )
        )
    else:
        links = asyncio.run(
            fetch_children_via_api(
                folder_id,
                cookie=cookie,
                page_size=args.page_size,
            )
        )

    links = filter_links(
        links,
        only_spreadsheet=args.only_spreadsheet,
        name_contains=args.name_contains,
    )
    links.sort(key=lambda l: l.name)

    if args.output:
        fmt = "csv" if args.output.suffix.lower() == ".csv" else "json"
        write_output(args.output.expanduser(), links, fmt)
        print(f"已导出 {len(links)} 条 → {args.output.expanduser()}")
    else:
        for l in links:
            print(f"{l.name}\t{l.url}")

    print(f"\n共 {len(links)} 个文档（目录 node: {folder_id}）", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
