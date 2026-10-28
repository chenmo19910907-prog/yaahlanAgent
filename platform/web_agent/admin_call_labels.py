"""Admin 操作记录：路径 + 参数 → 中文标题（Web Agent 侧自包含，不依赖 Admin/ 目录）。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ADMIN_CONFIG_PATH = _REPO_ROOT / "Admin" / "config.json"
_ADMIN_REGISTRY_PATH = _REPO_ROOT / "Admin" / "config" / "registry.json"
_PATH_IN_DESC_RE = re.compile(r"(?:POST|GET|PUT|DELETE|PATCH)\s+(/[^\s（(]+)", re.I)
_admin_path_operation_cache: dict[str, str] | None = None


def _normalize_admin_path(path: str) -> str:
    p = (path or "").strip()
    if not p:
        return ""
    if "://" in p:
        p = urlparse(p).path or p
    if not p.startswith("/"):
        p = f"/{p}"
    return p.rstrip("/") or p


def _registry_capability_list(data: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("items", "capabilities"):
        caps = data.get(key)
        if isinstance(caps, list):
            return [c for c in caps if isinstance(c, dict)]
    return []


def _build_admin_path_operation_index() -> dict[str, str]:
    """Admin config path + registry 描述中的 API 路径 → registry name。"""
    id_to_name: dict[str, str] = {}
    index: dict[str, str] = {}

    if _ADMIN_REGISTRY_PATH.is_file():
        try:
            reg_data = json.loads(_ADMIN_REGISTRY_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            reg_data = {}
        for cap in _registry_capability_list(reg_data):
            cid = str(cap.get("id") or "").strip()
            name = str(cap.get("name") or "").strip()
            if cid and name:
                id_to_name[cid] = name
            desc = str(cap.get("description") or "")
            for m in _PATH_IN_DESC_RE.finditer(desc):
                path = _normalize_admin_path(m.group(1))
                if path and name:
                    index[path] = name

    if _ADMIN_CONFIG_PATH.is_file():
        try:
            cfg = json.loads(_ADMIN_CONFIG_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            cfg = {}
        for key, val in cfg.items():
            if key == "api" or not isinstance(val, dict):
                continue
            path = _normalize_admin_path(str(val.get("path") or ""))
            if not path:
                continue
            name = id_to_name.get(str(key).strip())
            if name:
                index[path] = name

    return index


def _admin_operation_name_for_path(path: str) -> str:
    global _admin_path_operation_cache
    if _admin_path_operation_cache is None:
        _admin_path_operation_cache = _build_admin_path_operation_index()
    norm = _normalize_admin_path(path)
    if not norm:
        return ""
    if norm in _admin_path_operation_cache:
        return _admin_path_operation_cache[norm]

    best_name = ""
    best_len = 0
    for indexed_path, name in _admin_path_operation_cache.items():
        if norm == indexed_path or norm.endswith(indexed_path) or indexed_path.endswith(norm):
            if len(indexed_path) > best_len:
                best_len = len(indexed_path)
                best_name = name
    if best_name:
        return best_name

    tail = norm.rsplit("/", 1)[-1]
    if not tail:
        return ""
    matches = {
        name
        for indexed_path, name in _admin_path_operation_cache.items()
        if indexed_path.rsplit("/", 1)[-1] == tail
    }
    if len(matches) == 1:
        return next(iter(matches))
    return ""


def _admin_registry_operation_label(path: str) -> str:
    name = _admin_operation_name_for_path(path)
    if name:
        return f"Admin {name}"
    return ""


def admin_call_meta(url: str, body: dict[str, Any], *, http_method: str) -> tuple[str, str, str, str]:
    path = urlparse(url).path or url
    uid = str(body.get("userId") or body.get("uid") or body.get("momoid") or "").strip()
    phone = str(body.get("phone") or body.get("mobile") or "").strip()
    family_id = str(body.get("familyId") or "").strip()

    if "queryUserDetail" in path and uid:
        operation = f"Admin 查询用户 {uid} 详情"
        account = uid
        params = f"userId={uid}"
    elif "queryUserHistoryDeviceList" in path:
        operation = f"Admin 查询用户 {uid} 历史登录设备" if uid else "Admin 查询用户历史登录设备"
        account = uid
        page = body.get("page") or body.get("pageNo") or 1
        size = body.get("pageSize") or body.get("size") or 20
        params = f"userId={uid}，page={page}，pageSize={size}" if uid else f"page={page}，pageSize={size}"
    elif "queryUserProfileList" in path:
        id_list = body.get("userIdList") or body.get("userIds") or []
        ids: list[str] = []
        if isinstance(id_list, list):
            ids = [str(x).strip() for x in id_list if str(x).strip()]
        if len(ids) == 1:
            operation = f"Admin 查询用户 {ids[0]} 资料"
            account = ids[0]
        elif len(ids) > 1:
            operation = f"Admin 批量查询 {len(ids)} 个用户资料"
            account = f"{ids[0]} 等 {len(ids)} 人"
        else:
            operation = "Admin 查询用户资料列表"
            account = uid
        params = f"userIdList={ids[:5]}" + ("…" if len(ids) > 5 else "")
    elif "queryDeviceHistoryUsers" in path or "historyDevice" in path.lower():
        mmuid = str(body.get("mmuidv3") or body.get("mmuid") or "").strip()
        operation = "Admin 查询设备历史登录用户"
        account = mmuid[:32] + "..." if len(mmuid) > 32 else mmuid
        params = f"mmuidv3={mmuid}" if body.get("mmuidv3") else f"mmuid={mmuid}"
    elif "queryUserHistoryDevices" in path and uid:
        operation = f"Admin 查询用户 {uid} 历史设备"
        account = uid
        params = f"userId={uid}"
    elif "addFamilyMember" in path or "add_family" in path.lower():
        operation = f"Admin 家族添加成员 userId={uid or '?'}"
        account = uid or family_id
        params = f"userId={uid}，familyId={family_id}".strip("，")
    elif "resetCustomGift" in path or "custom_gift" in path.lower():
        operation = f"Admin 重置用户 {uid} 定制礼物上传"
        account = uid
        params = f"userId={uid}"
    else:
        operation = _admin_registry_operation_label(path) or f"Admin {path}"
        account = uid or phone or family_id
        parts = [f"{k}={v}" for k, v in list(body.items())[:4] if v is not None]
        params = "，".join(parts)[:240]

    return operation, account, params, path


def _admin_body_from_params_summary(params_summary: str, *, account_summary: str = "") -> dict[str, Any]:
    body: dict[str, Any] = {}
    text = params_summary or ""
    for piece in re.split(r"[，,]", text):
        seg = piece.strip()
        if not seg or "=" not in seg:
            continue
        key, val = seg.split("=", 1)
        key = key.strip()
        val = val.strip().split("（")[0].split("(")[0].strip()
        if not key or not val:
            continue
        if key in ("page", "pageNo", "pageSize", "size", "appId"):
            try:
                body[key] = int(val)
            except ValueError:
                body[key] = val
            continue
        if key == "userIdList":
            m = re.match(r"\[([^\]]*)\]", val)
            if m:
                body[key] = [x.strip() for x in m.group(1).split(",") if x.strip()]
            else:
                body[key] = [val]
            continue
        body[key] = val
    if not body.get("userIdList"):
        m = re.search(r"userIdList=\[([^\]]*)\]", text)
        if m:
            body["userIdList"] = [x.strip() for x in m.group(1).split(",") if x.strip()]
    if not body.get("userId") and account_summary:
        acc = re.sub(r"^(测试|线上)\s*·\s*", "", account_summary.strip()).strip()
        m_uid = re.match(r"^(\d{6,12})", acc)
        if m_uid:
            body["userId"] = m_uid.group(1)
    return body


def admin_operation_label_from_entry(
    *,
    service_url: str = "",
    operation_key: str = "",
    operation: str = "",
    params_summary: str = "",
    account_summary: str = "",
) -> str:
    path = (service_url or "").strip()
    if not path:
        m = re.match(r"admin#(.+)#", (operation_key or "").strip(), flags=re.I)
        if m:
            path = m.group(1).strip()
    op_raw = (operation or "").strip()
    if not path and op_raw.startswith("Admin /"):
        path = op_raw[len("Admin ") :].strip()
    if path and op_raw.startswith("Admin /"):
        named = _admin_registry_operation_label(path)
        if named:
            body = _admin_body_from_params_summary(params_summary, account_summary=account_summary)
            url = path if path.startswith("http") else f"https://admin.local{path}"
            return admin_call_meta(url, body, http_method="POST")[0]
    if not path:
        if op_raw.startswith("Admin ") and not op_raw.startswith("Admin /"):
            return op_raw
        return op_raw or "Admin 调用"
    body = _admin_body_from_params_summary(params_summary, account_summary=account_summary)
    url = path if path.startswith("http") else f"https://admin.local{path}"
    operation_label, _, _, _ = admin_call_meta(url, body, http_method="POST")
    return operation_label
