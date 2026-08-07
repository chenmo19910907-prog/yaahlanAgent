#!/usr/bin/env python3
"""PK 提款机 MSE pkAtmConfig → 钉钉活动配置表。"""

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
from mse_sync_to_workbook import _sheet_cell, _node_id  # noqa: E402
from repo_paths import mse_execute_path  # noqa: E402

import httpx  # noqa: E402

DEFAULT_CONFIG_KEY = "pkAtmConfig"
DEFAULT_NAMESPACE = "voga-common"

PARAM_LABELS: dict[str, str] = {
    "enabled": "活动总开关",
    "longTermEnabled": "长期活动开关",
    "startTime": "活动开始时间",
    "endTime": "活动结束时间",
    "dailyStartHour": "每日开始小时",
    "dailyEndHour": "每日结束小时",
    "minTotalPkValue": "场次总 PK 门槛",
    "minMemberRewardPk": "个人瓜分 PK 门槛",
    "broadcastMinDiamond": "广播最低钻石",
    "firstWinEnabled": "首胜翻倍开关",
    "firstWinMultiplier": "首胜倍数",
    "whiteList": "白名单",
    "activityNotifyRoomIdWhiteList": "活动通知房间白名单",
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
    """单表：分类 | 键 | 值 | 说明"""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000+00:00")
    rows: list[list[Any]] = [
        ["PK 提款机 · voga-common/pkAtmConfig（单表）"],
        [f"生成时间: {now}"],
        [],
        ["分类", "键", "值", "说明"],
        ["MSE元信息", "namespace", meta.get("nameSpace"), ""],
        ["MSE元信息", "configKey", meta.get("configKey"), ""],
        ["MSE元信息", "configDesc", meta.get("configDesc"), ""],
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
    for key, label in PARAM_LABELS.items():
        if key in cfg:
            rows.append(["基础参数", key, cfg.get(key), label])
    dispatch = cfg.get("diamondDispatchConfig")
    if isinstance(dispatch, dict):
        for sub_key, sub_val in dispatch.items():
            rows.append(["发钻配置", f"diamondDispatchConfig.{sub_key}", sub_val, ""])
    for item in cfg.get("matchPoolGradients") or []:
        if not isinstance(item, dict):
            continue
        min_pk = item.get("minTotalPkValue")
        ratio = item.get("returnRatioPercent")
        rows.append(
            [
                "梯度",
                f"minTotalPkValue={min_pk}",
                ratio,
                f"总 PK ≥ {min_pk:,} → 返 {ratio}%",
            ]
        )
    return rows


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


async def update_workbook_async(
    workbook_url_or_id: str,
    cfg: dict[str, Any],
    meta: dict[str, Any],
) -> str:
    workbook_id = _node_id(workbook_url_or_id)
    await _write_single_sheet(workbook_id, cfg, meta)
    return ALIDOCS_NODE.format(node_id=workbook_id)


async def create_workbook_async(
    *,
    title: str,
    parent_node_id: str,
    cfg: dict[str, Any],
    meta: dict[str, Any],
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
    await _write_single_sheet(workbook_id, cfg, meta)
    return ALIDOCS_NODE.format(node_id=workbook_id)


def sync_pk_atm_to_workbook(
    *,
    namespace: str = DEFAULT_NAMESPACE,
    config_key: str = DEFAULT_CONFIG_KEY,
    cluster: str = "alpha",
    env: str = "alpha",
    region: str = "alpha",
    workbook_name: str | None = None,
    parent_node_id: str | None = None,
    workbook_url: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    cfg, meta = _fetch_config(
        namespace=namespace,
        config_key=config_key,
        cluster=cluster,
        env=env,
        region=region,
    )
    title = workbook_name or "PK提款机 pkAtmConfig（MSE alpha）"
    export_cfg = load_export_config()
    parent = (parent_node_id or export_cfg.node_id).strip()
    out: dict[str, Any] = {
        "title": title,
        "parentNodeId": parent,
        "meta": meta,
        "highlights": {
            "minTotalPkValue": cfg.get("minTotalPkValue"),
            "minMemberRewardPk": cfg.get("minMemberRewardPk"),
            "firstWinMultiplier": cfg.get("firstWinMultiplier"),
            "gradientCount": len(cfg.get("matchPoolGradients") or []),
        },
    }
    if dry_run:
        out["paramPreview"] = _string_rows(build_unified_rows(cfg, meta))[:25]
        return out
    if workbook_url and workbook_url.strip():
        url = asyncio.run(
            update_workbook_async(
                workbook_url.strip(),
                cfg,
                meta,
            )
        )
        out["mode"] = "update"
    else:
        url = asyncio.run(
            create_workbook_async(
                title=title,
                parent_node_id=parent,
                cfg=cfg,
                meta=meta,
            )
        )
        out["mode"] = "create"
    out["workbookUrl"] = url
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="PK 提款机 pkAtmConfig MSE 配置写入钉钉表")
    parser.add_argument("--namespace", default=DEFAULT_NAMESPACE)
    parser.add_argument("--config-key", default=DEFAULT_CONFIG_KEY)
    parser.add_argument("--cluster", default="alpha")
    parser.add_argument("--env", default="alpha")
    parser.add_argument("--region", default="alpha")
    parser.add_argument("--workbook-name", help="钉钉表格名称（新建时）")
    parser.add_argument("--workbook-url", help="已有表格 URL 或 nodeId（覆盖更新）")
    parser.add_argument("--parent-node-id", help="父目录 nodeId，默认 Agent 导出目录")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    out = sync_pk_atm_to_workbook(
        namespace=args.namespace.strip(),
        config_key=args.config_key.strip(),
        cluster=args.cluster.strip(),
        env=args.env.strip(),
        region=args.region.strip(),
        workbook_name=args.workbook_name,
        parent_node_id=args.parent_node_id,
        workbook_url=args.workbook_url,
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
