"""从钉钉 alidocs 目录列举并拉取版本测试用例 Excel（供 testcase-kb 同步）。"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent
DEFAULT_CONFIG = ROOT / "DingTalk" / "config" / "kb.json"
FOLDERS_CONFIG = ROOT / "DingTalk" / "config" / "folders.json"
_LEGACY_CONFIG = SCRIPTS / "dingtalk_kb_config.json"

_VERSION_RE = re.compile(r"(?:[vV])?\.?\s*(\d+)\s*\.\s*(\d+)\s*\.\s*(\d+)")
_ALIDOCS_BASE = "https://alidocs.dingtalk.com"
_BOX_LIST_API = f"{_ALIDOCS_BASE}/box/api/v2/dentry/list"
_NODE_ID_RE = re.compile(r"/i/nodes/([^?/#]+)")
_SPREADSHEET_EXT = frozenset({"axls", "xlsx", "xls", "able", "sheet"})


@dataclass
class DingtalkWorkbook:
    name: str
    url: str
    node_id: str
    version_tuple: Tuple[int, int, int]
    version_label: str


def load_json_config(path: Path | None = None) -> dict[str, Any]:
    if path is not None:
        cfg_path = path
    elif DEFAULT_CONFIG.is_file():
        cfg_path = DEFAULT_CONFIG
    elif _LEGACY_CONFIG.is_file():
        cfg_path = _LEGACY_CONFIG
    else:
        return {}
    return json.loads(cfg_path.read_text(encoding="utf-8"))


def load_folders_config() -> dict[str, Any]:
    if not FOLDERS_CONFIG.is_file():
        return {"folders": []}
    return json.loads(FOLDERS_CONFIG.read_text(encoding="utf-8"))


def list_registered_folders() -> List[Dict[str, Any]]:
    data = load_folders_config()
    folders = data.get("folders")
    if not isinstance(folders, list):
        return []
    return [f for f in folders if isinstance(f, dict)]


def get_folder_entry(folder_id: str) -> Optional[Dict[str, Any]]:
    fid = (folder_id or "").strip()
    if not fid:
        return None
    for entry in list_registered_folders():
        if str(entry.get("id") or "").strip() == fid:
            return entry
    return None


def get_default_folder_entry() -> Optional[Dict[str, Any]]:
    folders = list_registered_folders()
    for entry in folders:
        if entry.get("default"):
            return entry
    return folders[0] if folders else None


def resolve_folder_url(
    *,
    folder_id: str | None = None,
    folder_url: str | None = None,
    kb_config: dict[str, Any] | None = None,
) -> tuple[str, Optional[Dict[str, Any]]]:
    """解析目录 URL；返回 (folder_url, 登记条目或 None)。"""
    direct = (folder_url or "").strip()
    if direct:
        fid = (folder_id or "").strip()
        entry = get_folder_entry(fid) if fid else None
        if entry is None and kb_config:
            cfg_id = str(kb_config.get("folderId") or "").strip()
            if cfg_id:
                entry = get_folder_entry(cfg_id)
        return direct, entry

    fid = (folder_id or "").strip()
    if fid:
        entry = get_folder_entry(fid)
        if not entry:
            raise ValueError(f"未登记的目录 id: {fid}（见 DingTalk/config/folders.json）")
        url = str(entry.get("folderUrl") or "").strip()
        if not url:
            raise ValueError(f"目录 {fid} 缺少 folderUrl")
        return url, entry

    cfg = kb_config if kb_config is not None else load_json_config()
    cfg_id = str(cfg.get("folderId") or "").strip()
    if cfg_id:
        entry = get_folder_entry(cfg_id)
        if entry:
            url = str(entry.get("folderUrl") or "").strip()
            if url:
                return url, entry

    cfg_url = str(cfg.get("folderUrl") or "").strip()
    if cfg_url:
        entry = get_folder_entry(cfg_id) if cfg_id else get_default_folder_entry()
        return cfg_url, entry

    entry = get_default_folder_entry()
    if entry:
        url = str(entry.get("folderUrl") or "").strip()
        if url:
            return url, entry

    raise ValueError(
        "未配置钉钉目录：请在 DingTalk/config/folders.json 登记，"
        "或在 DingTalk/config/kb.json 配置 folderUrl"
    )


def _load_mcp_env(server_key: str) -> dict[str, str]:
    """从 .mcp.secrets.json / mcp.json 读取 MCP env。"""
    try:
        from mcp_paths import load_mcp_env

        return load_mcp_env(server_key)
    except ImportError:
        candidates = [
            ROOT / ".cursor" / ".mcp.secrets.json",
            ROOT / ".cursor" / "mcp.json",
            Path.home() / ".cursor" / "mcp.json",
        ]
        for p in candidates:
            if not p.is_file():
                continue
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            srv = (data.get("mcpServers") or {}).get(server_key) or {}
            env = srv.get("env") or {}
            if isinstance(env, dict) and env:
                return {str(k): str(v) for k, v in env.items()}
        return {}


def resolve_dingtalk_cookie() -> str:
    cookie = os.environ.get("DINGTALK_COOKIE", "").strip()
    if cookie:
        return cookie
    for key in ("dingtalk-doc", "user-dingtalk-doc"):
        cookie = _load_mcp_env(key).get("DINGTALK_COOKIE", "").strip()
        if cookie:
            return cookie
    cookie_file = Path.home() / ".dingtalk_doc_cookie"
    if cookie_file.is_file():
        return cookie_file.read_text(encoding="utf-8").strip()
    raise RuntimeError(
        "缺少 DINGTALK_COOKIE：请写入 .cursor/.mcp.secrets.json、"
        "~/.dingtalk_doc_cookie，或运行 python3 DingTalk/.cookie_sync_execute.py"
    )


def resolve_aegis_credentials() -> tuple[str, str, str]:
    env = {**_load_mcp_env("dingtalk-excel-read"), **os.environ}
    key = str(env.get("DINGTALK_AEGIS_KEY") or "").strip()
    secret = str(env.get("DINGTALK_AEGIS_SECRET") or "").strip()
    workid = str(env.get("DINGTALK_WORKID") or "").strip()
    if not key or not secret or not workid:
        raise RuntimeError(
            "缺少钉钉 Excel 鉴权：请配置 dingtalk-excel-read 的 "
            "DINGTALK_AEGIS_KEY / DINGTALK_AEGIS_SECRET / DINGTALK_WORKID"
        )
    return key, secret, workid


def parse_version_from_name(name: str) -> Optional[Tuple[int, int, int]]:
    m = _VERSION_RE.search(name or "")
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def version_label_from_tuple(ver: Tuple[int, int, int]) -> str:
    return f"v{ver[0]}.{ver[1]}.{ver[2]}"


def extract_node_id_from_url(url_or_node_id: str) -> str:
    text = (url_or_node_id or "").strip()
    if text.startswith("http"):
        m = _NODE_ID_RE.search(text)
        if not m:
            raise ValueError(f"无法从 URL 解析 node_id: {text}")
        return m.group(1)
    return text


def _xsrf_from_cookie(cookie: str) -> str:
    m = re.search(r"XSRF-TOKEN=([^;]+)", cookie)
    return m.group(1) if m else ""


def is_case_workbook_name(name: str) -> bool:
    """文件名是否像版本/专项用例表（非模板类杂项可另行排除）。"""
    n = (name or "").strip()
    if not n:
        return False
    if parse_version_from_name(n):
        return True
    if "用例" in n:
        return True
    ext = n.rsplit(".", 1)[-1].lower() if "." in n else ""
    return ext in _SPREADSHEET_EXT


def _entry_extension(entry: Dict[str, Any], name: str) -> str:
    ext = str(entry.get("extension") or "").strip().lower()
    if not ext and "." in name:
        ext = name.rsplit(".", 1)[-1].lower()
    return ext


def is_spreadsheet_entry(entry: Dict[str, Any]) -> bool:
    """Box API 子项是否为可同步的表格文档（含运营活动表等无版本号文件）。"""
    name = str(entry.get("name") or "").strip()
    if not name:
        return False
    ext = _entry_extension(entry, name)
    if ext in _SPREADSHEET_EXT:
        return True
    return is_case_workbook_name(name)


def is_folder_entry(entry: Dict[str, Any]) -> bool:
    dtype = str(entry.get("dentryType") or "").lower()
    return dtype == "folder" or bool(entry.get("hasChildren"))


async def _list_folder_children_box_async(
    folder_node_id: str,
    *,
    cookie: str,
    page_size: int = 100,
    max_pages: int = 50,
) -> List[Dict[str, Any]]:
    import httpx

    headers = {
        "cookie": cookie,
        "user-agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
        "accept": "application/json, text/plain, */*",
        "referer": f"{_ALIDOCS_BASE}/i/nodes/{folder_node_id}",
        "x-xsrf-token": _xsrf_from_cookie(cookie),
    }
    found: List[Dict[str, Any]] = []
    load_more_id: Optional[str] = None

    async with httpx.AsyncClient(verify=False, timeout=60.0) as client:
        for _page in range(1, max_pages + 1):
            params: Dict[str, Any] = {
                "dentryUuid": folder_node_id,
                "orderType": "SORT_KEY",
                "sortType": "desc",
                "listDentrySource": "2",
                "pageSize": page_size,
            }
            if load_more_id:
                params["loadMoreId"] = load_more_id

            response = await client.get(_BOX_LIST_API, headers=headers, params=params)
            if response.status_code in (401, 403):
                raise RuntimeError("钉钉 Cookie 无效或已过期，请更新 DINGTALK_COOKIE")
            response.raise_for_status()
            payload = response.json()
            if not payload.get("isSuccess", True) and payload.get("status") not in (200, None):
                raise RuntimeError(f"目录列表 API 失败: {payload}")

            data = payload.get("data") or {}
            children = data.get("children") or []
            for entry in children:
                if isinstance(entry, dict) and entry.get("dentryUuid"):
                    found.append(entry)

            has_more = bool(data.get("hasMore"))
            load_more_id = data.get("loadMoreId")
            if not children or not has_more:
                break

    return found


def list_folder_children_via_box(
    folder_url_or_id: str,
    *,
    cookie: str | None = None,
) -> List[Dict[str, Any]]:
    folder_id = extract_node_id_from_url(folder_url_or_id)
    ck = cookie or resolve_dingtalk_cookie()
    return asyncio.run(_list_folder_children_box_async(folder_id, cookie=ck))


def _ensure_doc_mcp_import_path() -> None:
    mcp_dir = ROOT / ".cursor/skills/dingtalk-doc-read/mcp_dingtalk_doc"
    venv_lib = mcp_dir / "venv" / "lib"
    if venv_lib.is_dir():
        for sp in sorted(venv_lib.glob("python*/site-packages")):
            sp_str = str(sp)
            if sp_str not in sys.path:
                sys.path.insert(0, sp_str)
    mcp_str = str(mcp_dir)
    if mcp_str not in sys.path:
        sys.path.insert(0, mcp_str)


def _import_doc_mcp_module():
    _ensure_doc_mcp_import_path()
    mod_path = ROOT / ".cursor/skills/dingtalk-doc-read/mcp_dingtalk_doc/server.py"
    if not mod_path.is_file():
        raise RuntimeError(f"找不到钉钉文档 MCP: {mod_path}")
    spec = importlib.util.spec_from_file_location("dingtalk_doc_mcp_kb", mod_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载模块: {mod_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _ensure_excel_mcp_import_path() -> Path:
    mcp_dir = ROOT / ".cursor/skills/testcase-to-excel/mcp_dingtalk_excel"
    if not mcp_dir.is_dir():
        raise RuntimeError(f"找不到钉钉 Excel MCP 目录: {mcp_dir}")
    venv_lib = mcp_dir / "venv" / "lib"
    if venv_lib.is_dir():
        for sp in sorted(venv_lib.glob("python*/site-packages")):
            sp_str = str(sp)
            if sp_str not in sys.path:
                sys.path.insert(0, sp_str)
    mcp_str = str(mcp_dir)
    if mcp_str not in sys.path:
        sys.path.insert(0, mcp_str)
    return mcp_dir


def _import_server_read():
    _ensure_excel_mcp_import_path()
    import importlib

    return importlib.import_module("server_read")


async def _list_document_nodes(
    folder_url: str,
    *,
    cookie: str,
    recursive: bool,
    max_folder_fetches: int,
) -> List[Dict[str, Any]]:
    doc = _import_doc_mcp_module()
    if recursive:
        return await doc.collect_documents_under_folder(
            folder_url,
            cookie,
            recursive=True,
            max_folder_fetches=max_folder_fetches,
        )
    return await doc.list_folder_children(folder_url, cookie)


def list_document_nodes(
    folder_url: str,
    *,
    cookie: str | None = None,
    recursive: bool = True,
    max_folder_fetches: int = 80,
) -> List[Dict[str, Any]]:
    ck = cookie or resolve_dingtalk_cookie()
    return asyncio.run(
        _list_document_nodes(
            folder_url,
            cookie=ck,
            recursive=recursive,
            max_folder_fetches=max_folder_fetches,
        )
    )


def _is_workbook_fetch_error(exc: BaseException) -> bool:
    msg = str(exc)
    return "notWorkbook" in msg or "not workbook" in msg.lower()


async def _fetch_workbook_sheets_async(
    url: str,
    *,
    aegis_key: str,
    aegis_secret: str,
    workid: str,
) -> List[Tuple[str, List[List[Any]]]]:
    import httpx
    from server_read import (  # type: ignore[import-untyped]
        API_BASE_URL,
        COMMON_HEADERS,
        DEFAULT_TIMEOUT,
        MAX_CELLS_PER_REQUEST,
        clear_token_cache,
        extract_workbook_id_from_url,
        format_exception,
        format_http_error,
        getRangeData,
        getSheetList,
        getTokenAndOperatorId,
        is_invalid_auth_error,
        numberToColumnName,
    )

    workbook_id = extract_workbook_id_from_url(url)
    for attempt in range(2):
        try:
            access_token, operator_id = await getTokenAndOperatorId(
                aegis_key, aegis_secret, workid
            )
            break
        except httpx.HTTPStatusError as e:
            if attempt == 0 and is_invalid_auth_error(e):
                clear_token_cache(aegis_key, aegis_secret, workid)
                continue
            raise RuntimeError(str(e)) from e

    sheets = await getSheetList(workbook_id, operator_id, access_token)
    if not sheets:
        raise RuntimeError("工作簿中没有 Sheet")

    result: List[Tuple[str, List[List[Any]]]] = []
    headers = {**COMMON_HEADERS, "x-acs-dingtalk-access-token": access_token}

    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        for sheet in sheets:
            name = str(sheet.get("name") or "").strip()
            sheet_id = str(sheet.get("id") or "").strip()
            if not name or not sheet_id:
                continue
            max_row = 10000
            max_column = "ZZ"
            column_count = 702
            url_sheet_info = (
                f"{API_BASE_URL}/workbooks/{workbook_id}/sheets/{sheet_id}"
                f"?select=values&operatorId={operator_id}"
            )
            try:
                response = await client.get(url_sheet_info, headers=headers)
                response.raise_for_status()
                sheet_json = response.json()
                if sheet_json.get("rowCount"):
                    max_row = sheet_json["rowCount"]
                if sheet_json.get("columnCount"):
                    column_count = sheet_json["columnCount"]
                    max_column = numberToColumnName(column_count)
            except httpx.HTTPError as e:
                raise RuntimeError(
                    f"获取 Sheet 维度失败:\n{format_http_error(e, url_sheet_info)}"
                ) from e

            total_cells = max_row * column_count
            if total_cells > MAX_CELLS_PER_REQUEST:
                rows_per_batch = max(1, MAX_CELLS_PER_REQUEST // column_count - 1)
                all_values: List[List[Any]] = []
                for start_row in range(1, max_row + 1, rows_per_batch):
                    end_row = min(start_row + rows_per_batch - 1, max_row)
                    try:
                        batch_values = await getRangeData(
                            client,
                            workbook_id,
                            sheet_id,
                            operator_id,
                            access_token,
                            start_row,
                            end_row,
                            max_column,
                        )
                        all_values.extend(batch_values)
                    except Exception as e:
                        raise RuntimeError(
                            f"分批获取数据失败（行 {start_row}-{end_row}）:\n"
                            f"{format_exception(e)}"
                        ) from e
                values = all_values
            else:
                try:
                    values = await getRangeData(
                        client,
                        workbook_id,
                        sheet_id,
                        operator_id,
                        access_token,
                        1,
                        max_row,
                        max_column,
                    )
                except Exception as e:
                    raise RuntimeError(
                        f"获取 Sheet 数据失败:\n{format_exception(e)}"
                    ) from e
            result.append((name, values))
    return result


def discover_workbooks(
    folder_url: str,
    *,
    cookie: str | None = None,
    aegis_key: str | None = None,
    aegis_secret: str | None = None,
    workid: str | None = None,
    recursive: bool = True,
    max_documents: int = 200,
    max_folder_fetches: int = 80,
    verify_fetch: bool = False,
) -> List[DingtalkWorkbook]:
    """列举目录下用例相关工作簿（Box API 直拉子项），按版本号升序排序。"""
    ck = cookie or resolve_dingtalk_cookie()
    if not aegis_key or not aegis_secret or not workid:
        ak, sec, wid = resolve_aegis_credentials()
        aegis_key = aegis_key or ak
        aegis_secret = aegis_secret or sec
        workid = workid or wid

    if verify_fetch:
        _import_server_read()

    root_id = extract_node_id_from_url(folder_url)
    folder_queue: List[str] = [root_id]
    visited_folders: set[str] = set()
    found: Dict[str, DingtalkWorkbook] = {}

    while folder_queue and len(visited_folders) < max_folder_fetches:
        folder_id = folder_queue.pop(0)
        if folder_id in visited_folders:
            continue
        visited_folders.add(folder_id)

        entries = asyncio.run(_list_folder_children_box_async(folder_id, cookie=ck))
        for entry in entries:
            if len(found) >= max_documents:
                break
            if is_folder_entry(entry):
                child_id = str(entry.get("dentryUuid") or "").strip()
                if recursive and child_id and child_id not in visited_folders:
                    folder_queue.append(child_id)
                continue
            if not is_spreadsheet_entry(entry):
                continue
            name = str(entry.get("name") or "").strip()
            nid = str(entry.get("dentryUuid") or "").strip()
            if not name or not nid:
                continue
            url = f"{_ALIDOCS_BASE}/i/nodes/{nid}"
            ver = parse_version_from_name(name) or (0, 0, 0)
            vlabel = (
                version_label_from_tuple(ver)
                if parse_version_from_name(name)
                else "—"
            )
            if verify_fetch:
                try:
                    asyncio.run(
                        _fetch_workbook_sheets_async(
                            url,
                            aegis_key=aegis_key,
                            aegis_secret=aegis_secret,
                            workid=workid,
                        )
                    )
                except Exception as exc:
                    if _is_workbook_fetch_error(exc):
                        continue
                    raise RuntimeError(f"拉取工作簿失败 {name} ({url}): {exc}") from exc
            found[nid] = DingtalkWorkbook(
                name=name,
                url=url,
                node_id=nid,
                version_tuple=ver,
                version_label=vlabel,
            )

    return sorted(found.values(), key=lambda w: (w.version_tuple, w.name))


def fetch_workbook_sheets(
    url: str,
    *,
    aegis_key: str | None = None,
    aegis_secret: str | None = None,
    workid: str | None = None,
) -> List[Tuple[str, List[List[Any]]]]:
    if not aegis_key or not aegis_secret or not workid:
        ak, sec, wid = resolve_aegis_credentials()
        aegis_key = aegis_key or ak
        aegis_secret = aegis_secret or sec
        workid = workid or wid
    _import_server_read()
    return asyncio.run(
        _fetch_workbook_sheets_async(
            url,
            aegis_key=aegis_key,
            aegis_secret=aegis_secret,
            workid=workid,
        )
    )
