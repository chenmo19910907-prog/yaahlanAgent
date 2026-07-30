#!/usr/bin/env python3
"""Ultra Recharge MSE activityConfig.RechargeRebate → 钉钉活动配置表。"""

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

from alidocs_excel_export import (  # noqa: E402
    ALIDOCS_NODE,
    _create_workbook,
    _excel_env,
    _get_token_and_operator,
    _get_workspace_id,
)
from export_delivery import load_export_config  # noqa: E402
from family_pk_tab_to_workbook import _ensure_sheet, _write_sheet_replace  # noqa: E402
from mse_sync_to_workbook import _sheet_cell  # noqa: E402

import httpx  # noqa: E402

DEFAULT_CONFIG_KEY = "activityConfig.RechargeRebate"
DEFAULT_NAMESPACE = "Application"

PARAM_LABELS: dict[str, str] = {
    "dataVersion": "配置版本",
    "startTime": "活动开始时间",
    "endTime": "活动结束时间",
    "whiteUsers": "白名单用户",
    "giftIds": "统计礼物ID（自送获次等）",
    "baseRebateRatio": "基础返奖比（老用户默认）",
    "newUserPeriodDays": "新用户判定天数（≤此天为新用户）",
    "monthlyRebateCap": "月返钻上限",
    "newUserHighRatio": "新用户高返奖比（50万额度内）",
    "newUserLowRatio": "新用户低返奖比（超额部分）",
    "newUserRechargeCap": "新用户高比例充值额度上限",
    "oldUserStatDays": "老用户行为统计天数",
    "inactiveUserActiveDaysThreshold": "沉默用户活跃天数阈值",
    "inactiveUserDailyRechargeCap": "沉默用户日充值统计上限",
    "rechargeThresholds": "充值分档阈值（钻）",
    "lowConsumeThreshold": "低消费阈值（钻）",
    "giftPreferenceRatio": "送礼偏好系数",
    "gamePreferenceRatio": "游戏偏好系数",
    "gameBetConvertRatio": "游戏下注折算比",
    "riskHardControlRuleId": "风控硬控规则ID",
    "riskHardControlToken": "风控硬控Token",
    "riskNewUserDegradeRuleId": "新用户降级规则ID",
    "riskNewUserDegradeToken": "新用户降级Token",
    "riskCacheSeconds": "风控缓存秒数",
    "weeklyPrizeBagId": "周充礼包 prizeBagId",
    "monthlyPrizeBagId": "月充礼包 prizeBagId",
    "excludedPaySources": "排除充值渠道",
    "rechargeGotoStr": "充值跳转 deeplink",
}


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
        str(REPO_ROOT / "MSE/mse_execute.py"),
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
        "nameSpace": item.get("nameSpace") if item.get("nameSpace") not in (None, "") else "Application（私有）",
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


def build_param_rows(cfg: dict[str, Any], meta: dict[str, Any]) -> list[list[Any]]:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000+00:00")
    rows: list[list[Any]] = [
        ["Ultra Recharge · activityConfig.RechargeRebate 活动配置"],
        [f"生成时间: {now}"],
        [],
        ["MSE 元信息", "值"],
        ["namespace", meta.get("nameSpace")],
        ["configKey", meta.get("configKey")],
        ["appKey", meta.get("appKey")],
        ["cluster / env / region", f"{meta.get('cluster')} / {meta.get('env')} / {meta.get('region')}"],
        ["最后修改", meta.get("modified")],
        ["修改人", meta.get("modifiedBy")],
        ["状态", meta.get("status")],
        [],
        ["参数", "值", "说明"],
    ]
    skip_keys = {
        "prizeConfig",
        "rechargeConsumeMatrix",
        "gameLossTiers",
        "fortuneLevels",
        "ruleContentMap",
        "howToImprovePopupMap",
    }
    for key, label in PARAM_LABELS.items():
        if key in cfg:
            rows.append([key, cfg.get(key), label])
    prize = cfg.get("prizeConfig")
    if isinstance(prize, dict):
        rows.append([])
        rows.append(["prizeConfig 子项", "值", "说明"])
        for sub_key, sub_val in prize.items():
            rows.append([f"prizeConfig.{sub_key}", sub_val, ""])
            if isinstance(sub_val, dict):
                for k2, v2 in sub_val.items():
                    rows.append([f"prizeConfig.{sub_key}.{k2}", v2, ""])
    for key, value in cfg.items():
        if key in PARAM_LABELS or key in skip_keys:
            continue
        rows.append([key, value, ""])
    return rows


