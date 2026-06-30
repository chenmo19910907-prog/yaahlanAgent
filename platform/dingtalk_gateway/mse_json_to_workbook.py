#!/usr/bin/env python3
"""familyPkConfig JSON → 钉钉参数表 + configValue_JSON（可改表后 mse_param_sheet_to_json 回生成 JSON）。"""

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

from alidocs_excel_export import _excel_env, _get_token_and_operator  # noqa: E402
from mse_param_sheet_to_json import (  # noqa: E402
    JSON_SHEET,
    PARAM_SHEET,
    _json_sheet_rows,
    _node_id,
    _parse_param_sheet,
    _write_sheet,
)
from mse_config_export import _fetch_mse_config  # noqa: E402
from mse_workbook_utils import apply_parsed_values_to_original, format_rank_range  # noqa: E402

TIER_NOTE = "有效日均=max(区间日均,minBracketDailyAvg)；达标PK=有效日均×系数"


def _sheet_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (int, float)):
        return str(value)
    return str(value)


def _format_value(value: Any) -> str:
    return _sheet_cell(value)
TITLE = (
    "家族PK服务配置 · 参数表（仅改「参数值/系数/加成钻」列，改完 @Agent 生成 JSON）；"
    "区间日均低于 minBracketDailyAvg 时按 minBracketDailyAvg 计算档位"
)

DEFAULT_META = {
    "nameSpace": "voga-common",
    "configKey": "familyPkConfig",
    "configDesc": "家族pk",
    "modified": "",
}

DEFAULT_OPTIONAL = {
    "enabled": True,
    "eventGiftProductIds": [],
    "minBracketDailyAvg": 2000,
    "rewardRiskRuleId": "",
    "groupBarThrottleSec": 30,
    "roomBroadcastThrottleSec": 30,
    "activityH5Path": (
        "/yaahlan-fe/yaahlan-family-pk/index.html?_bid=1006677&_ui=256"
        "&_ui_mode=0&_ui_bg=ffffff&_wk=1&_resize=0"
    ),
    "bannerImageUrl": "",
    "groupStartImageUrl": "",
    "familyPkBgImg": "",
    "familyPkIcon": "",
    "familyPkVsIcon": "",
}


def _merge_config(raw: dict[str, Any]) -> dict[str, Any]:
    out = dict(DEFAULT_OPTIONAL)
    out.update(raw)
    dispatch = raw.get("diamondDispatchConfig")
    if isinstance(dispatch, dict):
        out["diamondDispatchConfig"] = dispatch
    return out


def build_param_sheet_rows(*, config: dict[str, Any], meta: dict[str, str]) -> list[list[Any]]:
    rows: list[list[Any]] = [
        [TITLE, "", "", ""],
        ["区块", "参数键", "参数值", "说明"],
    ]

    meta_rows = [
        ("nameSpace", "MSE 命名空间"),
        ("configKey", "配置键"),
        ("configDesc", "配置说明"),
        ("modified", "MSE 修改时间（ISO8601）"),
    ]
    for key, desc in meta_rows:
        rows.append(["元数据", key, meta.get(key, ""), desc])

    base_rows = [
        ("enabled", "是否开启"),
        ("activityStartDate", "活动开始时间（yyyy-MM-dd HH:mm:ss）"),
        ("activityEndDate", "活动结束时间（yyyy-MM-dd HH:mm:ss）"),
        ("pkStartHour", "PK 开始小时"),
        ("pkEndHour", "PK 结束小时"),
        ("basePoolDiamond", "0 档展示钻（999）"),
        ("minWinPk", "获胜最低 PK 值"),
        ("minRewardPk", "领奖最低 PK 值"),
        ("minListPk", "上榜最低 PK 值"),
        ("minBracketDailyAvg", "区间日均兜底：昨日收礼榜均值低于此值时，按此值参与档位达标PK计算"),
        ("maxRewardDiamondPerUser", "单用户最高奖励钻"),
        ("eventGiftProductIds", "活动礼物 ID 列表 JSON"),
        ("familyWhiteList", "家族白名单 JSON"),
    ]
    for key, desc in base_rows:
        if key in config:
            val = config[key]
            if key in ("activityStartDate", "activityEndDate") and val:
                val = f"\t{val}"
            rows.append(["基础", key, _format_value(val), desc])

    rows.append(["", "", "", ""])
    rows.append(["区块", "区间下标", "名次区间", "档位", "系数", "加成钻", "说明"])
    for bracket_idx, bracket in enumerate(config.get("bracketGradients") or []):
        rank_label = format_rank_range(bracket.get("rankStart"), bracket.get("rankEnd"))
        for tier_idx, item in enumerate(bracket.get("gradients") or [], start=1):
            note = f"{rank_label} · {tier_idx}档；{TIER_NOTE}"
            rows.append(
                [
                    "档位",
                    bracket_idx,
                    rank_label,
                    tier_idx,
                    item.get("coefficient"),
                    item.get("bonusDiamond"),
                    note,
                ]
            )

    rows.append(["", "", "", ""])
    rows.append(["区块", "参数键", "参数值", "说明"])

    dispatch = config.get("diamondDispatchConfig") or {}
    dispatch_rows = [
        ("diamondDispatchConfig.activityId", dispatch.get("activityId", ""), "活动 ID"),
        ("diamondDispatchConfig.activityTaskId", dispatch.get("activityTaskId", ""), "任务 ID"),
        ("diamondDispatchConfig.signKey", dispatch.get("signKey", ""), "签名 Key"),
    ]
    for key, val, desc in dispatch_rows:
        rows.append(["发钻", key, _format_value(val), desc])

    dotted_sections: list[tuple[str, list[tuple[str, str, str]]]] = [
        (
            "风控",
            [
                ("rewardRiskRuleId", "发奖风控规则 ID"),
            ],
        ),
        (
            "节流",
            [
                ("groupBarThrottleSec", "群 bar 节流秒"),
                ("roomBroadcastThrottleSec", "房间广播节流秒"),
            ],
        ),
        ("H5", [("activityH5Path", "活动 H5 路径")]),
        (
            "资源",
            [
                ("bannerImageUrl", "Banner 图"),
                ("groupStartImageUrl", "群开始图"),
                ("familyPkBgImg", "PK 背景图"),
                ("familyPkIcon", "PK 图标"),
                ("familyPkVsIcon", "VS 图标"),
            ],
        ),
    ]
    for block, fields in dotted_sections:
        for key, desc in fields:
            if key in config:
                rows.append([block, key, _format_value(config[key]), desc])

    return rows


