#!/usr/bin/env python3
"""家族 PK getFamilyPkPage 抓包：等待轮询 + 用户操作提示。"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

CAPTURE_API = "getFamilyPkPage"


def normalize_pk_date(pk_date: str) -> str:
    text = pk_date.strip()
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        return text
    raise ValueError(f"pk_date 须为 yyyy-MM-dd: {pk_date!r}")


def build_pk_page_capture_prompt(
    *,
    momoid: str,
    pk_date: str,
    wait_seconds: int,
    reason: str = "not_found",
) -> dict[str, Any]:
    target = normalize_pk_date(pk_date)
    actions = [
        f"确认 Tunnel 已开启，抓包账号 userId = {momoid}",
        "在该账号登录的设备上打开 Yaahlan App",
        "进入「家族 PK」页面",
        f"切换到日期 tab：{target}",
        "下拉刷新或退出后重新进入该 tab，以触发 getFamilyPkPage 请求",
    ]
    if reason == "prepare":
        headline = (
            f"即将读取 {CAPTURE_API}（pkDate={target}）。"
            f"若尚未抓包，请先完成下列操作；脚本将等待最多 {max(0, int(wait_seconds))}s。"
        )
    else:
        headline = (
            f"请在账号 {momoid} 的设备上打开家族 PK 页并切换到 {target}，"
            f"脚本将等待最多 {max(0, int(wait_seconds))}s 并自动读取 Tunnel 抓包。"
        )
    return {
        "status": "awaiting_capture",
        "reason": reason,
        "api": CAPTURE_API,
        "momoid": momoid,
        "pkDate": target,
        "waitSeconds": max(0, int(wait_seconds)),
        "userActions": actions,
        "message": headline,
    }


def print_capture_user_prompt(
    *,
    momoid: str,
    pk_date: str,
    wait_seconds: int,
    reason: str = "not_found",
) -> dict[str, Any]:
    """向 stdout 输出用户可执行的抓包操作说明（工作流/终端均可见）。"""
    payload = build_pk_page_capture_prompt(
        momoid=momoid,
        pk_date=pk_date,
        wait_seconds=wait_seconds,
        reason=reason,
    )
    banner = "=" * 62
    lines = [
        "",
        banner,
        "【需要抓包】请按下列步骤操作，完成后脚本将自动读取 Tunnel",
        banner,
    ]
    for index, step in enumerate(payload["userActions"], start=1):
        lines.append(f"  {index}. {step}")
    lines.extend(
        [
            "",
            f"接口：{CAPTURE_API}    PK 日期：{payload['pkDate']}    最长等待：{payload['waitSeconds']}s",
            banner,
            "",
        ]
    )
    text = "\n".join(lines)
    print(text, flush=True)
    print(json.dumps({"capturePrompt": payload}, ensure_ascii=False), flush=True)
    return payload


def _list_pk_page_tunnel_items(*, momoid: str, since: int) -> list[dict[str, Any]]:
    raw = subprocess.check_output(
        [
            sys.executable,
            str(REPO_ROOT / "Tunnel/tunnel_execute.py"),
            "--momoid",
            momoid,
            "--keyword",
            CAPTURE_API,
            "--since",
            str(since),
            "--output",
            "json",
        ],
        cwd=str(REPO_ROOT),
        text=True,
        stderr=subprocess.STDOUT,
    )
    payload = json.loads(raw)
    lst = payload.get("meta", {}).get("list", {}) or payload.get("data", {}).get("list", {})
    return [
        value
        for value in lst.values()
        if isinstance(value, dict)
        and CAPTURE_API in str(value.get("url", ""))
        and "UserList" not in str(value.get("url", ""))
    ]


def _request_pk_date(item: dict[str, Any]) -> str:
    req = item.get("request")
    if not isinstance(req, dict):
        return ""
    for key in ("date", "pkDate", "reqDate"):
        value = str(req.get(key) or "").strip()
        if len(value) >= 10 and value[4] == "-" and value[7] == "-":
            return value[:10]
    return ""


def _response_pk_date(item: dict[str, Any]) -> str:
    data = (item.get("response") or {}).get("data") or {}
    if not isinstance(data, dict):
        return ""
    value = str(data.get("date") or "").strip()
    if len(value) >= 10:
        return value[:10]
    return ""


def _parse_capture_time(text: str) -> float | None:
    value = str(text or "").strip()
    if not value:
        return None
    for fmt in ("%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt).timestamp()
        except ValueError:
            continue
    return None


def _pick_pk_page_capture(
    items: list[dict[str, Any]],
    pk_date: str,
    *,
    min_capture_epoch: float | None = None,
) -> dict[str, Any] | None:
    """按请求 date 匹配 pkDate；响应 data.date 常为当天，不能作为筛选依据。"""
    target = normalize_pk_date(pk_date)
    dated: list[dict[str, Any]] = []
    fallback: list[dict[str, Any]] = []
    for item in sorted(items, key=lambda row: str(row.get("time", "")), reverse=True):
        if min_capture_epoch is not None:
            captured_at = _parse_capture_time(str(item.get("time") or ""))
            if captured_at is None or captured_at < min_capture_epoch:
                continue
        data = (item.get("response") or {}).get("data") or {}
        if not isinstance(data, dict) or not data.get("pkList"):
            continue
        req_date = _request_pk_date(item)
        resp_date = _response_pk_date(item)
        if req_date == target or (not req_date and resp_date == target):
            dated.append(item)
        elif not req_date and resp_date != target:
            fallback.append(item)
    if dated:
        return dated[0]
    if fallback:
        return fallback[0]
    return None


def find_pk_page_capture(
    *,
    momoid: str,
    pk_date: str,
    since: int,
    wait_seconds: int = 0,
    poll_interval_ms: int = 3000,
    announce_wait: bool = True,
    min_capture_epoch: float | None = None,
) -> dict[str, Any]:
    """查找 getFamilyPkPage；wait_seconds>0 时提示用户操作并轮询 Tunnel。"""
    target = normalize_pk_date(pk_date)
    wait_seconds = max(0, int(wait_seconds))
    poll_interval_ms = max(500, int(poll_interval_ms))
    deadline = time.time() + wait_seconds if wait_seconds > 0 else time.time()
    wait_started = time.time()
    prompted = False
    polls = 0

    while True:
        polls += 1
        lookback = max(since, int(time.time() - wait_started) + 120)
        items = _list_pk_page_tunnel_items(momoid=momoid, since=lookback)
        hit = _pick_pk_page_capture(items, target, min_capture_epoch=min_capture_epoch)
        if hit is not None:
            if wait_seconds > 0 and polls > 1:
                print(
                    f"[抓包就绪] {CAPTURE_API} pkDate={target} capture={hit.get('_id')}",
                    flush=True,
                )
            return hit

        if wait_seconds <= 0 or time.time() >= deadline:
            break

        if not prompted:
            if announce_wait:
                print_capture_user_prompt(
                    momoid=momoid,
                    pk_date=target,
                    wait_seconds=wait_seconds,
                    reason="not_found",
                )
            prompted = True
        else:
            remaining = max(0, int(deadline - time.time()))
            print(f"[抓包等待] 轮询 #{polls}，剩余约 {remaining}s…", flush=True)

        time.sleep(poll_interval_ms / 1000.0)

    prompt = build_pk_page_capture_prompt(
        momoid=momoid,
        pk_date=target,
        wait_seconds=wait_seconds,
        reason="timeout" if wait_seconds > 0 else "not_found",
    )
    action_text = " → ".join(prompt["userActions"][:3])
    if wait_seconds > 0:
        raise RuntimeError(
            f"等待 {wait_seconds}s 后仍未找到 momoid={momoid} pkDate={target} 的 {CAPTURE_API}。"
            f"请确认已按提示操作：{action_text}"
        )
    raise RuntimeError(
        f"未找到 momoid={momoid} pkDate={target} 的 {CAPTURE_API}（since={since}s）。"
        f"请按提示抓包后重试（可加 --wait 180）：{action_text}"
    )