def build_matrix_rows(cfg: dict[str, Any]) -> list[list[Any]]:
    matrix = cfg.get("rechargeConsumeMatrix") or []
    thresholds = cfg.get("rechargeThresholds") or []
    low_consume = cfg.get("lowConsumeThreshold", 2000)
    row_labels = _matrix_row_labels(cfg)
    col_labels = _matrix_col_labels(cfg)
    rows: list[list[Any]] = [
        ["充值×消费 标签系数矩阵（rechargeConsumeMatrix）"],
        ["说明", "C = K_risk × 矩阵系数 × (1 + I_loss)；矩阵值为标签系数部分"],
        [],
        ["充值\\消费", *col_labels],
    ]
    for i, row_vals in enumerate(matrix):
        label = row_labels[i] if i < len(row_labels) else f"档位{i + 1}"
        if isinstance(row_vals, list):
            rows.append([label, *row_vals])
        else:
            rows.append([label, row_vals])
    rows.append([])
    rows.append(["rechargeThresholds", thresholds])
    rows.append(["lowConsumeThreshold", low_consume])
    return rows


def build_game_loss_rows(cfg: dict[str, Any]) -> list[list[Any]]:
    tiers = cfg.get("gameLossTiers") or []
    rows: list[list[Any]] = [
        ["游戏亏损系数（gameLossTiers）→ I_loss"],
        [],
        ["minLoss", "maxLoss", "coefficient", "说明"],
    ]
    for tier in tiers:
        if not isinstance(tier, dict):
            continue
        max_loss = tier.get("maxLoss")
        rows.append(
            [
                tier.get("minLoss"),
                max_loss if max_loss is not None else "∞",
                tier.get("coefficient"),
                f"亏损 [{tier.get('minLoss')}, {max_loss or '+∞'}) → +{tier.get('coefficient')}",
            ]
        )
    return rows


def build_fortune_rows(cfg: dict[str, Any]) -> list[list[Any]]:
    levels = cfg.get("fortuneLevels") or []
    rows: list[list[Any]] = [
        ["运势等级（fortuneLevels）"],
        [],
        ["level", "minRatio", "maxRatio", "说明"],
    ]
    for item in levels:
        if not isinstance(item, dict):
            continue
        rows.append(
            [
                item.get("level"),
                item.get("minRatio"),
                item.get("maxRatio"),
                f"[{item.get('minRatio')}, {item.get('maxRatio')})",
            ]
        )
    return rows


def build_json_rows(cfg: dict[str, Any], meta: dict[str, Any]) -> list[list[Any]]:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000+00:00")
    return [
        ["字段", "内容"],
        ["生成时间", now],
        ["configKey", meta.get("configKey")],
        ["modified", meta.get("modified")],
        ["configValue JSON", json.dumps(cfg, ensure_ascii=False, indent=2)],
    ]


def _matrix_row_labels(cfg: dict[str, Any]) -> list[str]:
    thresholds = cfg.get("rechargeThresholds") or []
    return [
        f"充值≤{thresholds[0] if thresholds else '?'}",
        f"充值({thresholds[0] if len(thresholds) > 0 else '?'}-{thresholds[1] if len(thresholds) > 1 else '?'})",
        f"充值({thresholds[1] if len(thresholds) > 1 else '?'}-{thresholds[2] if len(thresholds) > 2 else '?'})",
        f"充值>{thresholds[2] if len(thresholds) > 2 else '?'}",
        "充值档位5",
    ]


