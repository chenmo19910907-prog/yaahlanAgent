#!/usr/bin/env python3
"""3周年砸金蛋 CMS 奖池 getLotteryList → 钉钉 Sheet「金蛋奖池配置」。"""

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

from repo_paths import (
    admin_execute_path,
    admin_module_dir,
    batch_progress_script,
    get_repo_root,
    gift_execute_path,
    gift_module_dir,
    moa_execute_path,
    moa_module_dir,
    moa_template,
    mse_execute_path,
    mse_module_dir,
    stage_gateway_url,
    tmp_dir,
)
if str(REPO_ROOT / "Admin") not in sys.path:
    sys.path.insert(0, str(admin_module_dir()))

from alidocs_excel_export import _excel_env, _get_token_and_operator  # noqa: E402
from anniversary_egg_mse_to_workbook import (  # noqa: E402
    DEFAULT_CONFIG_KEY,
    DEFAULT_NAMESPACE,
    DEFAULT_WORKBOOK,
    _lookup_gift_names,
    fetch_year3_mse_config,
)
from family_pk_tab_to_workbook import _ensure_sheet, _string_rows, _write_sheet_replace  # noqa: E402
from mse_sync_to_workbook import _sheet_cell  # noqa: E402
from mse_workbook_utils import node_id  # noqa: E402

import httpx  # noqa: E402

DEFAULT_SHEET = "金蛋奖池配置"

EGG_POOL_KEYS: tuple[tuple[str, str], ...] = (
    ("freeLotteryId", "免费次数奖池"),
    ("lv1LotteryId", "LV1 金蛋档次奖池"),
    ("lv2LotteryId", "LV2 金蛋档次奖池"),
    ("lv3LotteryId", "LV3 金蛋档次奖池"),
    ("voucherLotteryId", "兑换券奖池"),
    ("mysteryLotteryId", "神秘奖励奖池"),
)

DETAIL_HEADER = [
    "奖池ID",
    "奖池名称",
    "MSE用途",
    "序号",
    "奖品类型",
    "数量/区间",
    "奖品ID",
    "奖品名称",
    "权重(rate)",
    "限量(limit)",
    "可替换",
    "权重占比",
    "名称/备注",
]


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _pct(weight: int | float, total: int | float) -> str:
    if not total:
        return ""
    return f"{100.0 * float(weight) / float(total):.2f}%"


def _format_num_range(num_start: Any, num_end: Any) -> str:
    try:
        start = int(num_start or 0)
        end = int(num_end or 0)
    except (TypeError, ValueError):
        return _cell(num_start)
    if end in (0, 1) or end == start:
        return str(start)
    if end < start:
        return f"{start}~{end}"
    return f"{start}-{end}"


def _is_lookup_prop_id(prize_id: str) -> bool:
    """奖池 id 字段为数字 propId 时可查 MDP 道具后台。"""
    text = str(prize_id or "").strip()
    return text.isdigit()


def _lookup_prop_names(prop_ids: list[str]) -> dict[str, dict[str, Any]]:
    """MDP propAdmin/queryPropInfo 查装扮/VIP 道具名；失败不阻断写表。"""
    ids = sorted({str(x).strip() for x in prop_ids if _is_lookup_prop_id(str(x))})
    if not ids:
        return {}
    try:
        from admin.env import load_local_env
        from admin.prop import lookup_prop_names

        load_local_env(str(admin_module_dir()))
        return lookup_prop_names(ids)
    except Exception:
        return {}


def _prop_display_name(
    prize_id: str,
    prop_names: dict[str, dict[str, Any]],
) -> str:
    if not _is_lookup_prop_id(prize_id):
        return ""
    info = prop_names.get(prize_id) or {}
    return str(info.get("propName") or "").strip()


def _prop_type_suffix(
    prize_id: str,
    prop_names: dict[str, dict[str, Any]],
) -> str:
    if not _is_lookup_prop_id(prize_id):
        return ""
    info = prop_names.get(prize_id) or {}
    return str(info.get("propTypeName") or "").strip()


def _gift_display_name(
    prize_id: str,
    gift_names: dict[str, dict[str, Any]],
) -> str:
    if not prize_id:
        return ""
    info = gift_names.get(prize_id) or {}
    return str(info.get("name") or "").strip()


def _prize_name(
    prize: dict[str, Any],
    *,
    gift_names: dict[str, dict[str, Any]],
    prop_names: dict[str, dict[str, Any]],
) -> str:
    prize_type = prize.get("type")
    prize_id = str(prize.get("id") or "").strip()
    if prize_type == 1:
        return "钻石"
    if prize_type == 7:
        return "兑换券"
    if prize_type == 3:
        name = _prop_display_name(prize_id, prop_names)
        return name or "VIP经验/成长值"
    if prize_type == 2:
        name = _prop_display_name(prize_id, prop_names)
        return name or f"装扮/道具 {prize_id}".strip()
    if prize_type == 5 and prize_id:
        return _gift_display_name(prize_id, gift_names) or prize_id
    return prize_id or ""


