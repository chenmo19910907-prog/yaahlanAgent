#!/usr/bin/env python3
"""PK 提款机测试：拉配置 → 随机匹配跨房 PK → 给房主送礼 → PK 赛况/对战验收 → 结算预期 → 结束 PK → 钻石到账验收 → 提款排名/吸底/本周总提款验收。

口径（2.5.9 PK 提款机）：
- 仅随机匹配跨房 PK（acrossPkType=1）计入提款机。
- 1 钻石礼物 = 10 PK 值；房间总 PK 来自 getAcrossRoomPkInfo roomRankValue / acrossRoomRankValue。
- 梯度发奖按双方总 PK 值（两房相加）匹配档位；个人瓜分 = (个人贡献 PK / 胜方总 PK) × 本场总奖金。
- PK 结束前用生成式 MOA 调 getAcrossRoomPkInfo 验收对战房间信息与 PK 值；并尝试活动页赛况列表接口。
- PK 结束后用生成式 MOA 尝试提款排名 tab：榜单序、吸底「本周已提款」、活动页「本周已被提走奖金」与钻石增量对齐（接口待抓包时默认跳过 MOA 层、保留钻石差值验收）。
"""

from __future__ import annotations

import argparse
import json
import math
import random
import subprocess
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class _WrongPkMatchError(Exception):
    """随机匹配配到了非目标房间。"""

    def __init__(self, *, pk_id: str, matched_room_id: str, expect_room_id: str) -> None:
        super().__init__(f"配到错误房间 {matched_room_id}，期望 {expect_room_id}")
        self.pk_id = pk_id
        self.matched_room_id = matched_room_id
        self.expect_room_id = expect_room_id


class _PkMatchExhaustedError(RuntimeError):
    """跨房 PK 随机匹配重试耗尽。"""

    def __init__(self, message: str, *, step: dict[str, Any]) -> None:
        super().__init__(message)
        self.step = step


MAX_CROSS_ROOM_MATCH_RETRIES = 3

REPO = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = REPO / "workflow/config/pk_atm_default_config.json"
PK_API = "/service/room/external/room-pk-api"
GIFT_ID_ROSE = "2005000233"

# MOA 配置接口候选（映射登记后可自动命中）
_CONFIG_CANDIDATES: list[tuple[str, str]] = [
    ("/service/room/external/room-pk-api", "getAcrossRoomPkWithdrawConfig"),
    ("/service/room/external/room-pk-api", "getPkWithdrawConfig"),
    ("/service/room/external/room-pk-api", "getAcrossRoomPkAtmConfig"),
    ("/service/vas/activity/across-room-pk-withdraw-v2-api", "getConfig"),
    ("/service/vas/activity/across-room-pk-withdraw-v2-api", "home"),
    ("/service/vas/activity/pk-withdraw-v2-api", "getConfig"),
]

# PK 提款机活动页「赛况/Reward」tab（H5 pkNew Reward → getAcrossPkMatchStatusV2）
_SITUATION_LIST_CANDIDATES: list[tuple[str, str]] = [
    ("/service/room/external/room-pk-api", "getAcrossPkMatchStatusV2"),
    ("/service/room/external/room-pk-api", "getAcrossPkMatchStatus"),
    ("/service/vas/activity/across-room-pk-withdraw-v2-api", "getPkSituationList"),
    ("/service/vas/activity/across-room-pk-withdraw-v2-api", "getPkStatusList"),
    ("/service/vas/activity/pk-withdraw-api", "getPkSituationList"),
]

# PK 提款机活动页「提款排名」tab + 本周总提款 / 吸底候选
_WITHDRAW_RANK_CANDIDATES: list[tuple[str, str]] = [
    ("/service/room/external/room-pk-api", "getAcrossPkRewardRankV2"),
    ("/service/room/external/room-pk-api", "getAcrossRoomPkWithdrawRankList"),
    ("/service/room/external/room-pk-api", "getAcrossRoomPkWithdrawRank"),
    ("/service/room/external/room-pk-api", "getAcrossRoomPkWithdrawPage"),
    ("/service/room/external/room-pk-api", "getAcrossRoomPkWithdrawData"),
    ("/service/room/external/room-pk-api", "getAcrossRoomPkWithdrawHome"),
    ("/service/vas/activity/across-room-pk-withdraw-v2-api", "home"),
    ("/service/vas/activity/across-room-pk-withdraw-v2-api", "getWithdrawRankList"),
    ("/service/vas/activity/across-room-pk-withdraw-v2-api", "getWithdrawRank"),
    ("/service/vas/activity/pk-withdraw-v2-api", "getWithdrawRankList"),
    ("/service/vas/activity/pk-withdraw-api", "getWithdrawRankList"),
]

DEFAULT_SENDERS = [
    "100465989", "100486375", "100305533", "100007541", "100414599",
    "100379555", "100108670", "100098146", "100121433", "100066819",
    "100164872", "100325190", "100226835", "100461468", "100295328",
    "100122125", "100305358", "100164559", "100067135", "100434454",
]

# 造数固定双房（Admin/Tunnel 不可用时兜底，避免两号解析到同一 roomId）
_KNOWN_PHONE_ROOMS: dict[str, tuple[str, str]] = {
    "13311111111": ("100465989", "38826842"),
    "13311111115": ("100305533", "83652563"),
    "13311111112": ("100486375", "31668628"),
    "13311111113": ("100079102", "50861924"),
    "13311111114": ("100006869", "80949067"),
}


@dataclass
class RoomParty:
    phone: str
    user_id: str
    room_id: str


@dataclass
class PkAtmConfig:
    source: str
    min_combined_pk: int
    personal_pk_threshold: int
    first_win_multiplier: int
    tiers: list[dict[str, Any]]
    raw: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "minCombinedPk": self.min_combined_pk,
            "personalPkThreshold": self.personal_pk_threshold,
            "firstWinMultiplier": self.first_win_multiplier,
            "tiers": self.tiers,
            "raw": self.raw,
        }


def _run_json(cmd: list[str], *, timeout: int = 180) -> dict[str, Any]:
    proc = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, timeout=timeout)
    out = (proc.stdout or "").strip()
    if not out:
        raise RuntimeError(f"empty stdout: {' '.join(cmd)}\nstderr={proc.stderr}")
    return json.loads(out)


def _moa_on(service: str, method: str, body: dict[str, Any], *, strict: int = 0) -> dict[str, Any]:
    tmp = REPO / ".tmp" / "pk_atm_moa"
    tmp.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex[:12]
    body_file = tmp / f"{method}.{token}.body.json"
    out_file = tmp / f"{method}.{token}.payload.json"
    body_file.write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        return _run_json(
            [
                sys.executable,
                "MOA-generative/scripts/run_generative_moa.py",
                "--url",
                service,
                "--method",
                method,
                "--body-file",
                str(body_file),
                "--out",
                str(out_file),
                "--timeout-ms",
                "20000",
                "--strict",
                str(strict),
            ]
        )
    finally:
        body_file.unlink(missing_ok=True)
        out_file.unlink(missing_ok=True)


def _moa(method: str, body: dict[str, Any], *, strict: int = 0) -> dict[str, Any]:
    return _moa_on(PK_API, method, body, strict=strict)


def _query_diamond(user_id: str) -> int | None:
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    from workflow.scripts.reward_verify import query_diamond  # noqa: WPS433

    return query_diamond(user_id)


