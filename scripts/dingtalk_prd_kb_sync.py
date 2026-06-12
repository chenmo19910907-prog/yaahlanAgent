#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
钉钉产品需求文档 → prd-kb 同步。

推荐入口：DingTalk/prd_sync_execute.py

通过 dingtalk-doc MCP 解析 .adoc / .dlink 正文，写入 prd-kb/.raw/ 后整理为业务模块知识库。
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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

from prd_kb_build import build_from_dir  # noqa: E402
from dingtalk_kb_source import (  # noqa: E402
    _ALIDOCS_BASE,
    extract_node_id_from_url,
    list_folder_children_via_box,
    load_json_config,
    parse_version_from_name,
    resolve_dingtalk_cookie,
    resolve_folder_url,
    version_label_from_tuple,
)

_PRD_CONFIG = _ROOT / "DingTalk" / "config" / "prd.json"
_PRD_EXT = frozenset({"adoc", "dlink", "doc"})
_SKIP_SPREADSHEET_EXT = frozenset({"axls", "xlsx", "xls", "able", "sheet"})
_FILENAME_BAD = re.compile(r'[<>:"|?*\\/]+')


@dataclass
class PrdDocument:
    name: str
    url: str
    node_id: str
    extension: str
    version_tuple: Tuple[int, int, int]
    version_label: str


def load_prd_config() -> dict[str, Any]:
    if _PRD_CONFIG.is_file():
        return json.loads(_PRD_CONFIG.read_text(encoding="utf-8"))
    return {}


def _entry_extension(entry: dict[str, Any], name: str) -> str:
    ext = str(entry.get("extension") or "").strip().lower()
    if not ext and "." in name:
        ext = name.rsplit(".", 1)[-1].lower()
    return ext


def is_prd_document(entry: dict[str, Any], *, include_spreadsheets: bool) -> bool:
    name = str(entry.get("name") or "").strip()
    if not name:
        return False
    ext = _entry_extension(entry, name)
    if ext in _PRD_EXT:
        return True
    if not include_spreadsheets and ext in _SKIP_SPREADSHEET_EXT:
        return False
    keywords = ("需求", "方案", "Roadmap", "待排期", "策略", "产运", "整改")
    return any(k in name for k in keywords)


def discover_prd_documents(
    folder_url: str,
    *,
    cookie: str | None = None,
    include_spreadsheets: bool = False,
    max_documents: int = 200,
    skip_patterns: Optional[List[str]] = None,
) -> List[PrdDocument]:
    ck = cookie or resolve_dingtalk_cookie()
    folder_id = extract_node_id_from_url(folder_url)
    entries = list_folder_children_via_box(folder_id, cookie=ck)
    skip_res = [re.compile(p, re.I) for p in (skip_patterns or [])]

    found: Dict[str, PrdDocument] = {}
    for entry in entries:
        if len(found) >= max_documents:
            break
        name = str(entry.get("name") or "").strip()
        nid = str(entry.get("dentryUuid") or "").strip()
        if not name or not nid:
            continue
        if any(p.search(name) for p in skip_res):
            continue
        if not is_prd_document(entry, include_spreadsheets=include_spreadsheets):
            continue
        ext = _entry_extension(entry, name)
        ver = parse_version_from_name(name) or (0, 0, 0)
        vlabel = version_label_from_tuple(ver) if parse_version_from_name(name) else "—"
        found[nid] = PrdDocument(
            name=name,
            url=f"{_ALIDOCS_BASE}/i/nodes/{nid}",
            node_id=nid,
            extension=ext,
            version_tuple=ver,
            version_label=vlabel,
        )
    return sorted(found.values(), key=lambda d: (d.version_tuple, d.name))


