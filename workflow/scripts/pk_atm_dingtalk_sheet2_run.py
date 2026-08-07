#!/usr/bin/env python3
"""PK 提款机全流程 → 钉钉 Sheet2 验收记录。"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import random
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
GATEWAY = REPO / "platform/dingtalk_gateway"
_EXCEL_VENV = REPO / ".cursor/skills/testcase-to-excel/mcp_dingtalk_excel/venv/bin/python3.13"

DEFAULT_WORKBOOK = "https://alidocs.dingtalk.com/i/nodes/oP0MALyR8k7Aow9wCY9wvqBd83bzYmDO"
DEFAULT_SHEET = "Sheet2"
SHEET_PREFIX = "测试结果"
DEFAULT_PERSONAL_PK_THRESHOLD = 10000  # MSE minMemberRewardPk，以服务端配置为准

SHEET2_HEADER = [
    "房间id",
    "房主id",
    "房主手机号",
    "用户id",
    "用户手机号",
    "送礼PK值",
    "房间PK值",
    "总PK值",
    "胜负",
    "是否首胜",
    "下发总钻石数",
    "应得钻石",
    "实发钻石",
    "弹窗总钻石数",
    "弹窗用户钻石",
    "PK页总钻石",
    "PK页增加钻石数",
    "测试结果总结",
    "说明",
]

if str(GATEWAY) not in sys.path:
    sys.path.insert(0, str(GATEWAY))
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "workflow/scripts"))
import pk_atm_test_run as pk  # noqa: E402

from MOA.scripts.pk_atm_page_query import query_pk_atm_page  # noqa: E402


def _run_generative(method: str, body: dict[str, Any]) -> dict[str, Any]:
    proc = subprocess.run(
        [
            sys.executable,
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
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "MOA 失败")[-400:])
    return json.loads(proc.stdout)


def _biz_data(resp: dict[str, Any]) -> dict[str, Any]:
    biz = resp.get("business") or {}
    if biz.get("ec") not in (200, "200", 0, "0"):
        raise RuntimeError(f"MOA ec={biz.get('ec')} em={biz.get('em')}")
    data = biz.get("data")
    if not isinstance(data, dict):
        raise RuntimeError("MOA data 非对象")
    return data


def _query_popup(user_id: str, room_id: str, pk_id: str) -> dict[str, Any]:
    body = {
        "userId": user_id,
        "uid": user_id,
        "roomId": room_id,
        "pkId": pk_id,
        "lang": "en",
        "area": "MENA",
        "appId": "2005",
        "os": "android",
        "osType": "android",
        "originRsp": 1,
        "dataType": "json",
        "_version_": 1000,
    }
    return _biz_data(_run_generative("getPkAtmMatchRewardDetail", body))


def _party_from_dict(data: dict[str, Any]) -> pk.RoomParty:
    return pk.RoomParty(
        phone=str(data.get("phone") or ""),
        user_id=str(data.get("user_id") or ""),
        room_id=str(data.get("room_id") or ""),
    )


def _reconcile_sender_pk(report: dict[str, Any]) -> None:
    """按 App 贡献榜 contributionAcrossRanks 重算各用户 PK 贡献。"""
    parties = report.get("parties") or {}
    party_a = _party_from_dict(parties.get("a") or {})
    party_b = _party_from_dict(parties.get("b") or {})
    gifts = report.get("gifts") or []
    if not gifts:
        return

    pk_data = {
        "acrossRoomPkId": report.get("pkId"),
        "roomRankValue": int(report.get("roomAPk") or 0),
        "acrossRoomRankValue": int(report.get("roomBPk") or 0),
        "roomRankList": report.get("roomRankList"),
        "acrossRoomRankList": report.get("acrossRoomRankList"),
    }
    sender_pk = pk._sender_pk_map(gifts, pk_data, party_a, party_b)
    report["senderPkByRoom"] = sender_pk

    for contributor in report.get("contributors") or []:
        if not isinstance(contributor, dict):
            continue
        sender = str(contributor.get("sender") or "")
        room_id = str(contributor.get("roomId") or "")
        pk_info = (sender_pk.get(sender) or {}).get(room_id) or {}
        sender_room_pk = int(pk_info.get("pkValue") or 0)
        contributor["senderRoomPk"] = sender_room_pk
        contributor["pkValue"] = sender_room_pk
        if sender_room_pk > 0:
            contributor["pkValueSource"] = pk_info.get("source") or contributor.get("pkValueSource")

    expected = report.get("expectedRewards") or {}
    users = expected.get("users") or {}
    winner_room = str(
        (report.get("winner") or {}).get("roomId")
        or expected.get("winnerRoomId")
        or ""
    )
    for uid, rooms in sender_pk.items():
        entry = users.setdefault(uid, {})
        personal_pk = int((rooms.get(winner_room) or {}).get("pkValue") or 0) if winner_room else sum(
            int((room_info or {}).get("pkValue") or 0) for room_info in rooms.values()
        )
        entry["personalPk"] = personal_pk
        entry["roomPkByRoom"] = rooms


def _reconcile_report_by_closer(report: dict[str, Any]) -> None:
    """按主动结束 PK 方记败规则，重算胜负、应得钻石与验收项。"""
    _reconcile_sender_pk(report)
    closer_phone = str(report.get("closerPhone") or (report.get("closer") or {}).get("phone") or "")
    if not closer_phone:
        return

    parties = report.get("parties") or {}
    party_a = _party_from_dict(parties.get("a") or {})
    party_b = _party_from_dict(parties.get("b") or {})
    if closer_phone == party_a.phone:
        closer = party_a
    elif closer_phone == party_b.phone:
        closer = party_b
    else:
        return

    room_a_pk = int(report.get("roomAPk") or 0)
    room_b_pk = int(report.get("roomBPk") or 0)
    sender_pk = report.get("senderPkByRoom") or {}
    cfg_dict = report.get("serviceConfig") or {}
    file_cfg = pk._load_default_config_file(pk.DEFAULT_CONFIG_PATH)
    # 报告内 MOA 快照可能滞后；个人门槛以 workflow/config 登记的服务端口径为准
    personal_threshold = int(
        file_cfg.get("personalPkThreshold")
        or cfg_dict.get("personalPkThreshold")
        or DEFAULT_PERSONAL_PK_THRESHOLD
    )
    cfg_dict = {**cfg_dict, "personalPkThreshold": personal_threshold}
    report["serviceConfig"] = cfg_dict
    cfg = pk.PkAtmConfig(
        source=str(cfg_dict.get("source") or "report"),
        min_combined_pk=int(cfg_dict.get("minCombinedPk") or 20000),
        personal_pk_threshold=personal_threshold,
        first_win_multiplier=int(cfg_dict.get("firstWinMultiplier") or 2),
        tiers=list(cfg_dict.get("tiers") or []),
        raw=cfg_dict.get("raw"),
    )
    pk_data = {"roomRankValue": room_a_pk, "acrossRoomRankValue": room_b_pk}
    expected = pk._calc_expected_rewards(
        cfg=cfg,
        pk_data=pk_data,
        party_a=party_a,
        party_b=party_b,
        sender_pk=sender_pk,
        assume_first_win=bool(report.get("assumeFirstWin")),
        closer=closer,
    )
    report["expectedRewards"] = expected
    report["pkAtm"] = expected.get("atm") or report.get("pkAtm")

    winner, loser, win_room_pk, outcome_rule = pk._resolve_outcome(
        room_a_pk,
        room_b_pk,
        party_a,
        party_b,
        closer=closer,
    )
    report["closer"] = closer.__dict__
    report["closerPhone"] = closer.phone
    report["outcomeRule"] = outcome_rule
    if winner:
        report["winner"] = {
            "phone": winner.phone,
            "userId": winner.user_id,
            "roomId": winner.room_id,
        }
    if loser:
        report["loser"] = {
            "phone": loser.phone,
            "userId": loser.user_id,
            "roomId": loser.room_id,
        }

    rooms = report.get("rooms") or {}
    for room_id, info in rooms.items():
        if not isinstance(info, dict):
            continue
        if winner and room_id == winner.room_id:
            info["result"] = "胜"
        elif loser and room_id == loser.room_id:
            info["result"] = "负"

    result = report.get("result") or {}
    if winner:
        result["winnerRoomId"] = winner.room_id
    if loser:
        result["loserRoomId"] = loser.room_id
    result["winRoomTotalPk"] = win_room_pk
    result["outcomeRule"] = outcome_rule
    report["result"] = result

    _finalize_expected_after_popup(report)


def _close_from(closer: pk.RoomParty, other: pk.RoomParty, pk_id: str) -> dict[str, Any]:
    body = {
        "userId": closer.user_id,
        "roomId": closer.room_id,
        "acrossRoomId": other.room_id,
        "acrossRoomPkId": pk_id,
        "lang": "en",
        "area": "MENA",
        "appId": "2005",
        "os": "android",
        "osType": "android",
    }
    return pk._moa("closeAcrossRoomPk", body, strict=0)


def _threshold_diamonds(cfg: pk.PkAtmConfig) -> int:
    return max(1, int(cfg.personal_pk_threshold or DEFAULT_PERSONAL_PK_THRESHOLD) // 10)


def _cell(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "是" if v else "否"
    return str(v)


def _load_phone_map() -> dict[str, str]:
    path = REPO / "testcase-kb/admin_user_pool_profiles.json"
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    data = json.loads(path.read_text(encoding="utf-8"))
    records = data.get("records") if isinstance(data, dict) else data
    if not isinstance(records, list):
        return out
    for item in records:
        if not isinstance(item, dict):
            continue
        uid = str(item.get("userId") or "").strip()
        phone = str(item.get("phone") or "").replace("+86 ", "").strip()
        if uid and phone:
            out[uid] = phone
    return out


def _cross_room_senders(gifts: list[dict[str, Any]]) -> set[str]:
    by_sender: dict[str, set[str]] = {}
    for g in gifts:
        if not g.get("ok"):
            continue
        by_sender.setdefault(str(g["sender"]), set()).add(str(g["roomId"]))
    return {uid for uid, rooms in by_sender.items() if len(rooms) > 1}


def _snapshot_users_page_sticky(user_ids: list[str]) -> dict[str, dict[str, Any]]:
    users: dict[str, dict[str, Any]] = {}
    for uid in user_ids:
        page = query_pk_atm_page(user_id=uid)
        cu = page.get("currentUser") if isinstance(page.get("currentUser"), dict) else {}
        users[uid] = {
            "weekWithdraw": cu.get("rewardValue"),
            "weekTotalWithdraw": page.get("weekTotalWithdrawDiamonds"),
        }
        time.sleep(0.12)
    return users


def _winner_personal_pk(uid: str, winner_room_id: str, sender_pk: dict[str, dict[str, Any]]) -> int:
    return int(((sender_pk.get(uid) or {}).get(winner_room_id) or {}).get("pkValue") or 0)


def _is_reward_eligible(*, personal_pk: int, personal_threshold: int, is_winner: bool) -> bool:
    return is_winner and personal_pk >= personal_threshold


def _verify_winner_popups(
    *,
    winner_room_id: str,
    pk_id: str,
    winner_uids: list[str],
    sender_pk: dict[str, dict[str, Any]],
    diamond_items: dict[str, dict[str, Any]],
    personal_threshold: int,
) -> dict[str, Any]:
    users: dict[str, Any] = {}
    room_total: int | None = None
    all_ok = True
    for uid in winner_uids:
        exp_pk = _winner_personal_pk(uid, winner_room_id, sender_pk)
        delta = diamond_items.get(uid, {}).get("diamondDelta")
        if not _is_reward_eligible(
            personal_pk=exp_pk, personal_threshold=personal_threshold, is_winner=True
        ):
            below_ok = delta in (None, 0)
            users[uid] = {
                "eligible": False,
                "myPkValue": exp_pk,
                "expectedPkValue": exp_pk,
                "myRewardDiamond": 0,
                "expectedReward": 0,
                "firstWinExtraDiamond": 0,
                "firstWin": False,
                "pkOk": True,
                "rewardOk": below_ok,
                "ok": below_ok,
                "reason": f"个人PK {exp_pk} < 门槛 {personal_threshold}，不应发钻",
            }
            if not below_ok:
                all_ok = False
            continue
        try:
            popup = _query_popup(uid, winner_room_id, pk_id)
            my_info = popup.get("myInfo") or {}
            if room_total is None:
                room_total = int(popup.get("roomTotalDiamond") or 0)
            my_pk = int(my_info.get("myPkValue") or 0)
            my_reward = int(my_info.get("myRewardDiamond") or 0)
            first_win_extra = int(my_info.get("firstWinExtraDiamond") or 0)
            pk_ok = my_pk == exp_pk
            reward_ok = delta is not None and my_reward == int(delta)
            user_ok = pk_ok and reward_ok
            users[uid] = {
                "eligible": True,
                "myPkValue": my_pk,
                "expectedPkValue": exp_pk,
                "myRewardDiamond": my_reward,
                "firstWinExtraDiamond": first_win_extra,
                "firstWin": first_win_extra > 0,
                "pkOk": pk_ok,
                "rewardOk": reward_ok,
                "ok": user_ok,
            }
            if not user_ok:
                all_ok = False
        except (RuntimeError, json.JSONDecodeError, subprocess.TimeoutExpired, ValueError) as exc:
            users[uid] = {"eligible": True, "ok": False, "error": str(exc)}
            all_ok = False
    return {"ok": all_ok, "roomTotalDiamond": room_total, "users": users}


def _verify_users_page_sticky(
    *,
    user_ids: list[str],
    page_before: dict[str, dict[str, Any]],
    page_after: dict[str, dict[str, Any]],
    diamond_items: dict[str, dict[str, Any]],
    winner_room: str,
    winner_uids: set[str],
    sender_pk: dict[str, dict[str, Any]],
    personal_threshold: int,
) -> dict[str, Any]:
    users: dict[str, Any] = {}
    all_ok = True
    before_total = next(iter(page_before.values()), {}).get("weekTotalWithdraw") if page_before else None
    after_total = next(iter(page_after.values()), {}).get("weekTotalWithdraw") if page_after else None
    payout_sum = sum(
        max(0, int(diamond_items.get(uid, {}).get("diamondDelta") or 0))
        for uid in user_ids
        if uid in winner_uids
        and _is_reward_eligible(
            personal_pk=_winner_personal_pk(uid, winner_room, sender_pk),
            personal_threshold=personal_threshold,
            is_winner=True,
        )
    )
    week_delta = None
    week_ok = True
    if before_total is not None and after_total is not None:
        week_delta = int(after_total) - int(before_total)
        week_ok = week_delta == payout_sum
        if not week_ok:
            all_ok = False
    for uid in user_ids:
        before = page_before.get(uid, {}).get("weekWithdraw")
        after = page_after.get(uid, {}).get("weekWithdraw")
        delta = None
        sticky_ok = True
        if before is not None and after is not None:
            delta = int(after) - int(before)
            if uid in winner_uids:
                personal_pk = _winner_personal_pk(uid, winner_room, sender_pk)
                eligible = _is_reward_eligible(
                    personal_pk=personal_pk,
                    personal_threshold=personal_threshold,
                    is_winner=True,
                )
                if not eligible:
                    sticky_ok = delta == 0
                else:
                    exp_delta = diamond_items.get(uid, {}).get("diamondDelta")
                    if exp_delta is not None:
                        sticky_ok = delta == int(exp_delta)
                    else:
                        sticky_ok = False
            else:
                sticky_ok = delta == 0
        else:
            sticky_ok = False
        users[uid] = {
            "weekWithdrawBefore": before,
            "weekWithdrawAfter": after,
            "delta": delta,
            "ok": sticky_ok,
            "isWinner": uid in winner_uids,
            "eligible": _is_reward_eligible(
                personal_pk=_winner_personal_pk(uid, winner_room, sender_pk),
                personal_threshold=personal_threshold,
                is_winner=uid in winner_uids,
            ),
        }
        if not sticky_ok:
            all_ok = False
    return {
        "ok": all_ok,
        "weekTotalCheck": {
            "before": before_total,
            "after": after_total,
            "delta": week_delta,
            "expectedDelta": payout_sum,
            "ok": week_ok,
        },
        "users": users,
    }


def _calc_user_expected_diamond(
    *,
    pool_diamonds: int,
    win_room_total_pk: int,
    personal_pk: int,
    personal_threshold: int,
    is_winner: bool,
    first_win: bool,
    first_win_multiplier: int,
    first_win_extra: int = 0,
) -> int:
    """按胜方奖池与个人 PK 占比计算应得钻石；首胜叠加 extra 或 ×倍数。"""
    if not is_winner or personal_pk < personal_threshold:
        return 0
    if pool_diamonds <= 0 or win_room_total_pk <= 0:
        return 0
    base = math.floor(pool_diamonds * personal_pk / win_room_total_pk)
    if not first_win:
        return base
    if first_win_extra > 0:
        return base + first_win_extra
    return base * max(1, first_win_multiplier)


def _resolve_reward_tier(report: dict[str, Any]) -> dict[str, Any] | None:
    combined = int(
        report.get("combinedPk")
        or (report.get("pkAtm") or {}).get("combinedPk")
        or ((report.get("expectedRewards") or {}).get("atm") or {}).get("combinedPk")
        or 0
    )
    cfg_raw = report.get("serviceConfig") or {}
    tiers = cfg_raw.get("tiers") or []
    if combined > 0 and tiers:
        cfg = pk.PkAtmConfig(
            source=str(cfg_raw.get("source") or "sheet"),
            min_combined_pk=int(cfg_raw.get("minCombinedPk") or 20000),
            personal_pk_threshold=int(cfg_raw.get("personalPkThreshold") or DEFAULT_PERSONAL_PK_THRESHOLD),
            first_win_multiplier=int(cfg_raw.get("firstWinMultiplier") or 2),
            tiers=tiers,
            raw=cfg_raw.get("raw") or cfg_raw,
        )
        return pk._match_tier(combined, cfg).get("tier")
    tier = (report.get("pkAtm") or {}).get("tier")
    if tier:
        return tier
    return ((report.get("expectedRewards") or {}).get("atm") or {}).get("tier")


def _calc_dispatch_total_diamonds(report: dict[str, Any]) -> int:
    """送礼钻石（总 PK/10）× 命中档位返钻比例 %（向下取整）。"""
    combined = int(
        report.get("combinedPk")
        or (report.get("pkAtm") or {}).get("combinedPk")
        or ((report.get("expectedRewards") or {}).get("atm") or {}).get("combinedPk")
        or 0
    )
    if combined <= 0:
        return 0
    min_pk = int(
        (report.get("pkAtm") or {}).get("minPkForReward")
        or (report.get("serviceConfig") or {}).get("minCombinedPk")
        or 20000
    )
    tier = _resolve_reward_tier(report)
    atm = {
        "eligible": combined >= min_pk,
        "tier": tier or {},
    }
    return pk._calc_dispatch_pool(combined, atm)


def _resolve_reward_pool(report: dict[str, Any]) -> int:
    pool = _calc_dispatch_total_diamonds(report)
    if pool > 0:
        return pool
    popup = report.get("popupVerify") or {}
    popup_pool = int(popup.get("roomTotalDiamond") or 0)
    if popup_pool > 0:
        return popup_pool
    return int((report.get("expectedRewards") or {}).get("poolDiamonds") or 0)


def _finalize_expected_after_popup(report: dict[str, Any]) -> None:
    """弹窗拿到 roomTotalDiamond / 首胜后，重算应得钻石并回写验收项。"""
    expected = report.get("expectedRewards") or {}
    cfg_raw = (report.get("serviceConfig") or {}).get("raw") or report.get("serviceConfig") or {}
    personal_threshold = int(
        (report.get("serviceConfig") or {}).get("personalPkThreshold")
        or cfg_raw.get("personalPkThreshold")
        or DEFAULT_PERSONAL_PK_THRESHOLD
    )
    multiplier = int((report.get("serviceConfig") or {}).get("firstWinMultiplier") or 2)
    winner_room = str(
        (report.get("winner") or {}).get("roomId")
        or expected.get("winnerRoomId")
        or ""
    )
    pool = _resolve_reward_pool(report)
    win_room_pk = int(expected.get("winRoomTotalPk") or 0)
    popup_users = (report.get("popupVerify") or {}).get("users") or {}
    sender_pk = report.get("senderPkByRoom") or {}

    users: dict[str, Any] = {}
    for uid, rooms in sender_pk.items():
        personal_pk = int((rooms.get(winner_room) or {}).get("pkValue") or 0)
        eligible = _is_reward_eligible(
            personal_pk=personal_pk,
            personal_threshold=personal_threshold,
            is_winner=bool(winner_room and winner_room in rooms),
        )
        pu = popup_users.get(uid) or {}
        first_win = bool(pu.get("firstWin"))
        first_extra = int(pu.get("firstWinExtraDiamond") or 0)
        exp = _calc_user_expected_diamond(
            pool_diamonds=pool,
            win_room_total_pk=win_room_pk,
            personal_pk=personal_pk,
            personal_threshold=personal_threshold,
            is_winner=bool(winner_room and winner_room in rooms),
            first_win=first_win,
            first_win_multiplier=multiplier,
            first_win_extra=first_extra,
        )
        users[uid] = {
            "expectedDiamonds": exp,
            "personalPk": personal_pk,
            "eligible": eligible,
            "firstWinApplied": first_win,
            "firstWinExtraDiamond": first_extra,
            "poolDiamonds": pool,
            "reason": (
                f"个人PK {personal_pk} < 门槛 {personal_threshold}，不应发钻"
                if winner_room in rooms and not eligible
                else ""
            ),
        }
    expected["poolDiamonds"] = pool
    expected["users"] = users
    expected["totalExpectedDiamonds"] = sum(int(u.get("expectedDiamonds") or 0) for u in users.values())
    report["expectedRewards"] = expected

    items = (report.get("diamondVerification") or {}).get("items") or []
    for item in items:
        uid = str(item.get("userId") or "")
        user_info = users.get(uid) or {}
        exp = int(user_info.get("expectedDiamonds") or 0)
        delta = item.get("diamondDelta")
        item["expectedDiamonds"] = exp
        item["eligible"] = user_info.get("eligible")
        if user_info.get("reason"):
            item["reason"] = user_info["reason"]
        if delta is not None:
            if user_info.get("eligible") is False:
                item["match"] = int(delta) == 0
            else:
                item["match"] = int(delta) == exp
    if items:
        report.setdefault("diamondVerification", {})["allMatch"] = all(
            i.get("match") is True
            for i in items
            if i.get("eligible") is not False or int(i.get("diamondDelta") or 0) != 0
        )


def _row_failure_notes(
    *,
    uid: str,
    is_winner: bool,
    cross_room: set[str],
    expected: int,
    actual: int | None,
    pu: dict[str, Any],
    pg: dict[str, Any],
    personal_pk: int,
    personal_threshold: int,
) -> str:
    notes: list[str] = []
    if uid in cross_room:
        notes.append("双房送礼")
    eligible = _is_reward_eligible(
        personal_pk=personal_pk,
        personal_threshold=personal_threshold,
        is_winner=is_winner,
    )
    if is_winner and not eligible:
        if actual not in (None, 0):
            notes.append(f"个人PK {personal_pk} 未达门槛 {personal_threshold}，不应发钻")
        if pu.get("myRewardDiamond") not in (None, 0):
            notes.append("弹窗仍展示返钻")
        if pg.get("delta") not in (None, 0):
            notes.append(f"PK页增量应为0，实际{pg.get('delta')}")
        return "；".join(notes)
    if is_winner:
        if actual is not None and expected != int(actual):
            notes.append(f"应得{expected}≠实发{actual}")
        if pu.get("ok") is False:
            notes.append(pu.get("error") or "弹窗验收失败")
        if pg.get("ok") is False:
            notes.append("PK页增加钻石数失败")
        elif pg.get("delta") is not None and expected != int(pg.get("delta") or 0):
            notes.append(f"应得{expected}≠PK页增量{pg.get('delta')}")
    else:
        if pg.get("ok") is False:
            notes.append("PK页增加钻石数失败")
        elif pg.get("delta") is not None and int(pg.get("delta") or 0) != 0:
            notes.append(f"败方PK页增量应为0，实际{pg.get('delta')}")
    return "；".join(notes)


def _aggregate_contributors(
    contributors: list[dict[str, Any]],
    *,
    winner_room: str,
    cross_room: set[str],
) -> list[dict[str, Any]]:
    """按用户聚合为一行；双房送礼用户仅保留胜房行并标记。"""
    merged: dict[str, dict[str, Any]] = {}
    for c in contributors:
        uid = str(c.get("sender") or "")
        room_id = str(c.get("roomId") or "")
        if uid in cross_room and room_id != winner_room:
            continue
        if uid not in merged:
            merged[uid] = dict(c)
            merged[uid]["crossRoomCorrected"] = uid in cross_room
            continue
        prev = merged[uid]
        prev["diamonds"] = int(prev.get("diamonds") or 0) + int(c.get("diamonds") or 0)
        prev["pkValue"] = int(prev.get("pkValue") or 0) + int(c.get("pkValue") or 0)
        prev["senderRoomPk"] = max(
            int(prev.get("senderRoomPk") or 0),
            int(c.get("senderRoomPk") or 0),
        )
    for entry in merged.values():
        sender_room_pk = int(entry.get("senderRoomPk") or 0)
        entry["pkValue"] = sender_room_pk
    return list(merged.values())


def _build_sheet_rows(report: dict[str, Any], *, phone_map: dict[str, str] | None = None) -> list[list[str]]:
    phone_map = phone_map or _load_phone_map()
    parties = report.get("parties") or {}
    pa = parties.get("a") or {}
    pb = parties.get("b") or {}
    room_host = {
        str(pa.get("room_id") or ""): (str(pa.get("user_id") or ""), str(pa.get("phone") or "")),
        str(pb.get("room_id") or ""): (str(pb.get("user_id") or ""), str(pb.get("phone") or "")),
    }
    winner = report.get("winner") or {}
    winner_room = str(winner.get("roomId") or report.get("expectedRewards", {}).get("winnerRoomId") or "")

    expected_users = (report.get("expectedRewards") or {}).get("users") or {}
    diamond_items = {
        str(i.get("userId")): i for i in (report.get("diamondVerification") or {}).get("items") or []
    }
    popup = report.get("popupVerify") or {}
    popup_users = popup.get("users") or {}
    popup_total = popup.get("roomTotalDiamond")
    page_verify = report.get("pageVerify") or {}
    page_users = page_verify.get("users") or {}
    page_total_delta = (page_verify.get("weekTotalCheck") or {}).get("delta")
    cross_room = set(report.get("crossRoomSenders") or [])
    cfg = report.get("serviceConfig") or {}
    personal_threshold = int(cfg.get("personalPkThreshold") or DEFAULT_PERSONAL_PK_THRESHOLD)
    multiplier = int(cfg.get("firstWinMultiplier") or 2)
    dispatch_total = _calc_dispatch_total_diamonds(report)

    overall = "通过" if report.get("ok") else "未通过"
    rows: list[list[str]] = [SHEET2_HEADER]

    sender_pk_map = report.get("senderPkByRoom") or {}
    contributors = _aggregate_contributors(
        list(report.get("contributors") or []),
        winner_room=winner_room,
        cross_room=cross_room,
    )
    room_a_pk = int(report.get("roomAPk") or 0)
    room_b_pk = int(report.get("roomBPk") or 0)
    room_pk = {
        str(pa.get("room_id") or ""): room_a_pk,
        str(pb.get("room_id") or ""): room_b_pk,
    }
    combined_pk = int(report.get("combinedPk") or (room_a_pk + room_b_pk))
    win_room_pk = int(room_pk.get(winner_room) or 0)
    contributors.sort(
        key=lambda c: (
            str(c.get("roomId") or ""),
            -int(c.get("senderRoomPk") or c.get("pkValue") or 0),
        )
    )

    for c in contributors:
        room_id = str(c.get("roomId") or "")
        uid = str(c.get("sender") or "")
        host_id, host_phone = room_host.get(room_id, ("", ""))
        exp_entry = expected_users.get(uid) or {}
        dv = diamond_items.get(uid) or {}
        pu = popup_users.get(uid) or {}
        pg = page_users.get(uid) or {}
        is_winner = room_id == winner_room
        pk_info = (sender_pk_map.get(uid) or {}).get(room_id) or {}
        personal_pk = int(pk_info.get("pkValue") or c.get("senderRoomPk") or 0)

        first_win = bool(pu.get("firstWin")) if is_winner else False
        first_extra = int(pu.get("firstWinExtraDiamond") or 0) if is_winner else 0
        row_dispatch_total = dispatch_total if is_winner else 0
        expected_diamonds = _calc_user_expected_diamond(
            pool_diamonds=row_dispatch_total,
            win_room_total_pk=win_room_pk if is_winner else int(room_pk.get(room_id) or 0),
            personal_pk=personal_pk,
            personal_threshold=personal_threshold,
            is_winner=is_winner,
            first_win=first_win,
            first_win_multiplier=multiplier,
            first_win_extra=first_extra,
        )

        actual_delta = dv.get("diamondDelta")
        user_page_delta = pg.get("delta")
        popup_user_diamond = pu.get("myRewardDiamond") if is_winner else None

        notes = _row_failure_notes(
            uid=uid,
            is_winner=is_winner,
            cross_room=cross_room,
            expected=expected_diamonds,
            actual=int(actual_delta) if actual_delta is not None else None,
            pu=pu,
            pg=pg,
            personal_pk=personal_pk,
            personal_threshold=personal_threshold,
        )

        eligible = _is_reward_eligible(
            personal_pk=personal_pk,
            personal_threshold=personal_threshold,
            is_winner=is_winner,
        )

        if uid in cross_room:
            row_ok = False
        elif is_winner and not eligible:
            row_ok = (
                expected_diamonds == 0
                and actual_delta in (None, 0)
                and popup_user_diamond in (None, 0)
                and (user_page_delta is None or int(user_page_delta) == 0)
                and not notes
            )
        elif is_winner:
            row_ok = (
                not notes
                and expected_diamonds == int(actual_delta or -1)
                and pu.get("ok") is not False
                and pg.get("ok") is not False
                and (user_page_delta is None or int(user_page_delta) == expected_diamonds)
            )
        else:
            row_ok = (
                expected_diamonds == 0
                and (actual_delta in (None, 0))
                and pg.get("ok") is not False
                and (user_page_delta is None or int(user_page_delta) == 0)
                and not notes
            )

        if not row_ok and not notes:
            notes = report.get("error") or "场次未通过"

        rows.append(
            [
                _cell(room_id),
                _cell(host_id),
                _cell(host_phone),
                _cell(uid),
                _cell(phone_map.get(uid, "")),
                _cell(personal_pk),
                _cell(room_pk.get(room_id, c.get("roomTotalPk"))),
                _cell(combined_pk),
                _cell("胜" if is_winner else "负"),
                _cell(first_win),
                _cell(row_dispatch_total if is_winner else ""),
                _cell(expected_diamonds if is_winner else 0),
                _cell(actual_delta),
                _cell(popup_total if is_winner else ""),
                _cell(popup_user_diamond if is_winner else ""),
                _cell(page_total_delta),
                _cell(user_page_delta),
                _cell("通过" if row_ok else "未通过"),
                _cell(notes),
            ]
        )

    if len(rows) == 1:
        rows.append([""] * len(SHEET2_HEADER))
        rows[-1][0] = report.get("pkId") or ""
        rows[-1][-2] = overall
        rows[-1][-1] = report.get("error") or ""
    return rows


async def _list_sheet_names(workbook_url: str) -> list[str]:
    from alidocs_excel_export import DOC_API, _excel_env, _get_token_and_operator  # noqa: E402
    from mse_workbook_utils import node_id  # noqa: E402

    env = _excel_env()
    token, operator = await _get_token_and_operator(env)
    wb_id = node_id(workbook_url)
    import httpx

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.get(
            f"{DOC_API}/workbooks/{wb_id}/sheets?operatorId={operator}",
            headers={"x-acs-dingtalk-access-token": token},
        )
        resp.raise_for_status()
        return [str(item.get("name") or "") for item in resp.json().get("value", [])]


def _next_sheet_name(existing: set[str], *, pk_id: str | None = None) -> str:
    if pk_id:
        short = str(pk_id)[-10:]
        candidate = f"{SHEET_PREFIX}-{short}"
        if candidate not in existing:
            return candidate
    n = 1
    while f"{SHEET_PREFIX}-{n}" in existing:
        n += 1
    return f"{SHEET_PREFIX}-{n}"


async def _resolve_sheet_name(
    workbook_url: str,
    *,
    sheet_name: str | None,
    new_sheet: bool,
    pk_id: str | None = None,
) -> str:
    if sheet_name:
        return sheet_name
    if new_sheet:
        names = set(await _list_sheet_names(workbook_url))
        return _next_sheet_name(names, pk_id=pk_id)
    return DEFAULT_SHEET


async def _write_sheet(workbook_url: str, sheet_name: str, rows: list[list[str]]) -> None:
    from alidocs_excel_export import _excel_env, _get_token_and_operator  # noqa: E402
    from family_pk_tab_to_workbook import _ensure_sheet, _write_sheet_replace  # noqa: E402
    from mse_workbook_utils import node_id  # noqa: E402

    env = _excel_env()
    token, operator = await _get_token_and_operator(env)
    wb_id = node_id(workbook_url)
    import httpx

    async with httpx.AsyncClient(timeout=120) as client:
        await _ensure_sheet(
            token=token,
            operator=operator,
            workbook_id=wb_id,
            sheet_name=sheet_name,
            client=client,
        )
    str_rows = [[str(c) if c is not None else "" for c in r] for r in rows]
    await _write_sheet_replace(
        token=token,
        operator=operator,
        workbook_id=wb_id,
        sheet_name=sheet_name,
        rows=str_rows,
    )


def run_flow(args: argparse.Namespace) -> dict[str, Any]:
    report: dict[str, Any] = {"steps": [], "ok": False}
    party_a = pk._resolve_party(args.phone_a)
    party_b = pk._resolve_party(args.phone_b)
    report["parties"] = {"a": party_a.__dict__, "b": party_b.__dict__}

    cfg, _ = pk._resolve_config(args, party_a)
    report["serviceConfig"] = cfg.to_dict()
    threshold_diamonds = _threshold_diamonds(cfg)
    report["thresholdDiamonds"] = threshold_diamonds

    existing = pk._pk_info(party_a)
    pk_id = existing.get("acrossRoomPkId")
    reuse = (
        pk_id
        and str((existing.get("acrossRoomInfo") or {}).get("roomId")) == party_b.room_id
        and int(existing.get("stage") or 0) >= 1
    )
    if reuse:
        report["steps"].append({"match": {"mode": "reuse_existing", "pkId": pk_id}})
    else:
        pk_id, match_step = pk._begin_random_match_cross_room_pk(
            party_a,
            party_b,
            timeout_sec=args.match_timeout,
            pk_minute=str(args.pk_minute),
            match_retries=getattr(args, "match_retries", 5),
        )
        report["steps"].append({"match": match_step})
    report["pkId"] = pk_id

    for _ in range(30):
        if int(pk._pk_info(party_a, pk_id=pk_id).get("stage") or 0) >= 2:
            break
        time.sleep(1)

    if args.pre_gift_wait > 0:
        time.sleep(args.pre_gift_wait)

    room_owners = pk._room_owners_map(party_a, party_b)
    room_ids = list(room_owners.keys())

    senders = [s.strip() for s in (args.senders or "").split(",") if s.strip()] or pk.DEFAULT_SENDERS
    senders = [s for s in senders if s not in (party_a.user_id, party_b.user_id)]
    random.shuffle(senders)
    pool = senders[: max(args.gift_count, len(senders))]

    sender_room = pk._assign_sender_rooms(pool, room_ids)
    gifts = pk._send_random_gifts(
        senders=pool,
        room_owners=room_owners,
        room_ids=room_ids,
        gift_min=args.gift_min_diamonds,
        gift_max=args.gift_max_diamonds,
        count=args.gift_count,
        sender_room=sender_room,
    )
    if args.target_combined_pk and args.target_combined_pk > 0:
        gifts.extend(
            pk._top_up_gifts_until_target(
                party_a=party_a,
                party_b=party_b,
                pk_id=pk_id,
                senders=pool,
                gift_min=args.gift_min_diamonds,
                gift_max=args.gift_max_diamonds,
                gift_count=args.gift_count,
                target_pk=args.target_combined_pk,
                sender_room=sender_room,
            )
        )
    report["gifts"] = gifts
    report["senderRoomAssignment"] = sender_room
    cross_room = _cross_room_senders(gifts)
    report["crossRoomSenders"] = sorted(cross_room)

    if args.post_gift_wait > 0:
        time.sleep(args.post_gift_wait)

    pk_pre_close = pk._pk_info(party_a, pk_id=pk_id)
    sender_pk = pk._sender_pk_map(gifts, pk_pre_close, party_a, party_b)
    report["roomRankList"] = pk_pre_close.get("roomRankList")
    report["acrossRoomRankList"] = pk_pre_close.get("acrossRoomRankList")
    verify_users = sorted(sender_pk.keys())
    report["pageBefore"] = _snapshot_users_page_sticky(verify_users)
    diamond_before = pk._snapshot_diamonds(verify_users)
    report["roomAPk"] = int(pk_pre_close.get("roomRankValue") or 0)
    report["roomBPk"] = int(pk_pre_close.get("acrossRoomRankValue") or 0)
    report["combinedPk"] = pk._combined_pk(pk_pre_close)

    withdraw_rank_before = pk._snapshot_withdraw_rank_context(party_a, verify_users)

    closer = random.choice([party_a, party_b])
    other = party_b if closer is party_a else party_a
    report["closerPhone"] = closer.phone
    report["closer"] = closer.__dict__

    expected = pk._calc_expected_rewards(
        cfg=cfg,
        pk_data=pk_pre_close,
        party_a=party_a,
        party_b=party_b,
        sender_pk=sender_pk,
        assume_first_win=args.assume_first_win,
        closer=closer,
    )
    report["expectedRewards"] = expected

    close_res = _close_from(closer, other, pk_id)

    if args.post_close_wait > 0:
        time.sleep(args.post_close_wait)

    diamond_after = pk._snapshot_diamonds(verify_users)
    withdraw_rank_verify = pk._verify_withdraw_rank_after_close(
        party_a,
        verify_users,
        diamond_before,
        diamond_after,
        expected,
        withdraw_rank_before,
        require_rank_api=False,
    )
    report["withdrawRankVerify"] = withdraw_rank_verify

    pk_end = pk._pk_info(party_a, pk_id=pk_id)
    final = pk._build_report(
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
        pk_status_verify={"ok": True, "skipped": True},
        withdraw_rank_verify=withdraw_rank_verify,
        closer=closer,
    )
    report.update(final)

    winner_party = other
    report["winner"] = {
        "phone": winner_party.phone,
        "userId": winner_party.user_id,
        "roomId": winner_party.room_id,
    }
    report["loser"] = {
        "phone": closer.phone,
        "userId": closer.user_id,
        "roomId": closer.room_id,
    }
    report["outcomeRule"] = "主动结束PK记败"

    winner_room = winner_party.room_id
    winner_uids = [
        uid
        for uid, rooms in sender_pk.items()
        if winner_room in rooms and int((rooms.get(winner_room) or {}).get("pkValue") or 0) > 0
    ]
    diamond_items = {
        str(i.get("userId")): i for i in (final.get("diamondVerification") or {}).get("items") or []
    }
    report["popupVerify"] = _verify_winner_popups(
        winner_room_id=winner_room,
        pk_id=pk_id,
        winner_uids=sorted(winner_uids),
        sender_pk=sender_pk,
        diamond_items=diamond_items,
        personal_threshold=int(cfg.personal_pk_threshold or DEFAULT_PERSONAL_PK_THRESHOLD),
    )
    _finalize_expected_after_popup(report)
    diamond_items = {
        str(i.get("userId")): i
        for i in (report.get("diamondVerification") or {}).get("items") or []
    }
    page_after = _snapshot_users_page_sticky(verify_users)
    report["pageAfter"] = page_after
    report["pageVerify"] = _verify_users_page_sticky(
        user_ids=verify_users,
        page_before=report["pageBefore"],
        page_after=page_after,
        diamond_items=diamond_items,
        winner_room=winner_room,
        winner_uids=set(winner_uids),
        sender_pk=sender_pk,
        personal_threshold=int(cfg.personal_pk_threshold or DEFAULT_PERSONAL_PK_THRESHOLD),
    )

    close_ok = bool((close_res.get("business") or {}).get("ec") in (200, "200"))
    verify_ok = report.get("diamondVerification", {}).get("allMatch") is True
    rank_ok = withdraw_rank_verify.get("ok") is True
    popup_ok = (report.get("popupVerify") or {}).get("ok") is True
    page_ok = (report.get("pageVerify") or {}).get("ok") is True
    cross_ok = len(cross_room) == 0
    target_ok = True
    if args.target_combined_pk and args.target_combined_pk > 0:
        target_ok = report["combinedPk"] >= args.target_combined_pk
        report["targetCombinedPk"] = args.target_combined_pk
        report["targetCombinedPkOk"] = target_ok
    report["ok"] = (
        close_ok and verify_ok and rank_ok and popup_ok and page_ok and target_ok and cross_ok
    )
    if cross_room:
        report["error"] = f"双房送礼账号: {','.join(sorted(cross_room))}"
    elif not target_ok:
        report["error"] = f"双方总 PK {report['combinedPk']:,} 未达目标 {args.target_combined_pk:,}"
    elif not report["ok"]:
        errs = []
        if not close_ok:
            errs.append("结束PK失败")
        if not verify_ok:
            errs.append("钻石到账不一致")
        if not rank_ok:
            errs.append("提款排名增量失败")
        if not popup_ok:
            errs.append("返钻弹窗失败")
        if not page_ok:
            errs.append("活动页吸底失败")
        report["error"] = "；".join(errs)
    return report


def main() -> int:
    if _EXCEL_VENV.is_file() and Path(sys.executable).resolve() != _EXCEL_VENV.resolve():
        os.execv(str(_EXCEL_VENV), [str(_EXCEL_VENV), str(Path(__file__).resolve()), *sys.argv[1:]])

    parser = argparse.ArgumentParser(description="PK提款机全流程 + 钉钉Sheet2")
    parser.add_argument("--phone-a", default="13311111111")
    parser.add_argument("--phone-b", default="13311111115")
    parser.add_argument("--pk-minute", type=int, default=10, choices=(5, 10, 30))
    parser.add_argument("--gift-count", type=int, default=50)
    parser.add_argument("--gift-min-diamonds", type=int, default=400)
    parser.add_argument("--gift-max-diamonds", type=int, default=600)
    parser.add_argument("--target-combined-pk", type=int, default=100000, help="双方总 PK 验收目标（默认10万）")
    parser.add_argument("--min-combined-pk", type=int, default=20000, help="MSE minTotalPkValue")
    parser.add_argument("--personal-pk-threshold", type=int, default=DEFAULT_PERSONAL_PK_THRESHOLD, help="MSE minMemberRewardPk（默认 10000，以服务端为准）")
    parser.add_argument("--pre-gift-wait", type=int, default=20)
    parser.add_argument("--post-gift-wait", type=int, default=20)
    parser.add_argument("--post-close-wait", type=int, default=20)
    parser.add_argument("--match-timeout", type=int, default=120)
    parser.add_argument("--senders", default="")
    parser.add_argument("--workbook-url", default=DEFAULT_WORKBOOK)
    parser.add_argument(
        "--sheet-name",
        default="",
        help="指定工作表名；省略则新一轮自动新建",
    )
    parser.add_argument(
        "--new-sheet",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="新一轮测试写入新 Sheet（默认开启）",
    )
    parser.add_argument("--assume-first-win", action="store_true")
    parser.add_argument("--skip-config-fetch", action="store_true")
    parser.add_argument("--from-report", help="仅从已有 JSON 报告重写 Sheet2")
    parser.add_argument("--rewrite-only", action="store_true", help="同 --from-report，只写表不跑流程")
    args = parser.parse_args()

    if args.from_report or args.rewrite_only:
        if not args.from_report:
            latest = sorted((REPO / ".tmp").glob("pk_atm_sheet2_*.json"))
            if not latest:
                raise SystemExit("未找到 .tmp/pk_atm_sheet2_*.json")
            args.from_report = str(latest[-1])
        report = json.loads(Path(args.from_report).read_text(encoding="utf-8"))
        _reconcile_report_by_closer(report)

        async def _rewrite() -> tuple[str, int]:
            rows = _build_sheet_rows(report)
            sheet_name = await _resolve_sheet_name(
                args.workbook_url,
                sheet_name=args.sheet_name or report.get("sheetName"),
                new_sheet=False,
                pk_id=str(report.get("pkId") or ""),
            )
            await _write_sheet(args.workbook_url, sheet_name, rows)
            return sheet_name, len(rows) - 1

        sheet_name, row_count = asyncio.run(_rewrite())
        print(
            json.dumps(
                {
                    "ok": True,
                    "mode": "rewrite",
                    "rows": row_count,
                    "workbookUrl": args.workbook_url,
                    "sheetName": sheet_name,
                },
                ensure_ascii=False,
            )
        )
        return 0

    ns = argparse.Namespace(
        phone_a=args.phone_a,
        phone_b=args.phone_b,
        gift_count=args.gift_count,
        gift_min_diamonds=args.gift_min_diamonds,
        gift_max_diamonds=args.gift_max_diamonds,
        pre_gift_wait=args.pre_gift_wait,
        post_gift_wait=args.post_gift_wait,
        post_close_wait=args.post_close_wait,
        match_timeout=args.match_timeout,
        pk_minute=args.pk_minute,
        senders=args.senders,
        out_dir=".tmp",
        config_file="",
        min_combined_pk=args.min_combined_pk,
        personal_pk_threshold=args.personal_pk_threshold,
        target_combined_pk=args.target_combined_pk,
        assume_first_win=args.assume_first_win,
        skip_config_fetch=args.skip_config_fetch,
        skip_diamond_verify=False,
        skip_pk_status_verify=True,
        require_pk_situation_list=False,
        skip_withdraw_rank_verify=False,
        require_withdraw_rank_api=False,
    )

    report = run_flow(ns)
    out_path = REPO / ".tmp" / f"pk_atm_sheet2_{report.get('pkId', 'run')}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    async def _publish() -> str:
        rows = _build_sheet_rows(report)
        sheet_name = await _resolve_sheet_name(
            args.workbook_url,
            sheet_name=args.sheet_name or None,
            new_sheet=args.new_sheet,
            pk_id=str(report.get("pkId") or ""),
        )
        await _write_sheet(args.workbook_url, sheet_name, rows)
        return sheet_name

    sheet_name = asyncio.run(_publish())
    report["workbookUrl"] = args.workbook_url
    report["sheetName"] = sheet_name
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "ok": report.get("ok"),
                "pkId": report.get("pkId"),
                "error": report.get("error"),
                "workbookUrl": args.workbook_url,
                "sheetName": sheet_name,
            },
            ensure_ascii=False,
        )
    )
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
