"""Web Agent 进行中任务落盘：服务重启后可恢复 SSE 与 worker 子进程。"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger("web-agent")

WEB_AGENT_DIR = Path(__file__).resolve().parent
RUNS_DIR = WEB_AGENT_DIR / "data" / "runs"

RUN_STATUS_RUNNING = "running"
RUN_STATUS_DONE = "done"
RUN_STATUS_ERROR = "error"
RUN_STATUS_INTERRUPTED = "interrupted"

_SNAPSHOT_FLUSH_INTERVAL_S = 1.5
_EVENT_FLUSH_INTERVAL_S = 0.4
_IMMEDIATE_SNAPSHOT_EVENTS = frozenset({"ack", "done", "error"})
_IMMEDIATE_EVENT_TYPES = frozenset({"ack", "done", "error", "status"})
_ACTIVE_RUNS_CACHE_TTL_S = 2.0
_WORKER_ALIVE_CACHE_TTL_S = 1.0
_COMPACT_JSON = (",", ":")


def compute_active_run_etag(session_id: str, payload: dict[str, Any]) -> str:
    """active-run 快照指纹，供 GET /active-run 返回 ETag。"""
    import hashlib

    sid = str(session_id or "").strip()
    if not payload.get("active"):
        digest = hashlib.sha256(f"inactive:{sid}".encode("utf-8")).hexdigest()[:16]
        return f'W/"{digest}"'
    proc = payload.get("process")
    proc_fp = ""
    if isinstance(proc, dict) and proc:
        proc_fp = hashlib.sha256(
            json.dumps(proc, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()[:12]
    markdown = str(payload.get("markdown") or "")
    parts = [
        sid,
        str(payload.get("run_id") or ""),
        str(payload.get("ack_line") or ""),
        str(payload.get("elapsed_line") or ""),
        str(payload.get("batch_line") or ""),
        str(payload.get("external_line") or ""),
        str(payload.get("phase_line") or ""),
        str(len(markdown)),
        proc_fp,
    ]
    digest = hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()[:16]
    return f'W/"{digest}"'


def _process_has_stream_content(proc: dict[str, Any]) -> bool:
    if str(proc.get("thinking") or "").strip():
        return True
    tools = proc.get("tools")
    return isinstance(tools, list) and bool(tools)


def resolve_process_phase_line(proc: dict[str, Any]) -> str:
    """流式 process → 顶部进度行。"""
    phase = str(proc.get("phase") or "").strip()
    if _process_has_stream_content(proc):
        return ""
    return phase


def _merge_process_payload(
    prev: dict[str, Any] | None,
    new: dict[str, Any],
) -> dict[str, Any]:
    """流式 process 快照：思考/工具链只增不减，避免重连后回退到短片段。"""
    out = dict(new)
    if not isinstance(prev, dict):
        return out
    prev_thinking = str(prev.get("thinking") or "")
    new_thinking = str(new.get("thinking") or "")
    if len(prev_thinking) > len(new_thinking):
        out["thinking"] = prev_thinking
    prev_tools = prev.get("tools")
    new_tools = new.get("tools")
    if isinstance(prev_tools, list) and isinstance(new_tools, list):
        if len(prev_tools) > len(new_tools):
            out["tools"] = list(prev_tools)
    return out


@dataclass
class RunMeta:
    run_id: str
    session_id: str
    message: str
    display_message: str
    model: str
    enabled_external_agents: list[str]
    author_id: str
    author_label: str
    image_paths: list[str]
    file_paths: list[str]
    attachment_names: list[str]
    worker_pid: int
    status: str
    started_at: float
    cancel_requested: bool = False
    push_result_to_dingtalk: bool = False
    push_dingtalk_staff_id: str = ""
    reply_mode: str = "standard"

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "session_id": self.session_id,
            "message": self.message,
            "display_message": self.display_message,
            "model": self.model,
            "enabled_external_agents": list(self.enabled_external_agents),
            "author_id": self.author_id,
            "author_label": self.author_label,
            "image_paths": list(self.image_paths),
            "file_paths": list(self.file_paths),
            "attachment_names": list(self.attachment_names),
            "worker_pid": int(self.worker_pid),
            "status": self.status,
            "started_at": float(self.started_at),
            "cancel_requested": bool(self.cancel_requested),
            "push_result_to_dingtalk": bool(self.push_result_to_dingtalk),
            "push_dingtalk_staff_id": str(self.push_dingtalk_staff_id or ""),
            "reply_mode": str(self.reply_mode or "standard"),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RunMeta:
        return cls(
            run_id=str(data.get("run_id") or ""),
            session_id=str(data.get("session_id") or ""),
            message=str(data.get("message") or ""),
            display_message=str(data.get("display_message") or ""),
            model=str(data.get("model") or ""),
            enabled_external_agents=[
                str(x) for x in (data.get("enabled_external_agents") or [])
            ],
            author_id=str(data.get("author_id") or ""),
            author_label=str(data.get("author_label") or ""),
            image_paths=[str(x) for x in (data.get("image_paths") or [])],
            file_paths=[str(x) for x in (data.get("file_paths") or [])],
            attachment_names=[str(x) for x in (data.get("attachment_names") or [])],
            worker_pid=int(data.get("worker_pid") or 0),
            status=str(data.get("status") or RUN_STATUS_RUNNING),
            started_at=float(data.get("started_at") or 0.0),
            cancel_requested=bool(data.get("cancel_requested")),
            push_result_to_dingtalk=bool(data.get("push_result_to_dingtalk")),
            push_dingtalk_staff_id=str(data.get("push_dingtalk_staff_id") or ""),
            reply_mode=str(data.get("reply_mode") or "standard"),
        )


@dataclass
class RunSnapshot:
    last_ack_line: str = ""
    last_elapsed_line: str = ""
    last_batch_line: str = ""
    last_external_line: str = ""
    last_phase_line: str = ""
    last_markdown: str = ""
    last_process: dict[str, Any] | None = None
    final_text: str = ""
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "last_ack_line": self.last_ack_line,
            "last_elapsed_line": self.last_elapsed_line,
            "last_batch_line": self.last_batch_line,
            "last_external_line": self.last_external_line,
            "last_phase_line": self.last_phase_line,
            "last_markdown": self.last_markdown,
            "final_text": self.final_text,
            "error": self.error,
        }
        if isinstance(self.last_process, dict):
            payload["last_process"] = self.last_process
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RunSnapshot:
        err = data.get("error")
        proc = data.get("last_process")
        return cls(
            last_ack_line=str(data.get("last_ack_line") or ""),
            last_elapsed_line=str(data.get("last_elapsed_line") or ""),
            last_batch_line=str(data.get("last_batch_line") or ""),
            last_external_line=str(data.get("last_external_line") or ""),
            last_phase_line=str(data.get("last_phase_line") or ""),
            last_markdown=str(data.get("last_markdown") or ""),
            last_process=proc if isinstance(proc, dict) else None,
            final_text=str(data.get("final_text") or ""),
            error=str(err) if err else None,
        )


def _apply_event_to_snapshot(snap: RunSnapshot, event: dict[str, Any]) -> None:
    etype = event.get("type")
    if etype == "ack":
        snap.last_ack_line = str(event.get("line") or "")
    elif etype == "status":
        if "elapsed_line" in event:
            snap.last_elapsed_line = str(event.get("elapsed_line") or "")
        if "batch_line" in event:
            snap.last_batch_line = str(event.get("batch_line") or "")
        if "external_line" in event:
            snap.last_external_line = str(event.get("external_line") or "")
        if "phase_line" in event:
            snap.last_phase_line = str(event.get("phase_line") or "")
    elif etype == "delta":
        markdown = event.get("markdown")
        if markdown:
            snap.last_markdown = str(markdown)
        proc = event.get("process")
        if isinstance(proc, dict):
            prev = snap.last_process if isinstance(snap.last_process, dict) else None
            snap.last_process = _merge_process_payload(prev, proc)
            snap.last_phase_line = resolve_process_phase_line(snap.last_process)
    elif etype == "done":
        snap.final_text = str(event.get("text") or "")
    elif etype == "error":
        snap.error = str(event.get("message") or "")
        snap.final_text = str(event.get("text") or "")


class WebRunStore:
    def __init__(self, root: Path | None = None) -> None:
        self._root = root or RUNS_DIR
        self._root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._snapshot_cache: dict[str, RunSnapshot] = {}
        self._snapshot_flush_at: dict[str, float] = {}
        self._event_streams: dict[str, list[dict[str, Any]]] = {}
        self._event_read_idx: dict[str, int] = {}
        self._event_disk_written: dict[str, int] = {}
        self._event_flush_at: dict[str, float] = {}
        self._active_runs: dict[str, RunMeta] = {}
        self._session_active_run: dict[str, str] = {}
        self._active_index_ready = False
        self._list_active_cache: tuple[float, list[RunMeta]] | None = None
        self._worker_alive_cache: dict[str, tuple[float, bool]] = {}
        self._snapshot_disk_mtime: dict[str, float] = {}

    def _run_dir(self, run_id: str) -> Path:
        return self._root / run_id

    def _meta_path(self, run_id: str) -> Path:
        return self._run_dir(run_id) / "meta.json"

    def _snapshot_path(self, run_id: str) -> Path:
        return self._run_dir(run_id) / "snapshot.json"

    def _events_path(self, run_id: str) -> Path:
        return self._run_dir(run_id) / "events.jsonl"

    def _tail_path(self, run_id: str) -> Path:
        return self._run_dir(run_id) / "tail.offset"

    def _invalidate_active_run_caches(self) -> None:
        self._list_active_cache = None

    def _index_active_run(self, meta: RunMeta) -> None:
        if meta.status == RUN_STATUS_RUNNING:
            self._active_runs[meta.run_id] = meta
            self._session_active_run[meta.session_id] = meta.run_id
        else:
            self._active_runs.pop(meta.run_id, None)
            if self._session_active_run.get(meta.session_id) == meta.run_id:
                self._session_active_run.pop(meta.session_id, None)
        self._invalidate_active_run_caches()

    def _ensure_active_index(self) -> None:
        if self._active_index_ready:
            return
        for meta in self.list_runs():
            if meta.status == RUN_STATUS_RUNNING:
                self._index_active_run(meta)
        self._active_index_ready = True

    def create_run(self, meta: RunMeta) -> None:
        run_dir = self._run_dir(meta.run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        with self._lock:
            self._meta_path(meta.run_id).write_text(
                json.dumps(meta.to_dict(), ensure_ascii=False, separators=_COMPACT_JSON),
                encoding="utf-8",
            )
            self._snapshot_path(meta.run_id).write_text("{}", encoding="utf-8")
            self._events_path(meta.run_id).write_text("", encoding="utf-8")
            self._tail_path(meta.run_id).write_text("0", encoding="utf-8")
            self._snapshot_cache[meta.run_id] = RunSnapshot()
            self._snapshot_flush_at[meta.run_id] = time.monotonic()
            self._event_streams[meta.run_id] = []
            self._event_read_idx[meta.run_id] = 0
            self._event_disk_written[meta.run_id] = 0
            self._event_flush_at[meta.run_id] = time.monotonic()
            self._index_active_run(meta)

    def get_run(self, run_id: str) -> RunMeta | None:
        path = self._meta_path(run_id)
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return None
            return RunMeta.from_dict(data)
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return None

    def update_meta(self, run_id: str, **fields: Any) -> None:
        with self._lock:
            meta = self.get_run(run_id)
            if meta is None:
                return
            payload = meta.to_dict()
            payload.update(fields)
            self._meta_path(run_id).write_text(
                json.dumps(payload, ensure_ascii=False, separators=_COMPACT_JSON),
                encoding="utf-8",
            )
            updated = RunMeta.from_dict(payload)
            if "worker_pid" in fields:
                self._worker_alive_cache.pop(run_id, None)
            if "status" in fields:
                self._index_active_run(updated)
            elif updated.status == RUN_STATUS_RUNNING:
                self._active_runs[run_id] = updated
                self._session_active_run[updated.session_id] = run_id
                self._invalidate_active_run_caches()

    def set_worker_pid(self, run_id: str, pid: int) -> None:
        self.update_meta(run_id, worker_pid=int(pid))

    def _load_snapshot_from_disk(self, run_id: str) -> RunSnapshot:
        path = self._snapshot_path(run_id)
        if not path.is_file():
            return RunSnapshot()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return RunSnapshot()
            return RunSnapshot.from_dict(data)
        except (OSError, json.JSONDecodeError):
            return RunSnapshot()

    def _get_cached_snapshot(self, run_id: str) -> RunSnapshot:
        path = self._snapshot_path(run_id)
        disk_mtime = 0.0
        if path.is_file():
            try:
                disk_mtime = float(path.stat().st_mtime)
            except OSError:
                disk_mtime = 0.0
        cached = self._snapshot_cache.get(run_id)
        cached_mtime = float(self._snapshot_disk_mtime.get(run_id, 0.0))
        if cached is not None and disk_mtime <= cached_mtime:
            return cached
        snap = self._load_snapshot_from_disk(run_id)
        self._snapshot_cache[run_id] = snap
        if disk_mtime > 0:
            self._snapshot_disk_mtime[run_id] = disk_mtime
        return snap

    def _write_snapshot_to_disk(self, run_id: str, snap: RunSnapshot) -> None:
        self._snapshot_path(run_id).write_text(
            json.dumps(snap.to_dict(), ensure_ascii=False, separators=_COMPACT_JSON),
            encoding="utf-8",
        )
        self._snapshot_flush_at[run_id] = time.monotonic()

    def _should_flush_snapshot(self, run_id: str, etype: str | None) -> bool:
        if etype in _IMMEDIATE_SNAPSHOT_EVENTS:
            return True
        last = self._snapshot_flush_at.get(run_id, 0.0)
        return time.monotonic() - last >= _SNAPSHOT_FLUSH_INTERVAL_S

    def get_snapshot(self, run_id: str) -> RunSnapshot:
        with self._lock:
            return self._get_cached_snapshot(run_id)

    def flush_snapshot(self, run_id: str) -> None:
        with self._lock:
            snap = self._snapshot_cache.get(run_id)
            if snap is None:
                snap = self._load_snapshot_from_disk(run_id)
                self._snapshot_cache[run_id] = snap
            self._write_snapshot_to_disk(run_id, snap)

    def update_snapshot(self, run_id: str, event: dict[str, Any]) -> RunSnapshot:
        etype = event.get("type")
        etype_str = etype if isinstance(etype, str) else None
        with self._lock:
            snap = self._get_cached_snapshot(run_id)
            _apply_event_to_snapshot(snap, event)
            self._snapshot_cache[run_id] = snap
            if self._should_flush_snapshot(run_id, etype_str):
                self._write_snapshot_to_disk(run_id, snap)
        return snap

    def _flush_events_to_disk_locked(self, run_id: str) -> None:
        stream = self._event_streams.get(run_id)
        if not stream:
            return
        start = self._event_disk_written.get(run_id, 0)
        if start >= len(stream):
            return
        lines = [json.dumps(event, ensure_ascii=False) for event in stream[start:]]
        with open(self._events_path(run_id), "a", encoding="utf-8") as fp:
            fp.write("\n".join(lines) + "\n")
        self._event_disk_written[run_id] = len(stream)
        self._event_flush_at[run_id] = time.monotonic()

    def _should_flush_events(self, run_id: str, etype: str | None) -> bool:
        if etype in _IMMEDIATE_EVENT_TYPES:
            return True
        last = self._event_flush_at.get(run_id, 0.0)
        return time.monotonic() - last >= _EVENT_FLUSH_INTERVAL_S

    def flush_events(self, run_id: str) -> None:
        with self._lock:
            self._flush_events_to_disk_locked(run_id)

    def append_event(self, run_id: str, event: dict[str, Any]) -> None:
        etype = event.get("type")
        etype_str = etype if isinstance(etype, str) else None
        with self._lock:
            stream = self._event_streams.setdefault(run_id, [])
            stream.append(event)
            if self._should_flush_events(run_id, etype_str):
                self._flush_events_to_disk_locked(run_id)
        self.update_snapshot(run_id, event)

    def _read_disk_events_locked(self, run_id: str) -> list[dict[str, Any]]:
        """读取 events.jsonl 增量（worker 子进程跨进程落盘）。"""
        events_path = self._events_path(run_id)
        tail_path = self._tail_path(run_id)
        if not events_path.is_file():
            return []
        try:
            offset = int(tail_path.read_text(encoding="utf-8").strip() or "0")
        except (OSError, ValueError):
            offset = 0
        try:
            with open(events_path, encoding="utf-8") as fp:
                fp.seek(offset)
                chunk = fp.read()
                new_offset = fp.tell()
        except OSError:
            return []
        events: list[dict[str, Any]] = []
        for line in chunk.splitlines():
            text = line.strip()
            if not text:
                continue
            try:
                item = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                events.append(item)
        if new_offset > offset:
            try:
                tail_path.write_text(str(new_offset), encoding="utf-8")
            except OSError:
                pass
        return events

    def _advance_disk_tail_eof_locked(self, run_id: str) -> None:
        """内存 event 已消费且曾落盘时，跳过磁盘重复 tail。"""
        events_path = self._events_path(run_id)
        if not events_path.is_file():
            return
        try:
            size = events_path.stat().st_size
            self._tail_path(run_id).write_text(str(size), encoding="utf-8")
        except OSError:
            return

    def read_new_events(self, run_id: str) -> tuple[list[dict[str, Any]], int]:
        """合并进程内 event 缓冲与磁盘 tail（worker 子进程仅写盘）。"""
        mem_events: list[dict[str, Any]] = []
        disk_events: list[dict[str, Any]] = []
        with self._lock:
            stream = self._event_streams.get(run_id)
            if stream is not None:
                idx = self._event_read_idx.get(run_id, 0)
                mem_events = list(stream[idx:])
                self._event_read_idx[run_id] = len(stream)
            if mem_events:
                self._advance_disk_tail_eof_locked(run_id)
            else:
                disk_events = self._read_disk_events_locked(run_id)
        combined = mem_events + disk_events
        return combined, len(combined)

    def request_cancel(self, run_id: str) -> None:
        self.update_meta(run_id, cancel_requested=True)

    def is_cancel_requested(self, run_id: str) -> bool:
        meta = self.get_run(run_id)
        return bool(meta and meta.cancel_requested)

    def mark_status(self, run_id: str, status: str) -> None:
        self.update_meta(run_id, status=status)
        if status != RUN_STATUS_RUNNING:
            self.flush_events(run_id)
            self.flush_snapshot(run_id)
            with self._lock:
                self._event_streams.pop(run_id, None)
                self._event_read_idx.pop(run_id, None)
                self._event_disk_written.pop(run_id, None)
                self._event_flush_at.pop(run_id, None)
                self._worker_alive_cache.pop(run_id, None)

    def list_runs(self) -> list[RunMeta]:
        out: list[RunMeta] = []
        if not self._root.is_dir():
            return out
        for child in self._root.iterdir():
            if not child.is_dir():
                continue
            meta = self.get_run(child.name)
            if meta is not None:
                out.append(meta)
        return out

    def list_active_runs(self) -> list[RunMeta]:
        self._ensure_active_index()
        now = time.monotonic()
        cached = self._list_active_cache
        if cached is not None and now - cached[0] < _ACTIVE_RUNS_CACHE_TTL_S:
            return list(cached[1])
        result = list(self._active_runs.values())
        self._list_active_cache = (now, result)
        return result

    def find_active_by_session(self, session_id: str) -> RunMeta | None:
        sid = (session_id or "").strip()
        if not sid:
            return None
        self._ensure_active_index()
        run_id = self._session_active_run.get(sid)
        if run_id:
            meta = self._active_runs.get(run_id)
            if meta is not None and meta.status == RUN_STATUS_RUNNING:
                return meta
        active = [
            m for m in self.list_active_runs()
            if m.session_id == sid
        ]
        if not active:
            return None
        return max(active, key=lambda m: m.started_at)

    @staticmethod
    def is_pid_alive(pid: int) -> bool:
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        try:
            proc = subprocess.run(
                ["ps", "-p", str(pid), "-o", "stat="],
                capture_output=True,
                text=True,
                timeout=1,
                check=False,
            )
            stat = (proc.stdout or "").strip()
            if stat.startswith("Z"):
                return False
        except (OSError, subprocess.TimeoutExpired):
            pass
        return True

    def discover_worker_pid(self, run_id: str) -> int:
        """扫描 run_worker 子进程（meta.worker_pid 尚未写入时仍可发现）。"""
        rid = (run_id or "").strip()
        if not rid:
            return 0
        needle = f"run_worker.py --run-id {rid}"
        try:
            proc = subprocess.run(
                ["pgrep", "-f", needle],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return 0
        if proc.returncode != 0:
            return 0
        for line in proc.stdout.splitlines():
            text = line.strip()
            if not text:
                continue
            try:
                pid = int(text)
            except ValueError:
                continue
            if pid > 0 and pid != os.getpid() and self.is_pid_alive(pid):
                return pid
        return 0

    def has_run_activity(self, run_id: str) -> bool:
        """是否已有 worker 输出或 SSE 事件（用于判断能否安全重跑）。"""
        events_path = self._events_path(run_id)
        try:
            if events_path.is_file() and events_path.stat().st_size > 0:
                return True
        except OSError:
            pass
        worker_log = self._run_dir(run_id) / "worker.log"
        try:
            if worker_log.is_file() and worker_log.stat().st_size > 0:
                return True
        except OSError:
            pass
        return False

    def is_worker_alive(self, run_id: str) -> bool:
        now = time.monotonic()
        cached = self._worker_alive_cache.get(run_id)
        if cached is not None and now - cached[0] < _WORKER_ALIVE_CACHE_TTL_S:
            return cached[1]

        meta = self.get_run(run_id)
        if meta is None:
            alive = False
        elif meta.status != RUN_STATUS_RUNNING:
            alive = False
        else:
            pid = int(meta.worker_pid or 0)
            if pid > 0:
                if pid == os.getpid():
                    from web_run_executor import is_run_thread_alive

                    alive = is_run_thread_alive(run_id)
                elif self.is_pid_alive(pid):
                    alive = True
                else:
                    # meta.worker_pid 可能因 daemon 转发/服务重启而过期，仍尝试 pgrep 发现
                    discovered = self.discover_worker_pid(run_id)
                    if discovered > 0:
                        self.set_worker_pid(run_id, discovered)
                        alive = True
                    else:
                        from web_run_executor import is_run_thread_alive

                        alive = is_run_thread_alive(run_id)
            else:
                discovered = self.discover_worker_pid(run_id)
                if discovered > 0:
                    self.set_worker_pid(run_id, discovered)
                    alive = True
                else:
                    from web_run_executor import is_run_thread_alive

                    alive = is_run_thread_alive(run_id)

        # worker 派发前（pid=0）的 False 不缓存，避免 spawn 后仍误判为已退出
        if alive or int((meta.worker_pid if meta is not None else 0) or 0) > 0:
            self._worker_alive_cache[run_id] = (now, alive)
        return alive

    def cleanup_old_runs(self, *, max_age_s: float = 86400.0) -> None:
        cutoff = time.time() - max_age_s
        for meta in self.list_runs():
            if meta.status == RUN_STATUS_RUNNING:
                continue
            if meta.started_at >= cutoff:
                continue
            run_dir = self._run_dir(meta.run_id)
            try:
                for path in run_dir.iterdir():
                    path.unlink(missing_ok=True)
                run_dir.rmdir()
            except OSError as exc:
                logger.debug("清理 run %s 失败: %s", meta.run_id, exc)


_STORE: WebRunStore | None = None
_STORE_LOCK = threading.Lock()


def get_run_store() -> WebRunStore:
    global _STORE
    with _STORE_LOCK:
        if _STORE is None:
            _STORE = WebRunStore()
        return _STORE
