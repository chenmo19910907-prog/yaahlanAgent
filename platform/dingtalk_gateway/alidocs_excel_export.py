"""CSV → 钉钉在线表格（创建 WORKBOOK + 写入数据，复用 Excel MCP 凭证）。"""

from __future__ import annotations

import csv
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

import httpx

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "scripts"))

from mcp_paths import load_mcp_env  # noqa: E402

DOC_API = "https://api.dingtalk.com/v1.0/doc"
TOKEN_API = "http://gaia-hg.momo.com/ding/excel/token"
ALIDOCS_NODE = "https://alidocs.dingtalk.com/i/nodes/{node_id}"
BATCH_ROWS = 100

_dentry_cache: dict[str, str] = {}


def _excel_env() -> dict[str, str]:
    for key in ("dingtalk-excel-write", "user-dingtalk-excel-write", "dingtalk-excel-read"):
        env = load_mcp_env(key)
        if env.get("DINGTALK_AEGIS_KEY"):
            return env
    raise RuntimeError(
        "缺少钉钉 Excel 凭证：请在 .cursor/.mcp.secrets.json 配置 "
        "dingtalk-excel-write 的 DINGTALK_AEGIS_KEY/SECRET/WORKID"
    )


async def _get_token_and_operator(env: dict[str, str]) -> tuple[str, str]:
    url = (
        f"{TOKEN_API}?aegisKey={env['DINGTALK_AEGIS_KEY']}"
        f"&aegisSecret={env['DINGTALK_AEGIS_SECRET']}&workid={env['DINGTALK_WORKID']}"
    )
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()
    if data.get("ec") != 200:
        raise RuntimeError(f"获取 Excel token 失败: {data}")
    token = data["data"]["token"]
    operator = data["data"]["operatorId"]
    return token, operator


def _get_workspace_id(parent_node_id: str, cookie: str) -> str:
    if parent_node_id in _dentry_cache:
        return _dentry_cache[parent_node_id]
    from mcp_paths import resolve_dingtalk_cookie
    import re

    ck = cookie or resolve_dingtalk_cookie()
    xsrf = re.search(r"XSRF-TOKEN=([^;]+)", ck)
    headers = {
        "cookie": ck,
        "referer": f"https://alidocs.dingtalk.com/i/nodes/{parent_node_id}",
        "user-agent": "Mozilla/5.0",
    }
    if xsrf:
        headers["x-xsrf-token"] = xsrf.group(1)
    url = (
        f"https://alidocs.dingtalk.com/box/api/v2/dentry/info"
        f"?dentryUuid={parent_node_id}&withParent=true"
    )
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    space_id = str(data["data"]["spaceId"])
    _dentry_cache[parent_node_id] = space_id
    return space_id


def _col_letter(n: int) -> str:
    s = ""
    while n:
        n, rem = divmod(n - 1, 26)
        s = chr(65 + rem) + s
    return s


async def _create_workbook(
    *,
    token: str,
    operator: str,
    workspace_id: str,
    parent_node_id: str,
    name: str,
) -> str:
    payload = {
        "name": name,
        "docType": "WORKBOOK",
        "operatorId": operator,
        "parentNodeId": parent_node_id,
    }
    url = f"{DOC_API}/workspaces/{workspace_id}/docs"
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            url,
            headers={"x-acs-dingtalk-access-token": token},
            json=payload,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"创建表格失败 HTTP {resp.status_code}: {resp.text[:500]}")
        data = resp.json()
    node_id = str(data.get("dentryUuid") or data.get("nodeId") or "")
    if not node_id:
        raise RuntimeError(f"创建表格未返回 nodeId: {data}")
    return node_id


async def _write_rows(
    *,
    token: str,
    operator: str,
    workbook_id: str,
    rows: list[list[str]],
) -> None:
    if not rows:
        raise ValueError("CSV 为空")
    async with httpx.AsyncClient(timeout=120) as client:
        sheets_url = f"{DOC_API}/workbooks/{workbook_id}/sheets?operatorId={operator}"
        resp = await client.get(
            sheets_url,
            headers={"x-acs-dingtalk-access-token": token},
        )
        resp.raise_for_status()
        sheets = resp.json().get("value", [])
        if not sheets:
            raise RuntimeError("工作簿无工作表")
        sheet_id = sheets[0]["id"]
        cols = max(len(r) for r in rows)
        for start in range(0, len(rows), BATCH_ROWS):
            chunk = rows[start : start + BATCH_ROWS]
            # 补齐列数
            chunk = [r + [""] * (cols - len(r)) for r in chunk]
            start_row = start + 1
            end_row = start_row + len(chunk) - 1
            range_str = f"A{start_row}:{_col_letter(cols)}{end_row}"
            write_url = (
                f"{DOC_API}/workbooks/{workbook_id}/sheets/{sheet_id}"
                f"/ranges/{range_str}?operatorId={operator}"
            )
            wr = await client.put(
                write_url,
                headers={
                    "x-acs-dingtalk-access-token": token,
                    "Content-Type": "application/json",
                },
                json={"values": chunk},
            )
            if wr.status_code >= 400:
                raise RuntimeError(
                    f"写入 {range_str} 失败 HTTP {wr.status_code}: {wr.text[:300]}"
                )


def _read_csv(path: Path) -> list[list[str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.reader(f))


async def export_rows_to_folder_async(
    rows: list[list[str]],
    *,
    parent_node_id: str,
    workbook_name: str,
) -> str:
    if not rows:
        raise ValueError("用例表格为空")
    env = _excel_env()
    token, operator = await _get_token_and_operator(env)
    workspace_id = _get_workspace_id(parent_node_id, "")
    workbook_id = await _create_workbook(
        token=token,
        operator=operator,
        workspace_id=workspace_id,
        parent_node_id=parent_node_id,
        name=workbook_name,
    )
    await _write_rows(token=token, operator=operator, workbook_id=workbook_id, rows=rows)
    return ALIDOCS_NODE.format(node_id=workbook_id)


def export_rows_to_folder(
    rows: list[list[str]],
    *,
    parent_node_id: str,
    workbook_name: str,
) -> str:
    import asyncio

    return asyncio.run(
        export_rows_to_folder_async(
            rows,
            parent_node_id=parent_node_id,
            workbook_name=workbook_name,
        )
    )


async def export_csv_to_folder_async(
    csv_path: Path | str,
    *,
    parent_node_id: str,
    workbook_name: str | None = None,
) -> str:
    path = Path(csv_path)
    rows = _read_csv(path)
    env = _excel_env()
    token, operator = await _get_token_and_operator(env)
    workspace_id = _get_workspace_id(parent_node_id, "")
    name = workbook_name or path.stem
    workbook_id = await _create_workbook(
        token=token,
        operator=operator,
        workspace_id=workspace_id,
        parent_node_id=parent_node_id,
        name=name,
    )
    await _write_rows(token=token, operator=operator, workbook_id=workbook_id, rows=rows)
    return ALIDOCS_NODE.format(node_id=workbook_id)


def export_csv_to_folder(
    csv_path: Path | str,
    *,
    parent_node_id: str,
    workbook_name: str | None = None,
) -> str:
    import asyncio

    return asyncio.run(
        export_csv_to_folder_async(
            csv_path,
            parent_node_id=parent_node_id,
            workbook_name=workbook_name,
        )
    )
