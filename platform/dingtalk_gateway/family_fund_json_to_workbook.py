#!/usr/bin/env python3
"""familyFundConfig JSON → 钉钉参数表 + configValue_JSON。"""

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
from family_fund_calc_utils import (  # noqa: E402
    FAMILY_FUND_APP_KEY,
    FAMILY_FUND_CONFIG_KEY,
    FAMILY_FUND_NAMESPACE,
    fetch_family_fund_config,
)
from mse_config_export import _fetch_mse_config  # noqa: E402
from mse_param_sheet_to_json import (  # noqa: E402
    JSON_SHEET,
    PARAM_SHEET,
    _json_sheet_rows,
    _node_id,
    _parse_param_sheet,
    _write_sheet,
)
from mse_workbook_utils import apply_parsed_values_to_original, format_rank_range  # noqa: E402

TITLE = (
    "家族基金服务配置 · 参数表（改「参数值/阈值/比例」列；"
    "周档位由上周总贡献决定；成员榜 Top30 按 rankPrizes 比例，榜外合格用户均分 afterTopRankRatio）"
)

DEFAULT_META = {
    "nameSpace": FAMILY_FUND_NAMESPACE,
    "configKey": FAMILY_FUND_CONFIG_KEY,
    "configDesc": "家族基金",
    "modified": "",
}


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


def build_param_sheet_rows(*, config: dict[str, Any], meta: dict[str, str]) -> list[list[Any]]:
    rows: list[list[Any]] = [
        [TITLE, "", "", ""],
        ["区块", "参数键", "参数值", "说明"],
    ]
    meta_rows = [
        ("nameSpace", "MSE 命名空间（Application 私有）"),
        ("configKey", "配置键"),
        ("configDesc", "配置说明"),
        ("modified", "MSE 修改时间"),
        ("appKey", "MSE appKey（voga-mts-user）"),
    ]
    for key, desc in meta_rows:
        val = meta.get(key, "")
        if key == "appKey" and not val:
            val = FAMILY_FUND_APP_KEY
        rows.append(["元数据", key, val, desc])

    base_rows = [
        ("minContributionToRank", "上榜最低贡献值"),
        ("contributionDiamondUnit", "贡献钻石单位"),
        ("contributionPointsPerUnit", "每单位贡献分"),
        ("afterTopRankRatio", "Top30 外合格用户总分配比例"),
        ("familyWhiteList", "家族白名单 JSON"),
    ]
    for key, desc in base_rows:
        if key in config:
            rows.append(["基础", key, _sheet_cell(config[key]), desc])

    rows.append(["", "", "", ""])
    rows.append(["区块", "档位", "上周贡献下限", "说明"])
    for item in config.get("tiers") or []:
        rows.append(
            [
                "周档位",
                str(item.get("tierName") or ""),
                item.get("minLastWeekContribution"),
                "上周总贡献 ≥ 下限 → 本周为该档",
            ]
        )

    rows.append(["", "", "", ""])
    rows.append(["区块", "档位", "小档序号", "贡献阈值", "奖池钻石", "说明"])
    for tier_name, sub_list in (config.get("tierSubTiers") or {}).items():
        for idx, item in enumerate(sub_list or [], start=1):
            rows.append(
                [
                    "小档奖池",
                    str(tier_name),
                    idx,
                    item.get("thresholdContribution"),
                    item.get("bonusDiamond"),
                    "本周总贡献达阈值 → 奖池为该档钻石数",
                ]
            )

    rows.append(["", "", "", ""])
    rows.append(["区块", "区间下标", "名次区间", "总比例", "名次比例Map", "说明"])
    for bracket_idx, group in enumerate(config.get("rankPrizes") or []):
        rank_label = format_rank_range(group.get("startRank"), group.get("endRank"))
        ratio_map = group.get("rewardRatioMap")
        rows.append(
            [
                "rankPrizes",
                bracket_idx,
                rank_label,
                group.get("ratio"),
                _sheet_cell(ratio_map) if ratio_map else "",
                "成员应发 = 奖池 × 总比例 × 名次比例",
            ]
        )

    rows.append(["", "", "", ""])
    rows.append(["区块", "参数键", "参数值", "说明"])
    dispatch = config.get("diamondDispatchConfig") or {}
    for key, desc in (
        ("diamondDispatchConfig.activityId", "活动 ID"),
        ("diamondDispatchConfig.activityTaskId", "任务 ID"),
        ("diamondDispatchConfig.signKey", "签名 Key"),
    ):
        short = key.split(".", 1)[1]
        rows.append(["发钻", key, _sheet_cell(dispatch.get(short)), desc])

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
    meta_info = {**DEFAULT_META, **(meta or {}), "appKey": FAMILY_FUND_APP_KEY}
    if not meta_info.get("modified"):
        meta_info["modified"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000+00:00")

    param_rows = build_param_sheet_rows(config=config, meta=meta_info)
    parsed, parsed_meta = _parse_param_sheet(param_rows)
    original = fetch_family_fund_config()
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


def json_to_workbook(workbook_url_or_id: str, config: dict[str, Any], **kwargs: Any) -> str:
    return asyncio.run(json_to_workbook_async(workbook_url_or_id, config, **kwargs))


def main() -> int:
    parser = argparse.ArgumentParser(description="familyFundConfig JSON 写入钉钉参数表")
    parser.add_argument("workbook", help="钉钉表格 URL 或 nodeId")
    parser.add_argument("--json-file", help="configValue JSON 文件；默认 stdin")
    args = parser.parse_args()
    raw_text = Path(args.json_file).read_text(encoding="utf-8") if args.json_file else sys.stdin.read()
    config = json.loads(raw_text)
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
