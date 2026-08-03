"""钉钉参数表读写与名次区间格式化（familyPkConfig）。"""

from __future__ import annotations

import asyncio
import copy
import re
from typing import Any

import httpx

from alidocs_excel_export import DOC_API, _col_letter, _excel_env, _get_token_and_operator

NODE_ID_RE = re.compile(r"/i/nodes/([^?/#]+)")


def node_id(url_or_id: str) -> str:
    text = (url_or_id or "").strip()
    match = NODE_ID_RE.search(text)
    return match.group(1) if match else text


def format_rank_range(rank_start: Any, rank_end: Any) -> str:
    try:
        start = int(rank_start)
    except (TypeError, ValueError):
        return ""
    if rank_end is None or str(rank_end).strip() in {"", "null", "None", "none"}:
        return f"TOP{start}~未上榜"
    try:
        end = int(rank_end)
    except (TypeError, ValueError):
        return f"TOP{start}~未上榜"
    if start == end:
        return f"TOP{start}"
    return f"TOP{start}~{end}"


def parse_rank_range(label: str) -> tuple[int | None, int | None]:
    text = (label or "").strip()
    if not text:
        return None, None
    upper = text.upper()
    if upper.endswith("~未上榜") or upper.endswith("+"):
        match = re.match(r"TOP(\d+)", upper, re.I)
        return (int(match.group(1)), None) if match else (None, None)
    match = re.match(r"TOP(\d+)~(\d+)", upper, re.I)
    if match:
        return int(match.group(1)), int(match.group(2))
    match = re.match(r"TOP(\d+)", upper, re.I)
    if match:
        value = int(match.group(1))
        return value, value
    return None, None


def _filter_empty_rows(values: list[list[Any]]) -> list[list[Any]]:
    filtered: list[list[Any]] = []
    for row in values:
        if not isinstance(row, list):
            if row is not None and str(row).strip():
                filtered.append([row])
            continue
        if any(cell is not None and str(cell).strip() for cell in row):
            filtered.append(row)
    return filtered


async def _fetch_sheet_matrix_async(
    *,
    workbook_id: str,
    sheet_name: str,
    token: str,
    operator: str,
    client: httpx.AsyncClient,
) -> list[list[Any]]:
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

    info_url = (
        f"{DOC_API}/workbooks/{workbook_id}/sheets/{sheet_id}"
        f"?select=values&operatorId={operator}"
    )
    info_resp = await client.get(info_url, headers={"x-acs-dingtalk-access-token": token})
    info_resp.raise_for_status()
    info = info_resp.json()
    row_count = int(info.get("rowCount") or 200)
    col_count = int(info.get("columnCount") or 10)
    end_col = _col_letter(col_count)
    range_url = (
        f"{DOC_API}/workbooks/{workbook_id}/sheets/{sheet_id}"
        f"/ranges/A1:{end_col}{row_count}?operatorId={operator}"
    )
    range_resp = await client.get(range_url, headers={"x-acs-dingtalk-access-token": token})
    range_resp.raise_for_status()
    return _filter_empty_rows(range_resp.json().get("values") or [])


async def fetch_workbook_sheets_async(workbook_url_or_id: str) -> dict[str, list[list[Any]]]:
    workbook_id = node_id(workbook_url_or_id)
    env = _excel_env()
    token, operator = await _get_token_and_operator(env)
    async with httpx.AsyncClient(timeout=120) as client:
        sheets_url = f"{DOC_API}/workbooks/{workbook_id}/sheets?operatorId={operator}"
        resp = await client.get(sheets_url, headers={"x-acs-dingtalk-access-token": token})
        resp.raise_for_status()
        names = [str(item.get("name") or "") for item in resp.json().get("value", []) if item.get("name")]
        result: dict[str, list[list[Any]]] = {}
        for name in names:
            result[name] = await _fetch_sheet_matrix_async(
                workbook_id=workbook_id,
                sheet_name=name,
                token=token,
                operator=operator,
                client=client,
            )
        return result


def fetch_workbook_sheets(workbook_url_or_id: str) -> dict[str, list[list[Any]]]:
    return asyncio.run(fetch_workbook_sheets_async(workbook_url_or_id))


def _coerce_like(new: Any, old: Any) -> Any:
    if isinstance(old, bool):
        return bool(new) if not isinstance(new, str) else new.lower() == "true"
    if isinstance(old, int) and not isinstance(old, bool):
        return int(float(new))
    if isinstance(old, float):
        return float(new)
    if isinstance(old, str):
        return str(new)
    if isinstance(old, list):
        return new
    if isinstance(old, dict):
        return new
    return new


