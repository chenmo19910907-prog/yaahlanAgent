"""Web Agent / 钉钉网关操作审计上下文：env + 落盘，供 MOA/Admin 子进程读取。"""

from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

WEB_AGENT_DIR = Path(__file__).resolve().parent
AUDIT_DIR = WEB_AGENT_DIR / "data" / "audit_context"
ACTIVE_PATH = AUDIT_DIR / "active.json"
BY_BATCH_DIR = AUDIT_DIR / "by_batch"

BATCH_KEY_ENV = "WEB_AGENT_BATCH_KEY"
RUN_ID_ENV = "WEB_AGENT_RUN_ID"
CALLER_STAFF_ENV = "WEB_AGENT_CALLER_STAFF_ID"
CALLER_NAME_ENV = "WEB_AGENT_CALLER_NAME"

DEFAULT_TTL_S = 7200


def _batch_file_key(batch_key: str) -> str:
    return hashlib.sha256(batch_key.encode("utf-8")).hexdigest()[:24]


def publish_audit_context(
    *,
    batch_key: str = "",
    run_id: str = "",
    operator_staff_id: str = "",
    operator_name: str = "",
    source: str = "",
) -> None:
    batch = (batch_key or os.environ.get(BATCH_KEY_ENV) or "").strip()
    rid = (run_id or os.environ.get(RUN_ID_ENV) or "").strip()
    staff = (operator_staff_id or os.environ.get(CALLER_STAFF_ENV) or "").strip()
    name = (operator_name or os.environ.get(CALLER_NAME_ENV) or "").strip()
    if not batch and not rid:
        return
    payload: dict[str, Any] = {
        "batch_key": batch,
        "run_id": rid,
        "operator_staff_id": staff,
        "operator_name": name,
        "source": (source or "").strip(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_epoch": time.time(),
    }
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    ACTIVE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if batch:
        BY_BATCH_DIR.mkdir(parents=True, exist_ok=True)
        path = BY_BATCH_DIR / f"{_batch_file_key(batch)}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _snapshot_fresh(snap: dict[str, Any], *, ttl_s: int) -> bool:
    try:
        epoch = float(snap.get("updated_epoch") or 0)
    except (TypeError, ValueError):
        epoch = 0.0
    if epoch <= 0:
        return False
    return (time.time() - epoch) <= ttl_s


def _pick_snapshot(*, batch_hint: str, run_hint: str = "", ttl_s: int) -> dict[str, Any] | None:
    """按 batch 文件优先；active.json 仅在与 batch/run  hint 一致时可用（禁止跨任务串线）。"""
    batch = (batch_hint or "").strip()
    run = (run_hint or "").strip()
    if batch:
        snap = _load_json(BY_BATCH_DIR / f"{_batch_file_key(batch)}.json")
        if snap and _snapshot_fresh(snap, ttl_s=ttl_s):
            return snap
    if not batch and not run:
        return None
    snap = _load_json(ACTIVE_PATH)
    if not snap or not _snapshot_fresh(snap, ttl_s=ttl_s):
        return None
    active_batch = str(snap.get("batch_key") or "").strip()
    active_run = str(snap.get("run_id") or "").strip()
    if run and active_run == run:
        return snap
    if batch and active_batch == batch:
        return snap
    return None


def hydrate_audit_env_from_store(*, ttl_s: int = DEFAULT_TTL_S) -> bool:
    """子进程启动时：用落盘上下文补全 os.environ（仅填空字段）。"""
    batch_hint = (os.environ.get(BATCH_KEY_ENV) or "").strip()
    run_hint = (os.environ.get(RUN_ID_ENV) or "").strip()
    snap = _pick_snapshot(batch_hint=batch_hint, run_hint=run_hint, ttl_s=ttl_s)
    if not snap:
        return False
    changed = False
    for env_key, snap_key in (
        (BATCH_KEY_ENV, "batch_key"),
        (RUN_ID_ENV, "run_id"),
        (CALLER_STAFF_ENV, "operator_staff_id"),
        (CALLER_NAME_ENV, "operator_name"),
    ):
        if (os.environ.get(env_key) or "").strip():
            continue
        val = str(snap.get(snap_key) or "").strip()
        if val:
            os.environ[env_key] = val
            changed = True
    return changed


def resolve_audit_context(*, ttl_s: int = DEFAULT_TTL_S) -> dict[str, str] | None:
    """解析 MOA/Admin 落库用的 run_id / batch / 调用人（env 优先，其次落盘）。"""
    batch = (os.environ.get(BATCH_KEY_ENV) or "").strip()
    run_id = (os.environ.get(RUN_ID_ENV) or "").strip()
    staff = (os.environ.get(CALLER_STAFF_ENV) or "").strip()
    name = (os.environ.get(CALLER_NAME_ENV) or "").strip()

    snap = _pick_snapshot(batch_hint=batch, run_hint=run_id, ttl_s=ttl_s)
    if snap:
        if not batch:
            batch = str(snap.get("batch_key") or "").strip()
        if not run_id:
            run_id = str(snap.get("run_id") or "").strip()
        if not staff:
            staff = str(snap.get("operator_staff_id") or "").strip()
        if not name:
            name = str(snap.get("operator_name") or "").strip()

    operator = name or staff
    if not operator or operator in ("未知", "unknown"):
        return None
    if not run_id and not batch:
        return None
    if not run_id and batch:
        run_id = f"batch:{_batch_file_key(batch)}"
    return {
        "batch_key": batch,
        "run_id": run_id,
        "operator_staff_id": staff,
        "operator_name": name or staff,
    }