def _string_rows(rows: list[list[Any]]) -> list[list[str]]:
    cols = max(len(r) for r in rows) if rows else 1
    out: list[list[str]] = []
    for row in rows:
        padded = list(row) + [""] * (cols - len(row))
        out.append([_sheet_cell(c) for c in padded])
    return out


async def json_to_workbook_async(
    workbook_url_or_id: str,
    config: dict[str, Any],
    *,
    meta: dict[str, str] | None = None,
) -> str:
    workbook_id = _node_id(workbook_url_or_id)
    url = f"https://alidocs.dingtalk.com/i/nodes/{workbook_id}"

    merged = _merge_config(config)
    meta_info = {**DEFAULT_META, **(meta or {})}
    if not meta_info.get("modified"):
        meta_info["modified"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000+00:00")

    param_rows = build_param_sheet_rows(config=merged, meta=meta_info)
    parsed, parsed_meta = _parse_param_sheet(param_rows)
    original = _fetch_mse_config(namespace="voga-common", config_key="familyPkConfig")["configValue"]
    canonical = apply_parsed_values_to_original(original, parsed)
    json_rows = _json_sheet_rows(meta={**meta_info, **parsed_meta}, config=canonical)

    env = _excel_env()
    token, operator = await _get_token_and_operator(env)
    await _write_sheet(
        token=token,
        operator=operator,
        workbook_id=workbook_id,
        sheet_name=PARAM_SHEET,
        rows=_string_rows(param_rows),
    )
    await _write_sheet(
        token=token,
        operator=operator,
        workbook_id=workbook_id,
        sheet_name=JSON_SHEET,
        rows=json_rows,
    )
    return url


def json_to_workbook(
    workbook_url_or_id: str,
    config: dict[str, Any],
    *,
    meta: dict[str, str] | None = None,
) -> str:
    return asyncio.run(json_to_workbook_async(workbook_url_or_id, config, meta=meta))


def main() -> int:
    parser = argparse.ArgumentParser(description="familyPkConfig JSON 写入钉钉参数表")
    parser.add_argument("workbook", help="钉钉表格 URL 或 nodeId")
    parser.add_argument(
        "--json-file",
        help="configValue JSON 文件路径；未指定则从 stdin 读取",
    )
    args = parser.parse_args()

    if args.json_file:
        raw_text = Path(args.json_file).read_text(encoding="utf-8")
    else:
        raw_text = sys.stdin.read()
    try:
        config = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        print(f"[FAIL] JSON 解析失败: {exc}", file=sys.stderr)
        return 1
    if not isinstance(config, dict):
        print("[FAIL] 根节点必须是 JSON object", file=sys.stderr)
        return 1

    try:
        url = json_to_workbook(args.workbook.strip(), config)
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1
    print(url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
