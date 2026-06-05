"""脚本连续执行失败追踪：达阈值后废弃，改 AI 读图 + Tunnel 抓包。"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .recorded_scripts import resolve_key, scripts_root

DEFAULT_MAX_CONSECUTIVE_FAILURES = 3
_STATE_FILE = scripts_root().parent / ".script_abandon.json"


def _load_state() -> dict[str, Any]:
    path = _STATE_FILE
    if not path.is_file():
        return {
            "version": 1,
            "maxConsecutiveFailures": DEFAULT_MAX_CONSECUTIVE_FAILURES,
            "scripts": {},
        }
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} 根节点须为 object")
    data.setdefault("scripts", {})
    data.setdefault("maxConsecutiveFailures", DEFAULT_MAX_CONSECUTIVE_FAILURES)
    return data


def _save_state(state: dict[str, Any]) -> None:
    _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _script_keys(name: str) -> set[str]:
    key = name.strip()
    keys = {key}
    for kind in ("fragment", "compose"):
        try:
            sid, sname, _ = resolve_key(key, kind=kind)
            keys.add(sid)
            keys.add(sname)
        except ValueError:
            continue
    return {k for k in keys if k}


def _find_entry(state: dict[str, Any], name: str) -> tuple[str, dict[str, Any]] | None:
    scripts = state.get("scripts")
    if not isinstance(scripts, dict):
        return None
    keys = _script_keys(name)
    for k, entry in scripts.items():
        if not isinstance(entry, dict):
            continue
        if (
            k in keys
            or str(entry.get("name", "")) in keys
            or str(entry.get("id", "")) in keys
        ):
            return k, entry
    return None


def max_consecutive_failures() -> int:
    return int(_load_state().get("maxConsecutiveFailures", DEFAULT_MAX_CONSECUTIVE_FAILURES))


def is_script_abandoned(name: str) -> bool:
    found = _find_entry(_load_state(), name)
    if not found:
        return False
    return bool(found[1].get("abandoned"))


def get_script_failure_info(name: str) -> dict[str, Any] | None:
    found = _find_entry(_load_state(), name)
    if not found:
        return None
    key, entry = found
    return {"storageKey": key, **entry}


def list_abandoned_scripts() -> list[dict[str, Any]]:
    scripts = _load_state().get("scripts")
    if not isinstance(scripts, dict):
        return []
    out: list[dict[str, Any]] = []
    for key, entry in scripts.items():
        if isinstance(entry, dict) and entry.get("abandoned"):
            out.append({"storageKey": key, **entry})
    out.sort(key=lambda x: str(x.get("abandonedAt", "")))
    return out


def restore_script(name: str) -> dict[str, Any]:
    state = _load_state()
    found = _find_entry(state, name)
    if not found:
        raise ValueError(f"未找到脚本 {name!r} 的失败记录")
    key, entry = found
    entry["abandoned"] = False
    entry["consecutiveFailures"] = 0
    entry["restoredAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    scripts = state["scripts"]
    if isinstance(scripts, dict):
        scripts[key] = entry
    _save_state(state)
    return {"ok": True, "restored": name, "entry": entry}


def record_script_run_outcome(
    *,
    name: str,
    kind: str,
    ok: bool,
    exit_code: int,
    reason: str | None = None,
    module: str | None = None,
    script_id: str | None = None,
) -> dict[str, Any]:
    state = _load_state()
    threshold = int(state.get("maxConsecutiveFailures", DEFAULT_MAX_CONSECUTIVE_FAILURES))
    scripts = state.setdefault("scripts", {})
    if not isinstance(scripts, dict):
        scripts = {}
        state["scripts"] = scripts

    found = _find_entry(state, name)
    storage_key = found[0] if found else str(script_id or name).strip()
    entry: dict[str, Any] = dict(found[1]) if found else {}

    entry.setdefault("name", name)
    entry.setdefault("kind", kind)
    if module:
        entry["module"] = module
    if script_id:
        entry["id"] = script_id

    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    entry["lastExitCode"] = exit_code
    entry["lastRunAt"] = now

    if ok:
        entry["consecutiveFailures"] = 0
        entry["lastSuccessAt"] = now
        entry.pop("lastFailureReason", None)
    else:
        consec = int(entry.get("consecutiveFailures", 0)) + 1
        entry["consecutiveFailures"] = consec
        entry["totalFailures"] = int(entry.get("totalFailures", 0)) + 1
        entry["lastFailedAt"] = now
        if reason:
            entry["lastFailureReason"] = reason
        if consec >= threshold:
            entry["abandoned"] = True
            entry["abandonedAt"] = now
            entry["abandonReason"] = (
                f"连续失败 {consec} 次（阈值 {threshold}）"
                + (f"：{reason}" if reason else "")
            )

    scripts[storage_key] = entry
    _save_state(state)
    return {
        "script": name,
        "ok": ok,
        "consecutiveFailures": entry.get("consecutiveFailures", 0),
        "abandoned": bool(entry.get("abandoned")),
        "threshold": threshold,
        "entry": entry,
    }


def failure_reason_from_result(result: dict[str, Any], exit_code: int) -> str:
    if exit_code == 0:
        return "ok"
    parts: list[str] = []
    if result.get("splashVerifyFailed"):
        parts.append("splashVerifyFailed")
    splash = result.get("splashVerify")
    if isinstance(splash, dict) and not splash.get("ok"):
        parts.append("splashVerify")
    if result.get("popupGateFailed"):
        parts.append("popupGateFailed")
    gate = result.get("popupGate")
    if isinstance(gate, dict) and (gate.get("blocked") or not gate.get("ok")):
        parts.append("popupGate")
    tv = result.get("tunnelVerify")
    if isinstance(tv, dict) and not tv.get("ok"):
        parts.append(f"tunnel:{tv.get('keyword', 'verify')}")
    fa = result.get("foregroundActivity")
    if isinstance(fa, dict) and fa.get("hint") in ("webview", "unknown", "visitor"):
        parts.append(f"hint={fa.get('hint')}")
    if not parts:
        parts.append(f"exitCode={exit_code}")
    return ";".join(parts)
