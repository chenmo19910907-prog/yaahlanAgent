"""从仓库 MCP 配置构建 Cursor SDK inline MCP servers。"""

from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path
from typing import Any

from cursor_sdk import StdioMcpServerConfig

GATEWAY_DIR = Path(__file__).resolve().parent
REPO_ROOT = GATEWAY_DIR.parent.parent
MCP_EXAMPLE = REPO_ROOT / ".cursor" / "mcp.example.json"
MCP_SECRETS = REPO_ROOT / ".cursor" / ".mcp.secrets.json"

# 钉钉网关默认启用的 MCP（按优先级）
DEFAULT_SERVER_KEYS = (
    "dingtalk-doc",
    "dingtalk-excel-read",
    "dingtalk-excel-write",
)

_cache_lock = threading.Lock()
_cached_servers: dict[str, StdioMcpServerConfig] | None = None
_cache_signature: tuple[float, float] | None = None


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _merge_mcp_servers() -> dict[str, dict[str, Any]]:
    merged = json.loads(json.dumps(_read_json(MCP_EXAMPLE).get("mcpServers", {})))
    secrets = _read_json(MCP_SECRETS).get("mcpServers", {})
    for name, secret_srv in secrets.items():
        if not isinstance(secret_srv, dict):
            continue
        secret_env = secret_srv.get("env") or {}
        if not isinstance(secret_env, dict):
            continue
        srv = merged.setdefault(name, {})
        if not isinstance(srv, dict):
            continue
        env = srv.setdefault("env", {})
        if not isinstance(env, dict):
            env = {}
            srv["env"] = env
        for key, value in secret_env.items():
            if str(value).strip():
                env[key] = value
    return {k: v for k, v in merged.items() if isinstance(v, dict)}


def _resolve_path(raw: str) -> str:
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = (REPO_ROOT / path).resolve()
    return str(path)


def _resolve_command(cmd: str) -> str:
    resolved = _resolve_path(cmd)
    if Path(resolved).is_file():
        return resolved
    # 模板里的 venv python 不存在时，尝试同目录 python3 / 系统 python3.13
    parent = Path(resolved).parent
    for name in ("python3.13", "python3", "python"):
        candidate = parent / name
        if candidate.is_file():
            return str(candidate)
    return resolved


def _env_ready(server_key: str, env: dict[str, str]) -> bool:
    if server_key == "dingtalk-doc":
        return bool(env.get("DINGTALK_COOKIE", "").strip())
    if server_key in ("dingtalk-excel-read", "dingtalk-excel-write"):
        return all(
            env.get(k, "").strip()
            for k in ("DINGTALK_AEGIS_KEY", "DINGTALK_AEGIS_SECRET", "DINGTALK_WORKID")
        )
    return bool(env)


def _mcp_files_signature() -> tuple[float, float]:
    def mtime(path: Path) -> float:
        try:
            return path.stat().st_mtime if path.is_file() else 0.0
        except OSError:
            return 0.0

    return (mtime(MCP_EXAMPLE), mtime(MCP_SECRETS))


def _build_stdio_mcp_servers_uncached(
    server_keys: tuple[str, ...],
) -> dict[str, StdioMcpServerConfig]:
    all_servers = _merge_mcp_servers()
    result: dict[str, StdioMcpServerConfig] = {}
    for key in server_keys:
        srv = all_servers.get(key)
        if not srv:
            continue
        command = str(srv.get("command") or "").strip()
        if not command:
            continue
        env = {str(k): str(v) for k, v in (srv.get("env") or {}).items() if str(v).strip()}
        if not _env_ready(key, env):
            continue
        args = [str(a) for a in (srv.get("args") or [])]
        resolved_args = [_resolve_path(a) for a in args]
        result[key] = StdioMcpServerConfig(
            command=_resolve_command(command),
            args=resolved_args,
            env=env,
            cwd=str(REPO_ROOT),
        )
    return result


def build_stdio_mcp_servers(
  server_keys: tuple[str, ...] = DEFAULT_SERVER_KEYS,
) -> dict[str, StdioMcpServerConfig]:
    """构建 SDK 可用的 stdio MCP 配置；凭证缺失的服务器会跳过。"""
    global _cached_servers, _cache_signature
    signature = _mcp_files_signature()
    with _cache_lock:
        if _cached_servers is not None and _cache_signature == signature:
            return _cached_servers
    built = _build_stdio_mcp_servers_uncached(server_keys)
    with _cache_lock:
        _cached_servers = built
        _cache_signature = signature
    return built


def inject_scripts_path() -> None:
    scripts = REPO_ROOT / "scripts"
    if scripts.is_dir() and str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
