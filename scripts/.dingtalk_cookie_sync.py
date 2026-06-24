#!/usr/bin/env python3
"""同步钉钉文档 Cookie：~/.dingtalk_doc_cookie ↔ .cursor/.mcp.secrets.json。"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from mcp_paths import (
    DINGTALK_COOKIE_FILE,
    MCP_LOCAL,
    MCP_SECRETS,
    merge_mcp_local,
)
from credential_probe import probe_dingtalk_doc_cookie, validate_dingtalk_doc_cookie_format

MCP_SERVER_KEYS = ("dingtalk-doc", "user-dingtalk-doc")
_DEFAULT_PROBE_NODE = "jb9Y4gmKWr7wodldCZEEZ3n1VGXn6lpz"


@dataclass
class CookieSource:
    name: str
    path: Path
    cookie: str
    mtime: float

    @property
    def mtime_label(self) -> str:
        if self.mtime <= 0:
            return "—"
        return datetime.fromtimestamp(self.mtime).strftime("%Y-%m-%d %H:%M:%S")


def _normalize_cookie(cookie: str) -> str:
    return " ".join((cookie or "").split())


def _cookie_preview(cookie: str) -> str:
    text = _normalize_cookie(cookie)
    if not text:
        return "(空)"
    keys = []
    for key in ("doc_atoken", "XSRF-TOKEN", "account"):
        m = re.search(rf"{re.escape(key)}=([^;]+)", text)
        if m:
            val = m.group(1)
            keys.append(f"{key}={val[:8]}…" if len(val) > 8 else f"{key}={val}")
    summary = ", ".join(keys) if keys else "无 doc_atoken/XSRF-TOKEN"
    return f"len={len(text)}, {summary}"


def _read_cookie_file() -> Optional[CookieSource]:
    if not DINGTALK_COOKIE_FILE.is_file():
        return None
    try:
        cookie = DINGTALK_COOKIE_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not cookie:
        return None
    return CookieSource(
        name="cookie 文件",
        path=DINGTALK_COOKIE_FILE,
        cookie=cookie,
        mtime=DINGTALK_COOKIE_FILE.stat().st_mtime,
    )


def _read_secrets_cookie(path: Path) -> Optional[CookieSource]:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    servers = data.get("mcpServers") or {}
    cookie = ""
    for key in MCP_SERVER_KEYS:
        env = (servers.get(key) or {}).get("env") or {}
        value = str(env.get("DINGTALK_COOKIE") or "").strip()
        if value:
            cookie = value
            break
    if not cookie:
        return None
    return CookieSource(
        name=f"secrets ({path.name})",
        path=path,
        cookie=cookie,
        mtime=path.stat().st_mtime,
    )


def _collect_sources() -> List[CookieSource]:
    sources: List[CookieSource] = []
    file_src = _read_cookie_file()
    if file_src:
        sources.append(file_src)
    for path in (MCP_SECRETS, MCP_LOCAL):
        secret_src = _read_secrets_cookie(path)
        if secret_src:
            sources.append(secret_src)
    return sources


def _cookies_equal(a: str, b: str) -> bool:
    return _normalize_cookie(a) == _normalize_cookie(b)


def _pick_cookie(sources: List[CookieSource], *, prefer: str) -> CookieSource:
    if prefer == "file":
        for src in sources:
            if src.path == DINGTALK_COOKIE_FILE:
                return src
        raise RuntimeError(f"未找到 {DINGTALK_COOKIE_FILE}，请先 refresh_cookie 或 --set 写入 Cookie")
    if prefer == "mcp":
        secret_sources = [s for s in sources if s.path != DINGTALK_COOKIE_FILE]
        if not secret_sources:
            raise RuntimeError(f"未在 {MCP_SECRETS} 中找到 DINGTALK_COOKIE")
        return max(secret_sources, key=lambda s: s.mtime)
    return max(sources, key=lambda s: s.mtime)


def _write_cookie_file(cookie: str, *, dry_run: bool) -> None:
    text = _normalize_cookie(cookie)
    if dry_run:
        print(f"[dry-run] 写入 {DINGTALK_COOKIE_FILE}")
        return
    DINGTALK_COOKIE_FILE.write_text(text, encoding="utf-8")
    print(f"✅ 已写入 {DINGTALK_COOKIE_FILE}")


def _write_secrets_cookie(cookie: str, *, dry_run: bool) -> None:
    text = _normalize_cookie(cookie)
    if MCP_SECRETS.is_file():
        try:
            data = json.loads(MCP_SECRETS.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"{MCP_SECRETS} JSON 解析失败: {exc}") from exc
    else:
        data = {"mcpServers": {}}

    servers = data.setdefault("mcpServers", {})
    updated = False
    for key in MCP_SERVER_KEYS:
        srv = servers.setdefault(key, {})
        if not isinstance(srv, dict):
            continue
        env = srv.setdefault("env", {})
        if not isinstance(env, dict):
            continue
        old = str(env.get("DINGTALK_COOKIE") or "").strip()
        if _cookies_equal(old, text):
            continue
        env["DINGTALK_COOKIE"] = text
        updated = True

    if not updated and MCP_SECRETS.is_file():
        print(f"ℹ️  {MCP_SECRETS} 中 DINGTALK_COOKIE 已是最新，跳过")
        if not dry_run:
            merge_mcp_local()
        return

    if dry_run:
        print(f"[dry-run] 更新 {MCP_SECRETS} → DINGTALK_COOKIE")
        print(f"[dry-run] 合并生成 {MCP_LOCAL}")
        return

    MCP_SECRETS.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"✅ 已更新 {MCP_SECRETS}")
    merge_mcp_local()
    print(f"✅ 已合并生成 {MCP_LOCAL}")


def _sync_to_all(cookie: str, *, dry_run: bool) -> None:
    _write_cookie_file(cookie, dry_run=dry_run)
    _write_secrets_cookie(cookie, dry_run=dry_run)


def _validate_format(cookie: str) -> List[str]:
    return validate_dingtalk_doc_cookie_format(cookie)


def _probe_cookie(cookie: str, *, node_id: str) -> tuple[bool, str]:
    return probe_dingtalk_doc_cookie(cookie, node_id=node_id)


def _print_status(sources: List[CookieSource]) -> int:
    if not sources:
        print("❌ 未找到任何 Cookie 来源")
        print(f"   - 文件: {DINGTALK_COOKIE_FILE}")
        print(f"   - secrets: {MCP_SECRETS}")
        print(f"   - merged: {MCP_LOCAL}")
        print("用法: python3 DingTalk/.cookie_sync_execute.py --set '<Cookie>'")
        return 1

    print("=== 钉钉文档 Cookie 状态 ===")
    for src in sources:
        print(f"- {src.name}")
        print(f"  路径: {src.path}")
        print(f"  更新: {src.mtime_label}")
        print(f"  摘要: {_cookie_preview(src.cookie)}")

    unique = {_normalize_cookie(s.cookie) for s in sources}
    if len(unique) == 1:
        print("\n✅ 各来源 Cookie 一致")
        return 0

    print("\n⚠️  各来源 Cookie 不一致，建议执行:")
    print("   python3 DingTalk/.cookie_sync_execute.py")
    return 2


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="同步钉钉文档 Cookie（~/.dingtalk_doc_cookie ↔ .cursor/.mcp.secrets.json）",
    )
    parser.add_argument("--status", action="store_true", help="仅查看各来源 Cookie 是否一致")
    parser.add_argument("--from-file", action="store_true", help="以 ~/.dingtalk_doc_cookie 为准写入 secrets")
    parser.add_argument("--from-mcp", action="store_true", help="以 .mcp.secrets.json 为准写入 cookie 文件")
    parser.add_argument("--set", metavar="COOKIE", help="写入新 Cookie 到全部目标")
    parser.add_argument("--stdin", action="store_true", help="从标准输入读取 Cookie 并写入全部目标")
    parser.add_argument("--check", action="store_true", help="同步后调用 Box API 探测 Cookie 是否有效")
    parser.add_argument("--probe-node", default=_DEFAULT_PROBE_NODE, help="--check 时使用的目录 node_id")
    parser.add_argument("--dry-run", action="store_true", help="只打印将执行的操作，不写文件")
    parser.add_argument("--merge-mcp", action="store_true", help="仅根据 secrets 重新生成 mcp.json")
    args = parser.parse_args(argv)

    if args.merge_mcp:
        merge_mcp_local(dry_run=args.dry_run)
        if not args.dry_run:
            print(f"✅ 已合并生成 {MCP_LOCAL}")
        return 0

    if args.stdin:
        cookie_in = sys.stdin.read().strip()
        if not cookie_in:
            print("❌ 标准输入为空", file=sys.stderr)
            return 1
        issues = _validate_format(cookie_in)
        for issue in issues:
            print(f"⚠️  {issue}")
        _sync_to_all(cookie_in, dry_run=args.dry_run)
        if args.check and not args.dry_run:
            ok, msg = _probe_cookie(cookie_in, node_id=args.probe_node)
            print(f"{'✅' if ok else '❌'} 在线探测: {msg}")
            return 0 if ok else 3
        return 0

    if args.set:
        issues = _validate_format(args.set)
        for issue in issues:
            print(f"⚠️  {issue}")
        _sync_to_all(args.set, dry_run=args.dry_run)
        if args.check and not args.dry_run:
            ok, msg = _probe_cookie(args.set, node_id=args.probe_node)
            print(f"{'✅' if ok else '❌'} 在线探测: {msg}")
            return 0 if ok else 3
        return 0

    sources = _collect_sources()
    if args.status:
        return _print_status(sources)

    if not sources:
        print(
            "❌ 未找到 Cookie。请先 refresh_cookie、配置 .mcp.secrets.json，或 --set / --stdin",
            file=sys.stderr,
        )
        return 1

    if args.from_file and args.from_mcp:
        print("❌ --from-file 与 --from-mcp 不能同时使用", file=sys.stderr)
        return 1

    prefer = "file" if args.from_file else ("mcp" if args.from_mcp else "newest")

    try:
        chosen = _pick_cookie(sources, prefer=prefer)
    except RuntimeError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 1

    all_same = all(_cookies_equal(chosen.cookie, s.cookie) for s in sources)
    if all_same:
        print("✅ Cookie 已同步，无需更新")
        print(f"   来源: {chosen.name}")
        print(f"   摘要: {_cookie_preview(chosen.cookie)}")
        if args.check:
            ok, msg = _probe_cookie(chosen.cookie, node_id=args.probe_node)
            print(f"{'✅' if ok else '❌'} 在线探测: {msg}")
            return 0 if ok else 3
        return 0

    print(f"🔄 以「{chosen.name}」为准同步（{chosen.mtime_label}）")
    print(f"   摘要: {_cookie_preview(chosen.cookie)}")
    issues = _validate_format(chosen.cookie)
    for issue in issues:
        print(f"⚠️  {issue}")

    _sync_to_all(chosen.cookie, dry_run=args.dry_run)
    if not args.dry_run:
        print("💡 若 Cursor MCP 仍用旧 Cookie，请 Reload Window（Cmd+Shift+P → Developer: Reload Window）")

    if args.check and not args.dry_run:
        ok, msg = _probe_cookie(chosen.cookie, node_id=args.probe_node)
        print(f"{'✅' if ok else '❌'} 在线探测: {msg}")
        return 0 if ok else 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
