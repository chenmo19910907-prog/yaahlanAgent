#!/usr/bin/env python3
"""MCP 本地路径与鉴权读取（Cookie/Token 存于 . 开头文件，不入库）。"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
MCP_EXAMPLE = ROOT / ".cursor" / "mcp.example.json"
MCP_LOCAL = ROOT / ".cursor" / "mcp.json"
MCP_SECRETS = ROOT / ".cursor" / ".mcp.secrets.json"
DINGTALK_COOKIE_FILE = Path.home() / ".dingtalk_doc_cookie"

_MCP_READ_PATHS = (
    MCP_SECRETS,
    MCP_LOCAL,
    ROOT / ".cursor" / "mcp.json",
    Path.home() / ".cursor" / "mcp.json",
)


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def load_mcp_env(server_key: str) -> dict[str, str]:
    """从 .mcp.secrets.json / mcp.json 读取某 MCP 服务器的 env。"""
    for path in _MCP_READ_PATHS:
        data = _read_json(path)
        if not data:
            continue
        srv = (data.get("mcpServers") or {}).get(server_key) or {}
        env = srv.get("env") or {}
        if isinstance(env, dict) and env:
            return {str(k): str(v) for k, v in env.items() if str(v).strip()}
    return {}


def _abs_repo_path(raw: str, *, follow_symlinks: bool = True) -> str:
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    if follow_symlinks:
        return str(path.resolve())
    return str(path.absolute())


def _resolve_mcp_command(cmd: str) -> str:
    resolved = _abs_repo_path(cmd, follow_symlinks=False)
    if Path(resolved).is_file():
        return resolved
    parent = Path(resolved).parent
    for name in ("python3", "python3.13", "python"):
        candidate = parent / name
        if candidate.is_file():
            return str(candidate.absolute())
    return resolved


def merge_mcp_local(*, dry_run: bool = False) -> bool:
    """用 mcp.example.json + .mcp.secrets.json 生成本地 .cursor/mcp.json（供 Cursor 读取）。"""
    base = _read_json(MCP_EXAMPLE)
    if not base:
        raise RuntimeError(f"缺少模板 {MCP_EXAMPLE}")

    existing = _read_json(MCP_LOCAL) or {}
    merged = json.loads(json.dumps(base))
    servers = merged.setdefault("mcpServers", {})
    # 保留模板外已登记服务（如 adb-screen），避免 merge 覆盖
    for name, srv in (existing.get("mcpServers") or {}).items():
        if name not in servers and isinstance(srv, dict):
            servers[name] = json.loads(json.dumps(srv))

    secrets = _read_json(MCP_SECRETS) or {}
    secret_servers = secrets.get("mcpServers") or {}

    for name, secret_srv in secret_servers.items():
        if not isinstance(secret_srv, dict):
            continue
        secret_env = secret_srv.get("env") or {}
        if not isinstance(secret_env, dict) or not secret_env:
            continue
        srv = servers.setdefault(name, {})
        if not isinstance(srv, dict):
            continue
        env = srv.setdefault("env", {})
        if not isinstance(env, dict):
            env = {}
            srv["env"] = env
        for key, value in secret_env.items():
            if str(value).strip():
                env[key] = value

    for name, srv in servers.items():
        if not isinstance(srv, dict):
            continue
        command = str(srv.get("command") or "").strip()
        if command:
            srv["command"] = _resolve_mcp_command(command)
        args = srv.get("args") or []
        if isinstance(args, list):
            srv["args"] = [
                _abs_repo_path(str(arg)) if str(arg).strip() else str(arg)
                for arg in args
            ]

    if dry_run:
        print(f"[dry-run] 将写入 {MCP_LOCAL}")
        return True

    MCP_LOCAL.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return True


def resolve_dingtalk_cookie() -> str:
    cookie = os.environ.get("DINGTALK_COOKIE", "").strip()
    if cookie:
        return cookie
    for key in ("dingtalk-doc", "user-dingtalk-doc"):
        cookie = load_mcp_env(key).get("DINGTALK_COOKIE", "").strip()
        if cookie:
            return cookie
    if DINGTALK_COOKIE_FILE.is_file():
        return DINGTALK_COOKIE_FILE.read_text(encoding="utf-8").strip()
    raise RuntimeError(
        "缺少 DINGTALK_COOKIE：请写入 .cursor/.mcp.secrets.json、"
        "~/.dingtalk_doc_cookie，或运行 python3 DingTalk/.cookie_sync_execute.py"
    )
