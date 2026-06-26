#!/usr/bin/env python3
"""从 MSE 读取 familyPkConfig → 更新钉钉参数表 + configValue_JSON。"""

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
from mse_config_export import _fetch_mse_config  # noqa: E402
from mse_workbook_utils import fetch_workbook_sheets, fetch_workbook_sheets_async, format_rank_range, node_id  # noqa: E402

import httpx  # noqa: E402

PARAM_SHEET = "参数表"
JSON_SHEET = "configValue_JSON"

BASE_KEYS = {
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
}

DOTTED_BLOCKS = {
    "发钻": "diamondDispatchConfig.",
    "风控": "",
    "节流": "",
    "H5": "",
    "资源": "",
}


def _node_id(url_or_id: str) -> str:
    return node_id(url_or_id)


def _cell(row: list[Any], idx: int) -> str:
    if idx >= len(row) or row[idx] is None:
        return ""
    return str(row[idx]).strip()


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


def _get_dotted(config: dict[str, Any], dotted: str) -> Any:
    cur: Any = config
    for part in [p for p in dotted.split(".") if p]:
        if not isinstance(cur, dict):
            return ""
        cur = cur.get(part, "")
    return cur


def _fetch_sheets_sync(workbook_url: str) -> dict[str, list[list[Any]]]:
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


def _apply_mse_to_param_sheet(
    matrix: list[list[Any]], *, config: dict[str, Any], meta: dict[str, str]
) -> list[list[Any]]:
    out: list[list[Any]] = []
    bracket_gradients = config.get("bracketGradients") or []

    for row in matrix:
        new_row = list(row)
        block = _cell(row, 0)

        if block == "元数据":
            key = _cell(row, 1)
            if key == "modified" and meta.get("modified"):
                new_row[2] = meta["modified"]
            elif key in meta:
                new_row[2] = meta[key]
        elif block == "基础":
            key = _cell(row, 1)
            if key in BASE_KEYS and key in config:
                new_row[2] = _format_value(config[key])
        elif block == "档位":
            try:
                bracket_idx = int(_cell(row, 1))
                tier = int(float(_cell(row, 3)))
            except (TypeError, ValueError):
                out.append(new_row)
                continue
            if 0 <= bracket_idx < len(bracket_gradients):
                bracket = bracket_gradients[bracket_idx]
                rank_label = format_rank_range(bracket.get("rankStart"), bracket.get("rankEnd"))
                if rank_label:
                    new_row[2] = rank_label
                grads = bracket.get("gradients") or []
                if 1 <= tier <= len(grads):
                    item = grads[tier - 1]
                    new_row[4] = item.get("coefficient", new_row[4] if len(new_row) > 4 else "")
                    new_row[5] = item.get("bonusDiamond", new_row[5] if len(new_row) > 5 else "")
        elif block in DOTTED_BLOCKS:
            key = _cell(row, 1)
            if key:
                val = _get_dotted(config, key)
                if val != "" or key in config or "." in key:
                    new_row[2] = _format_value(val) if val != "" else ""

        out.append(new_row)
    return out


async def _write_sheet(
    *,
    token: str,
    operator: str,
    workbook_id: str,
    sheet_name: str,
    rows: list[list[Any]],
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

        cols = max(len(r) for r in rows) if rows else 1
        chunk = []
        for r in rows:
            padded = list(r) + [""] * (cols - len(r))
            chunk.append([_sheet_cell(c) for c in padded])
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


async def sync_mse_to_workbook_async(
    workbook_url_or_id: str,
    *,
    namespace: str = "voga-common",
    config_key: str = "familyPkConfig",
) -> str:
    workbook_id = _node_id(workbook_url_or_id)
    url = f"https://alidocs.dingtalk.com/i/nodes/{workbook_id}"

    fetched = _fetch_mse_config(namespace=namespace, config_key=config_key)
    config = fetched["configValue"]
    item = fetched["meta"]
    meta = {
        "nameSpace": str(item.get("nameSpace") or namespace),
        "configKey": str(item.get("configKey") or config_key),
        "configDesc": str(item.get("configDesc") or ""),
        "modified": str(item.get("modified") or ""),
    }

    sheets = await fetch_workbook_sheets_async(url)
    if PARAM_SHEET not in sheets:
        raise RuntimeError(f"缺少工作表「{PARAM_SHEET}」")

    param_rows = _apply_mse_to_param_sheet(sheets[PARAM_SHEET], config=config, meta=meta)
    json_rows = _json_sheet_rows(meta=meta, config=config)

    env = _excel_env()
    token, operator = await _get_token_and_operator(env)
    await _write_sheet(
        token=token,
        operator=operator,
        workbook_id=workbook_id,
        sheet_name=PARAM_SHEET,
        rows=param_rows,
    )
    await _write_sheet(
        token=token,
        operator=operator,
        workbook_id=workbook_id,
        sheet_name=JSON_SHEET,
        rows=json_rows,
    )
    return url


def sync_mse_to_workbook(workbook_url_or_id: str, **kwargs: Any) -> str:
    return asyncio.run(sync_mse_to_workbook_async(workbook_url_or_id, **kwargs))


def main() -> int:
    parser = argparse.ArgumentParser(description="MSE 配置同步到钉钉参数表")
    parser.add_argument("workbook", help="钉钉表格 URL 或 nodeId")
    parser.add_argument("--namespace", default="voga-common")
    parser.add_argument("--config-key", default="familyPkConfig")
    args = parser.parse_args()
    try:
        url = sync_mse_to_workbook(
            args.workbook.strip(),
            namespace=args.namespace.strip(),
            config_key=args.config_key.strip(),
        )
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1
    print(url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
