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
FIGMA_ENV_LOCAL = REPO_ROOT / ".cursor" / "figma.env.local"

# 钉钉网关默认启用的 MCP（按优先级）
DEFAULT_SERVER_KEYS = (
    "dingtalk-doc",
    "dingtalk-excel-read",
    "dingtalk-excel-write",
    "dingtalk-notable-read",
    "figma-read",
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


def _resolve_path(raw: str, *, follow_symlinks: bool = True) -> str:
    """仓库内路径转绝对路径。follow_symlinks=False 时保留 venv/bin/python  symlink。"""
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = REPO_ROOT / path
    if follow_symlinks:
        return str(path.resolve())
    return str(path.absolute())


def _resolve_command(cmd: str) -> str:
    resolved = _resolve_path(cmd, follow_symlinks=False)
    if Path(resolved).is_file():
        return resolved
    # 模板里的 venv python 不存在时，尝试同目录 python3 / 系统 python3.13
    parent = Path(resolved).parent
    for name in ("python3", "python3.13", "python"):
        candidate = parent / name
        if candidate.is_file():
            return str(candidate.absolute())
    return resolved


def _read_dotenv(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    out: dict[str, str] = {}
    try:
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("'\"")
            if key and value:
                out[key] = value
    except OSError:
        return {}
    return out


def _apply_figma_env_overrides(env: dict[str, str]) -> None:
    """figma-read：合并 .cursor/figma.env.local 与进程环境变量。"""
    for key, value in _read_dotenv(FIGMA_ENV_LOCAL).items():
        if key in ("FIGMA_ACCESS_TOKEN", "FIGMA_API_KEY") and value.strip():
            env[key] = value.strip()
    for key in ("FIGMA_ACCESS_TOKEN", "FIGMA_API_KEY"):
        from_env = os.environ.get(key, "").strip()
        if from_env:
            env[key] = from_env


def _env_ready(server_key: str, env: dict[str, str]) -> bool:
    if server_key == "dingtalk-doc":
        return bool(env.get("DINGTALK_COOKIE", "").strip())
    if server_key in ("dingtalk-excel-read", "dingtalk-excel-write"):
        return all(
            env.get(k, "").strip()
            for k in ("DINGTALK_AEGIS_KEY", "DINGTALK_AEGIS_SECRET", "DINGTALK_WORKID")
        )
    if server_key == "dingtalk-notable-read":
        has_aegis = all(
            env.get(k, "").strip()
            for k in ("DINGTALK_AEGIS_KEY", "DINGTALK_AEGIS_SECRET", "DINGTALK_WORKID")
        )
        has_cookie = bool(env.get("DINGTALK_COOKIE", "").strip())
        return has_aegis or has_cookie
    if server_key == "figma-read":
        return bool(
            (env.get("FIGMA_ACCESS_TOKEN") or env.get("FIGMA_API_KEY") or "").strip()
        )
    return bool(env)


def _mcp_files_signature() -> tuple[float, float]:
    def mtime(path: Path) -> float:
        try:
            return path.stat().st_mtime if path.is_file() else 0.0
        except OSError:
            return 0.0

    return (mtime(MCP_EXAMPLE), mtime(MCP_SECRETS), mtime(FIGMA_ENV_LOCAL))


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
        if key == "figma-read":
            _apply_figma_env_overrides(env)
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
