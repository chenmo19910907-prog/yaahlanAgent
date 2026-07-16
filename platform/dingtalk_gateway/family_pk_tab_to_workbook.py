#!/usr/bin/env python3
"""抓包 getFamilyPkPage 指定日期 tab → 家族/成员/手机号写入钉钉 Sheet2。"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
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
    DOC_API,
    _col_letter,
    _excel_env,
    _get_token_and_operator,
    rename_workbook_async,
)
from family_pk_calc_utils import family_pk_workbook_title  # noqa: E402
from family_pk_tunnel_capture import find_pk_page_capture, print_capture_user_prompt  # noqa: E402
from mse_sync_to_workbook import _sheet_cell  # noqa: E402
from mse_workbook_utils import node_id  # noqa: E402

import httpx  # noqa: E402

DEFAULT_WORKBOOK = "https://alidocs.dingtalk.com/i/nodes/N7dx2rn0JbZQqA9ACZ1MoaaRJMGjLRb3"
DEFAULT_SHEET = "家族PK列表"
HEADER = ["家族ID", "家族名称", "成员userId", "手机号", "是否族长"]


def _run_json(cmd: list[str]) -> Any:
    proc = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip()[-500:]
        raise RuntimeError(f"命令失败 {' '.join(cmd)}: {tail}")
    text = (proc.stdout or "").strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise RuntimeError(f"未解析到 JSON: {text[:300]}")
    return json.loads(text[start : end + 1])


def _normalize_pk_date(pk_date: str) -> str:
    from family_pk_tunnel_capture import normalize_pk_date

    return normalize_pk_date(pk_date)


def extract_families(pk_list: list[Any]) -> list[dict[str, str]]:
    families: dict[str, str] = {}
    for pair in pk_list:
        if not isinstance(pair, dict):
            continue
        for key in ("familyInfo", "opponentFamily"):
            info = pair.get(key)
            if not isinstance(info, dict):
                continue
            fid = str(info.get("familyId") or "").strip()
            if not fid.isdigit():
                continue
            name = str(info.get("name") or info.get("familyName") or "").strip()
            families[fid] = name
    return [
        {"familyId": fid, "familyName": families[fid]}
        for fid in sorted(families, key=lambda x: int(x))
    ]


def query_family_owner(family_id: str) -> str:
    body = _run_json(
        [
            sys.executable,
            str(REPO_ROOT / "Admin/admin_execute.py"),
            "--query-family",
            "--family-id",
            family_id,
        ]
    )
    items = body.get("items") if isinstance(body, dict) else None
    if not isinstance(items, list) or not items:
        raise RuntimeError(f"Admin 未查到家族 {family_id}")
    owner = str(items[0].get("familyOwnerId") or "").strip()
    return owner


def query_family_members(family_id: str) -> list[str]:
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "MOA/moa_execute.py"),
            "--payload-file",
            str(REPO_ROOT / "MOA/templates/家族-查询成员userId.json"),
            "--family-id",
            family_id,
            "--family-query-members",
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"MOA 查询家族成员失败 {family_id}: {(proc.stderr or proc.stdout)[-400:]}")
    text = proc.stdout
    start = text.find("{")
    end = text.rfind("}")
    body = json.loads(text[start : end + 1])
    ids = body.get("memberUserIds") if isinstance(body, dict) else None
    if not isinstance(ids, list):
        raise RuntimeError(f"MOA 成员列表格式异常 familyId={family_id}")
    return [str(x).strip() for x in ids if str(x).strip()]


def query_user_phone(user_id: str, cache: dict[str, str]) -> str:
    if user_id in cache:
        return cache[user_id]
    body = _run_json(
        [
            sys.executable,
            str(REPO_ROOT / "Admin/admin_execute.py"),
            "--query-user-id",
            user_id,
        ]
    )
    user = body.get("user") if isinstance(body.get("user"), dict) else body
    phone = ""
    if isinstance(user, dict):
        phone = str(user.get("phone") or "").strip()
    cache[user_id] = phone
    return phone


def build_rows(*, families: list[dict[str, str]]) -> list[list[str]]:
    phone_cache: dict[str, str] = {}
    rows: list[list[str]] = [HEADER]
    for fam in families:
        fid = fam["familyId"]
        fname = fam["familyName"]
        owner_id = query_family_owner(fid)
        member_ids = query_family_members(fid)
        if owner_id and owner_id not in member_ids:
            member_ids = [owner_id] + member_ids
        for uid in member_ids:
            phone = query_user_phone(uid, phone_cache)
            is_owner = "是" if uid == owner_id else ""
            rows.append([fid, fname, uid, phone, is_owner])
    return rows


def _string_rows(rows: list[list[Any]]) -> list[list[str]]:
    cols = max(len(r) for r in rows) if rows else 1
    out: list[list[str]] = []
    for row in rows:
        padded = list(row) + [""] * (cols - len(row))
        out.append([_sheet_cell(c) for c in padded])
    return out


async def _ensure_sheet(
    *,
    token: str,
    operator: str,
    workbook_id: str,
    sheet_name: str,
    client: httpx.AsyncClient,
) -> None:
    sheets_url = f"{DOC_API}/workbooks/{workbook_id}/sheets?operatorId={operator}"
    resp = await client.get(sheets_url, headers={"x-acs-dingtalk-access-token": token})
    resp.raise_for_status()
    names = {str(item.get("name") or "") for item in resp.json().get("value", [])}
    if sheet_name in names:
        return
    create_resp = await client.post(
        sheets_url,
        headers={"x-acs-dingtalk-access-token": token, "Content-Type": "application/json"},
        json={"name": sheet_name},
    )
    if create_resp.status_code >= 400:
        raise RuntimeError(
            f"创建工作表 {sheet_name} 失败 HTTP {create_resp.status_code}: {create_resp.text[:300]}"
        )


DEFAULT_WORKBOOK_SHEET = "Sheet1"


async def _delete_sheet(
    *,
    token: str,
    operator: str,
    workbook_id: str,
    sheet_name: str,
    client: httpx.AsyncClient,
) -> bool:
    """删除工作表；不存在时返回 False。"""
    sheets_url = f"{DOC_API}/workbooks/{workbook_id}/sheets?operatorId={operator}"
    resp = await client.get(sheets_url, headers={"x-acs-dingtalk-access-token": token})
    resp.raise_for_status()
    for item in resp.json().get("value", []):
        if str(item.get("name") or "") != sheet_name:
            continue
        sheet_ref = str(item.get("id") or sheet_name)
        delete_url = (
            f"{DOC_API}/workbooks/{workbook_id}/sheets/{sheet_ref}?operatorId={operator}"
        )
        del_resp = await client.delete(
            delete_url,
            headers={"x-acs-dingtalk-access-token": token},
        )
        if del_resp.status_code >= 400:
            raise RuntimeError(
                f"删除工作表 {sheet_name} 失败 HTTP {del_resp.status_code}: {del_resp.text[:300]}"
            )
        return True
    return False


async def _write_sheet_replace(
    *,
    token: str,
    operator: str,
    workbook_id: str,
    sheet_name: str,
    rows: list[list[str]],
) -> None:
    """覆盖写入并清空旧的多余列/行（避免缩列后残留 PK日期、抓包账号 等）。"""
    if not rows:
        raise ValueError("表格为空")
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

        info_url = (
            f"{DOC_API}/workbooks/{workbook_id}/sheets/{sheet_id}"
            f"?select=rowCount,columnCount&operatorId={operator}"
        )
        info_resp = await client.get(info_url, headers={"x-acs-dingtalk-access-token": token})
        info_resp.raise_for_status()
        info = info_resp.json()
        old_row_count = int(info.get("rowCount") or 0)
        old_col_count = int(info.get("columnCount") or 0)

        cols = max(len(r) for r in rows)
        end_row = len(rows)
        chunk = [list(r) + [""] * (cols - len(r)) for r in rows]
        chunk = [[_sheet_cell(c) for c in r] for r in chunk]
        range_str = f"A1:{_col_letter(cols)}{end_row}"
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
            json={"values": chunk, "wordWrap": "autoWrap"},
        )
        if wr.status_code >= 400:
            raise RuntimeError(f"写入 {sheet_name} 失败 HTTP {wr.status_code}: {wr.text[:300]}")

        clear_to_row = max(end_row, old_row_count)
        clear_from_col = cols + 1
        clear_to_col = max(old_col_count, cols + 2)
        if clear_to_row >= 1 and clear_from_col <= clear_to_col:
            blank_cols = clear_to_col - clear_from_col + 1
            blank = [[""] * blank_cols for _ in range(clear_to_row)]
            clear_range = (
                f"{_col_letter(clear_from_col)}1:"
                f"{_col_letter(clear_to_col)}{clear_to_row}"
            )
            clear_url = (
                f"{DOC_API}/workbooks/{workbook_id}/sheets/{sheet_id}"
                f"/ranges/{clear_range}?operatorId={operator}"
            )
            cr = await client.put(
                clear_url,
                headers={
                    "x-acs-dingtalk-access-token": token,
                    "Content-Type": "application/json",
                },
                json={"values": blank},
            )
            if cr.status_code >= 400:
                raise RuntimeError(
                    f"清空 {sheet_name} 多余列失败 HTTP {cr.status_code}: {cr.text[:300]}"
                )

        if old_row_count > end_row:
            tail_rows = old_row_count - end_row
            tail_cols = max(cols, old_col_count)
            blank = [[""] * tail_cols for _ in range(tail_rows)]
            tail_range = (
                f"A{end_row + 1}:{_col_letter(tail_cols)}{old_row_count}"
            )
            tail_url = (
                f"{DOC_API}/workbooks/{workbook_id}/sheets/{sheet_id}"
                f"/ranges/{tail_range}?operatorId={operator}"
            )
            tr = await client.put(
                tail_url,
                headers={
                    "x-acs-dingtalk-access-token": token,
                    "Content-Type": "application/json",
                },
                json={"values": blank},
            )
            if tr.status_code >= 400:
                raise RuntimeError(
                    f"清空 {sheet_name} 多余行失败 HTTP {tr.status_code}: {tr.text[:300]}"
                )


async def write_family_list_async(
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
        rows=_string_rows(rows),
    )
    return url


def export_pk_tab_to_workbook(
    *,
    workbook: str,
    momoid: str,
    pk_date: str,
    since: int = 259200,
    wait_seconds: int = 180,
    poll_interval_ms: int = 3000,
    sheet_name: str = DEFAULT_SHEET,
) -> dict[str, Any]:
    pk_date = _normalize_pk_date(pk_date)
    if wait_seconds > 0:
        print_capture_user_prompt(
            momoid=momoid,
            pk_date=pk_date,
            wait_seconds=wait_seconds,
            reason="prepare",
        )
    capture = find_pk_page_capture(
        momoid=momoid,
        pk_date=pk_date,
        since=since,
        wait_seconds=wait_seconds,
        poll_interval_ms=poll_interval_ms,
        announce_wait=False,
    )
    data = (capture.get("response") or {}).get("data") or {}
    families = extract_families(data.get("pkList") or [])
    if not families:
        raise RuntimeError(f"抓包 pkList 为空: capture={capture.get('_id')}")

    rows = build_rows(families=families)
    workbook_id = node_id(workbook)

    async def _write_and_rename() -> str:
        doc_url = await write_family_list_async(workbook, rows, sheet_name=sheet_name)
        await rename_workbook_async(workbook_id, family_pk_workbook_title(pk_date))
        return doc_url

    doc_url = asyncio.run(_write_and_rename())
    member_rows = max(len(rows) - 1, 0)
    return {
        "workbookUrl": doc_url,
        "workbookTitle": family_pk_workbook_title(pk_date),
        "sheetName": sheet_name,
        "momoid": momoid,
        "pkDate": pk_date,
        "familyCount": len(families),
        "memberRowCount": member_rows,
        "captureId": capture.get("_id"),
        "captureTime": capture.get("time"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="家族PK列表 tab 抓包 → 钉钉 Sheet2")
    parser.add_argument("workbook", nargs="?", default=DEFAULT_WORKBOOK, help="钉钉表格 URL/nodeId")
    parser.add_argument("--momoid", default="100486375", help="MOA 请求账号 userId")
    parser.add_argument("--pk-date", default="2026-07-02", help="PK 日期 yyyy-MM-dd")
    parser.add_argument("--since", type=int, default=259200, help="Tunnel 回溯秒数")
    parser.add_argument(
        "--wait",
        type=int,
        default=180,
        dest="wait_seconds",
        help="未命中时最长等待秒数（0=立即失败；默认等待用户在 App 刷新 PK 页）",
    )
    parser.add_argument(
        "--poll-ms",
        type=int,
        default=3000,
        dest="poll_interval_ms",
        help="抓包等待轮询间隔毫秒",
    )
    parser.add_argument("--sheet-name", default=DEFAULT_SHEET, help="目标工作表名")
    args = parser.parse_args()
    try:
        summary = export_pk_tab_to_workbook(
            workbook=args.workbook.strip(),
            momoid=str(args.momoid).strip(),
            pk_date=args.pk_date.strip(),
            since=args.since,
            wait_seconds=args.wait_seconds,
            poll_interval_ms=args.poll_interval_ms,
            sheet_name=args.sheet_name.strip() or DEFAULT_SHEET,
        )
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
