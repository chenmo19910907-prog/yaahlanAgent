"""登记并终止与对话 user_key 绑定的子进程与 Shell 命令（Web Agent 中断时清理）。"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import signal
import subprocess
import threading
import time
from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from env_loader import GATEWAY_DIR

logger = logging.getLogger("dingtalk-gateway")

REGISTRY_DIR = GATEWAY_DIR / "data" / "run_child_processes"
_REGISTRY_LOCK = threading.Lock()


def _safe_filename(user_key: str) -> str:
    digest = hashlib.sha256(user_key.encode("utf-8")).hexdigest()[:24]
    return f"{digest}.json"


def _registry_path(user_key: str) -> Path:
    return REGISTRY_DIR / _safe_filename(user_key)


def _read_registry(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"user_key": "", "pids": [], "commands": []}
    if not isinstance(data, dict):
        return {"user_key": "", "pids": [], "commands": []}
    pids = data.get("pids")
    if not isinstance(pids, list):
        pids = []
    commands = data.get("commands")
    if not isinstance(commands, list):
        commands = []
    return {
        "user_key": str(data.get("user_key") or ""),
        "pids": pids,
        "commands": commands,
    }


def _write_registry(path: Path, user_key: str, pids: list[int], commands: list[str]) -> None:
    REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "user_key": user_key,
                "pids": sorted(set(int(pid) for pid in pids if int(pid) > 0)),
                "commands": sorted(set(str(item).strip() for item in commands if str(item).strip())),
                "updated_at": time.time(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _list_child_pids(parent_pid: int) -> list[int]:
    if parent_pid <= 0:
        return []
    try:
        proc = subprocess.run(
            ["pgrep", "-P", str(parent_pid)],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return []
    if proc.returncode != 0:
        return []
    pids: list[int] = []
    for token in proc.stdout.strip().split():
        if token.isdigit():
            pids.append(int(token))
    return pids


def collect_process_tree_pids(root_pid: int) -> list[int]:
    """收集 root 及其全部后代 PID（含 root）。"""
    root = int(root_pid)
    if root <= 0:
        return []
    seen: set[int] = {root}
    queue = [root]
    while queue:
        parent = queue.pop()
        for child in _list_child_pids(parent):
            if child not in seen:
                seen.add(child)
                queue.append(child)
    return sorted(seen)


def register_run_child(user_key: str, pid: int) -> None:
    key = (user_key or "").strip()
    child_pid = int(pid)
    if not key or child_pid <= 0:
        return
    path = _registry_path(key)
    with _REGISTRY_LOCK:
        data = _read_registry(path) if path.is_file() else {"user_key": key, "pids": [], "commands": []}
        pids = [int(item) for item in data.get("pids") or [] if str(item).isdigit()]
        commands = [str(item).strip() for item in data.get("commands") or [] if str(item).strip()]
        if child_pid not in pids:
            pids.append(child_pid)
        _write_registry(path, key, pids, commands)


def register_run_command(user_key: str, command: str) -> None:
    """登记 Agent Shell 命令片段，中断时用 pgrep -f 清理孤儿终端脚本。"""
    key = (user_key or "").strip()
    fragment = _command_pattern_fragment(command)
    if not key or not fragment:
        return
    path = _registry_path(key)
    with _REGISTRY_LOCK:
        data = _read_registry(path) if path.is_file() else {"user_key": key, "pids": [], "commands": []}
        pids = [int(item) for item in data.get("pids") or [] if str(item).isdigit()]
        commands = [str(item).strip() for item in data.get("commands") or [] if str(item).strip()]
        if fragment not in commands:
            commands.append(fragment)
        _write_registry(path, key, pids, commands)


def unregister_run_child(user_key: str, pid: int) -> None:
    key = (user_key or "").strip()
    child_pid = int(pid)
    if not key or child_pid <= 0:
        return
    path = _registry_path(key)
    with _REGISTRY_LOCK:
        if not path.is_file():
            return
        data = _read_registry(path)
        pids = [int(item) for item in data.get("pids") or [] if str(item).isdigit()]
        commands = [str(item).strip() for item in data.get("commands") or [] if str(item).strip()]
        pids = [item for item in pids if item != child_pid]
        if pids or commands:
            _write_registry(path, key, pids, commands)
        else:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass


def list_run_child_pids(user_key: str) -> list[int]:
    key = (user_key or "").strip()
    if not key:
        return []
    path = _registry_path(key)
    if not path.is_file():
        return []
    with _REGISTRY_LOCK:
        data = _read_registry(path)
    return [int(item) for item in data.get("pids") or [] if str(item).isdigit()]


def list_run_commands(user_key: str) -> list[str]:
    key = (user_key or "").strip()
    if not key:
        return []
    path = _registry_path(key)
    if not path.is_file():
        return []
    with _REGISTRY_LOCK:
        data = _read_registry(path)
    return [str(item).strip() for item in data.get("commands") or [] if str(item).strip()]


def is_pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _signal_pid(pid: int, sig: signal.Signals) -> None:
    if pid <= 0:
        return
    try:
        os.kill(pid, sig)
    except OSError as exc:
        logger.debug("signal pid=%s sig=%s 失败: %s", pid, sig.name, exc)


def terminate_process_tree(pid: int, *, wait_s: float = 3.0) -> None:
    """终止进程及其进程组（worker / Shell 子进程树）。"""
    root = int(pid)
    if root <= 0:
        return
    try:
        pgid = os.getpgid(root)
        os.killpg(pgid, signal.SIGTERM)
    except OSError:
        _signal_pid(root, signal.SIGTERM)
    deadline = time.monotonic() + max(0.1, wait_s)
    while time.monotonic() < deadline:
        if not is_pid_alive(root):
            return
        time.sleep(0.1)
    try:
        pgid = os.getpgid(root)
        os.killpg(pgid, signal.SIGKILL)
    except OSError:
        _signal_pid(root, signal.SIGKILL)


def _command_pattern_fragment(command: str) -> str:
    cmd = " ".join((command or "").split())
    if len(cmd) < 8:
        return ""
    for token in cmd.split():
        if token.endswith(".py") and ("/" in token or token.endswith("_execute.py")):
            return token
    return cmd if len(cmd) <= 120 else cmd[:120]


def _extract_shell_command(tool_call: Any) -> str:
    if not isinstance(tool_call, Mapping):
        return ""
    name = str(tool_call.get("name") or tool_call.get("toolName") or tool_call.get("tool") or "")
    if name.lower() != "shell":
        return ""
    args = tool_call.get("args") or tool_call.get("arguments") or {}
    if isinstance(args, str):
        text = args.strip()
        if text.startswith("{"):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                return text
            else:
                args = parsed if isinstance(parsed, Mapping) else {}
        else:
            return text
    if not isinstance(args, Mapping):
        return ""
    for key in ("command", "cmd", "script"):
        value = args.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def register_shell_tool_update(user_key: str, update: Any) -> None:
    """从 Agent 流式 tool-call 事件登记 Shell 命令。"""
    key = (user_key or "").strip()
    if not key or update is None:
        return
    if isinstance(update, Mapping):
        utype = str(update.get("type") or "")
        tool_call = update.get("toolCall") or update.get("tool_call")
    else:
        utype = str(getattr(update, "type", "") or "")
        tool_call = getattr(update, "tool_call", None)
    if utype not in ("tool-call-started", "tool-call-completed", "partial-tool-call"):
        return
    command = _extract_shell_command(tool_call)
    if command:
        register_run_command(key, command)


def _pids_matching_command(pattern: str) -> list[int]:
    fragment = (pattern or "").strip()
    if len(fragment) < 8:
        return []
    try:
        proc = subprocess.run(
            ["pgrep", "-f", fragment],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return []
    if proc.returncode != 0:
        return []
    pids: list[int] = []
    for token in proc.stdout.strip().split():
        if token.isdigit():
            pids.append(int(token))
    return pids


def kill_run_child_processes(
    user_key: str,
    *,
    extra_root_pids: Sequence[int] | None = None,
    wait_s: float = 2.0,
) -> int:
    """终止 user_key 下登记的子进程树与 Shell 命令匹配进程，返回终止的根进程数。"""
    key = (user_key or "").strip()
    if not key:
        return 0

    with _REGISTRY_LOCK:
        path = _registry_path(key)
        data = _read_registry(path) if path.is_file() else {"user_key": key, "pids": [], "commands": []}
        registered_pids = [int(item) for item in data.get("pids") or [] if str(item).isdigit()]
        commands = [str(item).strip() for item in data.get("commands") or [] if str(item).strip()]

    roots: set[int] = set(registered_pids)
    for pid in extra_root_pids or []:
        root = int(pid)
        if root > 0:
            roots.add(root)
    for pattern in commands:
        roots.update(_pids_matching_command(pattern))

    killed = 0
    for root in sorted(roots):
        if not is_pid_alive(root):
            continue
        terminate_process_tree(root, wait_s=max(0.3, wait_s / max(1, len(roots))))
        killed += 1

    if killed:
        logger.info(
            "已终止 user_key=%s 的相关进程 %s 个（登记 pid=%s，命令=%s）",
            key,
            killed,
            len(registered_pids),
            len(commands),
        )

    with _REGISTRY_LOCK:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
    return killed


@contextmanager
def run_child_guard(user_key: str | None) -> Iterator[None]:
    key = (user_key or "").strip()
    pid = os.getpid()
    if key:
        register_run_child(key, pid)
    try:
        yield
    finally:
        if key:
            unregister_run_child(key, pid)