def _matrix_col_labels(cfg: dict[str, Any]) -> list[str]:
    low_consume = cfg.get("lowConsumeThreshold", 2000)
    return [
        f"消费≤{low_consume}",
        "消费档位2",
        "消费档位3",
        "消费档位4",
        "消费档位5",
    ]


def build_unified_rows(cfg: dict[str, Any], meta: dict[str, Any]) -> list[list[Any]]:
    """单表：分类 | 键 | 值 | 说明"""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000+00:00")
    rows: list[list[Any]] = [
        ["Ultra Recharge · activityConfig.RechargeRebate（单表汇总）"],
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
        "rechargeConsumeMatrix",
        "gameLossTiers",
        "fortuneLevels",
        "ruleContentMap",
        "howToImprovePopupMap",
    }
    for key, label in PARAM_LABELS.items():
        if key in cfg:
            rows.append(["基础参数", key, cfg.get(key), label])
    prize = cfg.get("prizeConfig")
    if isinstance(prize, dict):
        for sub_key, sub_val in prize.items():
            if isinstance(sub_val, dict):
                for k2, v2 in sub_val.items():
                    rows.append(["prizeConfig", f"{sub_key}.{k2}", v2, ""])
            else:
                rows.append(["prizeConfig", sub_key, sub_val, ""])
    matrix = cfg.get("rechargeConsumeMatrix") or []
    row_labels = _matrix_row_labels(cfg)
    col_labels = _matrix_col_labels(cfg)
    for i, row_vals in enumerate(matrix):
        r_label = row_labels[i] if i < len(row_labels) else f"充值档位{i + 1}"
        if isinstance(row_vals, list):
            for j, val in enumerate(row_vals):
                c_label = col_labels[j] if j < len(col_labels) else f"消费档位{j + 1}"
                rows.append(["充值消费矩阵", f"{r_label} × {c_label}", val, "标签系数；C=K_risk×系数×(1+I_loss)"])
        else:
            rows.append(["充值消费矩阵", r_label, row_vals, ""])
    for tier in cfg.get("gameLossTiers") or []:
        if not isinstance(tier, dict):
            continue
        max_loss = tier.get("maxLoss")
        rows.append(
            [
                "游戏亏损系数",
                f"[{tier.get('minLoss')}, {max_loss if max_loss is not None else '+∞'})",
                tier.get("coefficient"),
                "I_loss 加成系数",
            ]
        )
    for item in cfg.get("fortuneLevels") or []:
        if not isinstance(item, dict):
            continue
        rows.append(
            [
                "运势等级",
                item.get("level"),
                f"minRatio={item.get('minRatio')}, maxRatio={item.get('maxRatio')}",
                f"[{item.get('minRatio')}, {item.get('maxRatio')})",
            ]
        )
    for key, value in cfg.items():
        if key in PARAM_LABELS or key in skip_keys:
            continue
        rows.append(["其他", key, value, ""])
    return rows


SHEETS = [
    ("活动配置", build_param_rows),
    ("充值消费矩阵", build_matrix_rows),
    ("游戏亏损系数", build_game_loss_rows),
    ("运势等级", build_fortune_rows),
    ("configValue_JSON", build_json_rows),
]


async def _write_all_sheets(workbook_id: str, cfg: dict[str, Any], meta: dict[str, Any]) -> None:
    env = _excel_env()
    token, operator = await _get_token_and_operator(env)
    async with httpx.AsyncClient(timeout=120) as client:
        for sheet_name, builder in SHEETS:
            await _ensure_sheet(
                token=token,
                operator=operator,
                workbook_id=workbook_id,
                sheet_name=sheet_name,
                client=client,
            )
            if builder in (build_param_rows, build_json_rows):
                raw_rows = builder(cfg, meta)
            else:
                raw_rows = builder(cfg)
            rows = _string_rows(raw_rows)
            await _write_sheet_replace(
                token=token,
                operator=operator,
                workbook_id=workbook_id,
                sheet_name=sheet_name,
                rows=rows,
            )


