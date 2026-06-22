"""上传文件到钉钉 alidocs 指定目录（开放平台 Storage API）。"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

from env_loader import load_env_local, require_env

TOKEN_URL = "https://api.dingtalk.com/v1.0/oauth2/accessToken"
UPLOAD_INFO_URL = (
    "https://api.dingtalk.com/v2.0/storage/spaces/files/{parent}/uploadInfos"
)
COMMIT_URL = "https://api.dingtalk.com/v2.0/storage/spaces/files/{parent}/commit"
ALIDOCS_NODE_URL = "https://alidocs.dingtalk.com/i/nodes/{node_id}"

_token_cache: dict[str, tuple[str, float]] = {}


def _post_json(url: str, payload: dict, *, headers: dict | None = None, params: dict | None = None) -> dict:
    if params:
        qs = "&".join(f"{k}={urllib.request.quote(str(v))}" for k, v in params.items())
        url = f"{url}?{qs}"
    data = json.dumps(payload).encode("utf-8")
    req_headers = {"Content-Type": "application/json; charset=utf-8"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, data=data, headers=req_headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {body[:500]}") from exc


def _put_bytes(url: str, content: bytes, headers: dict) -> None:
    req = urllib.request.Request(url, data=content, headers=headers, method="PUT")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            if resp.status >= 400:
                raise RuntimeError(f"PUT 上传失败: HTTP {resp.status}")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"PUT HTTP {exc.code}: {body[:500]}") from exc


def get_access_token() -> str:
    load_env_local()
    client_id = require_env("DINGTALK_CLIENT_ID")
    cached = _token_cache.get(client_id)
    if cached and cached[1] > time.time():
        return cached[0]
    result = _post_json(
        TOKEN_URL,
        {"appKey": client_id, "appSecret": require_env("DINGTALK_CLIENT_SECRET")},
    )
    token = str(result.get("accessToken") or "")
    expire_in = int(result.get("expireIn") or 7200)
    if not token:
        raise RuntimeError(f"获取 accessToken 失败: {result}")
    _token_cache[client_id] = (token, time.time() + expire_in - 120)
    return token


def require_union_id() -> str:
    load_env_local()
    import os

    union_id = os.environ.get("DINGTALK_UNION_ID", "").strip()
    if not union_id:
        raise RuntimeError(
            "缺少 DINGTALK_UNION_ID：开放平台上传文件需要操作者 unionId，"
            "请在 .env.local 配置（钉钉管理后台或通讯录 API 获取）"
        )
    return union_id


def upload_file_to_folder(
    local_path: Path | str,
    *,
    parent_node_id: str,
    file_name: str | None = None,
    convert_to_online_doc: bool = False,
) -> str:
    """上传本地文件到 alidocs 目录，返回节点 URL。"""
    path = Path(local_path)
    if not path.is_file():
        raise FileNotFoundError(path)
    name = file_name or path.name
    content = path.read_bytes()
    size = len(content)
    token = get_access_token()
    union_id = require_union_id()
    headers = {"x-acs-dingtalk-access-token": token}

    info = _post_json(
        UPLOAD_INFO_URL.format(parent=parent_node_id),
        {"fileName": name, "fileSize": size},
        headers=headers,
        params={"unionId": union_id},
    )
    upload_key = str(info.get("uploadKey") or "")
    resource_url = ""
    upload_headers: dict[str, str] = {}
    if isinstance(info.get("headerSignatureInfo"), dict):
        upload_headers = {
            str(k): str(v) for k, v in info["headerSignatureInfo"].get("headers", {}).items()
        }
        urls = info["headerSignatureInfo"].get("resourceUrls") or []
        if urls:
            resource_url = str(urls[0])
    if not upload_key or not resource_url:
        raise RuntimeError(f"获取 uploadInfos 失败: {info}")

    _put_bytes(resource_url, content, upload_headers)

    commit = _post_json(
        COMMIT_URL.format(parent=parent_node_id),
        {
            "uploadKey": upload_key,
            "name": name,
            "option": {
                "size": size,
                "conflictStrategy": "AUTO_RENAME",
                "convertToOnlineDoc": convert_to_online_doc,
            },
        },
        headers=headers,
        params={"unionId": union_id},
    )
    dentry = commit.get("dentry") if isinstance(commit, dict) else None
    node_id = ""
    if isinstance(dentry, dict):
        node_id = str(dentry.get("uuid") or dentry.get("id") or "")
    if not node_id:
        raise RuntimeError(f"提交文件失败，未返回 dentry.uuid: {commit}")
    return ALIDOCS_NODE_URL.format(node_id=node_id)
