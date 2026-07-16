#!/usr/bin/env python3
"""MOA 贡献榜 vs 测算 PK/钻石 验收逻辑（供用户发钻测试 Sheet 合并写入）。"""

from __future__ import annotations

import sys
from typing import Any

from family_pk_member_list_moa import fetch_family_pk_member_list


def list_threshold(config: dict[str, Any]) -> int:
    if config.get("minListPk") is not None:
        return int(config["minListPk"])
    return int(config["minRewardPk"])


def verify_member_contrib_row(
    *,
    calc: dict[str, Any],
    api: dict[str, Any] | None,
    min_list_pk: int,
) -> dict[str, Any]:
    calc_pk = int(calc.get("memberPk") or 0)
    calc_diamond = int(calc.get("expectedDiamond") or 0)
    # 仅应得钻>0 的成员须出现在贡献榜；PK 未达门槛或无应得钻不在榜算通过
    should_list = calc_diamond > 0

    if api is None:
        if should_list:
            return {
                "apiPk": "",
                "pkStatus": "未上榜",
                "apiDiamond": "",
                "diamondStatus": "—",
                "contribStatus": "失败",
                "contribNote": "测算应上榜但未出现在贡献榜",
            }
        if calc_pk < min_list_pk:
            note = f"用户PK<{min_list_pk}，榜单无此人"
        else:
            note = "无应得钻，榜单无此人"
        return {
            "apiPk": "",
            "pkStatus": "—",
            "apiDiamond": "",
            "diamondStatus": "—",
            "contribStatus": "通过",
            "contribNote": note,
        }

    api_pk = int(api.get("pkValue") or 0)
    api_diamond = int(api.get("rewardDiamond") or 0)
    pk_status = "通过" if api_pk == calc_pk else "不一致"
    diamond_status = "通过" if api_diamond == calc_diamond else "不一致"
    contrib_status = "通过" if pk_status == "通过" and diamond_status == "通过" else "失败"
    note = ""
    if pk_status != "通过":
        note = f"PK 测算{calc_pk} vs 榜单{api_pk}"
    elif diamond_status != "通过":
        note = f"钻石 测算{calc_diamond} vs 榜单{api_diamond}"
    return {
        "calcPk": calc_pk,
        "calcDiamond": calc_diamond,
        "apiPk": api_pk,
        "pkStatus": pk_status,
        "apiDiamond": api_diamond,
        "diamondStatus": diamond_status,
        "contribStatus": contrib_status,
        "contribNote": note,
    }


def format_contrib_verify_cell(
    ver: dict[str, Any],
    *,
    calc_pk: Any = "",
    calc_diamond: Any = "",
) -> str:
    """榜单验收结论（数值见榜单PK/榜单钻列）。"""
    if not ver:
        return ""

    overall = str(ver.get("contribStatus") or "").strip()
    pk_status = str(ver.get("pkStatus") or "").strip()
    diamond_status = str(ver.get("diamondStatus") or "").strip()
    note = str(ver.get("contribNote") or "").strip()

    if overall == "通过":
        return "通过"

    if pk_status == "拉榜失败":
        return "拉榜失败"
    if pk_status == "未上榜":
        return "未上榜"
    if pk_status == "多余" or diamond_status == "多余":
        return "榜单多余"

    issues: list[str] = []
    if pk_status == "不一致":
        issues.append("PK不一致")
    if diamond_status == "不一致":
        issues.append("钻不一致")
    if issues:
        return " ".join(issues)
    return note or "失败"


def verify_contrib_for_families(
    *,
    pk_date: str,
    member_rows: list[dict[str, Any]],
    user_id: str,
    config: dict[str, Any],
    area: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """逐家族 MOA getFamilyPkUserList，返回按成员的验收明细。"""
    min_list_pk = list_threshold(config)
    calc_by_family: dict[str, dict[str, dict[str, Any]]] = {}
    for row in member_rows:
        fid = str(row.get("familyId") or "")
        uid = str(row.get("userId") or "")
        if not fid.isdigit() or not uid.isdigit():
            continue
        calc_by_family.setdefault(fid, {})[uid] = row

    detail_rows: list[dict[str, Any]] = []
    family_stats: list[dict[str, Any]] = []
    pass_count = 0
    fail_count = 0

    for fid in sorted(calc_by_family, key=lambda x: int(x)):
        calc_map = calc_by_family[fid]
        print(f"贡献榜验收 familyId={fid} …", file=sys.stderr)
        try:
            api_members = fetch_family_pk_member_list(
                user_id=user_id,
                family_id=fid,
                pk_date=pk_date,
                area=area,
            )
        except (RuntimeError, ValueError, OSError) as exc:
            for uid, calc in calc_map.items():
                fail_count += 1
                detail_rows.append(
                    {
                        "familyId": fid,
                        "userId": uid,
                        **verify_member_contrib_row(
                            calc=calc,
                            api=None,
                            min_list_pk=min_list_pk,
                        ),
                        "pkStatus": "拉榜失败",
                        "diamondStatus": "拉榜失败",
                        "contribStatus": "失败",
                        "contribNote": str(exc)[-200:],
                    }
                )
            family_stats.append({"familyId": fid, "apiCount": 0, "error": str(exc)[-200:]})
            continue

        api_map = {
            str(m.get("userId") or ""): m
            for m in api_members
            if str(m.get("userId") or "").isdigit()
        }
        family_pass = 0
        family_fail = 0
        checked_uids = set(calc_map.keys())

        for uid in sorted(checked_uids, key=lambda x: int(x) if x.isdigit() else 0):
            calc = calc_map[uid]
            verified = verify_member_contrib_row(
                calc=calc,
                api=api_map.get(uid),
                min_list_pk=min_list_pk,
            )
            verified["calcPk"] = int(calc.get("memberPk") or 0)
            verified["calcDiamond"] = int(calc.get("expectedDiamond") or 0)
            if verified["contribStatus"] == "通过":
                pass_count += 1
                family_pass += 1
            else:
                fail_count += 1
                family_fail += 1
            detail_rows.append({"familyId": fid, "userId": uid, **verified})

        for uid, api in api_map.items():
            if uid in checked_uids:
                continue
            fail_count += 1
            family_fail += 1
            detail_rows.append(
                {
                    "familyId": fid,
                    "userId": uid,
                    "apiPk": api.get("pkValue", 0),
                    "pkStatus": "多余",
                    "apiDiamond": api.get("rewardDiamond", 0),
                    "diamondStatus": "多余",
                    "contribStatus": "失败",
                    "contribNote": "榜单有而测算无此用户",
                }
            )

        family_stats.append(
            {
                "familyId": fid,
                "apiCount": len(api_members),
                "checked": len(checked_uids),
                "pass": family_pass,
                "fail": family_fail,
            }
        )

    summary = {
        "pkDate": pk_date,
        "userId": user_id,
        "familyCount": len(calc_by_family),
        "rowCount": len(detail_rows),
        "passCount": pass_count,
        "failCount": fail_count,
        "minListPk": min_list_pk,
        "allPass": fail_count == 0,
        "familyStats": family_stats,
    }
    return detail_rows, summary
