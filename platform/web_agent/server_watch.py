#!/usr/bin/env python3
"""Web Agent 源码监视：变更后自动重启 HTTP 服务（开发默认启用）。"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Iterator

WEB_AGENT_DIR = Path(__file__).resolve().parent
PLATFORM_DIR = WEB_AGENT_DIR.parent
REPO_ROOT = PLATFORM_DIR.parent
GATEWAY_DIR = PLATFORM_DIR / "dingtalk_gateway"
PID_FILE = WEB_AGENT_DIR / "data" / "server_watch.pid"

WATCH_SUFFIXES = {".py", ".html", ".js", ".json"}
IGNORE_DIR_NAMES = {
    "data",
    "__pycache__",
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "bookmarks_backups",
    "messages",
    "exports",
}
IGNORE_FILE_PREFIXES = ("verify_",)
RESTART_COOLDOWN_S = 10.0
POST_RESTART_SETTLE_S = 2.0

logger = logging.getLogger("web-agent-watch")


def _python_can_import_cursor_sdk(python: Path) -> bool:
    try:
        proc = subprocess.run(
            [str(python), "-c", "import cursor_sdk"],
            capture_output=True,
            timeout=5,
            check=False,
        )
        return proc.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _resolve_python_executable() -> str:
    candidates = (
        GATEWAY_DIR / ".venv" / "bin" / "python3",
        REPO_ROOT / ".venv" / "bin" / "python3",
    )
    fallback: str | None = None
    for path in candidates:
        if not path.is_file() or not os.access(path, os.X_OK):
            continue
        resolved = str(path)
        if _python_can_import_cursor_sdk(path):
            return resolved
        fallback = fallback or resolved
    return fallback or sys.executable


PYTHON_EXECUTABLE = _resolve_python_executable()


def _iter_watch_files() -> Iterator[Path]:
    if WEB_AGENT_DIR.is_dir():
        for path in WEB_AGENT_DIR.rglob("*"):
            if not path.is_file():
                continue
            if any(part in IGNORE_DIR_NAMES for part in path.relative_to(WEB_AGENT_DIR).parts[:-1]):
                continue
            if path.suffix not in WATCH_SUFFIXES:
                continue
            if path.name.startswith(IGNORE_FILE_PREFIXES):
                continue
            if path.name in {"server.log", "server_watch.log", "restart.log"}:
                continue
            yield path


def snapshot_mtimes() -> dict[str, float]:
    out: dict[str, float] = {}
    for path in _iter_watch_files():
        try:
            out[str(path)] = path.stat().st_mtime
        except OSError:
            continue
    return out


def write_pid_file() -> None:
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()), encoding="utf-8")


def remove_pid_file() -> None:
    try:
        PID_FILE.unlink(missing_ok=True)
    except OSError:
        pass


def read_watch_pid() -> int | None:
    if not PID_FILE.is_file():
        return None
    try:
        return int(PID_FILE.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def is_process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def is_watch_running() -> bool:
    pid = read_watch_pid()
    return pid is not None and is_process_alive(pid)


def kill_all_watch_processes() -> None:
    pid = read_watch_pid()
    if pid is not None and is_process_alive(pid):
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
        time.sleep(0.3)
    remove_pid_file()
    try:
        proc = subprocess.run(
            ["pgrep", "-f", str(WEB_AGENT_DIR / "server_watch.py")],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        proc = None
    if proc is not None:
        for line in (proc.stdout or "").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                os.kill(int(line), signal.SIGTERM)
            except (OSError, ValueError):
                continue
    time.sleep(0.2)
    try:
        proc = subprocess.run(
            ["pgrep", "-f", str(WEB_AGENT_DIR / "server.py")],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return
    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            os.kill(int(line), signal.SIGTERM)
        except (OSError, ValueError):
            continue
    time.sleep(0.2)


def kill_process_on_port(port: int) -> None:
    try:
        proc = subprocess.run(
            ["lsof", "-ti", f":{port}"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return
    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            os.kill(int(line), signal.SIGTERM)
        except (OSError, ValueError):
            continue
    time.sleep(0.3)


def spawn_server(*, host: str, port: int) -> subprocess.Popen[bytes]:
    kill_process_on_port(port)
    log_path = WEB_AGENT_DIR / "data" / "server.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_fp = open(log_path, "a", encoding="utf-8")
    child = subprocess.Popen(
        [
            PYTHON_EXECUTABLE,
            str(WEB_AGENT_DIR / "server.py"),
            "--serve",
            "--no-watch",
            "--host",
            host,
            "--port",
            str(port),
        ],
        cwd=str(REPO_ROOT),
        stdout=log_fp,
        stderr=subprocess.STDOUT,
    )
    logger.info("Web Agent 子进程已启动 pid=%s", child.pid)
    return child


def stop_child(child: subprocess.Popen[bytes], *, wait_s: float = 8.0) -> None:
    if child.poll() is not None:
        return
    child.send_signal(signal.SIGTERM)
    deadline = time.monotonic() + wait_s
    while time.monotonic() < deadline:
        if child.poll() is not None:
            return
        time.sleep(0.1)
    child.kill()
    try:
        child.wait(timeout=3.0)
    except subprocess.TimeoutExpired:
        pass


def run_watch(
    *,
    host: str,
    port: int,
    poll_s: float = 1.0,
    debounce_s: float = 0.8,
) -> None:
    write_pid_file()
    child = spawn_server(host=host, port=port)
    time.sleep(POST_RESTART_SETTLE_S)
    mtimes = snapshot_mtimes()
    pending_change_at = 0.0
    last_restart_at = time.monotonic()

    shutting_down = False

    def _shutdown(*_args: object) -> None:
        nonlocal shutting_down
        if shutting_down:
            return
        shutting_down = True
        logger.info("监视进程退出，停止 Web Agent 子进程…")
        stop_child(child)
        remove_pid_file()
        os._exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    try:
        while True:
            time.sleep(poll_s)

            if child.poll() is not None:
                logger.warning("Web Agent 子进程退出 code=%s，重新拉起", child.returncode)
                kill_process_on_port(port)
                child = spawn_server(host=host, port=port)
                mtimes = snapshot_mtimes()
                pending_change_at = 0.0
                last_restart_at = time.monotonic()
                time.sleep(POST_RESTART_SETTLE_S)
                continue

            if time.monotonic() - last_restart_at < RESTART_COOLDOWN_S:
                continue

            new_mtimes = snapshot_mtimes()
            if new_mtimes != mtimes:
                if pending_change_at <= 0:
                    pending_change_at = time.monotonic()

            if pending_change_at <= 0:
                continue
            if time.monotonic() - pending_change_at < debounce_s:
                continue

            logger.info("检测到源码变更，重启 Web Agent（监视 %d 个文件）", len(mtimes))
            stop_child(child)
            kill_process_on_port(port)
            child = spawn_server(host=host, port=port)
            time.sleep(POST_RESTART_SETTLE_S)
            mtimes = snapshot_mtimes()
            pending_change_at = 0.0
            last_restart_at = time.monotonic()
    finally:
        stop_child(child)
        remove_pid_file()


def start_watch_background(*, host: str, port: int) -> subprocess.Popen[bytes]:
    log_path = WEB_AGENT_DIR / "data" / "server_watch.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_fp = open(log_path, "a", encoding="utf-8")
    return subprocess.Popen(
        [
            PYTHON_EXECUTABLE,
            str(WEB_AGENT_DIR / "server_watch.py"),
            "--host",
            host,
            "--port",
            str(port),
        ],
        cwd=str(REPO_ROOT),
        stdout=log_fp,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Web Agent 源码监视（自动重启）")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=18766)
    parser.add_argument("--poll", type=float, default=1.0, help="轮询间隔秒")
    parser.add_argument("--debounce", type=float, default=0.8, help="变更防抖秒")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    print(f"Web Agent 监视中: http://{args.host}:{args.port}/ （源码变更自动重启）")
    run_watch(host=args.host, port=args.port, poll_s=args.poll, debounce_s=args.debounce)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
