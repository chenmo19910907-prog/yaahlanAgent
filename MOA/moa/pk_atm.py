"""PK 提款机：解析最近 pkId（MOA / Tunnel）。"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]

_PK_ID_KEYS = ("pkId", "acrossRoomPkId", "roomPkId")
_TUNNEL_KEYWORDS = (
    "getPkAtmMatchRewardDetail",
    "closeAcrossRoomPk",
    "getAcrossRoomPkInfo",
    "applyAcrossRoomPk",
)


def _moa_business(res: dict[str, Any]) -> dict[str, Any]:
    inner = res.get("result")
    if isinstance(inner, dict):
        nested = inner.get("result")
        if isinstance(nested, dict):
            return nested
        return inner
    return res.get("business") if isinstance(res.get("business"), dict) else res


def _pk_id_from_obj(obj: Any) -> str | None:
    if not isinstance(obj, dict):
        return None
    for key in _PK_ID_KEYS:
        val = obj.get(key)
        if val:
            return str(val).strip()
    return None


def _run_generative_moa(method: str, body: dict[str, Any]) -> dict[str, Any]:
    proc = subprocess.run(
        [
            "python3",
            str(REPO / "MOA-generative/scripts/run_generative_moa.py"),
            "--url",
            "/service/room/external/room-pk-api",
            "--method",
            method,
            "--body-json",
            json.dumps(body, ensure_ascii=False, separators=(",", ":")),
            "--strict",
            "0",
        ],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    raw = (proc.stdout or "").strip()
    if not raw:
        raise RuntimeError((proc.stderr or "MOA 无输出")[-300:])
    return json.loads(raw)


def pk_id_from_across_room_pk_info(user_id: str, room_id: str) -> tuple[str | None, str]:
    body = {
        "userId": user_id,
        "roomId": room_id,
        "lang": "en",
        "area": "MENA",
        "appId": "2005",
        "os": "android",
        "osType": "android",
    }
    res = _run_generative_moa("getAcrossRoomPkInfo", body)
    biz = _moa_business(res)
    data = biz.get("data") if isinstance(biz.get("data"), dict) else {}
    pk_id = _pk_id_from_obj(data)
    stage = data.get("stage")
    if pk_id:
        return pk_id, f"getAcrossRoomPkInfo(stage={stage})"
    return None, "getAcrossRoomPkInfo(empty)"


def pk_id_from_tunnel(user_id: str, room_id: str, *, since: int = 7200) -> tuple[str | None, str]:
    for keyword in _TUNNEL_KEYWORDS:
        proc = subprocess.run(
            [
                "python3",
                str(REPO / "Tunnel/tunnel_execute.py"),
                "--momoid",
                user_id,
                "--keyword",
                keyword,
                "--since",
                str(since),
                "--output",
                "json",
            ],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
        if proc.returncode != 0:
            continue
        try:
            payload = json.loads(proc.stdout or "{}")
        except json.JSONDecodeError:
            continue
        lst = (payload.get("meta") or {}).get("list") or {}
        items = sorted(lst.values(), key=lambda x: x.get("time", ""), reverse=True)
        for item in items:
            req = item.get("request") if isinstance(item.get("request"), dict) else {}
            resp_data = (item.get("response") or {}).get("data")
            if not isinstance(resp_data, dict):
                resp_data = {}
            if str(req.get("roomId") or "") not in ("", room_id):
                continue
            pk_id = _pk_id_from_obj(req) or _pk_id_from_obj(resp_data)
            if pk_id:
                return pk_id, f"tunnel:{keyword}@{item.get('_id')}"
    return None, "tunnel(none)"


def resolve_latest_pk_id(
    user_id: str,
    room_id: str,
    *,
    since: int = 7200,
) -> tuple[str, str]:
    user_id = str(user_id).strip()
    room_id = str(room_id).strip()
    if not user_id or not room_id:
        raise ValueError("user_id / room_id 不能为空")

    pk_id, source = pk_id_from_across_room_pk_info(user_id, room_id)
    if pk_id:
        return pk_id, source

    pk_id, source = pk_id_from_tunnel(user_id, room_id, since=since)
    if pk_id:
        return pk_id, source

    raise RuntimeError(f"未找到 userId={user_id} roomId={room_id} 的最近 pkId")