async def _write_single_sheet(
    workbook_id: str,
    cfg: dict[str, Any],
    meta: dict[str, Any],
    *,
    sheet_name: str = "活动配置",
) -> None:
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


async def create_workbook_async(
    *,
    title: str,
    parent_node_id: str,
    cfg: dict[str, Any],
    meta: dict[str, Any],
    single_sheet: bool = False,
) -> str:
    env = _excel_env()
    token, operator = await _get_token_and_operator(env)
    workspace_id = _get_workspace_id(parent_node_id, "")
    workbook_id = await _create_workbook(
        token=token,
        operator=operator,
        workspace_id=workspace_id,
        parent_node_id=parent_node_id,
        name=title,
    )
    if single_sheet:
        await _write_single_sheet(workbook_id, cfg, meta)
    else:
        await _write_all_sheets(workbook_id, cfg, meta)
    return ALIDOCS_NODE.format(node_id=workbook_id)


def sync_recharge_rebate_to_workbook(
    *,
    namespace: str = DEFAULT_NAMESPACE,
    config_key: str = DEFAULT_CONFIG_KEY,
    cluster: str = "stage",
    env: str = "alpha",
    region: str = "alpha",
    workbook_name: str | None = None,
    parent_node_id: str | None = None,
    single_sheet: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    cfg, meta = _fetch_config(
        namespace=namespace,
        config_key=config_key,
        cluster=cluster,
        env=env,
        region=region,
    )
    title = workbook_name or "Ultra Recharge 活动配置（MSE）"
    export_cfg = load_export_config()
    parent = (parent_node_id or export_cfg.node_id).strip()
    out: dict[str, Any] = {
        "title": title,
        "parentNodeId": parent,
        "meta": meta,
        "highlights": {
            "startTime": cfg.get("startTime"),
            "endTime": cfg.get("endTime"),
            "baseRebateRatio": cfg.get("baseRebateRatio"),
            "monthlyRebateCap": cfg.get("monthlyRebateCap"),
            "newUserRechargeCap": cfg.get("newUserRechargeCap"),
            "weeklyPrizeBagId": cfg.get("weeklyPrizeBagId"),
            "monthlyPrizeBagId": cfg.get("monthlyPrizeBagId"),
        },
        "sheetCount": 1 if single_sheet else len(SHEETS),
        "singleSheet": single_sheet,
    }
    if dry_run:
        preview_builder = build_unified_rows if single_sheet else build_param_rows
        out["paramPreview"] = _string_rows(preview_builder(cfg, meta))[:20]
        return out
    url = asyncio.run(
        create_workbook_async(
            title=title,
            parent_node_id=parent,
            cfg=cfg,
            meta=meta,
            single_sheet=single_sheet,
        )
    )
    out["workbookUrl"] = url
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="RechargeRebate MSE 配置写入钉钉表")
    parser.add_argument("--namespace", default=DEFAULT_NAMESPACE)
    parser.add_argument("--config-key", default=DEFAULT_CONFIG_KEY)
    parser.add_argument("--cluster", default="stage")
    parser.add_argument("--env", default="alpha")
    parser.add_argument("--region", default="alpha")
    parser.add_argument("--workbook-name", help="钉钉表格名称")
    parser.add_argument("--parent-node-id", help="父目录 nodeId，默认 Agent 导出目录")
    parser.add_argument(
        "--single-sheet",
        action="store_true",
        help="全部写入单个 Sheet（分类|键|值|说明），不分页签",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    out = sync_recharge_rebate_to_workbook(
        namespace=args.namespace.strip(),
        config_key=args.config_key.strip(),
        cluster=args.cluster.strip(),
        env=args.env.strip(),
        region=args.region.strip(),
        workbook_name=args.workbook_name,
        parent_node_id=args.parent_node_id,
        single_sheet=args.single_sheet,
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
