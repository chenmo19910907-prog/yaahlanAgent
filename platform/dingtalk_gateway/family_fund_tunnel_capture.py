#!/usr/bin/env python3
"""家族基金 Tunnel 抓包：家族主页 + 基金贡献榜 HTTP 接口。"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

CAPTURE_KEYWORDS = ("familyfund", "family/fund", "fundrank", "fundcontribution", "familyFund")


def build_capture_prompt(*, momoid: str, family_id: str, wait_seconds: int) -> dict[str, Any]:
    actions = [
        f"确认 Tunnel 已开启，抓包账号 userId = {momoid}",
        "在该账号设备上打开 Yaahlan App",
        f"进入家族主页（familyId={family_id}）",
        "打开「任务&奖励」→ 家族基金 tab，或点击基金进度条进入贡献榜",
        "下拉刷新，确保触发家族基金相关 HTTP 请求",
    ]
    return {
        "status": "awaiting_capture",
        "momoid": momoid,
        "familyId": family_id,
        "waitSeconds": max(0, int(wait_seconds)),
        "userActions": actions,
        "keywords": list(CAPTURE_KEYWORDS),
    }


def print_capture_prompt(**kwargs: Any) -> dict[str, Any]:
    payload = build_capture_prompt(**kwargs)
    banner = "=" * 62
    lines = ["", banner, "【需要抓包】请打开家族主页 + 家族基金贡献榜", banner]
    for i, step in enumerate(payload["userActions"], start=1):
        lines.append(f"  {i}. {step}")
    lines.extend(["", f"最长等待：{payload['waitSeconds']}s", banner, ""])
    print("\n".join(lines), flush=True)
    print(json.dumps({"capturePrompt": payload}, ensure_ascii=False), flush=True)
    return payload


def _list_tunnel_items(*, momoid: str, since: int) -> list[dict[str, Any]]:
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "Tunnel" / "tunnel_execute.py"),
            "--momoid",
            str(momoid),
            "--since",
            str(since),
            "--output",
            "json",
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return []
    try:
        body = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return []
    raw = body.get("list")
    if isinstance(raw, dict):
        return [v for v in raw.values() if isinstance(v, dict)]
    if isinstance(raw, list):
        return [v for v in raw if isinstance(v, dict)]
    return []


def find_family_fund_captures(
    *,
    momoid: str,
    since: int = 3600,
    family_id: str | None = None,
) -> list[dict[str, Any]]:
    items = _list_tunnel_items(momoid=momoid, since=since)
    hits: list[dict[str, Any]] = []
    fid = str(family_id or "").strip()
    for item in items:
        url = str(item.get("url") or "").lower()
        if not any(k.lower() in url for k in CAPTURE_KEYWORDS):
            continue
        if fid and fid not in json.dumps(item, ensure_ascii=False):
            continue
        hits.append(item)
    hits.sort(key=lambda x: str(x.get("time") or x.get("timestamp") or ""), reverse=True)
    return hits


def wait_for_family_fund_capture(
    *,
    momoid: str,
    family_id: str,
    wait_seconds: int = 120,
    poll_seconds: int = 5,
) -> list[dict[str, Any]]:
    print_capture_prompt(momoid=momoid, family_id=family_id, wait_seconds=wait_seconds)
    deadline = time.time() + max(0, int(wait_seconds))
    while time.time() < deadline:
        hits = find_family_fund_captures(momoid=momoid, since=max(600, wait_seconds + 60), family_id=family_id)
        if hits:
            return hits
        time.sleep(max(1, int(poll_seconds)))
    return []