def _load_default_config_file(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _normalize_tiers(raw_tiers: Any) -> list[dict[str, Any]]:
    tiers: list[dict[str, Any]] = []
    if not isinstance(raw_tiers, list):
        return tiers
    for item in raw_tiers:
        if not isinstance(item, dict):
            continue
        max_pk = (
            item.get("maxCombinedPk")
            or item.get("maxPk")
            or item.get("pkThreshold")
            or item.get("thresholdPk")
            or item.get("totalPk")
            or item.get("pk")
        )
        pool = item.get("poolDiamonds") or item.get("rewardDiamonds") or item.get("diamonds") or item.get("reward")
        ratio = item.get("ratioPct") or item.get("ratio") or item.get("rate")
        if max_pk is None or pool is None:
            continue
        tiers.append(
            {
                "maxCombinedPk": int(max_pk),
                "poolDiamonds": int(pool),
                "ratioPct": float(ratio) if ratio is not None else None,
            }
        )
    tiers.sort(key=lambda x: x["maxCombinedPk"])
    return tiers


def _parse_config_from_moa_data(data: dict[str, Any]) -> PkAtmConfig | None:
    if not data:
        return None
    tiers = _normalize_tiers(
        data.get("tiers")
        or data.get("tierList")
        or data.get("gradientList")
        or data.get("rewardTiers")
        or data.get("pkTierList")
    )
    if not tiers:
        return None
    min_combined = (
        data.get("minCombinedPk")
        or data.get("minTotalPk")
        or data.get("roomMinPk")
        or data.get("minPkForReward")
        or tiers[0]["maxCombinedPk"]
    )
    personal = (
        data.get("personalPkThreshold")
        or data.get("personalMinPk")
        or data.get("userMinPk")
        or data.get("minPersonalPk")
        or data.get("personalThreshold")
        or 0
    )
    first_win = int(data.get("firstWinMultiplier") or data.get("firstWinRate") or 2)
    return PkAtmConfig(
        source="moa",
        min_combined_pk=int(min_combined),
        personal_pk_threshold=int(personal),
        first_win_multiplier=first_win,
        tiers=tiers,
        raw=data,
    )


def _fetch_service_config(party: RoomParty) -> tuple[PkAtmConfig | None, list[dict[str, Any]]]:
    body = {
        "userId": party.user_id,
        "roomId": party.room_id,
        "lang": "en",
        "area": "MENA",
        "appId": "2005",
        "os": "android",
        "osType": "android",
    }
    attempts: list[dict[str, Any]] = []
    for service, method in _CONFIG_CANDIDATES:
        try:
            res = _moa_on(service, method, body, strict=0)
        except (RuntimeError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
            attempts.append({"service": service, "method": method, "error": str(exc)})
            continue
        biz = res.get("business") or {}
        ec = biz.get("ec")
        data = biz.get("data") if isinstance(biz.get("data"), dict) else None
        attempts.append({"service": service, "method": method, "ec": ec, "hasData": bool(data)})
        if ec in (200, "200", 0, "0") and data:
            parsed = _parse_config_from_moa_data(data)
            if parsed:
                parsed.source = f"moa:{service}#{method}"
                parsed.raw = data
                return parsed, attempts
    return None, attempts


def _resolve_config(args: argparse.Namespace, party: RoomParty) -> tuple[PkAtmConfig, list[dict[str, Any]]]:
    attempts: list[dict[str, Any]] = []
    moa_cfg: PkAtmConfig | None = None
    if not args.skip_config_fetch:
        moa_cfg, attempts = _fetch_service_config(party)

    file_path = Path(args.config_file) if args.config_file else DEFAULT_CONFIG_PATH
    if not file_path.is_absolute():
        file_path = REPO / file_path
    file_data = _load_default_config_file(file_path)

    if moa_cfg:
        cfg = moa_cfg
    else:
        tiers = _normalize_tiers(file_data.get("tiers"))
        if not tiers:
            tiers = _normalize_tiers(
                [
                    {"maxCombinedPk": 500_000, "poolDiamonds": 2_000, "ratioPct": 4},
                    {"maxCombinedPk": 3_000_000, "poolDiamonds": 12_000, "ratioPct": 4},
                    {"maxCombinedPk": 8_000_000, "poolDiamonds": 40_000, "ratioPct": 5},
                    {"maxCombinedPk": 15_000_000, "poolDiamonds": 75_000, "ratioPct": 5},
                    {"maxCombinedPk": 25_000_000, "poolDiamonds": 150_000, "ratioPct": 6},
                    {"maxCombinedPk": 40_000_000, "poolDiamonds": 240_000, "ratioPct": 6},
                ]
            )
        cfg = PkAtmConfig(
            source=f"file:{file_path.name}",
            min_combined_pk=int(file_data.get("minCombinedPk") or tiers[0]["maxCombinedPk"]),
            personal_pk_threshold=int(file_data.get("personalPkThreshold") or 0),
            first_win_multiplier=int(file_data.get("firstWinMultiplier") or 2),
            tiers=tiers,
            raw=file_data or None,
        )

    if args.min_combined_pk is not None:
        cfg.min_combined_pk = int(args.min_combined_pk)
    if args.personal_pk_threshold is not None:
        cfg.personal_pk_threshold = int(args.personal_pk_threshold)
    return cfg, attempts


def _resolve_party(phone: str) -> RoomParty:
    known = _KNOWN_PHONE_ROOMS.get(phone.strip())
    if known:
        user_id, room_id = known
        return RoomParty(phone=phone, user_id=user_id, room_id=room_id)

    proc = subprocess.run(
        [
            sys.executable,
            "MOA/moa_execute.py",
            "--payload-file",
            "MOA/templates/用户-按手机号查userId.json",
            "--query-user-by-phone",
            phone,
            "--phone-output",
            "summary",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=60,
    )
    raw = proc.stdout or ""
    start = raw.find("{")
    if start < 0:
        raise RuntimeError(f"手机号 {phone} 查 userId 失败: {raw}\n{proc.stderr}")
    data = json.loads(raw[start:])
    user_id = str(data.get("userId") or "")
    if not user_id:
        inner = data.get("result") or {}
        if isinstance(inner, dict):
            nested = inner.get("result") if isinstance(inner.get("result"), dict) else inner
            if isinstance(nested, dict):
                user_id = str(nested.get("data") or nested.get("userId") or "")
    if not user_id:
        raise RuntimeError(f"手机号 {phone} 未解析到 userId: {data}")

    admin = _run_json(
        [sys.executable, "Admin/admin_execute.py", "--query-user-id", user_id],
        timeout=60,
    )
    owned = admin.get("ownedRoomInfo") if isinstance(admin.get("ownedRoomInfo"), dict) else {}
    room_id = str(admin.get("roomId") or owned.get("roomId") or "")
    if not room_id:
        tun = _run_json(
            [
                sys.executable,
                "Tunnel/tunnel_execute.py",
                "--momoid",
                user_id,
                "--keyword",
                "heartbeat",
                "--since",
                "86400",
                "--output",
                "json",
            ],
            timeout=90,
        )
        lst = (tun.get("meta") or {}).get("list") or {}
        for item in sorted(lst.values(), key=lambda x: x.get("time", ""), reverse=True):
            req = item.get("request") if isinstance(item.get("request"), dict) else {}
            rid = str(req.get("roomId") or "").strip()
            if rid:
                room_id = rid
                break
    if not room_id:
        raise RuntimeError(f"userId {user_id}（{phone}）无 roomId（Admin/Tunnel 均未取到）")
    return RoomParty(phone=phone, user_id=user_id, room_id=room_id)


def _query_admin_user(user_id: str) -> dict[str, Any]:
    return _run_json(
        [sys.executable, "Admin/admin_execute.py", "--query-user-id", user_id],
        timeout=60,
    )


def _tunnel_items(user_id: str, *, keyword: str, since_seconds: int) -> list[dict[str, Any]]:
    tun = _run_json(
        [
            sys.executable,
            "Tunnel/tunnel_execute.py",
            "--momoid",
            user_id,
            "--keyword",
            keyword,
            "--since",
            str(max(30, since_seconds)),
            "--output",
            "json",
        ],
        timeout=90,
    )
    lst = (tun.get("meta") or {}).get("list") or {}
    if not isinstance(lst, dict):
        return []
    return sorted(lst.values(), key=lambda x: x.get("time", ""), reverse=True)


def _room_id_from_tunnel_item(item: dict[str, Any]) -> str:
    req = item.get("request") if isinstance(item.get("request"), dict) else {}
    return str(req.get("roomId") or "").strip()


def _tunnel_current_room_id(user_id: str, *, since_seconds: int = 300) -> tuple[str | None, dict[str, Any]]:
    """从最近 heartbeat / enterRoom 抓包推断当前所在房间。"""
    for keyword in ("heartbeat", "enterRoom", "room/enter"):
        try:
            items = _tunnel_items(user_id, keyword=keyword, since_seconds=since_seconds)
        except (RuntimeError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
            return None, {"keyword": keyword, "error": str(exc)}
        for item in items:
            room_id = _room_id_from_tunnel_item(item)
            if room_id:
                return room_id, {
                    "keyword": keyword,
                    "time": item.get("time"),
                    "url": item.get("url"),
                    "requestId": item.get("_id"),
                }
    return None, {"reason": f"近 {since_seconds}s 无 heartbeat/enterRoom 带 roomId"}


def _admin_profile(user_id: str) -> dict[str, Any]:
    try:
        raw = _query_admin_user(user_id)
    except (RuntimeError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
        return {"error": str(exc)}
    if not isinstance(raw, dict):
        return {"error": "invalid_admin_response"}
    data = raw.get("data") if isinstance(raw.get("data"), dict) else raw
    profile = data.get("userProfile") if isinstance(data.get("userProfile"), dict) else {}
    owned = data.get("ownedRoomInfo") if isinstance(data.get("ownedRoomInfo"), dict) else {}
    online_status = profile.get("onlineStatus")
    if online_status is None and isinstance(data, dict):
        online_status = data.get("onlineStatus")
    return {
        "ec": raw.get("ec"),
        "onlineStatus": online_status,
        "ownedRoomId": owned.get("roomId") or data.get("roomId"),
    }


def _check_party_logged_in_own_room(party: RoomParty, *, since_seconds: int = 300) -> dict[str, Any]:
    admin = _admin_profile(party.user_id)
    online_status = admin.get("onlineStatus")
    admin_online = online_status in (1, "1") if online_status is not None else None

    current_room_id, tunnel_meta = _tunnel_current_room_id(party.user_id, since_seconds=since_seconds)
    in_own_room = current_room_id == party.room_id
    has_client_session = bool(current_room_id)

    issues: list[str] = []
    if not has_client_session:
        if admin_online is True:
            issues.append(
                f"Admin 显示在线但近 {since_seconds}s 无房内心跳，请打开 App 并进入自己的房间"
            )
        else:
            issues.append(f"未登录或 App 未在房间内（近 {since_seconds}s 无 heartbeat/enterRoom）")
    elif not in_own_room:
        issues.append(f"不在自己的房间(当前={current_room_id}, 期望={party.room_id})")

    logged_in = admin_online is True or has_client_session
    ok = has_client_session and in_own_room

    return {
        "phone": party.phone,
        "userId": party.user_id,
        "ownRoomId": party.room_id,
        "onlineStatus": online_status,
        "adminOnline": admin_online,
        "loggedIn": logged_in,
        "currentRoomId": current_room_id,
        "inOwnRoom": in_own_room,
        "tunnel": tunnel_meta,
        "admin": {k: admin.get(k) for k in ("ec", "onlineStatus", "ownedRoomId", "error") if k in admin},
        "ok": ok,
        "issues": issues,
    }


def _ensure_parties_ready_for_match(
    party_a: RoomParty,
    party_b: RoomParty,
    *,
    since_seconds: int = 300,
) -> list[dict[str, Any]]:
    """跨房 PK 随机匹配前：双方须 App 已登录且在自己的房间内（Admin 在线 + Tunnel heartbeat）。"""
    checks = [
        _check_party_logged_in_own_room(party_a, since_seconds=since_seconds),
        _check_party_logged_in_own_room(party_b, since_seconds=since_seconds),
    ]
    bad = [c for c in checks if not c.get("ok")]
    if bad:
        detail = "; ".join(
            f"{c['phone']}({c['userId']}): {', '.join(c.get('issues') or ['未知'])}"
            for c in bad
        )
        raise RuntimeError(
            "跨房 PK 匹配前须双方账号已登录且在自己的房间内: "
            f"{detail}。"
            "请先真机登录并进自己的房间，例如："
            f"`python3 adb/adb_execute.py macro 手机号登录 --text {party_a.phone}` + "
            f"`python3 adb/adb_execute.py macro 搜索进房 --text {party_a.room_id}`"
            f"（B 方同理）。"
        )
    return checks


def _pk_info(party: RoomParty, *, pk_id: str | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {
        "userId": party.user_id,
        "roomId": party.room_id,
        "lang": "en",
        "area": "MENA",
        "appId": "2005",
        "os": "android",
        "osType": "android",
    }
    if pk_id:
        body["acrossRoomPkId"] = pk_id
    res = _moa("getAcrossRoomPkInfo", body, strict=0)
    return (res.get("business") or {}).get("data") or {}


def _room_info_from_pk_block(block: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(block, dict):
        return {}
    return {
        "roomId": str(block.get("roomId") or ""),
        "roomName": str(block.get("roomName") or block.get("name") or ""),
        "roomAvatar": str(block.get("roomAvatar") or block.get("avatar") or block.get("icon") or ""),
    }


def _extract_situation_items(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if not isinstance(data, dict):
        return []
    for key in (
        "acrossPkList",
        "pkSituationList",
        "pkStatusList",
        "situationList",
        "ongoingPkList",
        "ongoingList",
        "pkList",
        "list",
        "items",
        "records",
    ):
        val = data.get(key)
        if isinstance(val, list) and val and isinstance(val[0], dict):
            return val
    return []


def _situation_pk_id(item: dict[str, Any]) -> str:
    for key in ("acrossRoomPKId", "acrossRoomPkId", "pkId", "roomPkId", "id"):
        val = item.get(key)
        if val:
            return str(val)
    return ""


def _situation_room_side(item: dict[str, Any], side: str) -> dict[str, Any]:
    side_keys = {
        "left": ("left", "leftRoom", "redRoom", "fromRoom", "roomInfo", "currentRoomInfo"),
        "right": ("right", "rightRoom", "blueRoom", "toRoom", "acrossRoomInfo", "targetRoomInfo"),
    }
    for key in side_keys.get(side, ()):
        block = item.get(key)
        if not isinstance(block, dict):
            continue
        pk_val = block.get("pkValue") or block.get("value") or block.get("roomRankValue") or block.get("pk")
        return {
            **_room_info_from_pk_block(block),
            "pkValue": int(pk_val or 0),
        }
    return {}


def _fetch_pk_situation_list(party: RoomParty) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    body = {
        "userId": party.user_id,
        "roomId": party.room_id,
        "lang": "en",
        "area": "MENA",
        "appId": "2005",
        "os": "android",
        "osType": "android",
    }
    attempts: list[dict[str, Any]] = []
    for service, method in _SITUATION_LIST_CANDIDATES:
        try:
            res = _moa_on(service, method, body, strict=0)
        except (RuntimeError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
            attempts.append({"service": service, "method": method, "error": str(exc)})
            continue
        biz = res.get("business") or {}
        ec = biz.get("ec")
        data = biz.get("data")
        items = _extract_situation_items(data)
        attempts.append({"service": service, "method": method, "ec": ec, "itemCount": len(items)})
        if ec in (200, "200", 0, "0") and items:
            return items, attempts
    return [], attempts


def _verify_pk_battle_and_values(
    party_a: RoomParty,
    party_b: RoomParty,
    pk_id: str,
    info_a: dict[str, Any],
    *,
    min_stage: int = 2,
    max_stage: int = 3,
) -> dict[str, Any]:
    """PK 结束前：生成式 MOA getAcrossRoomPkInfo 验收 PK 中/惩罚阶段对战信息与 PK 值。"""
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: Any = None) -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})

    info_b = _pk_info(party_b, pk_id=pk_id)

    stage = int(info_a.get("stage") or 0)
    add(
        "stage_pk_in_progress",
        min_stage <= stage <= max_stage,
        {"stage": stage, "expect": f"{min_stage}-{max_stage}"},
    )
    add("pk_id_match", str(info_a.get("acrossRoomPkId") or "") == pk_id, info_a.get("acrossRoomPkId"))

    cur_a = info_a.get("currentRoomInfo") or {}
    across_a = info_a.get("acrossRoomInfo") or {}
    cur_b = info_b.get("currentRoomInfo") or {}
    across_b = info_b.get("acrossRoomInfo") or {}

    add("room_a_id", str(cur_a.get("roomId") or "") == party_a.room_id, cur_a.get("roomId"))
    add("room_b_id", str(across_a.get("roomId") or "") == party_b.room_id, across_a.get("roomId"))
    add(
        "room_a_name_avatar",
        bool(cur_a.get("roomName") and cur_a.get("roomAvatar")),
        _room_info_from_pk_block(cur_a),
    )
    add(
        "room_b_name_avatar",
        bool(across_a.get("roomName") and across_a.get("roomAvatar")),
        _room_info_from_pk_block(across_a),
    )

    room_a_pk = int(info_a.get("roomRankValue") or 0)
    room_b_pk = int(info_a.get("acrossRoomRankValue") or 0)
    room_a_pk_from_b = int(info_b.get("acrossRoomRankValue") or 0)
    room_b_pk_from_b = int(info_b.get("roomRankValue") or 0)

    add("pk_values_non_negative", room_a_pk >= 0 and room_b_pk >= 0, {"roomA": room_a_pk, "roomB": room_b_pk})
    add(
        "pk_values_cross_view_a",
        room_a_pk == room_a_pk_from_b,
        {"fromA": room_a_pk, "fromB_opponent": room_a_pk_from_b},
    )
    add(
        "pk_values_cross_view_b",
        room_b_pk == room_b_pk_from_b,
        {"fromA": room_b_pk, "fromB": room_b_pk_from_b},
    )
    add(
        "b_view_rooms",
        str(cur_b.get("roomId") or "") == party_b.room_id
        and str(across_b.get("roomId") or "") == party_a.room_id,
        {"current": cur_b.get("roomId"), "across": across_b.get("roomId")},
    )

    ok = all(c["ok"] for c in checks)
    return {
        "ok": ok,
        "checks": checks,
        "stage": stage,
        "roomA": {"roomId": party_a.room_id, "pkValue": room_a_pk, **_room_info_from_pk_block(cur_a)},
        "roomB": {"roomId": party_b.room_id, "pkValue": room_b_pk, **_room_info_from_pk_block(across_a)},
        "combinedPk": room_a_pk + room_b_pk,
        "infoBStage": int(info_b.get("stage") or 0),
    }


def _verify_pk_situation_list_item(
    items: list[dict[str, Any]],
    pk_id: str,
    party_a: RoomParty,
    party_b: RoomParty,
    expected_a_pk: int,
    expected_b_pk: int,
) -> dict[str, Any]:
    matched: dict[str, Any] | None = None
    for item in items:
        if _situation_pk_id(item) == pk_id:
            matched = item
            break
        left = _situation_room_side(item, "left")
        right = _situation_room_side(item, "right")
        room_ids = {left.get("roomId"), right.get("roomId")}
        if party_a.room_id in room_ids and party_b.room_id in room_ids:
            matched = item
            break

    if not matched:
        return {"ok": False, "reason": "赛况列表未找到本场 PK", "listSize": len(items)}

    left = _situation_room_side(matched, "left")
    right = _situation_room_side(matched, "right")
    by_room = {left.get("roomId"): left, right.get("roomId"): right}
    item_a = by_room.get(party_a.room_id) or {}
    item_b = by_room.get(party_b.room_id) or {}

    checks: list[dict[str, Any]] = []
    for name, cond, detail in [
        ("situation_room_a", bool(item_a.get("roomName") and item_a.get("roomAvatar")), item_a),
        ("situation_room_b", bool(item_b.get("roomName") and item_b.get("roomAvatar")), item_b),
        (
            "situation_pk_a",
            int(item_a.get("pkValue") or 0) == expected_a_pk,
            {"list": item_a.get("pkValue"), "expected": expected_a_pk},
        ),
        (
            "situation_pk_b",
            int(item_b.get("pkValue") or 0) == expected_b_pk,
            {"list": item_b.get("pkValue"), "expected": expected_b_pk},
        ),
    ]:
        checks.append({"name": name, "ok": cond, "detail": detail})

    return {"ok": all(c["ok"] for c in checks), "checks": checks, "matchedItem": matched}


def _verify_pk_status_before_close(
    party_a: RoomParty,
    party_b: RoomParty,
    pk_id: str,
    info_a: dict[str, Any],
    *,
    require_situation_list: bool,
) -> dict[str, Any]:
    battle = _verify_pk_battle_and_values(party_a, party_b, pk_id, info_a)
    result: dict[str, Any] = {
        "ok": battle["ok"],
        "battleVerify": battle,
        "moaMethod": "getAcrossRoomPkInfo",
    }

    items, attempts = _fetch_pk_situation_list(party_a)
    result["situationListAttempts"] = attempts
    if items:
        situation = _verify_pk_situation_list_item(
            items,
            pk_id,
            party_a,
            party_b,
            int(battle["roomA"]["pkValue"]),
            int(battle["roomB"]["pkValue"]),
        )
        result["situationListVerify"] = situation
        result["situationListAvailable"] = True
        result["ok"] = battle["ok"] and situation["ok"]
    else:
        result["situationListAvailable"] = False
        result["situationListSkipped"] = (
            "活动页赛况列表接口未返回数据（测试环境 across-room-pk-withdraw-v2-api 可能未注册 MSE 路由）"
        )
        if require_situation_list:
            result["ok"] = False
            result["error"] = result["situationListSkipped"]

    return result


def _withdraw_rank_body(party: RoomParty, *, viewer_user_id: str | None = None) -> dict[str, Any]:
    uid = viewer_user_id or party.user_id
    return {
        "userId": uid,
        "uid": uid,
        "cycle": "1",
        "lang": "en",
        "area": "MENA",
        "appId": "2005",
        "os": "android",
        "osType": "android",
        "originRsp": 1,
        "dataType": "json",
        "_version_": 1000,
    }


def _fetch_withdraw_rank_page(
    party: RoomParty, *, viewer_user_id: str | None = None
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], str | None]:
    body = _withdraw_rank_body(party, viewer_user_id=viewer_user_id)
    attempts: list[dict[str, Any]] = []
    for service, method in _WITHDRAW_RANK_CANDIDATES:
        try:
            res = _moa_on(service, method, body, strict=0)
        except (RuntimeError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
            attempts.append({"service": service, "method": method, "error": str(exc)})
            continue
        biz = res.get("business") or {}
        ec = biz.get("ec")
        data = biz.get("data")
        attempts.append(
            {
                "service": service,
                "method": method,
                "ec": ec,
                "hasData": isinstance(data, dict),
            }
        )
        if ec in (200, "200", 0, "0") and isinstance(data, dict):
            return data, attempts, f"{service}#{method}"
    return None, attempts, None


def _extract_withdraw_rank_list(data: dict[str, Any]) -> list[dict[str, Any]]:
    for key in (
        "withdrawRankList",
        "rankList",
        "userRankList",
        "list",
        "records",
        "topList",
    ):
        val = data.get(key)
        if isinstance(val, list) and val and isinstance(val[0], dict):
            return val
    return []


def _rank_entry_user_id(item: dict[str, Any]) -> str:
    for key in ("userId", "uid", "momoid", "id"):
        val = item.get(key)
        if val:
            return str(val)
    user_info = item.get("userInfo")
    if isinstance(user_info, dict) and user_info.get("userId"):
        return str(user_info["userId"])
    return ""


def _rank_entry_withdraw_diamonds(item: dict[str, Any]) -> int:
    for key in (
        "rewardValue",
        "withdrawDiamonds",
        "weekWithdrawDiamonds",
        "receiveDiamonds",
        "rewardDiamonds",
        "diamonds",
        "diamond",
        "amount",
        "value",
    ):
        val = item.get(key)
        if val is not None:
            try:
                return int(val)
            except (TypeError, ValueError):
                continue
    return 0


def _rank_entry_rank_num(item: dict[str, Any], fallback: int) -> int:
    for key in ("rank", "rankNum", "rankNo", "position"):
        val = item.get(key)
        if val is not None:
            try:
                return int(val)
            except (TypeError, ValueError):
                continue
    return fallback


def _extract_sticky_withdraw(data: dict[str, Any]) -> dict[str, Any]:
    blocks: list[dict[str, Any]] = []
    for key in ("selfRank", "myRank", "bottomInfo", "stickyBottom", "currentUser", "userRank", "self"):
        block = data.get(key)
        if isinstance(block, dict):
            blocks.append(block)
    if isinstance(data.get("current"), dict):
        blocks.append(data["current"])

    for block in blocks:
        week = None
        for key in (
            "rewardValue",
            "weekWithdrawDiamonds",
            "withdrawDiamonds",
            "weekWithdraw",
            "receiveDiamonds",
            "rewardDiamonds",
            "diamonds",
        ):
            if block.get(key) is not None:
                try:
                    week = int(block[key])
                    break
                except (TypeError, ValueError):
                    continue
        rank = None
        for key in ("rank", "currentRank", "rankNum", "rankNo"):
            if block.get(key) is not None:
                try:
                    rank = int(block[key])
                    break
                except (TypeError, ValueError):
                    continue
        if week is not None or rank is not None:
            return {"weekWithdraw": week, "rank": rank, "source": block}
    return {}


def _extract_week_total_withdrawn(data: dict[str, Any]) -> int | None:
    for key in (
        "totalReward",
        "weekTotalWithdrawDiamonds",
        "weekWithdrawTotal",
        "weekTotalDiamonds",
        "totalWithdrawDiamonds",
        "weekRewardTotal",
        "totalRewardDiamonds",
        "weekWithdrawnTotal",
        "weekTotalWithdraw",
    ):
        val = data.get(key)
        if val is not None:
            try:
                return int(val)
            except (TypeError, ValueError):
                continue
    return None


def _snapshot_withdraw_rank_context(
    party: RoomParty,
    user_ids: list[str],
) -> dict[str, Any]:
    """拉取提款排名页：本周总提款（房主视角）+ 各用户吸底「本周已提款」。"""
    page_data, attempts, method = _fetch_withdraw_rank_page(party)
    out: dict[str, Any] = {
        "apiAvailable": page_data is not None,
        "method": method,
        "attempts": attempts,
        "weekTotalWithdraw": _extract_week_total_withdrawn(page_data) if page_data else None,
        "rankListSize": len(_extract_withdraw_rank_list(page_data)) if page_data else 0,
        "users": {},
    }
    if not page_data:
        return out

    rank_list = _extract_withdraw_rank_list(page_data)
    rank_by_uid = {_rank_entry_user_id(x): x for x in rank_list if _rank_entry_user_id(x)}

    sticky_host = _extract_sticky_withdraw(page_data)
    out["hostSticky"] = sticky_host

    for uid in user_ids:
        user_page, _, user_method = _fetch_withdraw_rank_page(party, viewer_user_id=uid)
        sticky = _extract_sticky_withdraw(user_page) if user_page else {}
        list_item = rank_by_uid.get(uid)
        out["users"][uid] = {
            "weekWithdraw": sticky.get("weekWithdraw"),
            "rank": sticky.get("rank"),
            "listWithdraw": _rank_entry_withdraw_diamonds(list_item) if list_item else None,
            "listRank": _rank_entry_rank_num(list_item, 0) if list_item else None,
            "method": user_method or method,
        }
        time.sleep(0.12)
    return out


def _verify_rank_list_order(rank_list: list[dict[str, Any]]) -> dict[str, Any]:
    values = [_rank_entry_withdraw_diamonds(x) for x in rank_list]
    sorted_desc = sorted(values, reverse=True)
    ok = values == sorted_desc
    return {"ok": ok, "size": len(rank_list), "top3": values[:3]}


def _verify_withdraw_rank_after_close(
    party_a: RoomParty,
    verify_users: list[str],
    diamond_before: dict[str, int | None],
    diamond_after: dict[str, int | None],
    expected: dict[str, Any],
    rank_before: dict[str, Any],
    *,
    require_rank_api: bool,
) -> dict[str, Any]:
    rank_after = _snapshot_withdraw_rank_context(party_a, verify_users)
    result: dict[str, Any] = {
        "ok": True,
        "rankBefore": rank_before,
        "rankAfter": rank_after,
        "userChecks": [],
        "weekTotalCheck": None,
        "rankOrderCheck": None,
    }

    if not rank_after.get("apiAvailable"):
        result["rankApiAvailable"] = False
        result["rankApiSkipped"] = (
            "提款排名/本周总提款接口未返回数据（room-pk-api withdraw 系列或 withdraw-v2-api 待抓包映射）"
        )
        if require_rank_api:
            result["ok"] = False
            result["error"] = result["rankApiSkipped"]
        return result

    result["rankApiAvailable"] = True
    result["method"] = rank_after.get("method")
    checks: list[dict[str, Any]] = []

    # 本周总提款增量
    before_total = rank_before.get("weekTotalWithdraw")
    after_total = rank_after.get("weekTotalWithdraw")
    payout_sum = 0
    for uid in verify_users:
        before = diamond_before.get(uid)
        after = diamond_after.get(uid)
        if before is not None and after is not None:
            payout_sum += max(0, after - before)
    if before_total is not None and after_total is not None:
        delta = after_total - before_total
        week_ok = delta == payout_sum
        result["weekTotalCheck"] = {
            "ok": week_ok,
            "before": before_total,
            "after": after_total,
            "delta": delta,
            "expectedDelta": payout_sum,
        }
        checks.append({"name": "week_total_withdraw_delta", "ok": week_ok, "detail": result["weekTotalCheck"]})

    # 榜单降序
    page_after_raw, _, _ = _fetch_withdraw_rank_page(party_a)
    rank_list = _extract_withdraw_rank_list(page_after_raw or {})
    order = _verify_rank_list_order(rank_list)
    result["rankOrderCheck"] = order
    checks.append({"name": "rank_list_desc_order", "ok": order["ok"], "detail": order})

    rank_by_uid = {_rank_entry_user_id(x): x for x in rank_list if _rank_entry_user_id(x)}

    for uid in verify_users:
        exp_diamonds = int(((expected.get("users") or {}).get(uid) or {}).get("expectedDiamonds") or 0)
        before = diamond_before.get(uid)
        after = diamond_after.get(uid)
        delta = (after - before) if before is not None and after is not None else None

        before_u = (rank_before.get("users") or {}).get(uid) or {}
        after_u = (rank_after.get("users") or {}).get(uid) or {}
        before_week = before_u.get("weekWithdraw")
        after_week = after_u.get("weekWithdraw")

        user_item_checks: list[dict[str, Any]] = []

        if before_week is not None and after_week is not None and delta is not None:
            week_delta_ok = (after_week - before_week) == delta
            user_item_checks.append(
                {
                    "name": "sticky_week_withdraw_delta",
                    "ok": week_delta_ok,
                    "detail": {
                        "before": before_week,
                        "after": after_week,
                        "diamondDelta": delta,
                        "expectedDiamonds": exp_diamonds,
                    },
                }
            )

        list_item = rank_by_uid.get(uid)
        if list_item is not None and after_week is not None:
            list_diamonds = _rank_entry_withdraw_diamonds(list_item)
            user_item_checks.append(
                {
                    "name": "rank_list_vs_sticky",
                    "ok": list_diamonds == after_week,
                    "detail": {"listWithdraw": list_diamonds, "stickyWeekWithdraw": after_week},
                }
            )
        elif delta and delta > 0:
            user_item_checks.append(
                {
                    "name": "rank_list_contains",
                    "ok": list_item is not None,
                    "detail": {"diamondDelta": delta, "onList": list_item is not None},
                }
            )

        sticky_rank = after_u.get("rank")
        list_rank = _rank_entry_rank_num(list_item, 0) if list_item else None
        if sticky_rank is not None and list_rank:
            user_item_checks.append(
                {
                    "name": "sticky_rank_match",
                    "ok": sticky_rank == list_rank,
                    "detail": {"stickyRank": sticky_rank, "listRank": list_rank},
                }
            )

        checks.extend({**c, "userId": uid} for c in user_item_checks)
        user_ok = all(c["ok"] for c in user_item_checks) if user_item_checks else True
        result["userChecks"].append(
            {
                "userId": uid,
                "ok": user_ok,
                "checks": user_item_checks,
                "diamondDelta": delta,
                "expectedDiamonds": exp_diamonds,
                "weekWithdrawBefore": before_week,
                "weekWithdrawAfter": after_week,
                "stickyRank": sticky_rank,
                "listRank": list_rank,
            }
        )

    result["checks"] = checks
    result["ok"] = all(c["ok"] for c in checks if c.get("ok") is not None)
    if not result["ok"]:
        result["error"] = "提款排名/吸底/本周总提款 MOA 验收未通过"
    return result


def _mic_users_by_room(pk_data: dict[str, Any]) -> dict[str, list[str]]:
    rooms: dict[str, list[str]] = {}
    for info in (pk_data.get("currentRoomInfo"), pk_data.get("acrossRoomInfo")):
        if not isinstance(info, dict):
            continue
        rid = str(info.get("roomId") or "")
        users = [str(s["uid"]) for s in (info.get("seatUserList") or []) if s.get("uid")]
        if rid and users:
            rooms[rid] = users
    return rooms


def _mic_sets_by_room(pk_data: dict[str, Any]) -> dict[str, set[str]]:
    return {rid: set(uids) for rid, uids in _mic_users_by_room(pk_data).items()}


def _gift_receiver_on_mic(
    gift: dict[str, Any],
    mic_by_room: dict[str, set[str]],
) -> bool:
    """麦下收礼不计 PK；自动化送礼会写 receiverOnMic=True。"""
    if gift.get("receiverOnMic") is False:
        return False
    if gift.get("receiverOnMic") is True:
        return True
    room_id = str(gift.get("roomId") or "")
    receiver = str(gift.get("receiver") or "")
    return bool(receiver and receiver in mic_by_room.get(room_id, set()))


def _gift_pk_contribution(
    gift: dict[str, Any],
    mic_by_room: dict[str, set[str]],
) -> int:
    if not gift.get("ok") or not _gift_receiver_on_mic(gift, mic_by_room):
        return 0
    return int(gift["diamonds"]) * 10


def _rank_map(lst: list[dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for item in lst or []:
        uid = str(item.get("userId") or "")
        if not uid:
            continue
        out[uid] = {
            "pkValue": int(item.get("value") or 0),
            "rank": item.get("rank"),
            "nickname": (item.get("userInfo") or {}).get("nickname") or "",
        }
    return out


def _contribution_rank_map(party: RoomParty, pk_id: str) -> dict[str, dict[str, Any]]:
    """App PK contribution leaderboard：contributionAcrossRanks。"""
    body = _moa_party_body(
        party,
        uid=party.user_id,
        acrossPkId=pk_id,
        originRsp=1,
        dataType="json",
        _version_=1000,
    )
    biz = _moa_business(_moa("contributionAcrossRanks", body, strict=0))
    data = biz.get("data") if isinstance(biz.get("data"), dict) else {}
    out: dict[str, dict[str, Any]] = {}
    for item in data.get("list") or []:
        if not isinstance(item, dict):
            continue
        uid = str(item.get("userId") or "")
        if not uid:
            continue
        out[uid] = {
            "pkValue": int(item.get("value") or 0),
            "rank": item.get("rank"),
            "nickname": (item.get("userInfo") or {}).get("nickname") or "",
            "source": "contributionAcrossRanks",
        }
    return out


def _match_tier(combined_pk: int, cfg: PkAtmConfig) -> dict[str, Any]:
    """MSE matchPoolGradients：双方总 PK ≥ minTotalPkValue 时取满足条件的最高档。"""
    hit = None
    for tier in cfg.tiers:
        threshold = int(tier["maxCombinedPk"])  # JSON 字段名沿用 maxCombinedPk，语义为 minTotalPkValue
        if combined_pk >= threshold:
            hit = {
                "thresholdPk": threshold,
                "poolDiamonds": tier["poolDiamonds"],
                "ratioPct": tier.get("ratioPct"),
            }
    return {
        "combinedPk": combined_pk,
        "minPkForReward": cfg.min_combined_pk,
        "eligible": combined_pk >= cfg.min_combined_pk,
        "tier": hit,
        "personalPkThreshold": cfg.personal_pk_threshold,
    }


def _calc_dispatch_pool(combined_pk: int, atm: dict[str, Any]) -> int:
    """返钻基数为送礼钻石（总 PK/10）× 命中档位返钻比例 %（向下取整）。"""
    if not atm.get("eligible") or combined_pk <= 0:
        return 0
    tier = atm.get("tier") or {}
    ratio = tier.get("ratioPct")
    if ratio is not None:
        return math.floor(combined_pk / 10 * float(ratio) / 100)
    return int(tier.get("poolDiamonds") or 0)


def _moa_party_body(party: RoomParty, **extra: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "userId": party.user_id,
        "roomId": party.room_id,
        "lang": "en",
        "area": "MENA",
        "appId": "2005",
        "os": "android",
        "osType": "android",
    }
    body.update(extra)
    return body


def _moa_business(res: dict[str, Any]) -> dict[str, Any]:
    return res.get("business") if isinstance(res.get("business"), dict) else res


def _apply_random_match(party: RoomParty, *, pk_minute: str = "5") -> dict[str, Any]:
    body = _moa_party_body(
        party,
        acrossRoomId="",
        acrossPkType="1",
        hostSeat="0",
        pkMinute=pk_minute,
    )
    biz = _moa_business(_moa("applyAcrossRoomPk", body, strict=0))
    return {
        "phone": party.phone,
        "roomId": party.room_id,
        "ec": biz.get("ec"),
        "em": biz.get("em"),
        "data": biz.get("data"),
    }


def _prepare_random_match(party_a: RoomParty, party_b: RoomParty) -> list[dict[str, Any]]:
    """清理残留 PK / 邀请 / 匹配队列，便于两房重新随机匹配。"""
    steps: list[dict[str, Any]] = []

    for party, other in ((party_a, party_b), (party_b, party_a)):
        data = _pk_info(party)
        pk_id = data.get("acrossRoomPkId")
        across = (data.get("acrossRoomInfo") or {}).get("roomId")
        if pk_id and str(across) == str(other.room_id):
            body = _moa_party_body(party, acrossRoomId=other.room_id, acrossRoomPkId=str(pk_id))
            biz = _moa_business(_moa("closeAcrossRoomPk", body, strict=0))
            steps.append(
                {
                    "action": "closeAcrossRoomPk",
                    "phone": party.phone,
                    "ec": biz.get("ec"),
                    "em": biz.get("em"),
                    "pkId": pk_id,
                }
            )

    for party, other in ((party_a, party_b), (party_b, party_a)):
        body = _moa_party_body(party, acrossRoomId=other.room_id, os="ios", osType="ios")
        biz = _moa_business(_moa("rejectAcrossRoomPkInvite", body, strict=0))
        steps.append(
            {
                "action": "rejectAcrossRoomPkInvite",
                "phone": party.phone,
                "ec": biz.get("ec"),
                "em": biz.get("em"),
            }
        )

    for party in (party_a, party_b):
        chk = _moa_business(_moa("checkAcrossRoomPkMatching", _moa_party_body(party), strict=0))
        chk_data = chk.get("data") if isinstance(chk.get("data"), dict) else {}
        match_id = chk_data.get("matchId") or _pk_info(party).get("matchId")
        cancel_body = _moa_party_body(party)
        if match_id:
            cancel_body["matchId"] = str(match_id)
        biz = _moa_business(_moa("cancelAcrossRoomPkMatch", cancel_body, strict=0))
        steps.append(
            {
                "action": "cancelAcrossRoomPkMatch",
                "phone": party.phone,
                "ec": biz.get("ec"),
                "em": biz.get("em"),
                "matchId": match_id,
                "acrossPkStatus": chk_data.get("acrossPkStatus"),
            }
        )

    time.sleep(3)
    return steps


def _apply_random_match_parallel(
    party_a: RoomParty,
    party_b: RoomParty,
    *,
    pk_minute: str = "5",
) -> tuple[dict[str, Any], dict[str, Any]]:
    """两房并行发起随机匹配，尽量同时进入匹配池。"""
    with ThreadPoolExecutor(max_workers=2) as pool:
        fa = pool.submit(_apply_random_match, party_a, pk_minute=pk_minute)
        fb = pool.submit(_apply_random_match, party_b, pk_minute=pk_minute)
        return fa.result(), fb.result()


def _match_apply_ok(ec: Any) -> bool:
    """200=新入队；20210111=已在匹配池/有待处理状态，视为有效。"""
    return ec in (200, "200", 0, "0", 20210111, "20210111")


def _in_matching_queue(party: RoomParty) -> bool:
    chk = _moa_business(_moa("checkAcrossRoomPkMatching", _moa_party_body(party), strict=0))
    data = chk.get("data") if isinstance(chk.get("data"), dict) else {}
    return int(data.get("acrossPkStatus") or 0) == 1


def _close_wrong_pk(party: RoomParty, pk_data: dict[str, Any]) -> dict[str, Any]:
    pk_id = str(pk_data.get("acrossRoomPkId") or "")
    across = str((pk_data.get("acrossRoomInfo") or {}).get("roomId") or "")
    if not pk_id or not across:
        return {"skipped": True}
    body = _moa_party_body(party, acrossRoomId=across, acrossRoomPkId=pk_id)
    biz = _moa_business(_moa("closeAcrossRoomPk", body, strict=0))
    return {"phone": party.phone, "pkId": pk_id, "acrossRoomId": across, "ec": biz.get("ec"), "em": biz.get("em")}


def _normalize_match_retries(match_retries: int) -> int:
    """跨房 PK 随机匹配最多重试 MAX_CROSS_ROOM_MATCH_RETRIES 轮，避免长时间死循环。"""
    return min(max(1, int(match_retries)), MAX_CROSS_ROOM_MATCH_RETRIES)


def _begin_random_match_cross_room_pk(
    party_a: RoomParty,
    party_b: RoomParty,
    *,
    timeout_sec: int = 120,
    pk_minute: str = "5",
    match_retries: int = MAX_CROSS_ROOM_MATCH_RETRIES,
    skip_party_room_check: bool = False,
    party_room_check_since: int = 300,
) -> tuple[str, dict[str, Any]]:
    """两房并行发起随机匹配（acrossPkType=1），失败最多重试 MAX_CROSS_ROOM_MATCH_RETRIES 轮。"""
    effective_retries = _normalize_match_retries(match_retries)
    step: dict[str, Any] = {
        "mode": "random",
        "acrossPkType": "1",
        "attempts": [],
        "maxRetries": effective_retries,
    }
    if not skip_party_room_check:
        step["partyRoomCheck"] = _ensure_parties_ready_for_match(
            party_a,
            party_b,
            since_seconds=party_room_check_since,
        )
    step["prepare"] = _prepare_random_match(party_a, party_b)

    last_error = ""
    for attempt in range(effective_retries):
        attempt_log: dict[str, Any] = {"attempt": attempt + 1}
        if attempt > 0:
            attempt_log["prepare"] = _prepare_random_match(party_a, party_b)

        match_a, match_b = _apply_random_match_parallel(party_a, party_b, pk_minute=pk_minute)
        attempt_log["matchA"] = match_a
        attempt_log["matchB"] = match_b

        ok_a = _match_apply_ok(match_a.get("ec")) or _in_matching_queue(party_a)
        ok_b = _match_apply_ok(match_b.get("ec")) or _in_matching_queue(party_b)
        attempt_log["queueReady"] = {"a": ok_a, "b": ok_b}
        if not (ok_a or ok_b):
            attempt_log["error"] = "随机匹配发起失败"
            attempt_log["failed"] = [match_a, match_b]
            step["attempts"].append(attempt_log)
            last_error = f"applyAcrossRoomPk 随机匹配失败: {[match_a, match_b]}"
            _prepare_random_match(party_a, party_b)
            time.sleep(3)
            continue

        try:
            pk_data = _wait_pk_matched(
                party_a,
                party_b,
                timeout_sec=timeout_sec,
            )
        except _WrongPkMatchError as exc:
            attempt_log["wrongMatch"] = {
                "pkId": exc.pk_id,
                "matchedRoomId": exc.matched_room_id,
                "expectRoomId": exc.expect_room_id,
            }
            attempt_log["closeWrong"] = [
                _close_wrong_pk(party_a, _pk_info(party_a)),
                _close_wrong_pk(party_b, _pk_info(party_b)),
            ]
            step["attempts"].append(attempt_log)
            last_error = str(exc)
            _prepare_random_match(party_a, party_b)
            time.sleep(3)
            continue
        except TimeoutError as exc:
            attempt_log["timeout"] = str(exc)
            step["attempts"].append(attempt_log)
            last_error = str(exc)
            _prepare_random_match(party_a, party_b)
            time.sleep(3)
            continue

        pk_id = str(pk_data.get("acrossRoomPkId") or "")
        if not pk_id:
            attempt_log["error"] = "随机匹配未返回 acrossRoomPkId"
            step["attempts"].append(attempt_log)
            last_error = attempt_log["error"]
            continue

        attempt_log["pkId"] = pk_id
        attempt_log["stage"] = pk_data.get("stage")
        step["attempts"].append(attempt_log)
        step["matchA"] = match_a
        step["matchB"] = match_b
        step["pkId"] = pk_id
        step["stage"] = pk_data.get("stage")
        step["rooms"] = {
            party_a.room_id: party_b.room_id,
            party_b.room_id: party_a.room_id,
        }
        return pk_id, step

    _prepare_random_match(party_a, party_b)
    step["error"] = last_error or f"随机匹配 {effective_retries} 轮均失败"
    step["failed"] = True
    raise _PkMatchExhaustedError(
        f"跨房 PK 随机匹配失败：已重试 {effective_retries} 轮，任务终止（{step['error']}）",
        step=step,
    )


def _wait_pk_matched(
    party_a: RoomParty,
    party_b: RoomParty,
    *,
    timeout_sec: int = 120,
) -> dict[str, Any]:
    """轮询直到 A/B 任一侧与目标房间配对；若配到其他房间则抛 WrongPkMatchError。"""
    deadline = time.time() + timeout_sec
    expect = party_b.room_id
    while time.time() < deadline:
        for party, other in ((party_a, party_b), (party_b, party_a)):
            data = _pk_info(party)
            pk_id = data.get("acrossRoomPkId")
            across = (data.get("acrossRoomInfo") or {}).get("roomId")
            stage = data.get("stage")
            if not pk_id or across is None:
                continue
            if str(across) == str(other.room_id) and stage is not None:
                return data
            if str(across) != str(other.room_id):
                raise _WrongPkMatchError(
                    pk_id=str(pk_id),
                    matched_room_id=str(across),
                    expect_room_id=str(other.room_id),
                )
        time.sleep(2)
    raise TimeoutError(
        f"等待随机匹配超时（{timeout_sec}s）: room={party_a.room_id} expect={expect}"
    )


def _gift_send(sender: str, room_id: str, receiver: str, diamonds: int) -> dict[str, Any]:
    return _run_json(
        [
            sys.executable,
            "Gift/gift_execute.py",
            "--scene",
            "chatroom",
            "--sender",
            sender,
            "--receivers",
            receiver,
            "--gift-id",
            GIFT_ID_ROSE,
            "--scene-id",
            room_id,
            "--num",
            str(diamonds),
        ]
    )


def _combined_pk(pk_data: dict[str, Any]) -> int:
    return int(pk_data.get("roomRankValue") or 0) + int(pk_data.get("acrossRoomRankValue") or 0)


def _random_gift_diamonds(gift_min: int, gift_max: int) -> int:
    """随机钻石，低/中/高三档采样，避免全员 PK 相近。"""
    lo, hi = min(gift_min, gift_max), max(gift_min, gift_max)
    if lo >= hi:
        return lo
    span = hi - lo
    tier = random.choice(("low", "mid", "high"))
    if tier == "low":
        return random.randint(lo, lo + max(1, span // 3))
    if tier == "mid":
        return random.randint(lo + span // 3, lo + 2 * span // 3)
    return random.randint(lo + 2 * span // 3, hi)


def _plan_total_pk(plan: list[dict[str, Any]]) -> int:
    return sum(int(p.get("pkValue") or int(p.get("diamonds") or 0) * 10) for p in plan)


def _plan_room_pk(plan: list[dict[str, Any]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for item in plan:
        room_id = str(item["roomId"])
        pk_val = int(item.get("pkValue") or int(item.get("diamonds") or 0) * 10)
        out[room_id] = out.get(room_id, 0) + pk_val
    return out


def _distribute_pk_deficit_to_plan(
    plan: list[dict[str, Any]],
    deficit_pk: int,
    *,
    gift_min: int,
    gift_max: int,
) -> None:
    """把缺口 PK 随机分摊到计划条目；为满足总目标可超出单笔 gift_max。"""
    if deficit_pk <= 0 or not plan:
        return
    lo_pk = max(10, gift_min * 10)
    hi_pk = max(lo_pk, gift_max * 10)
    indices = list(range(len(plan)))
    guard = 0
    while deficit_pk > 0 and guard < len(plan) * 200:
        guard += 1
        idx = random.choice(indices)
        chunk_pk = min(
            deficit_pk,
            random.randint(lo_pk, max(hi_pk, lo_pk + deficit_pk // max(1, len(plan)))),
        )
        add_diamonds = max(1, math.ceil(chunk_pk / 10))
        plan[idx]["diamonds"] = int(plan[idx].get("diamonds") or 0) + add_diamonds
        plan[idx]["pkValue"] = int(plan[idx]["diamonds"]) * 10
        deficit_pk -= add_diamonds * 10


def _build_threshold_gift_plan(
    *,
    party_a: RoomParty,
    party_b: RoomParty,
    senders: list[str],
    high_pk: int,
    low_pk: int,
    high_count: int,
    low_count: int,
) -> list[dict[str, Any]]:
    """固定 PK 档位送礼计划：高/低档随机分派到 A/B 两房。"""
    need = high_count + low_count
    pool = senders[:need]
    if len(pool) < need:
        raise ValueError(f"送礼账号不足：需要 {need}，仅 {len(pool)}")
    random.shuffle(pool)
    room_ids = [party_a.room_id, party_b.room_id]
    plan: list[dict[str, Any]] = []
    for i, uid in enumerate(pool[:high_count]):
        diamonds = max(1, high_pk // 10)
        plan.append(
            {
                "sender": uid,
                "roomId": room_ids[i % 2],
                "pkValue": high_pk,
                "diamonds": diamonds,
            }
        )
    for j, uid in enumerate(pool[high_count:need]):
        diamonds = max(1, low_pk // 10)
        plan.append(
            {
                "sender": uid,
                "roomId": room_ids[(high_count + j) % 2],
                "pkValue": low_pk,
                "diamonds": diamonds,
            }
        )
    return plan


def _build_target_pk_gift_plan(
    *,
    party_a: RoomParty,
    party_b: RoomParty,
    senders: list[str],
    target_pk: int,
    gift_count: int,
    gift_min: int,
    gift_max: int,
    high_pk: int = 0,
    low_pk: int = 0,
    high_count: int = 0,
    low_count: int = 0,
) -> list[dict[str, Any]]:
    """给定总 PK 与个人档位要求，先算清各用户各房送多少，再执行送礼。"""
    room_ids = [party_a.room_id, party_b.room_id]
    if high_pk > 0 and low_pk > 0:
        plan = _build_threshold_gift_plan(
            party_a=party_a,
            party_b=party_b,
            senders=senders,
            high_pk=high_pk,
            low_pk=low_pk,
            high_count=high_count,
            low_count=low_count,
        )
    else:
        pool = senders[: max(gift_count, 1)]
        if len(pool) < 1:
            raise ValueError("无可用送礼账号")
        sender_room = _assign_sender_rooms(pool, room_ids)
        plan = []
        for sender in pool[:gift_count]:
            diamonds = _random_gift_diamonds(gift_min, gift_max)
            plan.append(
                {
                    "sender": sender,
                    "roomId": sender_room[sender],
                    "pkValue": diamonds * 10,
                    "diamonds": diamonds,
                }
            )

    deficit = target_pk - _plan_total_pk(plan)
    if deficit > 0:
        _distribute_pk_deficit_to_plan(
            plan,
            deficit,
            gift_min=gift_min,
            gift_max=gift_max,
        )

    rooms_used = {str(p["roomId"]) for p in plan}
    if len(room_ids) >= 2 and len(rooms_used & set(room_ids)) < 2:
        # 兜底：至少一条礼物改到另一房
        alt = next(rid for rid in room_ids if rid not in rooms_used)
        plan[0]["roomId"] = alt

    planned_total = _plan_total_pk(plan)
    if planned_total < target_pk:
        raise ValueError(
            f"送礼计划总 PK {planned_total:,} 未达目标 {target_pk:,}（账号 {len(plan)} 不足）"
        )
    return plan


def _gift_plan_summary(plan: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "entries": len(plan),
        "plannedTotalPk": _plan_total_pk(plan),
        "roomPk": _plan_room_pk(plan),
        "pkRange": {
            "min": min(int(p.get("pkValue") or 0) for p in plan) if plan else 0,
            "max": max(int(p.get("pkValue") or 0) for p in plan) if plan else 0,
        },
    }


def _send_gift_plan(
    *,
    plan: list[dict[str, Any]],
    room_owners: dict[str, str],
) -> list[dict[str, Any]]:
    """按计划逐笔送礼（计划须事先算好，执行阶段不再改 PK）。"""
    gifts: list[dict[str, Any]] = []
    for item in plan:
        sender = str(item["sender"])
        room_id = str(item["roomId"])
        receiver = room_owners[room_id]
        diamonds = int(item.get("diamonds") or max(1, int(item.get("pkValue") or 0) // 10))
        try:
            res = _gift_send(sender, room_id, receiver, diamonds)
            gifts.append(
                {
                    "sender": sender,
                    "roomId": room_id,
                    "receiver": receiver,
                    "receiverOnMic": True,
                    "diamonds": diamonds,
                    "targetPkValue": int(item.get("pkValue") or diamonds * 10),
                    "ok": res.get("ok"),
                    "ec": (res.get("response") or {}).get("ec"),
                }
            )
        except (RuntimeError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
            gifts.append(
                {
                    "sender": sender,
                    "roomId": room_id,
                    "receiver": receiver,
                    "receiverOnMic": True,
                    "diamonds": diamonds,
                    "targetPkValue": int(item.get("pkValue") or diamonds * 10),
                    "ok": False,
                    "error": str(exc),
                }
            )
        time.sleep(0.15)
    return gifts


def _assign_sender_rooms(senders: list[str], room_ids: list[str]) -> dict[str, str]:
    """均分两房绑定送礼账号，确保两房都有人送，且同账号不跨房。"""
    if len(room_ids) < 2:
        rid = room_ids[0] if room_ids else ""
        return {sender: rid for sender in senders}
    ids = list(room_ids[:2])
    ordered = list(senders)
    random.shuffle(ordered)
    half = max(1, len(ordered) // 2)
    out: dict[str, str] = {}
    for i, sender in enumerate(ordered):
        out[sender] = ids[0] if i < half else ids[1]
    return out


def _pick_lagging_room(
    pk_data: dict[str, Any],
    party_a: RoomParty,
    party_b: RoomParty,
) -> str:
    """追加送礼时优先打 PK 较低的房间，保持双房都有贡献。"""
    room_a_pk = int(pk_data.get("roomRankValue") or 0)
    room_b_pk = int(pk_data.get("acrossRoomRankValue") or 0)
    if room_a_pk <= room_b_pk:
        return party_a.room_id
    return party_b.room_id


def _gifts_room_ids(gifts: list[dict[str, Any]]) -> set[str]:
    return {str(g["roomId"]) for g in gifts if g.get("ok") and g.get("roomId")}


def _room_owners_map(party_a: RoomParty, party_b: RoomParty) -> dict[str, str]:
    """roomId → 房主 userId（房主必在麦上，送礼只打房主避免麦下/无效麦位不计 PK）。"""
    return {party_a.room_id: party_a.user_id, party_b.room_id: party_b.user_id}


def _send_random_gifts(
    *,
    senders: list[str],
    room_owners: dict[str, str],
    room_ids: list[str],
    gift_min: int,
    gift_max: int,
    count: int,
    sender_room: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    gifts: list[dict[str, Any]] = []
    for sender in senders[:count]:
        room_id = (sender_room or {}).get(sender) or random.choice(room_ids)
        receiver = room_owners[room_id]
        diamonds = _random_gift_diamonds(gift_min, gift_max)
        try:
            res = _gift_send(sender, room_id, receiver, diamonds)
            gifts.append(
                {
                    "sender": sender,
                    "roomId": room_id,
                    "receiver": receiver,
                    "receiverOnMic": True,
                    "diamonds": diamonds,
                    "ok": res.get("ok"),
                    "ec": (res.get("response") or {}).get("ec"),
                }
            )
        except (RuntimeError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
            gifts.append(
                {
                    "sender": sender,
                    "roomId": room_id,
                    "receiver": receiver,
                    "receiverOnMic": True,
                    "diamonds": diamonds,
                    "ok": False,
                    "error": str(exc),
                }
            )
    return gifts


def _top_up_gifts_until_target(
    *,
    party_a: RoomParty,
    party_b: RoomParty,
    pk_id: str,
    senders: list[str],
    gift_min: int,
    gift_max: int,
    gift_count: int,
    target_pk: int,
    max_rounds: int = 5,
    batch_wait_sec: int = 5,
    sender_room: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """目标总 PK 未达标时追加送礼（每轮按缺口估算钻石）。"""
    extra: list[dict[str, Any]] = []
    if target_pk <= 0:
        return extra
    room_owners = _room_owners_map(party_a, party_b)
    room_ids = list(room_owners.keys())
    for _round in range(max_rounds):
        pk_data = _pk_info(party_a, pk_id=pk_id)
        combined = _combined_pk(pk_data)
        if combined >= target_pk:
            break
        deficit_pk = target_pk - combined
        deficit_diamonds = max(1, math.ceil(deficit_pk / 10))
        batch_size = min(gift_count, max(5, math.ceil(deficit_diamonds / gift_min)))
        avg_diamonds = max(gift_min, math.ceil(deficit_diamonds / batch_size))
        round_max = max(gift_max, avg_diamonds)
        round_min = max(gift_min, min(round_max, max(1, avg_diamonds // 2)))
        lag_room = _pick_lagging_room(pk_data, party_a, party_b)
        lag_senders = [
            s for s in senders if (sender_room or {}).get(s, lag_room) == lag_room
        ]
        other_senders = [s for s in senders if s not in lag_senders]
        random.shuffle(lag_senders)
        random.shuffle(other_senders)
        top_up_pool = lag_senders + other_senders
        top_up_room: dict[str, str] = {}
        for sender in top_up_pool[:batch_size]:
            top_up_room[sender] = (sender_room or {}).get(sender) or lag_room
        extra.extend(
            _send_random_gifts(
                senders=senders,
                room_owners=room_owners,
                room_ids=room_ids,
                gift_min=round_min,
                gift_max=round_max,
                count=batch_size,
                sender_room=top_up_room,
            )
        )
        if batch_wait_sec > 0:
            time.sleep(batch_wait_sec)
    return extra


def _wait_pk_natural_end(
    party: RoomParty,
    pk_id: str,
    *,
    timeout_sec: int = 420,
    poll_sec: float = 5.0,
    min_stage: int = 3,
) -> dict[str, Any]:
    """轮询直到 PK 时长走完进入惩罚阶段（stage>=3）或超时；不必等惩罚阶段结束（stage=4）。"""
    deadline = time.time() + timeout_sec
    last: dict[str, Any] = {}
    while time.time() < deadline:
        last = _pk_info(party, pk_id=pk_id)
        stage = int(last.get("stage") or 0)
        if stage >= min_stage:
            return last
        if stage <= 0 and not last.get("acrossRoomPkId"):
            return last
        time.sleep(poll_sec)
    raise TimeoutError(
        f"等待 PK 进入惩罚阶段超时（{timeout_sec}s）pkId={pk_id} stage={last.get('stage')} expect>={min_stage}"
    )


def _close_pk(party_a: RoomParty, party_b: RoomParty, pk_id: str) -> dict[str, Any]:
    body = {
        "userId": party_a.user_id,
        "roomId": party_a.room_id,
        "acrossRoomId": party_b.room_id,
        "acrossRoomPkId": pk_id,
        "lang": "en",
        "area": "MENA",
        "appId": "2005",
        "os": "android",
        "osType": "android",
    }
    return _moa("closeAcrossRoomPk", body, strict=0)


def _sender_pk_map(
    gifts: list[dict[str, Any]],
    pk_data: dict[str, Any],
    party_a: RoomParty,
    party_b: RoomParty,
) -> dict[str, dict[str, Any]]:
    """每个送礼人在各房间的 PK 贡献（优先 App 贡献榜；榜外用户用钻石×10累加回填）。"""
    pk_id = str(
        pk_data.get("acrossRoomPkId")
        or pk_data.get("acrossRoomPKId")
        or pk_data.get("pkId")
        or ""
    )
    a_ranks: dict[str, dict[str, Any]] = {}
    b_ranks: dict[str, dict[str, Any]] = {}
    if pk_id:
        try:
            a_ranks = _contribution_rank_map(party_a, pk_id)
            b_ranks = _contribution_rank_map(party_b, pk_id)
        except (RuntimeError, json.JSONDecodeError, KeyError, TypeError, ValueError):
            a_ranks = {}
            b_ranks = {}

    if not a_ranks:
        a_ranks = {
            uid: {**info, "source": "roomRankList"}
            for uid, info in _rank_map(pk_data.get("roomRankList")).items()
        }
    if not b_ranks:
        b_ranks = {
            uid: {**info, "source": "acrossRoomRankList"}
            for uid, info in _rank_map(pk_data.get("acrossRoomRankList")).items()
        }

    out: dict[str, dict[str, Any]] = {}
    for uid, info in a_ranks.items():
        api_pk = int(info.get("pkValue") or 0)
        if api_pk <= 0:
            continue
        out.setdefault(uid, {})
        out[uid][party_a.room_id] = {
            "pkValue": api_pk,
            "source": info.get("source") or "contributionAcrossRanks",
        }
    for uid, info in b_ranks.items():
        api_pk = int(info.get("pkValue") or 0)
        if api_pk <= 0:
            continue
        out.setdefault(uid, {})
        out[uid][party_b.room_id] = {
            "pkValue": api_pk,
            "source": info.get("source") or "contributionAcrossRanks",
        }

    # 贡献榜通常只返回 Top10；对榜外或未上榜的送礼人，用本局送礼钻石×10回填。
    mic_by_room = _mic_sets_by_room(pk_data)
    calc: dict[str, dict[str, int]] = {}
    for g in gifts:
        gift_pk = _gift_pk_contribution(g, mic_by_room)
        if gift_pk <= 0:
            continue
        sender = str(g["sender"])
        room_id = str(g["roomId"])
        calc.setdefault(sender, {})
        calc[sender][room_id] = calc[sender].get(room_id, 0) + gift_pk
    for sender, room_map in calc.items():
        per_room = out.setdefault(sender, {})
        for room_id, calc_pk in room_map.items():
            api_pk = int((per_room.get(room_id) or {}).get("pkValue") or 0)
            if api_pk > 0:
                continue
            per_room[room_id] = {"pkValue": calc_pk, "source": "钻石×10累加"}
    return out


def _resolve_room_pks(
    pk_data: dict[str, Any],
    sender_pk: dict[str, dict[str, Any]],
    party_a: RoomParty,
    party_b: RoomParty,
) -> tuple[int, int]:
    """房间总 PK：优先 MOA 字段，为 0 时回退送礼人 PK 累加。"""
    room_a_pk = int(pk_data.get("roomRankValue") or 0)
    room_b_pk = int(pk_data.get("acrossRoomRankValue") or 0)
    if room_a_pk <= 0:
        room_a_pk = sum(
            int((rooms.get(party_a.room_id) or {}).get("pkValue") or 0)
            for rooms in sender_pk.values()
        )
    if room_b_pk <= 0:
        room_b_pk = sum(
            int((rooms.get(party_b.room_id) or {}).get("pkValue") or 0)
            for rooms in sender_pk.values()
        )
    return room_a_pk, room_b_pk


def _winner_from_pk(
    room_a_pk: int, room_b_pk: int, party_a: RoomParty, party_b: RoomParty
) -> tuple[RoomParty | None, RoomParty | None, int]:
    if room_a_pk > room_b_pk:
        return party_a, party_b, room_a_pk
    if room_b_pk > room_a_pk:
        return party_b, party_a, room_b_pk
    return None, None, room_a_pk


def _resolve_outcome(
    room_a_pk: int,
    room_b_pk: int,
    party_a: RoomParty,
    party_b: RoomParty,
    *,
    closer: RoomParty | None = None,
) -> tuple[RoomParty | None, RoomParty | None, int, str]:
    """判定胜负：主动结束 PK 的一方记为败方；否则按 PK 值较高者为胜。"""
    if closer is not None:
        if closer.room_id == party_a.room_id:
            return party_b, party_a, room_b_pk, "主动结束PK记败"
        if closer.room_id == party_b.room_id:
            return party_a, party_b, room_a_pk, "主动结束PK记败"
    winner, loser, win_room_pk = _winner_from_pk(room_a_pk, room_b_pk, party_a, party_b)
    return winner, loser, win_room_pk, "PK值较高"


def _calc_expected_rewards(
    *,
    cfg: PkAtmConfig,
    pk_data: dict[str, Any],
    party_a: RoomParty,
    party_b: RoomParty,
    sender_pk: dict[str, dict[str, Any]],
    assume_first_win: bool,
    first_win_users: set[str] | None = None,
    closer: RoomParty | None = None,
) -> dict[str, Any]:
    room_a_pk, room_b_pk = _resolve_room_pks(pk_data, sender_pk, party_a, party_b)
    combined = room_a_pk + room_b_pk
    atm = _match_tier(combined, cfg)
    winner, loser, win_room_pk, outcome_rule = _resolve_outcome(
        room_a_pk, room_b_pk, party_a, party_b, closer=closer
    )

    pool = _calc_dispatch_pool(combined, atm)
    if not atm.get("eligible") or not winner or win_room_pk <= 0 or pool <= 0:
        return {
            "atm": atm,
            "winnerRoomId": winner.room_id if winner else None,
            "loserRoomId": loser.room_id if loser else None,
            "outcomeRule": outcome_rule,
            "poolDiamonds": pool,
            "users": {
                uid: {
                    "expectedDiamonds": 0,
                    "reason": "未达场次门槛或无胜方/无奖池",
                    "personalPk": sum(r.get("pkValue", 0) for r in rooms.values()),
                }
                for uid, rooms in sender_pk.items()
            },
        }

    win_room_id = winner.room_id
    users: dict[str, Any] = {}
    for uid, rooms in sender_pk.items():
        personal_pk = int((rooms.get(win_room_id) or {}).get("pkValue") or 0)
        if win_room_id not in rooms:
            users[uid] = {
                "expectedDiamonds": 0,
                "reason": "败方或无胜方房间贡献",
                "personalPk": sum(int(r.get("pkValue") or 0) for r in rooms.values()),
                "roomPkByRoom": rooms,
            }
            continue
        if personal_pk < cfg.personal_pk_threshold:
            users[uid] = {
                "expectedDiamonds": 0,
                "reason": f"个人 PK {personal_pk} < 门槛 {cfg.personal_pk_threshold}，不应发钻",
                "personalPk": personal_pk,
                "eligible": False,
                "roomPkByRoom": rooms,
            }
            continue
        base = math.floor(pool * personal_pk / win_room_pk)
        expected = base * cfg.first_win_multiplier if assume_first_win else base
        users[uid] = {
            "expectedDiamonds": expected,
            "baseDiamonds": base,
            "firstWinApplied": assume_first_win,
            "personalPk": personal_pk,
            "eligible": True,
            "roomPkByRoom": rooms,
            "formula": f"floor({pool}×{personal_pk}/{win_room_pk})"
            + (f"×{cfg.first_win_multiplier}" if assume_first_win else ""),
        }

    return {
        "atm": atm,
        "winnerRoomId": win_room_id,
        "loserRoomId": loser.room_id if loser else None,
        "poolDiamonds": pool,
        "winRoomTotalPk": win_room_pk,
        "outcomeRule": outcome_rule,
        "users": users,
    }


def _snapshot_diamonds(user_ids: list[str]) -> dict[str, int | None]:
    out: dict[str, int | None] = {}
    for uid in user_ids:
        try:
            out[uid] = _query_diamond(uid)
        except (RuntimeError, ValueError, TypeError):
            out[uid] = None
        time.sleep(0.15)
    return out


def _build_report(
    *,
    pk_id: str,
    cfg: PkAtmConfig,
    party_a: RoomParty,
    party_b: RoomParty,
    gifts: list[dict[str, Any]],
    pk_end: dict[str, Any],
    sender_pk: dict[str, dict[str, Any]],
    expected: dict[str, Any],
    diamond_before: dict[str, int | None],
    diamond_after: dict[str, int | None],
    pk_status_verify: dict[str, Any] | None = None,
    withdraw_rank_verify: dict[str, Any] | None = None,
    closer: RoomParty | None = None,
) -> dict[str, Any]:
    room_a_pk = int(pk_end.get("roomRankValue") or 0)
    room_b_pk = int(pk_end.get("acrossRoomRankValue") or 0)
    winner, loser, win_room_pk, outcome_rule = _resolve_outcome(
        room_a_pk, room_b_pk, party_a, party_b, closer=closer
    )

    mic_by_room = _mic_sets_by_room(pk_end)
    contributors: list[dict[str, Any]] = []
    for g in gifts:
        sender = g["sender"]
        room_id = g["roomId"]
        room_total = room_a_pk if room_id == party_a.room_id else room_b_pk
        pk_info = (sender_pk.get(sender) or {}).get(room_id) or {"pkValue": 0, "source": "—"}
        sender_total_pk = int(pk_info.get("pkValue") or 0)
        gift_pk = _gift_pk_contribution(g, mic_by_room)
        receiver_on_mic = _gift_receiver_on_mic(g, mic_by_room)
        contributors.append(
            {
                "sender": sender,
                "roomId": room_id,
                "receiver": g["receiver"],
                "receiverOnMic": receiver_on_mic,
                "diamonds": g["diamonds"],
                "pkValue": gift_pk,
                "senderRoomPk": sender_total_pk,
                "pkValueSource": "钻石×10" if gift_pk else pk_info.get("source"),
                "roomTotalPk": room_total,
                "sharePct": round(sender_total_pk / room_total * 100, 2) if room_total else 0.0,
                "giftOk": g.get("ok"),
            }
        )

    verifications: list[dict[str, Any]] = []
    all_match = True
    for uid in sorted(set(sender_pk.keys())):
        before = diamond_before.get(uid)
        after = diamond_after.get(uid)
        exp_info = (expected.get("users") or {}).get(uid) or {}
        expected_diamonds = int(exp_info.get("expectedDiamonds") or 0)
        delta = None
        match = None
        if before is not None and after is not None:
            delta = after - before
            if exp_info.get("eligible") is False:
                match = delta == 0
            else:
                match = delta == expected_diamonds
            if not match:
                all_match = False
        else:
            all_match = False
        verifications.append(
            {
                "userId": uid,
                "diamondBefore": before,
                "diamondAfter": after,
                "diamondDelta": delta,
                "expectedDiamonds": expected_diamonds,
                "match": match,
                "reason": exp_info.get("reason") or exp_info.get("formula"),
                "personalPk": exp_info.get("personalPk"),
            }
        )

    atm = expected.get("atm") or _match_tier(room_a_pk + room_b_pk, cfg)

    return {
        "ok": True,
        "pkId": pk_id,
        "stage": pk_end.get("stage"),
        "pkResult": pk_end.get("pkResult"),
        "matchMode": "random",
        "serviceConfig": cfg.to_dict(),
        "rooms": {
            party_a.room_id: {
                "phone": party_a.phone,
                "userId": party_a.user_id,
                "totalPkValue": room_a_pk,
                "result": "胜" if winner is party_a else ("负" if loser is party_a else "平"),
            },
            party_b.room_id: {
                "phone": party_b.phone,
                "userId": party_b.user_id,
                "totalPkValue": room_b_pk,
                "result": "胜" if winner is party_b else ("负" if loser is party_b else "平"),
            },
        },
        "result": {
            "winnerRoomId": winner.room_id if winner else None,
            "loserRoomId": loser.room_id if loser else None,
            "margin": abs(room_a_pk - room_b_pk),
            "draw": winner is None,
            "winRoomTotalPk": win_room_pk,
            "outcomeRule": outcome_rule,
        },
        "winner": {
            "phone": winner.phone,
            "userId": winner.user_id,
            "roomId": winner.room_id,
        }
        if winner
        else None,
        "loser": {
            "phone": loser.phone,
            "userId": loser.user_id,
            "roomId": loser.room_id,
        }
        if loser
        else None,
        "outcomeRule": outcome_rule,
        "closerPhone": closer.phone if closer else None,
        "pkAtm": atm,
        "expectedRewards": expected,
        "senderPkByRoom": sender_pk,
        "contributors": contributors,
        "diamondVerification": {
            "allMatch": all_match,
            "items": verifications,
        },
        "giftOkCount": sum(1 for g in gifts if g.get("ok")),
        "giftTotal": len(gifts),
        "pkStatusVerify": pk_status_verify,
        "withdrawRankVerify": withdraw_rank_verify,
    }


def _write_outputs(report: dict[str, Any], out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    pk_id = report.get("pkId") or "unknown"
    json_path = out_dir / f"pk_atm_report_{pk_id}.json"
    md_path = out_dir / f"pk_atm_report_{pk_id}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    cfg = report.get("serviceConfig") or {}
    lines = [
        f"# PK 提款机测试报告 · {pk_id}",
        "",
        "## 服务配置",
        "",
        f"- 来源：`{cfg.get('source')}`",
        f"- 场次最低 PK：**{cfg.get('minCombinedPk', 0):,}**",
        f"- 个人门槛 PK：**{cfg.get('personalPkThreshold', 0):,}**",
        "",
        "## 随机匹配开启跨房 PK",
        "",
        f"- 匹配方式：**{report.get('matchMode', 'random')}**（`acrossPkType=1`，不计指定邀请）",
    ]
    match_step = None
    for step in report.get("steps") or []:
        if isinstance(step, dict) and isinstance(step.get("match"), dict):
            match_step = step["match"]
            break
    if match_step:
        if match_step.get("mode") == "reuse_existing":
            lines.append(f"- 复用已有 PK：`{match_step.get('pkId')}`（stage={match_step.get('stage')}）")
        else:
            ma = match_step.get("matchA") or {}
            mb = match_step.get("matchB") or {}
            lines.append(
                f"- A 房 {ma.get('phone')} apply ec={ma.get('ec')}；"
                f"B 房 {mb.get('phone')} apply ec={mb.get('ec')}"
            )
            lines.append(f"- 配对 pkId：`{match_step.get('pkId')}`（stage={match_step.get('stage')}）")
            attempts = match_step.get("attempts") or []
            if len(attempts) > 1:
                lines.append(f"- 匹配重试：**{len(attempts)}** 轮")
            for att in attempts:
                if att.get("wrongMatch"):
                    wm = att["wrongMatch"]
                    lines.append(
                        f"  - 第 {att.get('attempt')} 轮配错房间 "
                        f"{wm.get('matchedRoomId')}（期望 {wm.get('expectRoomId')}）→ 已结束并重试"
                    )
                elif att.get("error") or att.get("timeout"):
                    reason = att.get("error") or att.get("timeout")
                    lines.append(f"  - 第 {att.get('attempt')} 轮失败：{reason} → 已重试")
    lines.extend(
        [
            "",
            "## 房间 PK 与胜负",
            "",
            "| 房间 | 手机号 | 总 PK 值 | 结果 |",
            "|------|--------|----------|------|",
        ]
    )
    for rid, info in report.get("rooms", {}).items():
        lines.append(
            f"| {rid} | {info.get('phone')} | {info.get('totalPkValue'):,} | {info.get('result')} |"
        )
    lines.extend(
        [
            "",
            f"- 分差：{report.get('result', {}).get('margin', 0):,}",
            "",
            "## PK 提款机梯度（双方总 PK）",
            "",
            f"- 双方总 PK：**{report.get('pkAtm', {}).get('combinedPk', 0):,}**",
            f"- 达场次门槛：**{'是' if report.get('pkAtm', {}).get('eligible') else '否'}**",
        ]
    )
    tier = report.get("pkAtm", {}).get("tier")
    pool = int((report.get("expectedRewards") or {}).get("poolDiamonds") or 0)
    if tier:
        ratio = tier.get("ratioPct")
        ratio_txt = f"（返钻 {ratio}% × 送礼钻）" if ratio is not None else ""
        lines.append(
            f"- 命中档位：≥{tier['thresholdPk']:,} PK → 下发总钻石 **{pool:,}** 钻{ratio_txt}"
        )
    else:
        lines.append("- 命中档位：无")

    if report.get("pkStatusVerify"):
        sv = report["pkStatusVerify"]
        battle = sv.get("battleVerify") or {}
        lines.extend(
            [
                "",
                "## PK 赛况与对战验收（结束前 · getAcrossRoomPkInfo）",
                "",
                f"- 对战验收：**{'通过' if battle.get('ok') else '未通过'}**（stage={battle.get('stage')}）",
                f"- 双方总 PK：**{battle.get('combinedPk', 0):,}**",
            ]
        )
        if sv.get("situationListAvailable"):
            sit = sv.get("situationListVerify") or {}
            lines.append(f"- 活动页赛况列表：**{'通过' if sit.get('ok') else '未通过'}**")
        else:
            lines.append(f"- 活动页赛况列表：跳过（{sv.get('situationListSkipped', '—')}）")
        for item in battle.get("checks") or []:
            mark = "✓" if item.get("ok") else "✗"
            lines.append(f"  - {mark} {item.get('name')}")

    if report.get("withdrawRankVerify"):
        wr = report["withdrawRankVerify"]
        lines.extend(
            [
                "",
                "## 提款排名验收（结束后 · 生成式 MOA）",
                "",
            ]
        )
        if wr.get("rankApiAvailable"):
            lines.append(f"- MOA 接口：**{wr.get('method') or '—'}**")
            wtc = wr.get("weekTotalCheck") or {}
            if wtc:
                lines.append(
                    f"- 本周总提款增量：**{'通过' if wtc.get('ok') else '未通过'}** "
                    f"（{wtc.get('before')} → {wtc.get('after')}，Δ={wtc.get('delta')}，预期 Δ={wtc.get('expectedDelta')}）"
                )
            roc = wr.get("rankOrderCheck") or {}
            if roc:
                lines.append(
                    f"- 榜单降序：**{'通过' if roc.get('ok') else '未通过'}**（共 {roc.get('size', 0)} 条）"
                )
            for uc in wr.get("userChecks") or []:
                mark = "✓" if uc.get("ok") else "✗"
                lines.append(
                    f"  - {mark} {uc.get('userId')} 吸底本周已提款 "
                    f"{uc.get('weekWithdrawBefore')}→{uc.get('weekWithdrawAfter')} "
                    f"（钻石 Δ={uc.get('diamondDelta')}）"
                )
            lines.append(f"- 总体验收：**{'通过' if wr.get('ok') else '未通过'}**")
        else:
            lines.append(f"- MOA 层：跳过（{wr.get('rankApiSkipped', '—')}）")
            lines.append("- 兜底：仍以「送礼人 PK 与钻石验收」钻石差值为准")

    lines.extend(
        [
            "",
            "## 送礼人 PK 与钻石验收",
            "",
            "| 用户 | 个人 PK | 送礼前余额 | 预期返钻 | 结束后余额 | 实际增量 | 一致 |",
            "|------|---------|------------|----------|------------|----------|------|",
        ]
    )
    for item in report.get("diamondVerification", {}).get("items", []):
        match = item.get("match")
        mark = "✓" if match is True else ("✗" if match is False else "—")
        lines.append(
            f"| {item.get('userId')} | {item.get('personalPk') or '—'} | "
            f"{item.get('diamondBefore') if item.get('diamondBefore') is not None else '—'} | "
            f"{item.get('expectedDiamonds', 0)} | "
            f"{item.get('diamondAfter') if item.get('diamondAfter') is not None else '—'} | "
            f"{item.get('diamondDelta') if item.get('diamondDelta') is not None else '—'} | {mark} |"
        )
    all_match = report.get("diamondVerification", {}).get("allMatch")
    lines.append("")
    lines.append(f"**整体验收：{'通过' if all_match else '未通过'}**")

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def run(args: argparse.Namespace) -> int:
    report: dict[str, Any] = {"steps": [], "ok": False}

    party_a = _resolve_party(args.phone_a)
    party_b = _resolve_party(args.phone_b)
    report["parties"] = {"a": party_a.__dict__, "b": party_b.__dict__}

    cfg, config_attempts = _resolve_config(args, party_a)
    report["serviceConfig"] = cfg.to_dict()
    report["steps"].append({"configFetchAttempts": config_attempts})

    existing = _pk_info(party_a)
    pk_id = existing.get("acrossRoomPkId")
    reuse = (
        pk_id
        and str((existing.get("acrossRoomInfo") or {}).get("roomId")) == party_b.room_id
        and int(existing.get("stage") or 0) >= 1
    )
    if reuse:
        report["steps"].append(
            {
                "match": {
                    "mode": "reuse_existing",
                    "pkId": pk_id,
                    "stage": existing.get("stage"),
                    "acrossPkType": "1",
                }
            }
        )
    else:
        try:
            pk_id, match_step = _begin_random_match_cross_room_pk(
                party_a,
                party_b,
                timeout_sec=args.match_timeout,
                pk_minute=str(args.pk_minute),
                match_retries=args.match_retries,
                skip_party_room_check=bool(getattr(args, "skip_party_room_check", False)),
                party_room_check_since=int(getattr(args, "party_room_check_since", 300) or 300),
            )
        except _PkMatchExhaustedError as exc:
            report["error"] = str(exc)
            report["steps"].append({"match": exc.step})
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 1
        except (RuntimeError, TimeoutError) as exc:
            report["error"] = str(exc)
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 1
        report["steps"].append({"match": match_step})
    report["matchMode"] = "random"
    report["pkId"] = pk_id

    for _ in range(30):
        if int(_pk_info(party_a, pk_id=pk_id).get("stage") or 0) >= 2:
            break
        time.sleep(1)

    if args.pre_gift_wait > 0:
        time.sleep(args.pre_gift_wait)

    room_owners = _room_owners_map(party_a, party_b)
    room_ids = list(room_owners.keys())

    senders = [s.strip() for s in (args.senders or "").split(",") if s.strip()] or DEFAULT_SENDERS
    senders = [s for s in senders if s not in (party_a.user_id, party_b.user_id)]
    random.shuffle(senders)
    pool = senders[: max(args.gift_count, len(senders))]

    if args.target_combined_pk and args.target_combined_pk > 0:
        gift_plan = _build_target_pk_gift_plan(
            party_a=party_a,
            party_b=party_b,
            senders=pool,
            target_pk=args.target_combined_pk,
            gift_count=args.gift_count,
            gift_min=args.gift_min_diamonds,
            gift_max=args.gift_max_diamonds,
        )
        sender_room = {str(p["sender"]): str(p["roomId"]) for p in gift_plan}
        plan_summary = _gift_plan_summary(gift_plan)
        gifts = _send_gift_plan(plan=gift_plan, room_owners=room_owners)
        report["steps"].append({"giftPlan": plan_summary, "gifts": gifts})
    else:
        sender_room = _assign_sender_rooms(pool, room_ids)
        gifts = _send_random_gifts(
            senders=pool,
            room_owners=room_owners,
            room_ids=room_ids,
            gift_min=args.gift_min_diamonds,
            gift_max=args.gift_max_diamonds,
            count=args.gift_count,
            sender_room=sender_room,
        )
        report["steps"].append({"gifts": gifts})

    if args.post_gift_wait > 0:
        time.sleep(args.post_gift_wait)

    pk_pre_close = _pk_info(party_a, pk_id=pk_id)
    sender_pk = _sender_pk_map(gifts, pk_pre_close, party_a, party_b)

    pk_status_verify = _verify_pk_status_before_close(
        party_a,
        party_b,
        pk_id,
        pk_pre_close,
        require_situation_list=args.require_pk_situation_list,
    )
    report["steps"].append({"pkStatusVerify": pk_status_verify})
    if not pk_status_verify.get("ok") and not args.skip_pk_status_verify:
        report["error"] = pk_status_verify.get("error") or "PK 赛况/对战信息验收未通过"
        report["pkStatusVerify"] = pk_status_verify
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1

    verify_users = sorted(sender_pk.keys())

    diamond_before = _snapshot_diamonds(verify_users)
    report["steps"].append({"diamondBeforeClose": diamond_before})

    expected = _calc_expected_rewards(
        cfg=cfg,
        pk_data=pk_pre_close,
        party_a=party_a,
        party_b=party_b,
        sender_pk=sender_pk,
        assume_first_win=args.assume_first_win,
        closer=party_a,
    )
    report["steps"].append(
        {
            "preClosePk": {
                "roomA": int(pk_pre_close.get("roomRankValue") or 0),
                "roomB": int(pk_pre_close.get("acrossRoomRankValue") or 0),
            },
            "senderPkByRoom": sender_pk,
            "expectedRewards": expected,
        }
    )

    withdraw_rank_before = _snapshot_withdraw_rank_context(party_a, verify_users)
    report["steps"].append({"withdrawRankBeforeClose": withdraw_rank_before})

    close_res = _close_pk(party_a, party_b, pk_id)
    report["steps"].append({"close": close_res.get("business")})
    report["closerPhone"] = party_a.phone

    if args.post_close_wait > 0:
        time.sleep(args.post_close_wait)

    diamond_after = _snapshot_diamonds(verify_users)
    report["steps"].append({"diamondAfterClose": diamond_after})

    withdraw_rank_verify = _verify_withdraw_rank_after_close(
        party_a,
        verify_users,
        diamond_before,
        diamond_after,
        expected,
        withdraw_rank_before,
        require_rank_api=args.require_withdraw_rank_api,
    )
    report["steps"].append({"withdrawRankVerify": withdraw_rank_verify})

    pk_end = _pk_info(party_a, pk_id=pk_id)
    final = _build_report(
        pk_id=pk_id,
        cfg=cfg,
        party_a=party_a,
        party_b=party_b,
        gifts=gifts,
        pk_end=pk_end,
        sender_pk=sender_pk,
        expected=expected,
        diamond_before=diamond_before,
        diamond_after=diamond_after,
        pk_status_verify=pk_status_verify,
        withdraw_rank_verify=withdraw_rank_verify,
        closer=party_a,
    )
    report.update(final)

    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = REPO / out_dir
    json_path, md_path = _write_outputs(final, out_dir)
    report["reportFiles"] = {"json": str(json_path), "markdown": str(md_path)}

    close_ok = bool((close_res.get("business") or {}).get("ec") in (200, "200"))
    verify_ok = final.get("diamondVerification", {}).get("allMatch") is True
    status_ok = pk_status_verify.get("ok") is True or args.skip_pk_status_verify
    rank_ok = withdraw_rank_verify.get("ok") is True or args.skip_withdraw_rank_verify
    target_ok = True
    combined_pk = int(final.get("pkAtm", {}).get("combinedPk") or 0)
    if args.target_combined_pk and args.target_combined_pk > 0:
        target_ok = combined_pk >= args.target_combined_pk
        report["targetCombinedPk"] = args.target_combined_pk
        report["targetCombinedPkOk"] = target_ok
    report["ok"] = close_ok and (verify_ok or args.skip_diamond_verify) and status_ok and rank_ok and target_ok

    if not target_ok:
        report["error"] = f"双方总 PK {combined_pk:,} 未达目标 {args.target_combined_pk:,}"
    elif not rank_ok and not args.skip_withdraw_rank_verify:
        report["error"] = withdraw_rank_verify.get("error") or "提款排名 MOA 验收未通过"

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


def _optional_int(value: str | None) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    return int(value)


def main() -> int:
    parser = argparse.ArgumentParser(description="PK 提款机测试：配置→造数→预期→结束→钻石验收")
    parser.add_argument("--phone-a", default="13311111111", help="A 方房主手机号")
    parser.add_argument("--phone-b", default="13311111115", help="B 方房主手机号")
    parser.add_argument("--gift-count", type=int, default=20, help="送礼账号数")
    parser.add_argument("--gift-min-diamonds", type=int, default=1, help="单笔最小钻石")
    parser.add_argument("--gift-max-diamonds", type=int, default=1000, help="单笔最大钻石")
    parser.add_argument("--pre-gift-wait", type=int, default=20, help="匹配开始后、送礼前等待秒数")
    parser.add_argument("--post-gift-wait", type=int, default=20, help="全部送礼后、结束 PK 前等待秒数")
    parser.add_argument("--post-close-wait", type=int, default=8, help="结束 PK 后等待发钻秒数")
    parser.add_argument("--match-timeout", type=int, default=90, help="每轮随机匹配等待秒数")
    parser.add_argument(
        "--match-retries",
        type=int,
        default=MAX_CROSS_ROOM_MATCH_RETRIES,
        help=f"随机匹配失败/配错房间时的重试轮数（上限 {MAX_CROSS_ROOM_MATCH_RETRIES}，用尽则任务失败）",
    )
    parser.add_argument(
        "--skip-party-room-check",
        action="store_true",
        help="跳过匹配前「已登录且在自己的房间内」校验（仅 MOA 调试）",
    )
    parser.add_argument(
        "--party-room-check-since",
        type=int,
        default=300,
        help="匹配前 Tunnel heartbeat/进房 回溯秒数（默认 300）",
    )
    parser.add_argument("--pk-minute", type=int, default=5, choices=(2, 5, 10, 30), help="随机匹配 PK 时长（分钟）")
    parser.add_argument("--senders", default="", help="逗号分隔送礼 userId，默认 20 个测试号")
    parser.add_argument("--out-dir", default=".tmp", help="报告输出目录")
    parser.add_argument("--config-file", default="", help="服务配置 JSON（默认 workflow/config/pk_atm_default_config.json）")
    parser.add_argument("--min-combined-pk", type=_optional_int, default=None, help="覆盖场次最低 PK 门槛")
    parser.add_argument("--personal-pk-threshold", type=_optional_int, default=None, help="覆盖个人领奖 PK 门槛")
    parser.add_argument("--target-combined-pk", type=int, default=0, help="验收：双方总 PK 须达到该值（0=不校验）")
    parser.add_argument("--assume-first-win", action="store_true", help="预期计算假设当日首胜 ×2")
    parser.add_argument("--skip-config-fetch", action="store_true", help="跳过 MOA 拉配置，仅用本地配置")
    parser.add_argument("--skip-diamond-verify", action="store_true", help="跳过钻石到账一致性校验")
    parser.add_argument("--skip-pk-status-verify", action="store_true", help="跳过 PK 结束前赛况/对战 MOA 验收")
    parser.add_argument(
        "--require-pk-situation-list",
        action="store_true",
        help="强制要求活动页赛况列表接口返回并匹配（默认仅验收 getAcrossRoomPkInfo 对战信息）",
    )
    parser.add_argument(
        "--skip-withdraw-rank-verify",
        action="store_true",
        help="跳过 PK 结束后提款排名/吸底/本周总提款 MOA 验收",
    )
    parser.add_argument(
        "--require-withdraw-rank-api",
        action="store_true",
        help="强制要求提款排名 MOA 接口返回并匹配（默认接口未映射时跳过 MOA 层）",
    )
    args = parser.parse_args()
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
