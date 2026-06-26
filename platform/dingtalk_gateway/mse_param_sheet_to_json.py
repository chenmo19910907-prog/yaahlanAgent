#!/usr/bin/env python3
"""从钉钉参数表 Sheet 生成 familyPkConfig JSON，并写回 configValue_JSON Sheet。"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
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

from alidocs_excel_export import DOC_API, _col_letter, _excel_env, _get_token_and_operator  # noqa: E402
from mse_workbook_utils import (  # noqa: E402
    apply_parsed_values_to_original,
    fetch_workbook_sheets_async,
    find_param_sheet_name,
    node_id,
    parse_rank_range,
)
from mse_config_export import _fetch_mse_config  # noqa: E402

import httpx  # noqa: E402

PARAM_SHEET = "参数表"
JSON_SHEET = "configValue_JSON"


def _node_id(url_or_id: str) -> str:
    return node_id(url_or_id)


def _cell(row: list[Any], idx: int) -> str:
    if idx >= len(row) or row[idx] is None:
        return ""
    return str(row[idx]).strip()


def _parse_value(raw: str) -> Any:
    text = (raw or "").strip()
    if text == "":
        return ""
    if text.lower() in {"true", "false"}:
        return text.lower() == "true"
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    if re.fullmatch(r"-?\d+\.\d+", text):
        return float(text)
    return text


def _set_dotted(config: dict[str, Any], dotted: str, value: Any) -> None:
    parts = [p for p in dotted.split(".") if p]
    if not parts:
        return
    cur: dict[str, Any] = config
    for key in parts[:-1]:
        nxt = cur.get(key)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[key] = nxt
        cur = nxt
    cur[parts[-1]] = value


def _parse_param_sheet(matrix: list[list[Any]]) -> tuple[dict[str, Any], dict[str, str]]:
    meta: dict[str, str] = {}
    config: dict[str, Any] = {
        "eventGiftProductIds": [],
        "familyWhiteList": [],
        "bracketGradients": [{"gradients": []} for _ in range(6)],
    }
    base_keys = {
        "enabled",
        "pkStartHour",
        "pkEndHour",
        "basePoolDiamond",
        "minWinPk",
        "minRewardPk",
        "minListPk",
        "minBracketDailyAvg",
        "eventGiftProductIds",
        "familyWhiteList",
        "rewardRiskRuleId",
        "maxRewardDiamondPerUser",
        "groupBarThrottleSec",
        "roomBroadcastThrottleSec",
        "activityH5Path",
        "bannerImageUrl",
        "groupStartImageUrl",
        "familyPkBgImg",
        "familyPkIcon",
        "familyPkVsIcon",
    }

    for row in matrix:
        block = _cell(row, 0)
        if block == "元数据":
            key = _cell(row, 1)
            val = _cell(row, 2)
            if key:
                meta[key] = val
            continue
        if block == "基础":
            key = _cell(row, 1)
            if key in base_keys:
                config[key] = _parse_value(_cell(row, 2))
            continue
        if block == "档位":
            try:
                bracket_idx = int(_cell(row, 1))
                coeff = float(_cell(row, 4))
                diamond = int(float(_cell(row, 5)))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"档位行解析失败: {row}") from exc
            if bracket_idx < 0 or bracket_idx >= len(config["bracketGradients"]):
                raise ValueError(f"区间下标越界: {bracket_idx}")
            bracket = config["bracketGradients"][bracket_idx]
            rank_label = _cell(row, 2)
            if rank_label:
                rank_start, rank_end = parse_rank_range(rank_label)
                if rank_start is not None:
                    bracket["rankStart"] = rank_start
                if rank_end is not None:
                    bracket["rankEnd"] = rank_end
                else:
                    bracket.pop("rankEnd", None)
            bracket["gradients"].append(
                {"coefficient": coeff, "bonusDiamond": diamond}
            )
            continue
        if block in {"发钻", "风控", "节流", "H5", "资源"}:
            key = _cell(row, 1)
            if key:
                _set_dotted(config, key, _parse_value(_cell(row, 2)))

    for bracket in config["bracketGradients"]:
        grads = bracket.get("gradients") or []
        if len(grads) != 4:
            raise ValueError(f"每个区间应有 4 个档位，当前为 {len(grads)} 个: {grads}")

    if "diamondDispatchConfig" not in config:
        config["diamondDispatchConfig"] = {
            "activityId": "",
            "activityTaskId": "",
            "signKey": "",
        }
    return config, meta


def _fetch_sheets_sync(workbook_url: str) -> dict[str, list[list[Any]]]:
    from mse_workbook_utils import fetch_workbook_sheets

    return fetch_workbook_sheets(workbook_url)


def _json_sheet_rows(*, meta: dict[str, str], config: dict[str, Any]) -> list[list[str]]:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000+00:00")
    rows: list[list[str]] = [["字段", "内容"]]
    rows.append(["生成时间", now])
    for key in ("nameSpace", "configKey", "configDesc", "modified"):
        if meta.get(key):
            rows.append([key, meta[key]])
    rows.append(["configValue", json.dumps(config, ensure_ascii=False, indent=2)])
    return rows


async def _write_sheet(
    *,
    token: str,
    operator: str,
    workbook_id: str,
    sheet_name: str,
    rows: list[list[str]],
) -> None:
    async with httpx.AsyncClient(timeout=120) as client:
        sheets_url = f"{DOC_API}/workbooks/{workbook_id}/sheets?operatorId={operator}"
        resp = await client.get(sheets_url, headers={"x-acs-dingtalk-access-token": token})
        resp.raise_for_status()
        sheet_id = None
        for item in resp.json().get("value", []):
            if str(item.get("name") or "") == sheet_name:
                sheet_id = str(item.get("id") or "")
                break
        if not sheet_id:
            raise RuntimeError(f"未找到工作表: {sheet_name}")

        cols = max(len(r) for r in rows)
        chunk = [r + [""] * (cols - len(r)) for r in rows]
        end_row = len(chunk)
        range_str = f"A1:{_col_letter(cols)}{end_row}"
        write_url = (
            f"{DOC_API}/workbooks/{workbook_id}/sheets/{sheet_id}"
            f"/ranges/{range_str}?operatorId={operator}"
        )
        payload = {"values": chunk, "wordWrap": "autoWrap"}
        wr = await client.put(
            write_url,
            headers={
                "x-acs-dingtalk-access-token": token,
                "Content-Type": "application/json",
            },
            json=payload,
        )
        if wr.status_code >= 400:
            raise RuntimeError(f"写入 {sheet_name} 失败 HTTP {wr.status_code}: {wr.text[:300]}")


async def generate_json_async(
    workbook_url_or_id: str,
    *,
    namespace: str = "voga-common",
    config_key: str = "familyPkConfig",
) -> tuple[str, dict[str, Any]]:
    workbook_id = _node_id(workbook_url_or_id)
    url = f"https://alidocs.dingtalk.com/i/nodes/{workbook_id}"
    sheets = await fetch_workbook_sheets_async(url)
    param_sheet = find_param_sheet_name(sheets)
    parsed, meta = _parse_param_sheet(sheets[param_sheet])
    original = _fetch_mse_config(namespace=namespace, config_key=config_key)["configValue"]
    config = apply_parsed_values_to_original(original, parsed)
    mse_meta = _fetch_mse_config(namespace=namespace, config_key=config_key)["meta"]
    meta.setdefault("nameSpace", str(mse_meta.get("nameSpace") or namespace))
    meta.setdefault("configKey", str(mse_meta.get("configKey") or config_key))
    meta.setdefault("configDesc", str(mse_meta.get("configDesc") or ""))
    if mse_meta.get("modified"):
        meta["modified"] = str(mse_meta["modified"])
    rows = _json_sheet_rows(meta=meta, config=config)

    env = _excel_env()
    token, operator = await _get_token_and_operator(env)
    await _write_sheet(
        token=token,
        operator=operator,
        workbook_id=workbook_id,
        sheet_name=JSON_SHEET,
        rows=rows,
    )
    return url, config


def generate_json(workbook_url_or_id: str) -> tuple[str, dict[str, Any]]:
    return asyncio.run(generate_json_async(workbook_url_or_id))


def main() -> int:
    parser = argparse.ArgumentParser(description="参数表 → configValue JSON 并写回钉钉表格")
    parser.add_argument("workbook", help="钉钉表格 URL 或 nodeId")
    parser.add_argument("--stdout-json", action="store_true", help="额外打印 configValue JSON")
    args = parser.parse_args()
    try:
        doc_url, config = generate_json(args.workbook.strip())
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1
    print(doc_url)
    if args.stdout_json:
        print(json.dumps(config, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
