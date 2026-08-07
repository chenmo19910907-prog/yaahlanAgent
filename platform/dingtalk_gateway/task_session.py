"""网关任务会话：支持按用户中断、子进程与 Agent run 可取消。"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import threading
import time
from collections.abc import Sequence
from typing import Any

from log_redact import redact_for_log

logger = logging.getLogger("dingtalk-gateway")


def _subprocess_env() -> dict[str, str]:
    try:
        import sys
        from pathlib import Path

        platform_dir = Path(__file__).resolve().parents[1]
        if str(platform_dir) not in sys.path:
            sys.path.insert(0, str(platform_dir))
        from project.runtime_env import merge_project_env

        return merge_project_env()
    except (ImportError, OSError, ValueError):
        import os

        return dict(os.environ)


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


def _kill_process_tree(root_pid: int, *, grace_s: float = 0.3) -> None:
    """先终止子进程，再终止 root（用于中断 Agent Shell / python 脚本）。"""
    if root_pid <= 0:
        return
    for child_pid in _list_child_pids(root_pid):
        _kill_process_tree(child_pid, grace_s=grace_s)
    try:
        os.kill(root_pid, signal.SIGTERM)
    except OSError:
        return
    if grace_s <= 0:
        return
    deadline = time.monotonic() + grace_s
    while time.monotonic() < deadline:
        try:
            os.kill(root_pid, 0)
        except OSError:
            return
        time.sleep(0.05)
    try:
        os.kill(root_pid, signal.SIGKILL)
    except OSError:
        pass


def _terminate_child_processes(*, root_pid: int | None = None) -> None:
    """终止当前进程的直接/间接子进程（不杀自身）。"""
    parent = root_pid if root_pid is not None else os.getpid()
    for child_pid in _list_child_pids(parent):
        _kill_process_tree(child_pid)


def safe_cancel_run(run: Any | None) -> bool:
    """尽力取消 Agent run；run.id 尚未就绪时可能失败，由 agent.close 兜底。"""
    if run is None:
        return False
    run_id = getattr(run, "id", "") or ""
    try:
        run.cancel()
        logger.info("已取消 Agent run id=%s", run_id or "(pending)")
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("取消 Agent run 失败 id=%s: %s", run_id or "(pending)", exc)
        return False


class TaskInterrupted(Exception):
    """当前任务被用户请求中断。"""


class TaskSession:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._busy = False
        self._conversation_id = ""
        self._cancel_requested = threading.Event()
        self._current_prompt = ""
        self._started_at = 0.0
        self._budget_s = 600.0
        self._phase = ""
        self._active_run: Any | None = None
        self._active_agent: Any | None = None
        self._active_subprocess: subprocess.Popen[str] | None = None
        self._cleanup_applied = False

    def arm_cancel(self) -> None:
        """在 begin 之前也可预置中断（worker 已取任务但尚未 begin）。"""
        self._cancel_requested.set()

    def begin(
        self,
        prompt: str,
        *,
        conversation_id: str = "",
        budget_s: float = 600.0,
    ) -> None:
        with self._lock:
            preserve_cancel = self._cancel_requested.is_set()
            self._busy = True
            self._conversation_id = conversation_id or ""
            if not preserve_cancel:
                self._cancel_requested.clear()
            self._cleanup_applied = False
            self._current_prompt = prompt
            self._started_at = time.monotonic()
            self._budget_s = max(1.0, budget_s)
            self._phase = "prepare"

    def set_phase(self, phase: str) -> None:
        with self._lock:
            self._phase = (phase or "").strip()

    def phase(self) -> str:
        with self._lock:
            return self._phase

    def end(self) -> None:
        with self._lock:
            self._busy = False
            self._conversation_id = ""
            self._cancel_requested.clear()
            self._current_prompt = ""
            self._started_at = 0.0
            self._budget_s = 600.0
            self._phase = ""
            self._active_run = None
            self._active_agent = None
            self._active_subprocess = None
            self._cleanup_applied = False

    def is_busy(self) -> bool:
        with self._lock:
            return self._busy

    def busy_conversation_id(self) -> str:
        with self._lock:
            return self._conversation_id

    def current_prompt(self) -> str:
        with self._lock:
            return self._current_prompt

    def elapsed_s(self) -> float:
        with self._lock:
            if not self._busy or self._started_at <= 0:
                return 0.0
            return time.monotonic() - self._started_at

    def estimated_remaining_s(self) -> float | None:
        with self._lock:
            if not self._busy or self._started_at <= 0:
                return None
            return max(0.0, self._budget_s - (time.monotonic() - self._started_at))

    def check_cancelled(self) -> None:
        if self._cancel_requested.is_set():
            self._apply_cancel_cleanup()
            raise TaskInterrupted()

    def cancel_requested(self) -> bool:
        return self._cancel_requested.is_set()

    def register_agent(self, agent: Any) -> None:
        with self._lock:
            self._active_agent = agent

    def register_run(self, agent: Any, run: Any) -> None:
        with self._lock:
            self._active_agent = agent
            self._active_run = run

    def register_subprocess(self, proc: subprocess.Popen[str]) -> None:
        with self._lock:
            self._active_subprocess = proc

    def _apply_cancel_cleanup(self) -> None:
        with self._lock:
            if self._cleanup_applied:
                return
            self._cleanup_applied = True
            run = self._active_run
            agent = self._active_agent
            proc = self._active_subprocess

        safe_cancel_run(run)

        if agent is not None:
            agent_id = getattr(agent, "agent_id", "") or ""
            try:
                agent.close()
                logger.info("已关闭 Agent agent_id=%s", agent_id or "(unknown)")
            except Exception as exc:  # noqa: BLE001
                logger.warning("关闭 Agent 失败 agent_id=%s: %s", agent_id or "(unknown)", exc)

        if proc is not None and proc.poll() is None:
            proc.kill()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                logger.warning("子进程 kill 后仍未退出: pid=%s", proc.pid)

        active_conv = ""
        with self._lock:
            active_conv = self._conversation_id
        if active_conv:
            from run_child_processes import kill_run_child_processes

            kill_run_child_processes(active_conv)

        _terminate_child_processes()

    def request_cancel(self, conversation_id: str = "") -> bool | None:
        """None=空闲，False=会话不匹配，True=已发起中断。"""
        with self._lock:
            if not self._busy:
                return None
            if conversation_id and self._conversation_id and conversation_id != self._conversation_id:
                return False
            self._cancel_requested.set()
            prompt = self._current_prompt
            active_conv = self._conversation_id
            phase = self._phase

        logger.info(
            "收到中断请求 conv=%s active_conv=%s phase=%s prompt=%s",
            conversation_id or "-",
            active_conv or "-",
            phase or "-",
            redact_for_log(prompt),
        )

        self._apply_cancel_cleanup()
        return True


def run_subprocess_cancellable(
    cmd: Sequence[str],
    *,
    cwd: str,
    session: TaskSession | None,
    timeout_s: float = 120,
) -> tuple[int, str, str]:
    if session:
        session.check_cancelled()
    env = _subprocess_env()
    proc = subprocess.Popen(
        list(cmd),
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    user_key = ""
    if session:
        session.register_subprocess(proc)
        user_key = (session.busy_conversation_id() or "").strip()
    if user_key:
        from run_child_processes import register_run_child, unregister_run_child

        register_run_child(user_key, proc.pid)

    deadline = time.monotonic() + timeout_s
    stdout = ""
    stderr = ""
    try:
        while True:
            if session:
                session.check_cancelled()
            try:
                stdout, stderr = proc.communicate(timeout=0.5)
                break
            except subprocess.TimeoutExpired:
                if time.monotonic() >= deadline:
                    proc.kill()
                    proc.communicate(timeout=3)
                    raise TimeoutError(f"命令超时（>{timeout_s}s）: {' '.join(cmd)}") from None
    finally:
        if user_key:
            from run_child_processes import unregister_run_child

            unregister_run_child(user_key, proc.pid)

    return proc.returncode, stdout or "", stderr or ""