def _merge_bracket_item(original_item: dict[str, Any], parsed_item: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(original_item)
    for key in original_item:
        if key == "gradients":
            merged[key] = copy.deepcopy(parsed_item.get(key) or [])
            continue
        if key in parsed_item:
            merged[key] = parsed_item[key]
    for key, value in parsed_item.items():
        if key not in merged:
            merged[key] = value
    # 保持 MSE 原始字段顺序
    ordered: dict[str, Any] = {}
    for key in original_item:
        if key in merged:
            ordered[key] = merged[key]
    for key, value in merged.items():
        if key not in ordered:
            ordered[key] = value
    return ordered


def apply_parsed_values_to_original(original: dict[str, Any], parsed: dict[str, Any]) -> dict[str, Any]:
    """将参数表解析结果写回 MSE 原始 JSON 结构，仅更新已有字段数值。"""
    out = copy.deepcopy(original)
    for key, orig_val in original.items():
        if key not in parsed:
            continue
        par_val = parsed[key]
        if key == "bracketGradients":
            orig_list = orig_val if isinstance(orig_val, list) else []
            par_list = par_val if isinstance(par_val, list) else []
            merged_list: list[dict[str, Any]] = []
            for idx, par_item in enumerate(par_list):
                template = orig_list[idx] if idx < len(orig_list) else orig_list[-1]
                merged_list.append(_merge_bracket_item(template, par_item))
            out[key] = merged_list
            continue
        if key == "diamondDispatchConfig" and isinstance(orig_val, dict) and isinstance(par_val, dict):
            merged = copy.deepcopy(orig_val)
            for dk, dv in orig_val.items():
                if dk in par_val:
                    merged[dk] = _coerce_like(par_val[dk], dv)
            out[key] = merged
            continue
        out[key] = _coerce_like(par_val, orig_val)
    return out


def find_param_sheet_name(sheets: dict[str, list[list[Any]]]) -> str:
    if "参数表" in sheets:
        return "参数表"
    for name in sheets:
        if name != "configValue_JSON":
            return name
    raise RuntimeError("未找到参数表工作表")


def resolve_param_sheet_name(
    sheets: dict[str, list[list[Any]]],
    preferred: str | None = None,
) -> str:
    if preferred:
        pref = preferred.strip()
        if pref in sheets:
            return pref
        raise RuntimeError(f"未找到工作表: {pref}")
    return find_param_sheet_name(sheets)


def _cell_str(row: list[Any], idx: int) -> str:
    if idx >= len(row) or row[idx] is None:
        return ""
    return str(row[idx]).strip()


def param_row_key(row: list[Any]) -> tuple[str, ...] | None:
    block = _cell_str(row, 0)
    if not block or block == "区块" or block.startswith("家族PK服务配置"):
        return None
    if block == "档位":
        bracket = _cell_str(row, 1)
        tier = _cell_str(row, 3)
        if bracket and tier:
            return (block, bracket, tier)
        return None
    key = _cell_str(row, 1)
    if block in {"元数据", "基础", "发钻", "风控", "节流", "H5", "资源"} and key:
        return (block, key)
    return None


def looks_like_param_sheet(matrix: list[list[Any]]) -> bool:
    if not matrix:
        return False
    for row in matrix[:6]:
        text = " ".join(_cell_str(row, i) for i in range(min(4, len(row))))
        if "参数键" in text or "参数值" in text:
            return True
        if _cell_str(row, 0) == "区块":
            return True
    return False


def reconcile_param_sheet_rows(
    existing: list[list[Any]] | None,
    fresh: list[list[Any]],
    *,
    applied: list[list[Any]],
) -> list[list[Any]]:
    """在已有参数表上合并 MSE 最新结构：更新数值、增删参数行，保留表头与说明列。"""
    if not existing or not looks_like_param_sheet(existing):
        return fresh

    applied_by_key: dict[tuple[str, ...], list[Any]] = {}
    for row in applied:
        key = param_row_key(row)
        if key:
            applied_by_key[key] = row

    out: list[list[Any]] = []
    for row in fresh:
        key = param_row_key(row)
        if key is None:
            out.append(list(row))
            continue
        if key in applied_by_key:
            merged = list(applied_by_key[key])
            cols = max(len(merged), len(row))
            for idx in range(cols):
                if idx < 2:
                    merged[idx] = row[idx] if idx < len(row) else merged[idx]
                elif idx == 2 and idx < len(row):
                    merged[idx] = row[idx]
                elif idx in {4, 5} and idx < len(row):
                    merged[idx] = row[idx]
            out.append(merged)
        else:
            out.append(list(row))
    return out
