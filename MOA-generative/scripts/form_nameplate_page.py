#!/usr/bin/env python3
"""查询用户铭牌页（nameplatePageData）：Tunnel 自动读取，无需人工验收。

HTTP：/yaahlan/userProfile/nameplatePageData
数据源：Tunnel 抓包库（Agent 自动查询；不要求测试员人工读数/核对）。
说明：gw-api 直连需 SESSIONID；MOA ServiceUrl 待确认。抓包可由 App 打开铭牌页产生一次，后续验收自动读 Tunnel。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
_HTTP_PATH = "/yaahlan/userProfile/nameplatePageData"
_TUNNEL_KEYWORD = "userProfile/nameplatePageData"
_TEMPLATE_BODY = _REPO / "MOA-generative/templates/example-nameplatePageData.body.json"
_CACHE_DIR = _REPO / ".tmp" / "nameplate_cache"
_DEFAULT_SINCE_TIERS = (7200, 86400, 604800)


def _safe_json_loads(raw: str) -> dict[str, Any]:
    raw = (raw or "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        if "{" not in raw:
            return {}
        return json.loads(raw[raw.find("{") : raw.rfind("}") + 1])


def _normalize_nameplate(item: dict[str, Any], *, unlocked: bool) -> dict[str, Any]:
    remain = item.get("remainTime")
    unlock = item.get("unlockTime")
    remain_days = round(float(remain) / 86400, 2) if isinstance(remain, (int, float)) and remain >= 0 else None
    unlock_label = None
    if isinstance(unlock, (int, float)) and unlock > 0:
        unlock_label = datetime.fromtimestamp(int(unlock), tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    return {
        "id": str(item.get("id") or ""),
        "title": item.get("title"),
        "subtitle": item.get("subtitle"),
        "unlockTime": unlock,
        "unlockTimeLabel": unlock_label,
        "remainTime": remain,
        "remainDays": remain_days,
        "wearState": item.get("wearState"),
        "progress": item.get("progress"),
        "count": item.get("count"),
        "unlocked": unlocked,
        "url": item.get("url"),
    }


def _summarize_page(data: dict[str, Any]) -> dict[str, Any]:
    unlocked = data.get("unlockedNameplates") if isinstance(data.get("unlockedNameplates"), list) else []
    locked = data.get("lockedNameplates") if isinstance(data.get("lockedNameplates"), list) else []
    by_id: dict[str, dict[str, Any]] = {}
    for item in unlocked:
        if isinstance(item, dict) and item.get("id") is not None:
            by_id[str(item["id"])] = _normalize_nameplate(item, unlocked=True)
    for item in locked:
        if isinstance(item, dict) and item.get("id") is not None:
            nid = str(item["id"])
            if nid not in by_id:
                by_id[nid] = _normalize_nameplate(item, unlocked=False)
    return {
        "unlockedCount": len(unlocked),
        "lockedCount": len(locked),
        "nameplates": by_id,
        "unlockedIds": [str(x.get("id")) for x in unlocked if isinstance(x, dict) and x.get("id") is not None],
    }


def _parse_tunnel_item(item: dict[str, Any]) -> dict[str, Any] | None:
    resp = item.get("response")
    if isinstance(resp, str):
        resp = _safe_json_loads(resp)
    if not isinstance(resp, dict):
        return None
    if resp.get("ec") not in (200, "200"):
        return None
    data = resp.get("data")
    return data if isinstance(data, dict) else None


def _cache_path(user_id: str) -> Path:
    return _CACHE_DIR / f"{user_id}.json"


def _write_cache(user_id: str, result: dict[str, Any]) -> None:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "cachedAt": datetime.now(timezone.utc).isoformat(),
        "userId": user_id,
        "source": result.get("source"),
        "tunnelRequestId": result.get("tunnelRequestId"),
        "tunnelTime": result.get("tunnelTime"),
        "nameplates": result.get("nameplates"),
        "unlockedCount": result.get("unlockedCount"),
        "lockedCount": result.get("lockedCount"),
        "unlockedIds": result.get("unlockedIds"),
        "raw": result.get("raw"),
    }
    _cache_path(user_id).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _read_cache(user_id: str) -> dict[str, Any] | None:
    path = _cache_path(user_id)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    plates = data.get("nameplates")
    if not isinstance(plates, dict) or not plates:
        return None
    return {
        "ok": True,
        "source": "cache",
        "userId": user_id,
        "cachedAt": data.get("cachedAt"),
        "tunnelRequestId": data.get("tunnelRequestId"),
        "tunnelTime": data.get("tunnelTime"),
        "nameplates": plates,
        "unlockedCount": data.get("unlockedCount"),
        "lockedCount": data.get("lockedCount"),
        "unlockedIds": data.get("unlockedIds"),
        "raw": data.get("raw"),
    }


def query_from_tunnel(user_id: str, *, since: int = 7200) -> dict[str, Any]:
    proc = subprocess.run(
        [
            "python3",
            str(_REPO / "Tunnel/tunnel_execute.py"),
            "--momoid",
            user_id,
            "--keyword",
            _TUNNEL_KEYWORD,
            "--since",
            str(since),
            "--limit",
            "200",
            "--output",
            "json",
        ],
        cwd=str(_REPO),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    stdout = proc.stdout or ""
    payload = _safe_json_loads(stdout)
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    for item in items:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "")
        if _TUNNEL_KEYWORD not in url:
            continue
        data = _parse_tunnel_item(item)
        if data is None:
            continue
        summary = _summarize_page(data)
        result = {
            "ok": True,
            "source": "tunnel",
            "userId": user_id,
            "tunnelSinceSec": since,
            "tunnelRequestId": item.get("id") or item.get("_id"),
            "tunnelTime": item.get("time"),
            "tunnelUrl": item.get("url"),
            **summary,
            "raw": data,
        }
        _write_cache(user_id, result)
        return result
    return {
        "ok": False,
        "source": "tunnel",
        "userId": user_id,
        "tunnelSinceSec": since,
        "error": f"Tunnel 近 {since}s 无 nameplatePageData 抓包",
    }


def query_auto(user_id: str, *, since_tiers: tuple[int, ...] = _DEFAULT_SINCE_TIERS) -> dict[str, Any]:
    """自动读 Tunnel（逐级扩大回溯窗口）→ 本地缓存兜底，无需人工参与验收。"""
    last: dict[str, Any] = {"ok": False, "userId": user_id}
    for since in since_tiers:
        result = query_from_tunnel(user_id, since=since)
        if result.get("ok"):
            result["autoSinceTiers"] = list(since_tiers)
            return result
        last = result
    cached = _read_cache(user_id)
    if cached:
        cached["autoSinceTiers"] = list(since_tiers)
        cached["fallback"] = "cache_after_tunnel_miss"
        return cached
    last["error"] = (
        f"Tunnel 无 nameplatePageData（已尝试 since={list(since_tiers)}），且无本地缓存。"
        "需 App 打开铭牌页产生一次抓包（仅需一次），之后验收全自动。"
    )
    return last


def main() -> int:
    parser = argparse.ArgumentParser(description="查询用户铭牌页（Tunnel 自动读取 nameplatePageData）")
    parser.add_argument("--user-id", required=True, help="userId")
    parser.add_argument("--since", type=int, default=0, help="Tunnel 回溯秒数；0=自动多级回溯")
    parser.add_argument("--nameplate-id", default="", help="仅输出指定铭牌 id（如 1138）")
    args = parser.parse_args()

    user_id = str(args.user_id).strip()
    if int(args.since) > 0:
        result = query_from_tunnel(user_id, since=int(args.since))
    else:
        result = query_auto(user_id)
    if args.nameplate_id and result.get("ok"):
        nid = str(args.nameplate_id).strip()
        plates = result.get("nameplates") if isinstance(result.get("nameplates"), dict) else {}
        picked = plates.get(nid)
        if picked:
            result["picked"] = picked
        else:
            result["ok"] = False
            result["error"] = f"铭牌 {nid} 未在 unlocked/locked 列表中"
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
