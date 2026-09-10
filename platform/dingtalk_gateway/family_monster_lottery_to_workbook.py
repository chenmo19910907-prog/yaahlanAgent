#!/usr/bin/env python3
"""家族怪兽挑战 CMS 奖池 getLotteryList → 钉钉 Sheet「怪兽挑战奖池配置」。"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

GATEWAY_DIR = Path(__file__).resolve().parent
REPO_ROOT = GATEWAY_DIR.parents[1]
_EXCEL_VENV = (
    REPO_ROOT / ".cursor/skills/testcase-to-excel/mcp_dingtalk_excel/venv/bin/python3.13"
)

if (
    __name__ == "__main__"
    and _EXCEL_VENV.is_file()
    and Path(sys.executable).resolve() != _EXCEL_VENV.resolve()
):
    os.execv(str(_EXCEL_VENV), [str(_EXCEL_VENV), str(Path(__file__).resolve()), *sys.argv[1:]])

if str(GATEWAY_DIR) not in sys.path:
    sys.path.insert(0, str(GATEWAY_DIR))

from anniversary_egg_lottery_to_workbook import (  # noqa: E402
    _format_num_range,
    _lookup_prop_names,
    _pct,
    _prize_name,
    _prop_type_suffix,
    fetch_lottery_pools,
    write_lottery_sheet_async,
)
from family_monster_mse_to_workbook import (  # noqa: E402
    DEFAULT_CONFIG_KEY,
    DEFAULT_NAMESPACE,
    _fetch_config,
)
from mse_sync_to_workbook import _sheet_cell  # noqa: E402
from repo_paths import admin_module_dir  # noqa: E402

DEFAULT_WORKBOOK = "https://alidocs.dingtalk.com/i/nodes/QG53mjyd80RNdKjKCeLv20KKV6zbX04v"
DEFAULT_SHEET = "怪兽挑战奖池配置"
DEFAULT_PRIZE_SHEET = "道具明细"

# 用户指定排版：仅 10 列，无元数据/MSE 映射等额外内容（见 config/family_monster_workbook_layout.json）
MONSTER_LOTTERY_HEADER = [
    "奖池ID",
    "奖池名称",
    "序号",
    "奖品类型",
    "数量/区间",
    "奖品ID",
    "奖品名称",
    "限量(limit)",
    "权重占比",
    "名称/备注",
]

PRIZE_DETAIL_HEADER = [
    "奖品ID",
    "CMS类型",
    "中台名称",
    "道具/礼物类型",
    "使用类型",
    "获取途径",
    "价格(钻)",
    "有效期起",
    "有效期止",
    "出现奖池",
    "中台查询",
]


def _collect_monster_pool_ids(cfg: dict[str, Any]) -> list[tuple[int, str, str]]:
    """(pool_id, mse_field, role) 去重保序。"""
    ordered: list[tuple[int, str, str]] = []
    seen: set[int] = set()

    def add(raw: Any, field: str, role: str) -> None:
        if raw in (None, ""):
            return
        try:
            pool_id = int(str(raw).strip())
        except (TypeError, ValueError):
            return
        if pool_id in seen:
            return
        seen.add(pool_id)
        ordered.append((pool_id, field, role))

    add(cfg.get("participateBagId"), "participateBagId", "参与奖池")
    add(cfg.get("eliteBagId") or _first_monster_field(cfg, "eliteBagId"), "eliteBagId", "精英奖池")
    for monster in cfg.get("monsters") or []:
        if not isinstance(monster, dict):
            continue
        lv = monster.get("level")
        add(monster.get("normalBagId"), f"monsters[Lv{lv}].normalBagId", f"Lv.{lv} 普通奖池")
        milestone = monster.get("familyMilestoneBagId")
        if milestone and str(milestone) != str(monster.get("normalBagId") or ""):
            add(milestone, f"monsters[Lv{lv}].familyMilestoneBagId", f"Lv.{lv} 家族里程碑奖池")
    return ordered


def _first_monster_field(cfg: dict[str, Any], field: str) -> Any:
    for monster in cfg.get("monsters") or []:
        if isinstance(monster, dict) and monster.get(field) not in (None, ""):
            return monster.get(field)
    return None


def _lookup_gift_stage(gift_ids: list[str]) -> dict[str, dict[str, Any]]:
    ids = sorted({str(x).strip() for x in gift_ids if str(x).strip()})
    if not ids:
        return {}
    if str(REPO_ROOT / "Gift") not in sys.path:
        sys.path.insert(0, str(REPO_ROOT / "Gift"))
    try:
        from gift.send_stage import query_gift
    except Exception:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for gid in ids:
        try:
            meta = query_gift(gid, lang="en")
        except Exception:
            continue
        out[gid] = {
            "name": meta.get("productName") or "",
            "price": meta.get("price"),
        }
    return out


def _lookup_gift_mdp(gift_ids: list[str]) -> dict[str, dict[str, Any]]:
    """MDP giftAdmin/queryGiftList 按 baseId 查礼物配置。"""
    ids = sorted({str(x).strip() for x in gift_ids if str(x).strip()})
    if not ids:
        return {}
    if str(admin_module_dir()) not in sys.path:
        sys.path.insert(0, str(admin_module_dir()))
    try:
        from admin.client import http_post_json
        from admin.config import defaults
        from admin.env import load_local_env
        from admin.gift import mdp_gift_success, parse_query_gift_list_summary
    except Exception:
        return {}

    load_local_env(str(admin_module_dir()))
    cfg = defaults("query_gift_list")
    base_url = str(
        cfg.get("baseUrl") or "https://alpha-mdp-user-admin-api-stage.wemomo.com"
    ).rstrip("/")
    path = str(cfg.get("path") or "/giftAdmin/queryGiftList")
    try:
        app_id = int(cfg.get("defaultAppId") or 2005)
    except (TypeError, ValueError):
        app_id = 2005

    out: dict[str, dict[str, Any]] = {}
    for gid in ids:
        body = {
            "appId": app_id,
            "baseId": gid,
            "createTimeBegin": "",
            "createTimeEnd": "",
            "giftType": "",
            "productName": "",
            "giftStatus": "",
            "giftEffectCate": "",
            "giftSubType": "",
            "createSource": "",
            "pageSize": 20,
            "pageNo": 1,
        }
        try:
            resp = http_post_json(f"{base_url}{path}", body, auth="mdp_nova")
        except Exception:
            continue
        if not mdp_gift_success(resp.get("ec")):
            continue
        summary = parse_query_gift_list_summary(resp.get("data"))
        records = summary.get("records") or []
        if records and isinstance(records[0], dict):
            out[gid] = records[0]
    return out


def _monster_prize_note(
    prize: dict[str, Any],
    *,
    gift_names: dict[str, dict[str, Any]],
    prop_names: dict[str, dict[str, Any]],
) -> str:
    """怪兽挑战奖池「名称/备注」列：钻石区间 / 道具类型 / 背包礼物价格。"""
    prize_type = prize.get("type")
    prize_id = str(prize.get("id") or "").strip()
    if prize_type == 1:
        return "钻石区间"
    if prize_type == 7:
        return "兑换券"
    if prize_type == 3:
        return _prop_type_suffix(prize_id, prop_names) or "VIP经验/成长值"
    if prize_type == 2:
        return _prop_type_suffix(prize_id, prop_names) or "装扮/道具"
    if prize_type == 5 and prize_id:
        info = gift_names.get(prize_id) or {}
        price = info.get("price")
        if price is not None:
            return f"{float(price):.1f}钻"
        return ""
    return ""


def _collect_prize_refs(
    pools_by_id: dict[int, dict[str, Any]],
    pool_ids: list[tuple[int, str, str]],
) -> dict[str, dict[str, Any]]:
    """按奖品 ID 汇总出现奖池与 CMS 类型。"""
    refs: dict[str, dict[str, Any]] = {}
    for pool_id, _, role in pool_ids:
        pool = pools_by_id.get(pool_id) or {}
        pool_name = str(pool.get("name") or "").strip()
        pool_label = f"{pool_id}·{pool_name}" if pool_name else str(pool_id)
        for prize in pool.get("lotteryList") or []:
            if not isinstance(prize, dict):
                continue
            prize_id = str(prize.get("id") or "").strip()
            if not prize_id:
                continue
            prize_type = int(prize.get("type") or 0)
            entry = refs.setdefault(
                prize_id,
                {
                    "prizeId": prize_id,
                    "cmsType": prize.get("typeLabel") or prize_type,
                    "cmsTypeCode": prize_type,
                    "pools": [],
                },
            )
            if pool_label not in entry["pools"]:
                entry["pools"].append(pool_label)
            if role and role not in entry.get("roles", []):
                entry.setdefault("roles", []).append(role)
    return refs


def build_prize_detail_rows(
    prize_refs: dict[str, dict[str, Any]],
    *,
    prop_names: dict[str, dict[str, Any]],
    gift_mdp: dict[str, dict[str, Any]],
    gift_stage: dict[str, dict[str, Any]],
) -> list[list[Any]]:
    synced = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    rows: list[list[Any]] = [
        ["家族怪兽挑战 · 奖品 ID 中台明细", "", "", "", f"同步时间 {synced}"],
        ["数据源", "propAdmin/queryPropInfo + giftAdmin/queryGiftList", "", "", ""],
        ["", "", "", "", "", "", "", "", "", "", ""],
        list(PRIZE_DETAIL_HEADER),
    ]

    def sort_key(item: tuple[str, dict[str, Any]]) -> tuple[int, str]:
        ref = item[1]
        try:
            code = int(ref.get("cmsTypeCode") or 99)
        except (TypeError, ValueError):
            code = 99
        return code, item[0]

    for prize_id, ref in sorted(prize_refs.items(), key=sort_key):
        cms_type_code = int(ref.get("cmsTypeCode") or 0)
        pools = "；".join(ref.get("pools") or [])
        if cms_type_code == 1:
            rows.append([prize_id, ref.get("cmsType"), "钻石", "", "", "", "", "", "", pools, "无需查中台"])
            continue
        if cms_type_code == 7:
            rows.append([prize_id, ref.get("cmsType"), "兑换券/代币", "", "", "", "", "", "", pools, "无需查中台"])
            continue
        if cms_type_code == 5:
            info = gift_mdp.get(prize_id) or {}
            stage = gift_stage.get(prize_id) or {}
            name = info.get("productName") or stage.get("name") or ""
            query_status = "giftAdmin" if info else ("stage" if stage else "未命中")
            rows.append(
                [
                    prize_id,
                    ref.get("cmsType"),
                    name,
                    "背包礼物",
                    "",
                    "",
                    info.get("price") or stage.get("price") or "",
                    "",
                    "",
                    pools,
                    query_status,
                ]
            )
            continue

        info = prop_names.get(prize_id) or {}
        rows.append(
            [
                prize_id,
                ref.get("cmsType"),
                info.get("propName") or "",
                info.get("propTypeName") or "",
                info.get("useTypeName") or "",
                info.get("obtainWayEntryName") or "",
                "",
                info.get("validStartTime") or "",
                info.get("validEndTime") or "",
                pools,
                "propAdmin" if info else "未命中",
            ]
        )
    return rows


def build_lottery_rows(
    *,
    cfg: dict[str, Any],
    meta: dict[str, Any],
    pools_by_id: dict[int, dict[str, Any]],
) -> tuple[list[list[Any]], dict[str, Any]]:
    pool_ids = _collect_monster_pool_ids(cfg)
    rows: list[list[Any]] = [list(MONSTER_LOTTERY_HEADER)]

    gift_ids: list[str] = []
    prop_ids: list[str] = []
    for pool_id, _, _ in pool_ids:
        pool = pools_by_id.get(pool_id) or {}
        for prize in pool.get("lotteryList") or []:
            if not isinstance(prize, dict):
                continue
            prize_type = int(prize.get("type") or 0)
            pid = str(prize.get("id") or "").strip()
            if prize_type == 5 and pid:
                gift_ids.append(pid)
            elif prize_type in (2, 3) and pid.isdigit():
                prop_ids.append(pid)
    gift_names = _lookup_gift_stage(sorted(set(gift_ids)))
    gift_mdp = _lookup_gift_mdp(sorted(set(gift_ids)))
    for gid, info in gift_mdp.items():
        if gid not in gift_names and isinstance(info, dict):
            gift_names[gid] = {
                "name": info.get("productName") or "",
                "price": info.get("price"),
            }
        elif gid in gift_names and isinstance(info, dict):
            entry = gift_names[gid]
            if not entry.get("name"):
                entry["name"] = info.get("productName") or ""
            if entry.get("price") is None:
                entry["price"] = info.get("price")
    prop_names = _lookup_prop_names(prop_ids)

    for pool_id, field, _role in pool_ids:
        pool = pools_by_id.get(pool_id)
        if not isinstance(pool, dict):
            rows.append(
                [
                    pool_id,
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    f"未在 CMS 找到 lotteryId={pool_id} ({field})",
                ]
            )
            continue
        pool_name = str(pool.get("name") or "").strip()
        prizes = [p for p in (pool.get("lotteryList") or []) if isinstance(p, dict)]
        total_rate = sum(int(p.get("rate") or 0) for p in prizes)
        for idx, prize in enumerate(prizes, start=1):
            rate = int(prize.get("rate") or 0)
            rows.append(
                [
                    pool_id if idx == 1 else "",
                    pool_name if idx == 1 else "",
                    idx,
                    prize.get("typeLabel") or prize.get("type"),
                    _format_num_range(prize.get("numStart"), prize.get("numEnd")),
                    prize.get("id") or "",
                    _prize_name(prize, gift_names=gift_names, prop_names=prop_names),
                    prize.get("limit") or "",
                    _pct(rate, total_rate),
                    _monster_prize_note(
                        prize, gift_names=gift_names, prop_names=prop_names
                    ),
                ]
            )

    prize_refs = _collect_prize_refs(pools_by_id, pool_ids)
    prize_detail_rows = build_prize_detail_rows(
        prize_refs,
        prop_names=prop_names,
        gift_mdp=gift_mdp,
        gift_stage=gift_names,
    )
    meta_out = {
        "giftNamesResolved": len(gift_names),
        "giftMdpResolved": len(gift_mdp),
        "propNamesResolved": len(prop_names),
        "prizeIdCount": len(prize_refs),
        "prizeDetailRowCount": len(prize_detail_rows),
        "prizeDetailRows": prize_detail_rows,
    }
    return rows, meta_out


def sync_family_monster_lottery_to_workbook(
    *,
    workbook: str = DEFAULT_WORKBOOK,
    sheet_name: str = DEFAULT_SHEET,
    prize_sheet_name: str = DEFAULT_PRIZE_SHEET,
    namespace: str = DEFAULT_NAMESPACE,
    config_key: str = DEFAULT_CONFIG_KEY,
    cluster: str = "alpha",
    env: str = "alpha",
    region: str = "alpha",
    dry_run: bool = False,
) -> dict[str, Any]:
    cfg, meta = _fetch_config(
        namespace=namespace,
        config_key=config_key,
        cluster=cluster,
        env=env,
        region=region,
    )
    pools_by_id = fetch_lottery_pools(force_refresh=True)
    pool_ids = _collect_monster_pool_ids(cfg)
    rows, name_meta = build_lottery_rows(cfg=cfg, meta=meta, pools_by_id=pools_by_id)
    missing = [pid for pid, _, _ in pool_ids if pid not in pools_by_id]
    prize_detail_rows = name_meta.pop("prizeDetailRows", [])
    out: dict[str, Any] = {
        "sheetName": sheet_name,
        "prizeSheetName": prize_sheet_name,
        "rowCount": len(rows),
        "poolCount": len(pool_ids),
        "poolIds": [pid for pid, _, _ in pool_ids],
        "missingPoolIds": missing,
        "meta": meta,
        **name_meta,
    }
    if dry_run:
        out["rowsPreview"] = [[_sheet_cell(c) for c in r] for r in rows[:40]]
        out["prizeDetailPreview"] = [
            [_sheet_cell(c) for c in r] for r in prize_detail_rows[:30]
        ]
        return out

    async def _write_both() -> str:
        url = await write_lottery_sheet_async(workbook, rows, sheet_name=sheet_name)
        return url

    url = asyncio.run(_write_both())
    out["workbookUrl"] = url
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="家族怪兽挑战 CMS 奖池写入钉钉表")
    parser.add_argument("--workbook", default=DEFAULT_WORKBOOK)
    parser.add_argument("--sheet-name", default=DEFAULT_SHEET)
    parser.add_argument("--prize-sheet-name", default=DEFAULT_PRIZE_SHEET)
    parser.add_argument("--namespace", default=DEFAULT_NAMESPACE)
    parser.add_argument("--config-key", default=DEFAULT_CONFIG_KEY)
    parser.add_argument("--cluster", default="alpha")
    parser.add_argument("--env", default="alpha")
    parser.add_argument("--region", default="alpha")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    out = sync_family_monster_lottery_to_workbook(
        workbook=args.workbook,
        sheet_name=args.sheet_name,
        prize_sheet_name=args.prize_sheet_name,
        namespace=args.namespace,
        config_key=args.config_key,
        cluster=args.cluster,
        env=args.env,
        region=args.region,
        dry_run=args.dry_run,
    )
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001 — CLI 边界打印
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
