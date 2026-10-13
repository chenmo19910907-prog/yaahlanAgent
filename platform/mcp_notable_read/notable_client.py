"""钉钉 AI 表格（Notable / .able）读取：Open API + alidocs Cookie 绕过。"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEDULE_REGISTRY = REPO_ROOT / "documents" / "schedule_links.json"
NODE_ID_RE = re.compile(r"/i/nodes/([^?/#]+)")
MAINSITE_SCRIPT_RE = re.compile(
    r'<script[^>]*id="mainsite_server_content"[^>]*>([\s\S]*?)</script>',
    re.IGNORECASE,
)
TOKEN_API_URL = "http://gaia-hg.momo.com/ding/excel/token"
ALIDOCS_DOCUMENT_DATA = "https://alidocs.dingtalk.com/api/document/data"
NOTABLE_LIST_URL = (
    "https://api.dingtalk.com/v1.0/notable/bases/{doc_key}/sheets/{sheet_id}/records/list"
)
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
)


def _load_mcp_env(server_key: str) -> dict[str, str]:
    for rel in (".cursor/.mcp.secrets.json", ".cursor/mcp.json"):
        path = REPO_ROOT / rel
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        srv = (data.get("mcpServers") or {}).get(server_key) or {}
        env = srv.get("env") or {}
        if isinstance(env, dict) and env:
            return {str(k): str(v) for k, v in env.items()}
    return {}


def load_dingtalk_cookie() -> str:
    cookie_file = Path.home() / ".dingtalk_doc_cookie"
    if cookie_file.is_file():
        cookie = cookie_file.read_text(encoding="utf-8").strip()
        if cookie:
            return cookie
    cookie = (os.environ.get("DINGTALK_COOKIE") or "").strip()
    if cookie:
        return cookie
    for key in ("dingtalk-notable-read", "dingtalk-doc", "user-dingtalk-doc"):
        cookie = _load_mcp_env(key).get("DINGTALK_COOKIE", "").strip()
        if cookie:
            return cookie
    raise RuntimeError(
        "缺少 DINGTALK_COOKIE（dingtalk-doc refresh_cookie 或 .cursor/.mcp.secrets.json）"
    )


def load_aegis_credentials() -> tuple[str, str, str]:
    env = {**_load_mcp_env("dingtalk-excel-read"), **os.environ}
    key = str(env.get("DINGTALK_AEGIS_KEY") or "").strip()
    secret = str(env.get("DINGTALK_AEGIS_SECRET") or "").strip()
    workid = str(env.get("DINGTALK_WORKID") or "").strip()
    if not key or not secret or not workid:
        raise RuntimeError(
            "缺少 DINGTALK_AEGIS_KEY / DINGTALK_AEGIS_SECRET / DINGTALK_WORKID"
        )
    return key, secret, workid


async def fetch_access_token(aegis_key: str, aegis_secret: str, workid: str) -> tuple[str, str]:
    url = f"{TOKEN_API_URL}?aegisKey={aegis_key}&aegisSecret={aegis_secret}&workid={workid}"
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url, headers={"content-type": "application/json"})
        resp.raise_for_status()
        payload = resp.json()
    if payload.get("ec") != 200:
        raise RuntimeError(
            f"获取钉钉 token 失败: ec={payload.get('ec')} em={payload.get('em')}"
        )
    data = payload.get("data") or {}
    token = str(data.get("token") or "").strip()
    operator_id = str(data.get("operatorId") or "").strip()
    if not token or not operator_id:
        raise RuntimeError("钉钉 token 响应缺少 token 或 operatorId")
    return token, operator_id


def extract_node_id(url_or_node_id: str) -> str:
    text = (url_or_node_id or "").strip()
    if text.startswith("http"):
        match = NODE_ID_RE.search(text)
        if not match:
            raise ValueError(f"无法从 URL 解析 node_id: {text}")
        return match.group(1)
    return text


def extract_sheet_id(url: str, *, fallback: str = "") -> str:
    sheet_id = (fallback or "").strip()
    if sheet_id:
        return sheet_id
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    iframe = qs.get("iframeQuery", [""])[0]
    inner = parse_qs(iframe) if iframe else {}
    return str((inner.get("sheetId") or [""])[0] or "").strip()


def lookup_schedule_by_node(node_id: str) -> dict[str, Any] | None:
    if not SCHEDULE_REGISTRY.is_file():
        return None
    data = json.loads(SCHEDULE_REGISTRY.read_text(encoding="utf-8"))
    for entry in data.get("schedules") or []:
        if not isinstance(entry, dict):
            continue
        url = str(entry.get("url") or "")
        try:
            nid = extract_node_id(url) if url else ""
        except ValueError:
            nid = ""
        if nid == node_id:
            return entry
    return None


async def fetch_dentry_key_from_mainsite(node_id: str, cookie: str) -> str:
    url = f"https://alidocs.dingtalk.com/i/nodes/{node_id}"
    async with httpx.AsyncClient(verify=False, timeout=30.0, follow_redirects=True) as client:
        resp = await client.get(
            url,
            headers={"cookie": cookie, "user-agent": USER_AGENT, "accept": "text/html"},
        )
        resp.raise_for_status()
        html = resp.text
    match = MAINSITE_SCRIPT_RE.search(html)
    if not match:
        raise RuntimeError("无法从 alidocs 页面解析 mainsite_server_content")
    raw = match.group(1).strip()
    mainsite = json.loads(raw)
    dentry = (
        mainsite.get("dentryInfo", {}).get("data", {}).get("dentryKey")
        if isinstance(mainsite.get("dentryInfo"), dict)
        else None
    )
    if not dentry:
        raise RuntimeError("mainsite 中未找到 dentryKey")
    return str(dentry).strip()


def resolve_notable_target(
    *,
    url: str = "",
    doc_key: str = "",
    sheet_id: str = "",
    node_id: str = "",
) -> tuple[str, str, str, str, str]:
    """返回 (doc_key, sheet_id, label, source_url, dentry_key)。"""
    source_url = (url or "").strip()
    nid = (node_id or "").strip()
    if not nid and source_url:
        nid = extract_node_id(source_url)

    registry = lookup_schedule_by_node(nid) if nid else None
    label = str((registry or {}).get("label") or "AI 表格")
    if registry and not source_url:
        source_url = str(registry.get("url") or "").strip()

    dk = (doc_key or "").strip() or str((registry or {}).get("docKey") or "").strip()
    sid = (sheet_id or "").strip()
    if not sid:
        sid = str((registry or {}).get("sheetId") or "").strip()
    if not sid and source_url:
        sid = extract_sheet_id(source_url)
    dentry_key = str((registry or {}).get("dentryKey") or "").strip()

    if not dk:
        raise ValueError(
            "缺少 docKey：请在 documents/schedule_links.json 登记，或传入 doc_key"
        )
    if not sid:
        raise ValueError("缺少 sheetId：URL 需含 iframeQuery.sheetId，或传入 sheet_id")
    return dk, sid, label, source_url, dentry_key


def _find_notable(obj: Any, depth: int = 0) -> dict[str, Any] | None:
    if depth > 12:
        return None
    if isinstance(obj, dict):
        if obj.get("name") == "notable" and isinstance(obj.get("sheetMap"), dict):
            return obj
        for value in obj.values():
            found = _find_notable(value, depth + 1)
            if found:
                return found
    elif isinstance(obj, str) and "sheetMap" in obj and obj.strip().startswith("{"):
        try:
            return _find_notable(json.loads(obj), depth + 1)
        except json.JSONDecodeError:
            return None
    elif isinstance(obj, list):
        for item in obj:
            found = _find_notable(item, depth + 1)
            if found:
                return found
    return None


def _notable_from_document_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    if not isinstance(data, dict):
        return None
    doc_content = data.get("documentContent")
    if isinstance(doc_content, dict):
        checkpoint = doc_content.get("checkpoint")
        if isinstance(checkpoint, dict) and checkpoint.get("content"):
            try:
                notable = json.loads(str(checkpoint["content"]))
                if isinstance(notable, dict):
                    return notable
            except json.JSONDecodeError:
                pass
    return _find_notable(data)


def _cell_value(cell: Any) -> str:
    if cell is None:
        return ""
    if isinstance(cell, dict):
        for key in ("value", "data", "text", "name", "title"):
            if cell.get(key) not in (None, ""):
                return field_text(cell.get(key))
        return field_text(cell)
    return field_text(cell)


def _records_from_notable_sheet(notable: dict[str, Any], sheet_id: str) -> list[dict[str, Any]]:
    sheet_map = notable.get("sheetMap") or {}
    sheet = sheet_map.get(sheet_id)
    if not isinstance(sheet, dict):
        raise RuntimeError(f"快照中无 sheetId={sheet_id}")

    field_map = sheet.get("fieldMap") or {}
    id_to_name: dict[str, str] = {}
    for fid, meta in field_map.items():
        if isinstance(meta, dict) and not meta.get("deleted"):
            id_to_name[str(fid)] = str(meta.get("name") or fid)

    record_map = sheet.get("recordMap")
    if not isinstance(record_map, dict) or not record_map:
        record_map = notable.get("recordMap") if isinstance(notable.get("recordMap"), dict) else {}

    out: list[dict[str, Any]] = []
    if record_map:
        for rec in record_map.values():
            if not isinstance(rec, dict):
                continue
            cells = rec.get("cells") if isinstance(rec.get("cells"), dict) else {}
            fields: dict[str, Any] = {}
            if cells:
                for fid, cell in cells.items():
                    fname = id_to_name.get(str(fid), str(fid))
                    fields[fname] = _cell_value(cell)
            elif isinstance(rec.get("fields"), dict):
                for fid, cell in rec["fields"].items():
                    fname = id_to_name.get(str(fid), str(fid))
                    fields[fname] = _cell_value(cell)
            if fields:
                out.append({"fields": fields, "id": rec.get("id")})
        return out

    record_ids = sheet.get("recordIds") or []
    if record_ids:
        raise RuntimeError(
            f"alidocs 快照仅有 {len(record_ids)} 条 recordId、无单元格数据；"
            "请用浏览器登录 alidocs 后执行 dingtalk-doc 的 refresh_cookie 更新 Cookie 再试"
        )
    return out


async def _fetch_openapi_records(*, doc_key: str, sheet_id: str) -> list[dict[str, Any]]:
    ak, sec, wid = load_aegis_credentials()
    access, operator_id = await fetch_access_token(ak, sec, wid)
    url = NOTABLE_LIST_URL.format(doc_key=doc_key, sheet_id=sheet_id)
    headers = {
        "x-acs-dingtalk-access-token": access,
        "content-type": "application/json",
    }
    records: list[dict[str, Any]] = []
    next_token = ""
    async with httpx.AsyncClient(timeout=60.0) as client:
        while True:
            body: dict[str, Any] = {"maxResults": 100}
            if next_token:
                body["nextToken"] = next_token
            resp = await client.post(
                url, params={"operatorId": operator_id}, headers=headers, json=body
            )
            resp.raise_for_status()
            payload = resp.json()
            batch = payload.get("records") or []
            if isinstance(batch, list):
                records.extend(r for r in batch if isinstance(r, dict))
            next_token = str(payload.get("nextToken") or "").strip()
            if not next_token or not batch:
                break
    return records


async def _fetch_cookie_records(
    *,
    doc_key: str,
    sheet_id: str,
    dentry_key: str,
    node_id: str,
) -> list[dict[str, Any]]:
    cookie = load_dingtalk_cookie()
    if not dentry_key and node_id:
        dentry_key = await fetch_dentry_key_from_mainsite(node_id, cookie)
    if not dentry_key:
        raise RuntimeError("缺少 dentryKey，无法走 alidocs Cookie 拉取")

    headers = {
        "user-agent": USER_AGENT,
        "accept": "*/*",
        "content-type": "application/json",
        "cookie": cookie,
        "origin": "https://alidocs.dingtalk.com",
        "a-dentry-key": dentry_key,
        "a-doc-key": doc_key,
        "referer": (
            f"https://alidocs.dingtalk.com/iframe/notable?"
            f"docKey={doc_key}&dentryKey={dentry_key}&sheetId={sheet_id}"
        ),
    }
    payloads: list[dict[str, Any]] = [{}, {"fetchBody": True}]
    last_error = "未知错误"
    async with httpx.AsyncClient(verify=False, timeout=90.0) as client:
        for body in payloads:
            resp = await client.post(ALIDOCS_DOCUMENT_DATA, headers=headers, json=body)
            if resp.status_code == 401:
                raise RuntimeError(
                    "DINGTALK_COOKIE 已过期，请用 dingtalk-doc 的 refresh_cookie 更新"
                )
            if resp.status_code != 200:
                last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                continue
            notable = _notable_from_document_payload(resp.json())
            if not notable:
                last_error = "document/data 响应中未找到 notable 快照"
                continue
            try:
                records = _records_from_notable_sheet(notable, sheet_id)
            except RuntimeError as exc:
                last_error = str(exc)
                continue
            if records:
                return records
    raise RuntimeError(last_error)


async def fetch_notable_records(
    *,
    doc_key: str,
    sheet_id: str,
    node_id: str = "",
    url: str = "",
    prefer_cookie: bool = False,
) -> list[dict[str, Any]]:
    _, _, _, _, dentry_key = resolve_notable_target(
        url=url,
        doc_key=doc_key,
        sheet_id=sheet_id,
        node_id=node_id,
    )
    if not prefer_cookie:
        try:
            return await _fetch_openapi_records(doc_key=doc_key, sheet_id=sheet_id)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code not in (401, 403):
                raise
        except RuntimeError:
            pass
    return await _fetch_cookie_records(
        doc_key=doc_key,
        sheet_id=sheet_id,
        dentry_key=dentry_key,
        node_id=node_id,
    )


def field_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        parts = [field_text(v) for v in value]
        return "、".join(p for p in parts if p)
    if isinstance(value, dict):
        for key in ("name", "text", "title", "label", "value"):
            if value.get(key) not in (None, ""):
                return field_text(value.get(key))
        return json.dumps(value, ensure_ascii=False)
    return str(value).strip()


def records_to_markdown(
    records: list[dict[str, Any]],
    *,
    label: str,
    url: str = "",
    limit: int = 50,
) -> str:
    if not records:
        return f"**{label}** 当前无记录。" + (f"\n\n来源：{url}" if url else "")

    field_names: list[str] = []
    seen: set[str] = set()
    for rec in records:
        fields = rec.get("fields")
        if not isinstance(fields, dict):
            continue
        for name in fields:
            if name not in seen:
                seen.add(name)
                field_names.append(str(name))

    if not field_names:
        return f"**{label}** 已拉取 {len(records)} 条，但字段为空。"

    lines = [
        f"**{label}**（共 {len(records)} 条）",
        "",
        "| " + " | ".join(field_names) + " |",
        "| " + " | ".join(["---"] * len(field_names)) + " |",
    ]
    for rec in records[:limit]:
        fields = rec.get("fields") if isinstance(rec.get("fields"), dict) else {}
        row = [field_text(fields.get(name)) for name in field_names]
        lines.append("| " + " | ".join(cell.replace("|", "\\|") for cell in row) + " |")
    if len(records) > limit:
        lines.append("")
        lines.append(f"…（共 {len(records)} 条，已展示前 {limit} 条）")
    if url:
        lines.extend(["", f"来源：{url}"])
    return "\n".join(lines)
