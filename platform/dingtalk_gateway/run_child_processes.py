"""登记并终止与对话 user_key 绑定的 Python 子进程（Web Agent 中断时清理）。"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import signal
import threading
import time
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
        return {"user_key": "", "pids": []}
    if not isinstance(data, dict):
        return {"user_key": "", "pids": []}
    pids = data.get("pids")
    if not isinstance(pids, list):
        pids = []
    return {"user_key": str(data.get("user_key") or ""), "pids": pids}


def _write_registry(path: Path, user_key: str, pids: list[int]) -> None:
    REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "user_key": user_key,
                "pids": sorted(set(int(pid) for pid in pids if int(pid) > 0)),
                "updated_at": time.time(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def register_run_child(user_key: str, pid: int) -> None:
    key = (user_key or "").strip()
    child_pid = int(pid)
    if not key or child_pid <= 0:
        return
    path = _registry_path(key)
    with _REGISTRY_LOCK:
        data = _read_registry(path) if path.is_file() else {"user_key": key, "pids": []}
        pids = [int(item) for item in data.get("pids") or [] if str(item).isdigit()]
        if child_pid not in pids:
            pids.append(child_pid)
        _write_registry(path, key, pids)


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
        pids = [item for item in pids if item != child_pid]
        if pids:
            _write_registry(path, key, pids)
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
    """终止进程及其进程组（worker 子进程树）。"""
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


def kill_run_child_processes(user_key: str, *, wait_s: float = 1.0) -> int:
    """终止 user_key 下登记的子进程，返回成功发送 SIGTERM 的数量。"""
    key = (user_key or "").strip()
    if not key:
        return 0
    pids = list_run_child_pids(key)
    killed = 0
    for pid in pids:
        if not is_pid_alive(pid):
            continue
        _signal_pid(pid, signal.SIGTERM)
        killed += 1
    if killed:
        deadline = time.monotonic() + max(0.1, wait_s)
        while time.monotonic() < deadline:
            if not any(is_pid_alive(pid) for pid in pids):
                break
            time.sleep(0.05)
        for pid in pids:
            if is_pid_alive(pid):
                _signal_pid(pid, signal.SIGKILL)
        logger.info("已终止 user_key=%s 的登记子进程 %s 个", key, killed)
    with _REGISTRY_LOCK:
        try:
            _registry_path(key).unlink(missing_ok=True)
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