def _prize_note(
    prize: dict[str, Any],
    *,
    gift_names: dict[str, dict[str, Any]],
    prop_names: dict[str, dict[str, Any]],
) -> str:
    prize_type = prize.get("type")
    prize_id = str(prize.get("id") or "").strip()
    if prize_type == 1:
        return "钻石区间"
    if prize_type == 7:
        return "兑换券"
    if prize_type == 3:
        type_name = _prop_type_suffix(prize_id, prop_names)
        return type_name or "VIP经验/成长值"
    if prize_type == 2:
        type_name = _prop_type_suffix(prize_id, prop_names)
        if type_name:
            return type_name
        return f"propId={prize_id}" if prize_id else "装扮/道具"
    if prize_type == 5 and prize_id:
        info = gift_names.get(prize_id) or {}
        price = info.get("price")
        if price is not None:
            return f"{price}钻"
        return prize_id
    return prize_id or ""


def _collect_egg_pool_ids(cfg: dict[str, Any]) -> list[tuple[int, str, str]]:
    pool_cfg = cfg.get("eggPoolConfig") or {}
    if not isinstance(pool_cfg, dict):
        return []
    ordered: list[tuple[int, str, str]] = []
    seen: set[int] = set()
    for key, role in EGG_POOL_KEYS:
        raw = pool_cfg.get(key)
        if raw in (None, ""):
            continue
        try:
            pool_id = int(str(raw).strip())
        except (TypeError, ValueError):
            continue
        if pool_id in seen:
            continue
        seen.add(pool_id)
        ordered.append((pool_id, key, role))
    return ordered


def build_lottery_rows(
    *,
    cfg: dict[str, Any],
    meta: dict[str, Any],
    pools_by_id: dict[int, dict[str, Any]],
) -> tuple[list[list[Any]], dict[str, Any]]:
    synced = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    rows: list[list[Any]] = [
        ["3周年砸金蛋 · CMS 奖池配置", "", "", "", f"同步时间 {synced}"],
        ["区块", "项", "值", "补充", "说明"],
        [
            "元数据",
            "configKey",
            meta.get("configKey") or DEFAULT_CONFIG_KEY,
            "",
            "MSE 活动配置键，eggPoolConfig 映射各 lotteryId",
        ],
        [
            "元数据",
            "MSE modified",
            meta.get("modified") or "",
            "",
            "MSE 配置最近修改时间",
        ],
        [
            "元数据",
            "数据源",
            "POST /yaahlan/cms/activity/getLotteryList + MDP propAdmin/queryPropInfo",
            "",
            "CMS 奖池全量；装扮/VIP 道具名来自 propId 查 MDP 道具后台",
        ],
        ["", "", "", "", ""],
        ["MSE 奖池映射", "MSE 字段", "lotteryId", "CMS 奖池名称", "用途说明"],
    ]

    pool_roles: dict[int, tuple[str, str]] = {}
    for pool_id, key, role in _collect_egg_pool_ids(cfg):
        pool = pools_by_id.get(pool_id) or {}
        pool_name = str(pool.get("name") or "").strip()
        pool_roles[pool_id] = (key, role)
        rows.append(["MSE 奖池映射", key, pool_id, pool_name, role])

    rows.append(["", "", "", "", ""])
    rows.append(list(DETAIL_HEADER))

    gift_ids: list[str] = []
    prop_ids: list[str] = []
    for pool_id in pool_roles:
        pool = pools_by_id.get(pool_id) or {}
        for prize in pool.get("lotteryList") or []:
            if not isinstance(prize, dict):
                continue
            prize_type = int(prize.get("type") or 0)
            pid = str(prize.get("id") or "").strip()
            if prize_type == 5 and pid:
                gift_ids.append(pid)
            elif prize_type in (2, 3) and _is_lookup_prop_id(pid):
                prop_ids.append(pid)
    gift_names = _lookup_gift_names(sorted(set(gift_ids)))
    prop_names = _lookup_prop_names(prop_ids)
    unresolved_prop_ids = sorted(
        {pid for pid in set(prop_ids) if pid not in prop_names}
    )

    for pool_id, key, role in _collect_egg_pool_ids(cfg):
        pool = pools_by_id.get(pool_id)
        if not isinstance(pool, dict):
            rows.append(
                [
                    pool_id,
                    "",
                    role,
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    f"未在 CMS 找到 lotteryId={pool_id}",
                ]
            )
            continue
        pool_name = str(pool.get("name") or "").strip()
        prizes = [p for p in (pool.get("lotteryList") or []) if isinstance(p, dict)]
        total_rate = 0
        for prize in prizes:
            try:
                total_rate += int(prize.get("rate") or 0)
            except (TypeError, ValueError):
                pass
        for idx, prize in enumerate(prizes, start=1):
            try:
                rate = int(prize.get("rate") or 0)
            except (TypeError, ValueError):
                rate = 0
            rows.append(
                [
                    pool_id,
                    pool_name,
                    role,
                    idx,
                    prize.get("typeLabel") or prize.get("type"),
                    _format_num_range(prize.get("numStart"), prize.get("numEnd")),
                    prize.get("id") or "",
                    _prize_name(prize, gift_names=gift_names, prop_names=prop_names),
                    rate,
                    prize.get("limit") or "",
                    prize.get("isReplace") or "",
                    _pct(rate, total_rate),
                    _prize_note(prize, gift_names=gift_names, prop_names=prop_names),
                ]
            )

    rows.append(["", "", "", "", "", "", "", "", "", "", "", "", ""])
    rows.append(
        [
            "说明",
            "rate",
            "CMS 权重基数",
            "",
            "同奖池内各行 rate 占比 = 权重占比列",
        ]
    )
    rows.append(
        [
            "说明",
            "验收对照",
            "smashEgg.prizeId / prizeType / num",
            "",
            "档次奖励验收时对照本表对应 MSE 用途奖池（兑换券另对照 voucherLotteryId）",
        ]
    )
    rows.append(
        [
            "说明",
            "奖品名称",
            "装扮/道具/VIP 来自 MDP queryPropInfo；礼物来自 giftAdmin",
            "",
            "名称/备注列补充类型或价格",
        ]
    )
    meta_out = {
        "giftNamesResolved": len(gift_names),
        "propNamesResolved": len(prop_names),
        "unresolvedPropIds": unresolved_prop_ids,
    }
    return rows, meta_out


