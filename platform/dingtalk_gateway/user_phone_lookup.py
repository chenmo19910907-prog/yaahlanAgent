"""Admin queryUserDetail → userId 对应手机号（钉钉落表 userId 后须跟手机号列）。"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]

from repo_paths import admin_execute_path  # noqa: E402


def _run_json(cmd: list[str]) -> dict:
    proc = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip()[-400:]
        raise RuntimeError(f"命令失败 {' '.join(cmd)}: {tail}")
    text = (proc.stdout or "").strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise RuntimeError(f"未解析到 JSON: {text[:200]}")
    return json.loads(text[start : end + 1])


def query_user_phone(user_id: str, cache: dict[str, str] | None = None) -> str:
    uid = str(user_id).strip()
    if not uid:
        return ""
    if cache is not None and uid in cache:
        return cache[uid]
    body = _run_json(
        [
            sys.executable,
            str(admin_execute_path()),
            "--query-user-id",
            uid,
        ]
    )
    user = body.get("user") if isinstance(body.get("user"), dict) else body
    phone = ""
    if isinstance(user, dict):
        phone = str(user.get("phone") or "").strip()
    if cache is not None:
        cache[uid] = phone
    return phone


def batch_user_phones(user_ids: Iterable[str]) -> dict[str, str]:
    cache: dict[str, str] = {}
    for uid in user_ids:
        query_user_phone(str(uid).strip(), cache)
    return cache
