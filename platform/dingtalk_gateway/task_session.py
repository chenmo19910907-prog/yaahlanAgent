"""网关任务会话：支持按用户中断、子进程与 Agent run 可取消。"""

from __future__ import annotations

import logging
import subprocess
import threading
import time
from collections.abc import Sequence
from typing import Any

from log_redact import redact_for_log

logger = logging.getLogger("dingtalk-gateway")


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

    def request_cancel(self, conversation_id: str = "") -> bool | None:
        """None=空闲，False=会话不匹配，True=已发起中断。"""
        with self._lock:
            if not self._busy:
                return None
            if conversation_id and self._conversation_id and conversation_id != self._conversation_id:
                return False
            self._cancel_requested.set()
            run = self._active_run
            agent = self._active_agent
            proc = self._active_subprocess
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
    proc = subprocess.Popen(
        list(cmd),
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if session:
        session.register_subprocess(proc)

    deadline = time.monotonic() + timeout_s
    stdout = ""
    stderr = ""
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

    return proc.returncode, stdout or "", stderr or ""