def _import_doc_server():
    mcp_dir = _ROOT / ".cursor/skills/dingtalk-doc-read/mcp_dingtalk_doc"
    venv_lib = mcp_dir / "venv" / "lib"
    if venv_lib.is_dir():
        for sp in sorted(venv_lib.glob("python*/site-packages")):
            sp_str = str(sp)
            if sp_str not in sys.path:
                sys.path.insert(0, sp_str)
    mcp_str = str(mcp_dir)
    if mcp_str not in sys.path:
        sys.path.insert(0, mcp_str)
    mod_path = mcp_dir / "server.py"
    spec = importlib.util.spec_from_file_location("dingtalk_doc_prd_kb", mod_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载钉钉文档 MCP: {mod_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _html_to_markdown(html: str) -> str:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    content = soup.select_one(".content") or soup.body or soup
    lines: List[str] = []

    for node in content.children:
        name = getattr(node, "name", None)
        if not name:
            text = str(node).strip()
            if text:
                lines.append(text)
            continue
        if name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            level = int(name[1])
            text = node.get_text(" ", strip=True)
            if text:
                lines.append(f"{'#' * level} {text}")
                lines.append("")
        elif name == "p":
            text = node.get_text(" ", strip=True)
            if text and text != "\xa0":
                lines.append(text)
                lines.append("")
        elif name == "table":
            rows = []
            for tr in node.find_all("tr"):
                cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
                if cells:
                    rows.append(cells)
            if rows:
                header = rows[0]
                lines.append("| " + " | ".join(header) + " |")
                lines.append("| " + " | ".join("---" for _ in header) + " |")
                for row in rows[1:]:
                    while len(row) < len(header):
                        row.append("")
                    lines.append("| " + " | ".join(row[: len(header)]) + " |")
                lines.append("")
        elif name == "div" and "code-block" in (node.get("class") or []):
            code = node.find("code")
            text = code.get_text("\n", strip=False) if code else node.get_text("\n", strip=False)
            if text.strip():
                lines.append("```")
                lines.append(text.strip())
                lines.append("```")
                lines.append("")
        elif name == "div":
            text = node.get_text("\n", strip=True)
            if text:
                lines.append(text)
                lines.append("")

    out = "\n".join(lines)
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    return out


async def fetch_prd_markdown(url: str, *, cookie: str) -> Tuple[str, str]:
    """返回 (标题, markdown 正文)。"""
    mod = _import_doc_server()
    result = await mod.get_complete_document_data(url, cookie, save_files=False)
    title = ""
    if result.mainsite_content:
        title = mod._get_document_title_from_mainsite(result.mainsite_content) or ""
    if not title:
        title = url.rsplit("/", 1)[-1]
    html = result.html or ""
    if not html:
        raise RuntimeError("文档解析结果为空（可能为非正文节点或权限不足）")
    body = _html_to_markdown(html)
    if not body.strip():
        raise RuntimeError("文档正文转换后为空")
    return title.strip(), body


def safe_output_name(doc_name: str) -> str:
    base = doc_name.strip()
    for ext in (".adoc", ".dlink", ".axls", ".able", ".doc"):
        if base.lower().endswith(ext):
            base = base[: -len(ext)]
    base = _FILENAME_BAD.sub("_", base).strip(" .")
    return (base or "untitled") + ".md"


def render_prd_md(
    doc: PrdDocument,
    *,
    title: str,
    body: str,
    synced_at: str,
) -> str:
    display_title = title or doc.name
    lines = [
        f"# {display_title}",
        "",
        f"> **文档类型**：产品需求文档（PRD）",
        f"> **来源**：[{doc.name}]({doc.url})",
    ]
    if doc.version_label != "—":
        lines.append(f"> **版本**：`{doc.version_label}`")
    lines.append(f"> **同步时间**：{synced_at}")
    lines.extend(["", "## 正文", "", body, ""])
    return "\n".join(lines)


def raw_output_dir(output_dir: Path) -> Path:
    return output_dir / ".raw"


def main() -> int:
    prd_cfg = load_prd_config()
    kb_cfg = load_json_config()
    ap = argparse.ArgumentParser(description="钉钉 PRD 目录 → prd-kb 同步")
    ap.add_argument("--folder-id", default=str(prd_cfg.get("folderId") or "yaahlan-prd"))
    ap.add_argument("--folder-url", default="")
    ap.add_argument("--document-url", action="append", default=[])
    ap.add_argument(
        "--output-dir",
        type=Path,
        default=_ROOT / str(prd_cfg.get("outputDir") or "prd-kb"),
    )
    ap.add_argument("--only-version", default="", help="仅同步文件名含该版本号的文档，如 2.5.4")
    ap.add_argument("--list-only", action="store_true")
    ap.add_argument(
        "--build-only",
        action="store_true",
        help="仅从 prd-kb/.raw 整理模块知识库，不拉取钉钉正文",
    )
    ap.add_argument("--max-documents", type=int, default=int(prd_cfg.get("maxDocuments", 200)))
    ap.add_argument(
        "--include-spreadsheets",
        action="store_true",
        default=bool(prd_cfg.get("includeSpreadsheets", False)),
    )
    args = ap.parse_args()

    cookie = resolve_dingtalk_cookie()
    skip_patterns = prd_cfg.get("skipNamePatterns")
    if not isinstance(skip_patterns, list):
        skip_patterns = []

    docs: List[PrdDocument] = []
    folder_url = ""

    if args.document_url:
        folder_url = str(prd_cfg.get("folderUrl") or "")
        try:
            folder_url, _ = resolve_folder_url(
                folder_id=args.folder_id or None,
                folder_url=folder_url or None,
                kb_config=kb_cfg,
            )
        except ValueError:
            pass
        catalog = (
            discover_prd_documents(
                folder_url,
                cookie=cookie,
                include_spreadsheets=args.include_spreadsheets,
                max_documents=args.max_documents,
                skip_patterns=skip_patterns,
            )
            if folder_url
            else []
        )
        by_id = {d.node_id: d for d in catalog}
        for url in args.document_url:
            nid = extract_node_id_from_url(url)
            hit = by_id.get(nid)
            if hit:
                docs.append(hit)
            else:
                docs.append(
                    PrdDocument(
                        name=nid,
                        url=url,
                        node_id=nid,
                        extension="",
                        version_tuple=(0, 0, 0),
                        version_label="—",
                    )
                )
    else:
        folder_url, folder_entry = resolve_folder_url(
            folder_id=args.folder_id or None,
            folder_url=args.folder_url or None,
            kb_config={**kb_cfg, "folderId": args.folder_id, "folderUrl": prd_cfg.get("folderUrl")},
        )
        label = folder_entry.get("name") if folder_entry else folder_url
        print(f"扫描 PRD 目录: {label} ({folder_url})")
        docs = discover_prd_documents(
            folder_url,
            cookie=cookie,
            include_spreadsheets=args.include_spreadsheets,
            max_documents=args.max_documents,
            skip_patterns=skip_patterns,
        )

    if args.only_version:
        t = tuple(int(x) for x in args.only_version.split("."))
        docs = [d for d in docs if d.version_tuple == t]

    if not docs:
        raise SystemExit("未发现可同步的 PRD 文档（目录为空或过滤后无匹配）")

    print(f"将处理 {len(docs)} 个 PRD 文档，输出: {args.output_dir}")
    for d in docs:
        print(f"  - {d.version_label}  {d.name}  {d.url}")

    if args.list_only:
        return 0

    args.output_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = raw_output_dir(args.output_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)

    if args.build_only:
        modules, _ = build_from_dir(raw_dir, args.output_dir, folder_url=folder_url, remove_raw=False)
        print(f"已整理 {len(modules)} 个模块 → {args.output_dir}")
        return 0

    synced_names: List[str] = []
    failed: List[Tuple[str, str]] = []
    synced_at = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S %z")

    for doc in docs:
        print(f"\n=== PRD 开始: {doc.name} ===")
        try:
            title, body = asyncio.run(fetch_prd_markdown(doc.url, cookie=cookie))
            out_name = safe_output_name(doc.name)
            out_path = raw_dir / out_name
            out_path.write_text(
                render_prd_md(doc, title=title, body=body, synced_at=synced_at),
                encoding="utf-8",
            )
            synced_names.append(out_name)
            print(f"    已写入: {out_path.name}")
        except Exception as exc:
            failed.append((doc.name, str(exc)))
            print(f"    失败: {exc}", file=sys.stderr)

    modules, _ = build_from_dir(raw_dir, args.output_dir, folder_url=folder_url, remove_raw=False)
    print(f"\n同步统计: 原始 {len(synced_names)} 篇，失败 {len(failed)}，模块 {len(modules)} 个")
    print(f"知识库: {args.output_dir / 'README.md'}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
