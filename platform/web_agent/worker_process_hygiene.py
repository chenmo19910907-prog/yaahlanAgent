"""回收已结束 worker 子进程并清理无对应 RUNNING 任务的孤儿 run_worker。"""

from __future__ import annotations

import logging
import os
import re
import subprocess
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from web_run_store import RunMeta, WebRunStore

logger = logging.getLogger("web-agent")

_RUN_ID_RE = re.compile(r"run_worker\.py\s+--run-id\s+(\S+)")
_WARM_NEEDLE = "run_worker.py --warm"
_RUN_WORKER_NEEDLE = "run_worker.py --run-id"
_WARM_MAX_AGE_S = 240.0


def _hygiene_enabled() -> bool:
    raw = os.environ.get("WEB_AGENT_WORKER_HYGIENE", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _pgrep_pids(pattern: str) -> list[int]:
    needle = (pattern or "").strip()
    if len(needle) < 8:
        return []
    try:
        proc = subprocess.run(
            ["pgrep", "-f", needle],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if proc.returncode != 0:
        return []
    pids: list[int] = []
    for token in proc.stdout.strip().split():
        if token.isdigit():
            pid = int(token)
            if pid > 0 and pid != os.getpid():
                pids.append(pid)
    return sorted(set(pids))


def _process_command_line(pid: int) -> str:
    try:
        proc = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return (proc.stdout or "").strip()


def _parse_run_id_from_cmdline(cmdline: str) -> str:
    match = _RUN_ID_RE.search(cmdline or "")
    if not match:
        return ""
    return match.group(1).strip()


def iter_run_worker_processes() -> list[tuple[int, str]]:
    """返回 (pid, run_id) 列表（仅 --run-id one-shot worker）。"""
    out: list[tuple[int, str]] = []
    for pid in _pgrep_pids(_RUN_WORKER_NEEDLE):
        run_id = _parse_run_id_from_cmdline(_process_command_line(pid))
        if run_id:
            out.append((pid, run_id))
    return out


def _terminate_tree(pid: int) -> None:
    from run_child_processes import terminate_process_tree

    terminate_process_tree(int(pid))


def _is_orphan_worker(
    run_id: str,
    pid: int,
    meta: RunMeta | None,
    *,
    store: WebRunStore,
) -> bool:
    from web_run_store import RUN_STATUS_RUNNING

    if meta is None:
        return True
    if meta.status != RUN_STATUS_RUNNING:
        return True
    expected = int(meta.worker_pid or 0)
    if expected == pid:
        return False
    if expected > 0 and store.is_pid_alive(expected):
        return True
    discovered = store.discover_worker_pid(run_id)
    if discovered > 0:
        return pid != discovered
    return False


def sweep_orphan_run_workers(*, kill: bool = True) -> int:
    """清理无有效 RUNNING 任务绑定的 run_worker --run-id 进程。"""
    if not _hygiene_enabled():
        return 0
    from web_run_store import RUN_STATUS_RUNNING, get_run_store

    store = get_run_store()
    removed = 0
    for pid, run_id in iter_run_worker_processes():
        meta = store.get_run(run_id)
        if meta is not None and meta.status == RUN_STATUS_RUNNING and not _is_orphan_worker(
            run_id, pid, meta, store=store
        ):
            continue
        if not kill:
            removed += 1
            continue
        try:
            _terminate_tree(pid)
            removed += 1
            logger.info("已清理孤儿 run_worker pid=%s run=%s", pid, run_id)
        except OSError as exc:
            logger.debug("清理孤儿 run_worker pid=%s 失败: %s", pid, exc)
    return removed


def sweep_stale_warm_workers(*, max_age_s: float = _WARM_MAX_AGE_S) -> int:
    """终止超时未退出的 run_worker --warm（正常预热 ≤180s）。"""
    if not _hygiene_enabled():
        return 0
    removed = 0
    for pid in _pgrep_pids(_WARM_NEEDLE):
        try:
            proc = subprocess.run(
                ["ps", "-p", str(pid), "-o", "etime="],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        etime = (proc.stdout or "").strip()
        if not etime:
            continue
        if not _etime_exceeds(etime, max_age_s):
            continue
        try:
            _terminate_tree(pid)
            removed += 1
            logger.info("已清理超时 warm worker pid=%s etime=%s", pid, etime)
        except OSError as exc:
            logger.debug("清理 warm worker pid=%s 失败: %s", pid, exc)
    return removed


def _etime_exceeds(etime: str, max_age_s: float) -> bool:
    text = etime.strip()
    if not text:
        return False
    if "-" in text:
        return True
    parts = text.split(":")
    try:
        if len(parts) == 2:
            minutes, seconds = int(parts[0]), int(parts[1])
            return minutes * 60 + seconds >= max_age_s
        if len(parts) == 3:
            hours, minutes, seconds = int(parts[0]), int(parts[1]), int(parts[2])
            return hours * 3600 + minutes * 60 + seconds >= max_age_s
    except ValueError:
        return False
    return False


def kill_stray_workers_for_run(run_id: str) -> int:
    """任务已结束但 worker/子树仍存活时，按 run_id 匹配并终止。"""
    rid = (run_id or "").strip()
    if not rid:
        return 0
    killed = 0
    needle = f"run_worker.py --run-id {rid}"
    for pid in _pgrep_pids(needle):
        try:
            _terminate_tree(pid)
            killed += 1
        except OSError as exc:
            logger.debug("终止 run=%s worker pid=%s 失败: %s", rid, pid, exc)
    return killed


def run_worker_hygiene_pass() -> dict[str, int]:
    """HTTP 定时 sweep 入口：回收 + 孤儿 worker + 超时 warm。"""
    if not _hygiene_enabled():
        return {"reaped": 0, "orphans": 0, "warm": 0}
    from web_run_executor import reap_finished_run_procs

    reaped = reap_finished_run_procs()
    orphans = sweep_orphan_run_workers(kill=True)
    warm = sweep_stale_warm_workers()
    if reaped or orphans or warm:
        logger.info(
            "worker 卫生 sweep：reaped=%s orphans=%s warm=%s",
            reaped,
            orphans,
            warm,
        )
    return {"reaped": reaped, "orphans": orphans, "warm": warm}
