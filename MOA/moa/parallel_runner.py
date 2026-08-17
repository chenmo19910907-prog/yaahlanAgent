"""通用并行批处理执行器 — 将任务列表按 workers 数分片并发执行。

用法:
    from moa.parallel_runner import run_parallel_batch, BatchTask, BatchResult

    tasks = [BatchTask(id="uid1", payload={"uid": "uid1"}), ...]
    results = run_parallel_batch(
        tasks=tasks,
        worker_fn=my_worker_fn,
        workers=5,
        sleep_between=0.3,
    )
"""

from __future__ import annotations

import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class BatchTask:
    """单个批处理任务。"""
    id: str
    payload: Any = None


@dataclass
class TaskResult:
    """单个任务执行结果。"""
    task_id: str
    ok: bool
    detail: Any = None
    error: str | None = None


@dataclass
class BatchSummary:
    """整批执行汇总。"""
    total: int
    success: int
    failed: int
    results: list[TaskResult] = field(default_factory=list)
    elapsed_seconds: float = 0.0


WorkerFn = Callable[[BatchTask], TaskResult]
ProgressFn = Callable[[int, int, TaskResult], None]


def _worker_loop(
    tasks: list[BatchTask],
    worker_fn: WorkerFn,
    sleep_between: float,
    results: list[TaskResult],
    lock: threading.Lock,
    counter: list[int],
    total: int,
    progress_fn: ProgressFn | None,
) -> None:
    """单个线程的工作循环：顺序执行分配到的 tasks，每个之间 sleep。"""
    for i, task in enumerate(tasks):
        try:
            result = worker_fn(task)
        except Exception as e:
            result = TaskResult(task_id=task.id, ok=False, error=str(e))

        with lock:
            results.append(result)
            counter[0] += 1
            current = counter[0]

        if progress_fn is not None:
            try:
                progress_fn(current, total, result)
            except Exception:
                pass

        if i < len(tasks) - 1 and sleep_between > 0:
            time.sleep(sleep_between)


def run_parallel_batch(
    *,
    tasks: list[BatchTask],
    worker_fn: WorkerFn,
    workers: int = 1,
    sleep_between: float = 0.3,
    progress_fn: ProgressFn | None = None,
) -> BatchSummary:
    """将 tasks 均匀分片到 workers 个线程并发执行。

    Args:
        tasks: 待执行任务列表
        worker_fn: 执行单个任务的函数，接收 BatchTask 返回 TaskResult
        workers: 并发线程数（默认 1 = 串行）
        sleep_between: 同一线程内两次任务间隔秒数
        progress_fn: 可选进度回调 (current, total, last_result)

    Returns:
        BatchSummary 汇总结果
    """
    if not tasks:
        return BatchSummary(total=0, success=0, failed=0)

    workers = max(1, min(workers, len(tasks)))
    total = len(tasks)

    chunks: list[list[BatchTask]] = [[] for _ in range(workers)]
    for i, task in enumerate(tasks):
        chunks[i % workers].append(task)

    results: list[TaskResult] = []
    lock = threading.Lock()
    counter = [0]
    start_time = time.time()

    if workers == 1:
        _worker_loop(
            chunks[0], worker_fn, sleep_between,
            results, lock, counter, total, progress_fn,
        )
    else:
        threads: list[threading.Thread] = []
        for chunk in chunks:
            if not chunk:
                continue
            t = threading.Thread(
                target=_worker_loop,
                args=(chunk, worker_fn, sleep_between, results, lock, counter, total, progress_fn),
                daemon=True,
            )
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

    elapsed = time.time() - start_time
    success = sum(1 for r in results if r.ok)
    return BatchSummary(
        total=total,
        success=success,
        failed=total - success,
        results=results,
        elapsed_seconds=round(elapsed, 2),
    )


def default_progress_printer(current: int, total: int, result: TaskResult) -> None:
    """默认进度打印（stderr）。"""
    status = "✓" if result.ok else "✗"
    detail = f" {result.error}" if result.error else ""
    print(
        f"[{current}/{total}] {result.task_id} {status}{detail}",
        file=sys.stderr,
    )
