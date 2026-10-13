"""MSE MOA 控制台分享：save_data → shareId → src.cn 短链。"""

from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

_MSE_SHORT_APP_ID = "767b0e33727bc325571840df13bd0d01"
_MSE_SHORT_SECRET = "8e5af931e298085764c56d51e8e39495"
_MSE_BASE = "https://mse.wemomo.com"


def _mse_post_json(
    path: str,
    cookie: str,
    payload: dict[str, Any],
    *,
    request_source: str,
    timeout_s: float,
) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        "Cookie": cookie,
        "request-source": request_source,
        "Origin": os.environ.get("MOA_ORIGIN") or _MSE_BASE,
        "Referer": os.environ.get("MOA_REFERER") or f"{_MSE_BASE}/",
    }
    ua = os.environ.get("MOA_USER_AGENT")
    if ua:
        headers["User-Agent"] = ua
    req = urllib.request.Request(f"{_MSE_BASE}{path}", data=body, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace") if e.fp else str(e)
        raise RuntimeError(f"HTTP {e.code}: {raw}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"网络错误: {e}") from e
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"返回不是合法 JSON: {raw[:1000]}") from e
    if not isinstance(obj, dict):
        raise RuntimeError(f"返回不是 object: {raw[:500]}")
    return obj


def payload_to_mse_collection_config(payload: dict[str, Any]) -> dict[str, Any]:
    """将 moa_execute payload JSON 转为 MSE collection/save_data 的 config。"""
    params = payload.get("params")
    if not isinstance(params, list):
        raise ValueError("payload.params 必须是 list")

    editable: list[dict[str, Any]] = []
    for i, p in enumerate(params):
        if not isinstance(p, dict):
            continue
        val = str(p.get("value") if p.get("value") is not None else p.get("txt") or "")
        editable.append(
            {
                "title": p.get("title") or f"参数{i + 1}",
                "name": str(p.get("name") or i + 1),
                "txt": val,
                "json": p.get("json") or "",
                "type": p.get("type") or "string",
                "value": val,
            }
        )
    editable.append({"name": len(params) + 1, "title": "", "txt": "", "json": "", "type": "string", "value": ""})

    settings = payload.get("settings")
    if not isinstance(settings, dict):
        settings = {}

    return {
        "overTime": str(settings.get("time") or "2000"),
        "group": settings.get("group") or "default",
        "serviceHostPort": settings.get("host") or "",
        "moaService": str(payload.get("url") or ""),
        "moaMethod": str(payload.get("method") or ""),
        "editableTabs": editable,
        "headerText": str(payload.get("header") or ""),
        "headerMOAList": [{"key": "", "value": ""}],
        "headerType": settings.get("headerType") or "TXT",
        "moaBodyType": "none",
        "bodyRow": '""',
    }


def _env_block(payload: dict[str, Any]) -> dict[str, str]:
    return {
        "region": str(payload.get("region") or "alpha"),
        "env": str(payload.get("env") or "alpha"),
        "cluster": str(payload.get("cluster") or "stage"),
        "server": str(payload.get("server") or "config"),
        "momoId": str(payload.get("momoId") or ""),
        "momoName": str(payload.get("momoName") or ""),
    }


def build_moa_share_page_url(share_id: str, *, corp: str, cluster: str) -> str:
    return (
        f"{_MSE_BASE}/#/config/app?corp={corp}&env={cluster}"
        f"&serviceType=moa&shareId={share_id}&type=share"
    )


def short_url_sign(page_url: str, timestamp_ms: int) -> str:
    raw = f"{_MSE_SHORT_APP_ID}{page_url}{timestamp_ms}{_MSE_SHORT_SECRET}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def create_moa_share_link(
    payload: dict[str, Any],
    cookie: str,
    *,
    timeout_s: float = 30.0,
) -> dict[str, str]:
    """保存 MOA 配置并生成 src.cn 短链（与 MSE 控制台「分享」一致）。"""
    env = _env_block(payload)
    save_body = {"config": payload_to_mse_collection_config(payload), **env}
    save_resp = _mse_post_json(
        "/apirest/collection/save_data",
        cookie,
        save_body,
        request_source="moaProxy",
        timeout_s=timeout_s,
    )
    if save_resp.get("ec") != 200:
        raise RuntimeError(f"save_data 失败: {save_resp.get('em') or save_resp}")

    share_id = str(save_resp.get("result") or "").strip()
    if not share_id:
        raise RuntimeError(f"save_data 未返回 shareId: {save_resp}")

    page_url = build_moa_share_page_url(share_id, corp=env["region"], cluster=env["cluster"])
    ts = int(time.time() * 1000)
    create_body = {
        "appId": _MSE_SHORT_APP_ID,
        "sign": short_url_sign(page_url, ts),
        "url": page_url,
        "timestamp": ts,
        **env,
    }
    create_resp = _mse_post_json(
        "/apirest/httpproxy/_/create",
        cookie,
        create_body,
        request_source="short_url",
        timeout_s=timeout_s,
    )
    if create_resp.get("code") != 0:
        raise RuntimeError(f"短链创建失败: {create_resp.get('msg') or create_resp}")

    short = str(create_resp.get("data") or "").strip()
    if not short:
        raise RuntimeError(f"短链为空: {create_resp}")

    return {"share_id": share_id, "page_url": page_url, "short_url": short}
