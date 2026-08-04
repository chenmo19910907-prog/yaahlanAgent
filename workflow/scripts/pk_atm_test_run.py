#!/usr/bin/env python3
"""PK 提款机测试：拉配置 → 随机匹配跨房 PK → 麦上机器人 → 随机送礼 → PK 赛况/对战验收 → 结算预期 → 结束 PK → 钻石到账验收 → 提款排名/吸底/本周总提款验收。

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
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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

# PK 提款机活动页「赛况」tab 候选（测试环境 MSE 可能未注册 withdraw-v2-api）
_SITUATION_LIST_CANDIDATES: list[tuple[str, str]] = [
    ("/service/vas/activity/across-room-pk-withdraw-v2-api", "home"),
    ("/service/vas/activity/across-room-pk-withdraw-v2-api", "getPkSituationList"),
    ("/service/vas/activity/across-room-pk-withdraw-v2-api", "getPkStatusList"),
    ("/service/vas/activity/pk-withdraw-api", "home"),
    ("/service/vas/activity/pk-withdraw-api", "getPkSituationList"),
]

# PK 提款机活动页「提款排名」tab + 本周总提款 / 吸底候选（待抓包映射）
_WITHDRAW_RANK_CANDIDATES: list[tuple[str, str]] = [
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
    body_file = tmp / f"{method}.body.json"
    body_file.write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
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
            str(tmp / f"{method}.payload.json"),
            "--timeout-ms",
            "20000",
            "--strict",
            str(strict),
        ]
    )


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
    proc = subprocess.run(
        [
            sys.executable,
            "MOA/moa_execute.py",
            "--query-user-by-phone",
            phone,
            "--phone-output",
            "json",
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
        raise RuntimeError(f"手机号 {phone} 未解析到 userId: {data}")

    admin = _run_json(
        [sys.executable, "Admin/admin_execute.py", "--query-user-id", user_id],
        timeout=60,
    )
    owned = admin.get("ownedRoomInfo") if isinstance(admin.get("ownedRoomInfo"), dict) else {}
    room_id = str(admin.get("roomId") or owned.get("roomId") or "")
    if not room_id:
        raise RuntimeError(f"userId {user_id}（{phone}）无 ownedRoomInfo.roomId")
    return RoomParty(phone=phone, user_id=user_id, room_id=room_id)


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
        "roomName": str(block.get("roomName") or ""),
        "roomAvatar": str(block.get("roomAvatar") or ""),
    }


def _extract_situation_items(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if not isinstance(data, dict):
        return []
    for key in (
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
    for key in ("acrossRoomPkId", "pkId", "roomPkId", "id"):
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


def _moa_party_body(party: RoomParty, *, viewer_user_id: str | None = None) -> dict[str, Any]:
    return {
        "userId": viewer_user_id or party.user_id,
        "roomId": party.room_id,
        "lang": "en",
        "area": "MENA",
        "appId": "2005",
        "os": "android",
        "osType": "android",
    }


def _fetch_withdraw_rank_page(
    party: RoomParty, *, viewer_user_id: str | None = None
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], str | None]:
    body = _moa_party_body(party, viewer_user_id=viewer_user_id)
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


def _match_tier(combined_pk: int, cfg: PkAtmConfig) -> dict[str, Any]:
    hit = None
    for tier in cfg.tiers:
        if combined_pk <= tier["maxCombinedPk"]:
            hit = {
                "thresholdPk": tier["maxCombinedPk"],
                "poolDiamonds": tier["poolDiamonds"],
                "ratioPct": tier.get("ratioPct"),
            }
            break
    return {
        "combinedPk": combined_pk,
        "minPkForReward": cfg.min_combined_pk,
        "eligible": combined_pk >= cfg.min_combined_pk,
        "tier": hit,
        "personalPkThreshold": cfg.personal_pk_threshold,
    }


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


def _begin_random_match_cross_room_pk(
    party_a: RoomParty,
    party_b: RoomParty,
    *,
    timeout_sec: int = 120,
    pk_minute: str = "5",
) -> tuple[str, dict[str, Any]]:
    """两房先后发起随机匹配（acrossPkType=1），等待配对成功并返回 pkId。"""
    step: dict[str, Any] = {"mode": "random", "acrossPkType": "1"}
    step["prepare"] = _prepare_random_match(party_a, party_b)

    match_a = _apply_random_match(party_a, pk_minute=pk_minute)
    time.sleep(1)
    match_b = _apply_random_match(party_b, pk_minute=pk_minute)
    step["matchA"] = match_a
    step["matchB"] = match_b

    pending = [m for m in (match_a, match_b) if m.get("ec") == 20210111]
    if pending:
        step["prepareRetry"] = _prepare_random_match(party_a, party_b)
        for item in pending:
            party = party_a if item["phone"] == party_a.phone else party_b
            retry = _apply_random_match(party, pk_minute=pk_minute)
            step[f"matchRetry_{party.phone}"] = retry
            if party is party_a:
                match_a = retry
            else:
                match_b = retry
        step["matchA"] = match_a
        step["matchB"] = match_b

    failed = [m for m in (match_a, match_b) if m.get("ec") not in (200, "200", 0, "0")]
    if failed:
        step["error"] = "随机匹配发起失败"
        step["failed"] = failed
        raise RuntimeError(f"applyAcrossRoomPk 随机匹配失败: {failed}")

    pk_data = _wait_pk_matched(party_a, party_b.room_id, timeout_sec=timeout_sec)
    pk_id = str(pk_data.get("acrossRoomPkId") or "")
    if not pk_id:
        raise RuntimeError("随机匹配未返回 acrossRoomPkId")
    step["pkId"] = pk_id
    step["stage"] = pk_data.get("stage")
    step["rooms"] = {
        party_a.room_id: party_b.room_id,
        party_b.room_id: party_a.room_id,
    }
    return pk_id, step


def _wait_pk_matched(party: RoomParty, other_room_id: str, *, timeout_sec: int = 120) -> dict[str, Any]:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        data = _pk_info(party)
        pk_id = data.get("acrossRoomPkId")
        across = (data.get("acrossRoomInfo") or {}).get("roomId")
        stage = data.get("stage")
        if pk_id and str(across) == str(other_room_id) and stage is not None:
            return data
        time.sleep(2)
    raise TimeoutError(f"等待随机匹配超时（{timeout_sec}s）: room={party.room_id} expect={other_room_id}")


def _add_room_bots(room_id: str, total: int, on_mic: int) -> dict[str, Any]:
    proc = subprocess.run(
        [
            sys.executable,
            "MOA/moa_execute.py",
            "--payload-file",
            "MOA/templates/房间-增加机器人.json",
            "--room-bot-room-id",
            room_id,
            "--room-bot-total",
            str(total),
            "--room-bot-on-mic",
            str(on_mic),
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=60,
    )
    raw = proc.stdout or ""
    start = raw.find("{")
    if start < 0:
        return {"ok": proc.returncode == 0, "stderr": proc.stderr}
    return json.loads(raw[start:])


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
    """每个送礼人在各房间的 PK 贡献（优先服务端榜单，否则钻石×10 累加）。"""
    a_ranks = _rank_map(pk_data.get("roomRankList"))
    b_ranks = _rank_map(pk_data.get("acrossRoomRankList"))
    calc: dict[str, dict[str, int]] = {}
    for g in gifts:
        if not g.get("ok"):
            continue
        sender = g["sender"]
        room_id = g["roomId"]
        calc.setdefault(sender, {})
        calc[sender][room_id] = calc[sender].get(room_id, 0) + int(g["diamonds"]) * 10

    out: dict[str, dict[str, Any]] = {}
    for sender, room_map in calc.items():
        per_room: dict[str, Any] = {}
        for room_id, calc_pk in room_map.items():
            rank_info = a_ranks.get(sender) if room_id == party_a.room_id else b_ranks.get(sender)
            api_pk = rank_info["pkValue"] if rank_info else 0
            if api_pk > 0:
                per_room[room_id] = {"pkValue": api_pk, "source": "服务端榜单"}
            else:
                per_room[room_id] = {"pkValue": calc_pk, "source": "钻石×10累加"}
        out[sender] = per_room
    return out


def _winner_from_pk(
    room_a_pk: int, room_b_pk: int, party_a: RoomParty, party_b: RoomParty
) -> tuple[RoomParty | None, RoomParty | None, int]:
    if room_a_pk > room_b_pk:
        return party_a, party_b, room_a_pk
    if room_b_pk > room_a_pk:
        return party_b, party_a, room_b_pk
    return None, None, room_a_pk


def _calc_expected_rewards(
    *,
    cfg: PkAtmConfig,
    pk_data: dict[str, Any],
    party_a: RoomParty,
    party_b: RoomParty,
    sender_pk: dict[str, dict[str, Any]],
    assume_first_win: bool,
) -> dict[str, Any]:
    room_a_pk = int(pk_data.get("roomRankValue") or 0)
    room_b_pk = int(pk_data.get("acrossRoomRankValue") or 0)
    combined = room_a_pk + room_b_pk
    atm = _match_tier(combined, cfg)
    winner, loser, win_room_pk = _winner_from_pk(room_a_pk, room_b_pk, party_a, party_b)

    pool = (atm.get("tier") or {}).get("poolDiamonds") or 0
    if not atm.get("eligible") or not winner or win_room_pk <= 0 or pool <= 0:
        return {
            "atm": atm,
            "winnerRoomId": winner.room_id if winner else None,
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
                "reason": f"个人 PK {personal_pk} < 门槛 {cfg.personal_pk_threshold}",
                "personalPk": personal_pk,
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
            "roomPkByRoom": rooms,
            "formula": f"floor({pool}×{personal_pk}/{win_room_pk})"
            + (f"×{cfg.first_win_multiplier}" if assume_first_win else ""),
        }

    return {
        "atm": atm,
        "winnerRoomId": win_room_id,
        "poolDiamonds": pool,
        "winRoomTotalPk": win_room_pk,
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
) -> dict[str, Any]:
    room_a_pk = int(pk_end.get("roomRankValue") or 0)
    room_b_pk = int(pk_end.get("acrossRoomRankValue") or 0)
    winner, loser, win_room_pk = _winner_from_pk(room_a_pk, room_b_pk, party_a, party_b)

    contributors: list[dict[str, Any]] = []
    for g in gifts:
        sender = g["sender"]
        room_id = g["roomId"]
        room_total = room_a_pk if room_id == party_a.room_id else room_b_pk
        pk_info = (sender_pk.get(sender) or {}).get(room_id) or {"pkValue": 0, "source": "—"}
        pk_value = int(pk_info.get("pkValue") or 0)
        contributors.append(
            {
                "sender": sender,
                "roomId": room_id,
                "receiver": g["receiver"],
                "diamonds": g["diamonds"],
                "pkValue": pk_value,
                "pkValueSource": pk_info.get("source"),
                "roomTotalPk": room_total,
                "sharePct": round(pk_value / room_total * 100, 2) if room_total else 0.0,
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
            "draw": room_a_pk == room_b_pk,
            "winRoomTotalPk": win_room_pk,
        },
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
    if tier:
        ratio = tier.get("ratioPct")
        ratio_txt = f"（返奖比 {ratio}%）" if ratio is not None else ""
        lines.append(
            f"- 命中档位：≤{tier['thresholdPk']:,} PK → 本场总奖金 **{tier['poolDiamonds']:,}** 钻{ratio_txt}"
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
            )
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

    bots_a = _add_room_bots(party_a.room_id, args.bot_total, args.bot_on_mic)
    bots_b = _add_room_bots(party_b.room_id, args.bot_total, args.bot_on_mic)
    report["steps"].append({"bots": {party_a.room_id: bots_a, party_b.room_id: bots_b}})

    if args.pre_gift_wait > 0:
        time.sleep(args.pre_gift_wait)

    mic_rooms = _mic_users_by_room(_pk_info(party_a, pk_id=pk_id))
    if not mic_rooms:
        report["error"] = "无麦上用户，无法送礼"
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1

    senders = [s.strip() for s in (args.senders or "").split(",") if s.strip()] or DEFAULT_SENDERS
    senders = [s for s in senders if s not in (party_a.user_id, party_b.user_id)]
    random.shuffle(senders)
    senders = senders[: args.gift_count]

    gifts: list[dict[str, Any]] = []
    room_ids = list(mic_rooms.keys())
    for sender in senders:
        room_id = random.choice(room_ids)
        receiver = random.choice(mic_rooms[room_id])
        diamonds = random.randint(args.gift_min_diamonds, args.gift_max_diamonds)
        try:
            res = _gift_send(sender, room_id, receiver, diamonds)
            gifts.append(
                {
                    "sender": sender,
                    "roomId": room_id,
                    "receiver": receiver,
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
                    "diamonds": diamonds,
                    "ok": False,
                    "error": str(exc),
                }
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
    report["ok"] = close_ok and (verify_ok or args.skip_diamond_verify) and status_ok and rank_ok

    if not rank_ok and not args.skip_withdraw_rank_verify:
        report["error"] = withdraw_rank_verify.get("error") or "提款排名 MOA 验收未通过"

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


def _optional_int(value: str | None) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    return int(value)


def main() -> int:
    parser = argparse.ArgumentParser(description="PK 提款机测试：配置→造数→预期→结束→钻石验收")
    parser.add_argument("--phone-a", default="13311111113", help="A 方房主手机号")
    parser.add_argument("--phone-b", default="13311111114", help="B 方房主手机号")
    parser.add_argument("--bot-total", type=int, default=5, help="每房机器人数")
    parser.add_argument("--bot-on-mic", type=int, default=5, help="每房麦上机器人数")
    parser.add_argument("--gift-count", type=int, default=20, help="送礼账号数")
    parser.add_argument("--gift-min-diamonds", type=int, default=1, help="单笔最小钻石")
    parser.add_argument("--gift-max-diamonds", type=int, default=1000, help="单笔最大钻石")
    parser.add_argument("--pre-gift-wait", type=int, default=20, help="加机器人后、送礼前等待秒数")
    parser.add_argument("--post-gift-wait", type=int, default=20, help="全部送礼后、结束 PK 前等待秒数")
    parser.add_argument("--post-close-wait", type=int, default=8, help="结束 PK 后等待发钻秒数")
    parser.add_argument("--match-timeout", type=int, default=120, help="随机匹配等待秒数")
    parser.add_argument("--pk-minute", type=int, default=5, choices=(5, 10, 30), help="随机匹配 PK 时长（分钟）")
    parser.add_argument("--senders", default="", help="逗号分隔送礼 userId，默认 20 个测试号")
    parser.add_argument("--out-dir", default=".tmp", help="报告输出目录")
    parser.add_argument("--config-file", default="", help="服务配置 JSON（默认 workflow/config/pk_atm_default_config.json）")
    parser.add_argument("--min-combined-pk", type=_optional_int, default=None, help="覆盖场次最低 PK 门槛")
    parser.add_argument("--personal-pk-threshold", type=_optional_int, default=None, help="覆盖个人领奖 PK 门槛")
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