def fetch_lottery_pools(*, force_refresh: bool = True) -> dict[int, dict[str, Any]]:
    from admin.env import load_local_env

    load_local_env(str(admin_module_dir()))
    from admin.activity import fetch_lottery_pools_by_id

    return fetch_lottery_pools_by_id(force_refresh=force_refresh)


async def write_lottery_sheet_async(
    workbook_url_or_id: str,
    rows: list[list[Any]],
    *,
    sheet_name: str = DEFAULT_SHEET,
) -> str:
    workbook_id = node_id(workbook_url_or_id)
    url = f"https://alidocs.dingtalk.com/i/nodes/{workbook_id}"
    env = _excel_env()
    token, operator = await _get_token_and_operator(env)
    async with httpx.AsyncClient(timeout=120) as client:
        await _ensure_sheet(
            token=token,
            operator=operator,
            workbook_id=workbook_id,
            sheet_name=sheet_name,
            client=client,
        )
    await _write_sheet_replace(
        token=token,
        operator=operator,
        workbook_id=workbook_id,
        sheet_name=sheet_name,
        rows=_string_rows([[_sheet_cell(c) for c in r] for r in rows]),
    )
    return url


def sync_year3_lottery_to_workbook(
    *,
    workbook: str = DEFAULT_WORKBOOK,
    sheet_name: str = DEFAULT_SHEET,
    namespace: str = DEFAULT_NAMESPACE,
    config_key: str = DEFAULT_CONFIG_KEY,
    cluster: str = "alpha",
    env: str = "alpha",
    region: str = "alpha",
    dry_run: bool = False,
) -> dict[str, Any]:
    cfg, meta = fetch_year3_mse_config(
        namespace=namespace,
        config_key=config_key,
        cluster=cluster,
        env=env,
        region=region,
    )
    pools_by_id = fetch_lottery_pools(force_refresh=True)
    pool_ids = _collect_egg_pool_ids(cfg)
    rows, name_meta = build_lottery_rows(cfg=cfg, meta=meta, pools_by_id=pools_by_id)
    missing = [pid for pid, _, _ in pool_ids if pid not in pools_by_id]
    out: dict[str, Any] = {
        "sheetName": sheet_name,
        "rowCount": len(rows),
        "poolCount": len(pool_ids),
        "poolIds": [pid for pid, _, _ in pool_ids],
        "missingPoolIds": missing,
        "meta": meta,
        **name_meta,
    }
    if dry_run:
        out["rowsPreview"] = rows[:40]
        return out
    url = asyncio.run(
        write_lottery_sheet_async(workbook, rows, sheet_name=sheet_name)
    )
    out["workbookUrl"] = url
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="3周年砸金蛋 CMS 奖池写入钉钉表")
    parser.add_argument("--workbook", default=DEFAULT_WORKBOOK)
    parser.add_argument("--sheet-name", default=DEFAULT_SHEET)
    parser.add_argument("--namespace", default=DEFAULT_NAMESPACE)
    parser.add_argument("--config-key", default=DEFAULT_CONFIG_KEY)
    parser.add_argument("--cluster", default="alpha")
    parser.add_argument("--env", default="alpha")
    parser.add_argument("--region", default="alpha")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    out = sync_year3_lottery_to_workbook(
        workbook=args.workbook,
        sheet_name=args.sheet_name,
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
