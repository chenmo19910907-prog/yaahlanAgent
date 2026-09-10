#!/usr/bin/env python3
"""家族怪兽挑战 MSE activityConfig.FamilyMonster → 钉钉活动配置表。"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
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

from alidocs_excel_export import ALIDOCS_NODE, _excel_env, _get_token_and_operator  # noqa: E402
from family_pk_tab_to_workbook import _ensure_sheet, _write_sheet_replace  # noqa: E402
from mse_sync_to_workbook import _sheet_cell  # noqa: E402
from mse_workbook_utils import node_id  # noqa: E402
from repo_paths import gift_module_dir, mse_execute_path  # noqa: E402

import httpx  # noqa: E402

DEFAULT_CONFIG_KEY = "activityConfig.FamilyMonster"
DEFAULT_NAMESPACE = "voga-common"
DEFAULT_SHEET = "怪兽挑战配置"
DEFAULT_WORKBOOK = "https://alidocs.dingtalk.com/i/nodes/QG53mjyd80RNdKjKCeLv20KKV6zbX04v"

PARAM_LABELS: dict[str, str] = {
    "whiteUsers": "白名单用户",
    "startTime": "活动开始时间",
    "endTime": "活动结束时间",
    "dataVersion": "配置版本",
    "giftIds": "活动礼物 ID",
    "roomScreenGiftValueThreshold": "房间公屏礼物价值阈值",
    "chestClaimSeconds": "宝箱领取秒数",
    "roomUpdateMsgIntervalSec": "房间更新消息间隔秒",
    "multTipGapDamage": "倍率提示间隔伤害",
    "multTipDisplaySec": "倍率提示展示秒",
    "normalDamageThreshold": "普通伤害阈值",
    "eliteDamageThreshold": "精英伤害阈值",
    "participateStockPerMonster": "每怪参与库存",
    "familyJackpotDamage": "家族 jackpot 伤害",
    "platformJackpotDamage": "平台 jackpot 伤害",
    "familyJackpotDiamond": "家族 jackpot 钻石",
    "platformJackpotDiamond": "平台 jackpot 钻石",
    "floatDiamondThreshold": "飘屏钻石阈值",
    "participateBagId": "参与袋 ID",
    "memberRankTopN": "成员榜 TopN",
    "familyRankTopN": "家族榜 TopN",
    "memberRankBagId": "成员榜袋 ID",
    "familyRankBagId": "家族榜袋 ID",
}


def _lookup_gift_names(gift_ids: list[str]) -> dict[str, dict[str, Any]]:
    """查礼物名/价格；失败不阻断写表。"""
    out: dict[str, dict[str, Any]] = {}
    if not gift_ids:
        return out
    try:
        sys.path.insert(0, str(gift_module_dir()))
        from gift.send_stage import query_gift  # noqa: E402
    except Exception:
        return out
    for gid in gift_ids:
        try:
            meta = query_gift(str(gid), lang="en")
            out[str(gid)] = {
                "name": meta.get("productName") or "",
                "price": meta.get("price"),
            }
        except Exception:
            continue
    return out


def _format_gift_ids_note(gift_ids: Any, *, base_label: str) -> str:
    if not isinstance(gift_ids, list) or not gift_ids:
        return base_label
    name_map = _lookup_gift_names([str(x) for x in gift_ids])
    parts: list[str] = []
    for gid in gift_ids:
        gid_s = str(gid)
        info = name_map.get(gid_s) or {}
        name = info.get("name") or ""
        price = info.get("price")
        if name and price is not None:
            parts.append(f"{gid_s} {name}({int(price) if float(price).is_integer() else price}钻)")
        elif name:
            parts.append(f"{gid_s} {name}")
        else:
            parts.append(gid_s)
    detail = "；".join(parts)
    return f"{base_label}：{detail}" if detail else base_label


def _fetch_config(
    *,
    namespace: str,
    config_key: str,
    cluster: str,
    env: str,
    region: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    cmd = [
        "python3",
        str(mse_execute_path()),
        "--namespace",
        namespace,
        "--config-key",
        config_key,
        "--cluster",
        cluster,
        "--env",
        env,
        "--region",
        region,
        "--output",
        "json",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO_ROOT))
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "MSE 读取失败").strip())
    data = json.loads(proc.stdout)
    if not isinstance(data, list) or not data:
        raise RuntimeError(f"未找到配置 {namespace}/{config_key}")
    item = data[0]
    raw_value = item.get("configValue")
    if isinstance(raw_value, str):
        parsed = json.loads(raw_value)
    elif isinstance(raw_value, dict):
        parsed = raw_value
    else:
        raise RuntimeError("configValue 不是 JSON 对象")
    if not isinstance(parsed, dict):
        raise RuntimeError("configValue 解析后不是对象")
    meta = {
        "nameSpace": item.get("nameSpace") or namespace,
        "configKey": item.get("configKey") or config_key,
        "configDesc": item.get("configDesc") or "",
        "modified": item.get("modified") or "",
        "modifiedBy": item.get("momoName") or "",
        "status": item.get("status") or "",
        "appKey": item.get("appKey") or "",
        "region": region,
        "env": env,
        "cluster": cluster,
    }
    return parsed, meta


def _string_rows(rows: list[list[Any]]) -> list[list[str]]:
    return [[_sheet_cell(c) for c in row] for row in rows]


def build_unified_rows(cfg: dict[str, Any], meta: dict[str, Any]) -> list[list[Any]]:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000+00:00")
    rows: list[list[Any]] = [
        ["家族怪兽挑战 · activityConfig.FamilyMonster（单表）"],
        [f"生成时间: {now}"],
        [],
        ["分类", "键", "值", "说明"],
        ["MSE元信息", "namespace", meta.get("nameSpace"), ""],
        ["MSE元信息", "configKey", meta.get("configKey"), ""],
        ["MSE元信息", "appKey", meta.get("appKey"), ""],
        [
            "MSE元信息",
            "cluster / env / region",
            f"{meta.get('cluster')} / {meta.get('env')} / {meta.get('region')}",
            "",
        ],
        ["MSE元信息", "最后修改", meta.get("modified"), meta.get("modifiedBy") or ""],
        ["MSE元信息", "状态", meta.get("status"), ""],
    ]
    skip_keys = {
        "prizeConfig",
        "chestResource",
        "monsters",
        "giftRebateConfigs",
        "damageMultiplierTiers",
        "recordGoto",
        "ruleGoto",
        "joinFamilyGoto",
        "activityGoto",
        "floatBgImg",
        "progressStartColor",
        "progressEndColor",
        "progressBgColor",
        "hpTextColor",
    }
    for key, label in PARAM_LABELS.items():
        if key not in cfg:
            continue
        note = label
        if key == "giftIds":
            note = _format_gift_ids_note(cfg.get(key), base_label=label)
        rows.append(["基础参数", key, cfg.get(key), note])
    prize = cfg.get("prizeConfig")
    if isinstance(prize, dict):
        for sub_key, sub_val in prize.items():
            if isinstance(sub_val, dict):
                for k2, v2 in sub_val.items():
                    rows.append(["发奖配置", f"prizeConfig.{sub_key}.{k2}", v2, ""])
            else:
                rows.append(["发奖配置", f"prizeConfig.{sub_key}", sub_val, ""])
    chest = cfg.get("chestResource")
    if isinstance(chest, dict):
        for k, v in chest.items():
            rows.append(["宝箱资源", k, v, ""])
    for monster in cfg.get("monsters") or []:
        if not isinstance(monster, dict):
            continue
        lv = monster.get("level")
        milestone = monster.get("familyMilestoneBagId")
        value_parts = [
            f"maxHp={monster.get('maxHp')}",
            f"maxClaimCount={monster.get('maxClaimCount')}",
            f"普通袋={monster.get('normalBagId')}",
            f"精英袋={monster.get('eliteBagId')}",
            f"里程碑袋={milestone if milestone not in (None, '') else '-'}",
        ]
        rows.append(
            [
                "怪兽",
                f"Lv.{lv}",
                " ".join(value_parts),
                "奖池明细见 Sheet「怪兽挑战奖池配置」",
            ]
        )
    for gift_cfg in cfg.get("giftRebateConfigs") or []:
        if not isinstance(gift_cfg, dict):
            continue
        gift_id = gift_cfg.get("giftId")
        for w in gift_cfg.get("weights") or []:
            if not isinstance(w, dict):
                continue
            rows.append(
                [
                    "礼物返利",
                    gift_id,
                    f"rate={w.get('rate')} min={w.get('min')} max={w.get('max')}",
                    "giftRebateConfigs",
                ]
            )
    for tier in cfg.get("damageMultiplierTiers") or []:
        if not isinstance(tier, dict):
            continue
        rows.append(
            [
                "伤害倍率",
                tier.get("threshold"),
                tier.get("multiplier"),
                f"累计伤害≥{tier.get('threshold')} → ×{tier.get('multiplier')}",
            ]
        )
    goto_keys = ("recordGoto", "ruleGoto", "joinFamilyGoto", "activityGoto")
    for key in goto_keys:
        if key in cfg:
            rows.append(["跳转", key, cfg.get(key), ""])
    ui_keys = (
        "floatBgImg",
        "progressStartColor",
        "progressEndColor",
        "progressBgColor",
        "hpTextColor",
    )
    for key in ui_keys:
        if key in cfg:
            rows.append(["UI", key, cfg.get(key), ""])
    for key, value in cfg.items():
        if key in PARAM_LABELS or key in skip_keys:
            continue
        rows.append(["其他", key, value, ""])
    rows.append([])
    rows.append(["configValue JSON", json.dumps(cfg, ensure_ascii=False, indent=2)])
    return rows


async def update_workbook_async(
    workbook_url_or_id: str,
    cfg: dict[str, Any],
    meta: dict[str, Any],
    *,
    sheet_name: str = DEFAULT_SHEET,
) -> str:
    workbook_id = node_id(workbook_url_or_id)
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
        rows = _string_rows(build_unified_rows(cfg, meta))
        await _write_sheet_replace(
            token=token,
            operator=operator,
            workbook_id=workbook_id,
            sheet_name=sheet_name,
            rows=rows,
        )
    return ALIDOCS_NODE.format(node_id=workbook_id)


def sync_family_monster_to_workbook(
    *,
    namespace: str = DEFAULT_NAMESPACE,
    config_key: str = DEFAULT_CONFIG_KEY,
    cluster: str = "alpha",
    env: str = "alpha",
    region: str = "alpha",
    workbook_url: str,
    sheet_name: str = DEFAULT_SHEET,
    dry_run: bool = False,
) -> dict[str, Any]:
    cfg, meta = _fetch_config(
        namespace=namespace,
        config_key=config_key,
        cluster=cluster,
        env=env,
        region=region,
    )
    out: dict[str, Any] = {
        "sheetName": sheet_name,
        "meta": meta,
        "highlights": {
            "dataVersion": cfg.get("dataVersion"),
            "startTime": cfg.get("startTime"),
            "endTime": cfg.get("endTime"),
            "monsterCount": len(cfg.get("monsters") or []),
            "giftCount": len(cfg.get("giftIds") or []),
        },
    }
    if dry_run:
        out["paramPreview"] = _string_rows(build_unified_rows(cfg, meta))[:25]
        return out
    url = asyncio.run(
        update_workbook_async(
            workbook_url.strip(),
            cfg,
            meta,
            sheet_name=sheet_name,
        )
    )
    out["workbookUrl"] = url
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="FamilyMonster MSE 配置写入钉钉表")
    parser.add_argument("--namespace", default=DEFAULT_NAMESPACE)
    parser.add_argument("--config-key", default=DEFAULT_CONFIG_KEY)
    parser.add_argument("--cluster", default="alpha")
    parser.add_argument("--env", default="alpha")
    parser.add_argument("--region", default="alpha")
    parser.add_argument(
        "--workbook-url",
        default=DEFAULT_WORKBOOK,
        help="目标表格 URL 或 nodeId",
    )
    parser.add_argument("--sheet-name", default=DEFAULT_SHEET, help="工作表名称")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    out = sync_family_monster_to_workbook(
        namespace=args.namespace.strip(),
        config_key=args.config_key.strip(),
        cluster=args.cluster.strip(),
        env=args.env.strip(),
        region=args.region.strip(),
        workbook_url=args.workbook_url.strip(),
        sheet_name=args.sheet_name.strip(),
        dry_run=args.dry_run,
    )
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
