"""MSE 配置中心 HTTP 客户端。"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


def _is_auth_body(body: str) -> bool:
    lower = (body or "").lower()
    if "aegis sso" in lower:
        return True
    if "login" in lower and "sso" in lower:
        return True
    if "<!doctype html>" in lower and ("aegis" in lower or "login" in lower):
        return True
    return False


def _is_auth_error(code: int, body: str) -> bool:
    if code in (401, 403):
        return True
    if code == 302 and "aegis" in (body or "").lower():
        return True
    return _is_auth_body(body)


def _current_mse_cookie(fallback: str) -> str:
    for key in ("MSE_COOKIE", "MOA_COOKIE", "MOA_ONLINE_COOKIE"):
        refreshed = os.environ.get(key, "").strip()
        if refreshed:
            return refreshed
    return fallback


def _try_auto_refresh_mse() -> bool:
    """通过 Aegis SSO 刷新 MOA/MSE Cookie，成功返回 True。"""
    repo_root = Path(__file__).resolve().parents[2]
    admin_dir = repo_root / "Admin"
    if str(admin_dir) not in sys.path:
        sys.path.insert(0, str(admin_dir))
    try:
        from admin.aegis_sso import auto_refresh_moa
        from admin.env import load_local_env

        load_local_env(str(admin_dir))
        sys.stderr.write("[Auto-Refresh] MSE Cookie 过期，正在通过 Aegis SSO 重新登录...\n")
        result = auto_refresh_moa()
        if result.success:
            user = result.username or result.momo_id or "unknown"
            sys.stderr.write(f"[Auto-Refresh] 刷新成功: user={user}\n")
            return True
        sys.stderr.write(f"[Auto-Refresh] 刷新失败: {result.error}\n")
        return False
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"[Auto-Refresh] 异常: {exc}\n")
        return False


def _headers(cookie: str) -> dict[str, str]:
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json, text/plain, */*",
        "Cookie": cookie,
        "request-source": os.environ.get("MSE_REQUEST_SOURCE", "config"),
    }
    for env_key, header_key in (
        ("MSE_ORIGIN", "Origin"),
        ("MSE_REFERER", "Referer"),
        ("MSE_USER_AGENT", "User-Agent"),
    ):
        value = os.environ.get(env_key)
        if value:
            headers[header_key] = value
    if "Origin" not in headers:
        headers["Origin"] = "https://mse.wemomo.com"
    if "Referer" not in headers:
        headers["Referer"] = "https://mse.wemomo.com/"
    return headers


def _rebuild_request_with_cookie(req: urllib.request.Request, cookie: str) -> urllib.request.Request:
    headers = dict(req.headers)
    headers["Cookie"] = cookie
    return urllib.request.Request(
        url=req.full_url,
        data=req.data,
        method=req.get_method(),
        headers=headers,
    )


def _parse_ec_payload(raw: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"返回不是合法 JSON: {raw[:800]}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("返回 JSON 不是 object")
    return payload


def _ensure_ec_success(payload: dict[str, Any], *, action: str) -> Any:
    ec = payload.get("ec")
    try:
        ec_int = int(ec)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"无法解析 ec: {ec}") from exc
    if ec_int not in (0, 200):
        em = payload.get("em")
        raise RuntimeError(f"{action}失败: ec={ec_int}, em={em}")
    return payload.get("result")


def _post_form_request(
    req: urllib.request.Request,
    *,
    timeout_s: float,
    auto_refresh: bool = True,
    action: str = "请求",
    _retried: bool = False,
) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") if exc.fp else str(exc)
        if not _retried and auto_refresh and _is_auth_error(exc.code, detail):
            if _try_auto_refresh_mse():
                new_cookie = _current_mse_cookie("")
                new_req = _rebuild_request_with_cookie(req, new_cookie)
                return _post_form_request(
                    new_req,
                    timeout_s=timeout_s,
                    auto_refresh=auto_refresh,
                    action=action,
                    _retried=True,
                )
        raise RuntimeError(f"HTTP {exc.code}: {detail[:800]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"网络错误: {exc.reason}") from exc

    if not _retried and auto_refresh and _is_auth_body(raw):
        if _try_auto_refresh_mse():
            new_cookie = _current_mse_cookie("")
            new_req = _rebuild_request_with_cookie(req, new_cookie)
            return _post_form_request(
                new_req,
                timeout_s=timeout_s,
                auto_refresh=auto_refresh,
                action=action,
                _retried=True,
            )
    return _parse_ec_payload(raw)


def _post_httpproxy_form(
    *,
    base_url: str,
    cookie: str,
    path: str,
    form: dict[str, Any],
    region: str,
    env: str,
    cluster: str,
    server: str = "config",
    momo_id: str = "",
    momo_name: str = "",
    timeout_s: float = 30.0,
    auto_refresh: bool = True,
    action: str = "请求",
) -> dict[str, Any]:
    body_fields = dict(form)
    body_fields.setdefault("region", region)
    body_fields.setdefault("env", env)
    body_fields.setdefault("cluster", cluster)
    body_fields.setdefault("server", server)
    if momo_id:
        body_fields.setdefault("momoId", momo_id)
    if momo_name:
        body_fields.setdefault("momoName", momo_name)

    encoded: dict[str, str] = {}
    for key, value in body_fields.items():
        if value is None:
            continue
        if isinstance(value, (dict, list)):
            encoded[key] = json.dumps(value, ensure_ascii=False)
        else:
            encoded[key] = str(value)

    root = base_url.rstrip("/")
    url = f"{root}/apirest/httpproxy{path}"
    body = urllib.parse.urlencode(encoded).encode("utf-8")
    cookie = _current_mse_cookie(cookie)
    req = urllib.request.Request(url, data=body, method="POST", headers=_headers(cookie))
    return _post_form_request(req, timeout_s=timeout_s, auto_refresh=auto_refresh, action=action)


def _post_apirest_form(
    *,
    base_url: str,
    cookie: str,
    path: str,
    form: dict[str, Any] | None = None,
    timeout_s: float = 30.0,
    auto_refresh: bool = True,
    action: str = "请求",
) -> dict[str, Any]:
    root = base_url.rstrip("/")
    url = f"{root}{path}"
    body = urllib.parse.urlencode(form or {}).encode("utf-8")
    cookie = _current_mse_cookie(cookie)
    req = urllib.request.Request(url, data=body, method="POST", headers=_headers(cookie))
    return _post_form_request(req, timeout_s=timeout_s, auto_refresh=auto_refresh, action=action)


def _post_configs_request(
    req: urllib.request.Request,
    *,
    timeout_s: float,
    auto_refresh: bool = True,
    _retried: bool = False,
) -> list[dict[str, Any]]:
    payload = _post_form_request(
        req,
        timeout_s=timeout_s,
        auto_refresh=auto_refresh,
        action="读取配置",
        _retried=_retried,
    )
    result = _ensure_ec_success(payload, action="读取配置")
    if result is None:
        return []
    if not isinstance(result, list):
        raise RuntimeError("result 不是 array")
    return [item for item in result if isinstance(item, dict)]


def get_configs_by_namespace(
    *,
    base_url: str,
    cookie: str,
    region: str,
    app_key: str,
    name_space: str,
    cluster: str,
    env: str,
    config_key: str = "",
    order: bool = False,
    server: str = "config",
    timeout_s: float = 30.0,
    auto_refresh: bool = True,
) -> list[dict[str, Any]]:
    """调用 getConfigsByAppKeyAndNameSpace，返回 result 配置列表。"""
    root = base_url.rstrip("/")
    path = "/apirest/httpproxy/config/getConfigsByAppKeyAndNameSpace"
    url = f"{root}{path}"
    body = urllib.parse.urlencode(
        {
            "region": region,
            "appKey": app_key,
            "nameSpace": name_space,
            "cluster": cluster,
            "key": config_key or "",
            "order": "true" if order else "false",
            "env": env,
            "server": server,
        }
    ).encode("utf-8")
    cookie = _current_mse_cookie(cookie)
    req = urllib.request.Request(url, data=body, method="POST", headers=_headers(cookie))
    return _post_configs_request(req, timeout_s=timeout_s, auto_refresh=auto_refresh)


def get_session_user(
    *,
    base_url: str,
    cookie: str,
    timeout_s: float = 30.0,
    auto_refresh: bool = True,
) -> dict[str, Any]:
    payload = _post_apirest_form(
        base_url=base_url,
        cookie=cookie,
        path="/apirest/session/user",
        timeout_s=timeout_s,
        auto_refresh=auto_refresh,
        action="读取 session",
    )
    result = _ensure_ec_success(payload, action="读取 session")
    if not isinstance(result, dict):
        raise RuntimeError("session result 不是 object")
    return result


def get_config_by_id(
    *,
    base_url: str,
    cookie: str,
    region: str,
    env: str,
    cluster: str,
    app_key: str,
    config_id: int | str,
    timeout_s: float = 30.0,
    auto_refresh: bool = True,
) -> dict[str, Any]:
    payload = _post_httpproxy_form(
        base_url=base_url,
        cookie=cookie,
        path="/config/getConfigById",
        form={"id": str(config_id), "appKey": app_key},
        region=region,
        env=env,
        cluster=cluster,
        timeout_s=timeout_s,
        auto_refresh=auto_refresh,
        action="读取配置详情",
    )
    result = _ensure_ec_success(payload, action="读取配置详情")
    if not isinstance(result, dict):
        raise RuntimeError("配置详情 result 不是 object")
    return result


def get_config_by_id_and_cluster(
    *,
    base_url: str,
    cookie: str,
    region: str,
    env: str,
    cluster: str,
    app_key: str,
    config_id: int | str,
    timeout_s: float = 30.0,
    auto_refresh: bool = True,
) -> dict[str, Any]:
    payload = _post_httpproxy_form(
        base_url=base_url,
        cookie=cookie,
        path="/config/getConfigByIdAndCluster",
        form={"id": str(config_id), "appKey": app_key, "cluster": cluster},
        region=region,
        env=env,
        cluster=cluster,
        timeout_s=timeout_s,
        auto_refresh=auto_refresh,
        action="读取集群配置详情",
    )
    result = _ensure_ec_success(payload, action="读取集群配置详情")
    if not isinstance(result, dict):
        raise RuntimeError("集群配置详情 result 不是 object")
    return result


def save_or_update_config_model(
    *,
    base_url: str,
    cookie: str,
    region: str,
    env: str,
    cluster: str,
    payload: dict[str, Any],
    timeout_s: float = 30.0,
    auto_refresh: bool = True,
) -> dict[str, Any]:
    response = _post_httpproxy_form(
        base_url=base_url,
        cookie=cookie,
        path="/record/saveOrUpdateConfigModel",
        form={"json": json.dumps(payload, ensure_ascii=False), "relationEnvs": ""},
        region=region,
        env=env,
        cluster=cluster,
        timeout_s=timeout_s,
        auto_refresh=auto_refresh,
        action="保存配置",
    )
    _ensure_ec_success(response, action="保存配置")
    return response


def create_publish_record(
    *,
    base_url: str,
    cookie: str,
    region: str,
    env: str,
    cluster: str,
    payload: dict[str, Any],
    momo_id: str = "",
    momo_name: str = "",
    timeout_s: float = 30.0,
    auto_refresh: bool = True,
) -> int:
    response = _post_httpproxy_form(
        base_url=base_url,
        cookie=cookie,
        path="/record/createPublishRecord",
        form={"json": json.dumps(payload, ensure_ascii=False)},
        region=region,
        env=env,
        cluster=cluster,
        momo_id=momo_id,
        momo_name=momo_name,
        timeout_s=timeout_s,
        auto_refresh=auto_refresh,
        action="创建发布记录",
    )
    result = _ensure_ec_success(response, action="创建发布记录")
    try:
        return int(result)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"发布 recordId 无效: {result}") from exc


def skip_grey_publish(
    *,
    base_url: str,
    cookie: str,
    region: str,
    env: str,
    cluster: str,
    record_id: int | str,
    momo_id: str = "",
    momo_name: str = "",
    timeout_s: float = 30.0,
    auto_refresh: bool = True,
) -> dict[str, Any]:
    response = _post_httpproxy_form(
        base_url=base_url,
        cookie=cookie,
        path="/record/updatePublishRecordProcess",
        form={"id": str(record_id)},
        region=region,
        env=env,
        cluster=cluster,
        momo_id=momo_id,
        momo_name=momo_name,
        timeout_s=timeout_s,
        auto_refresh=auto_refresh,
        action="跳过灰度",
    )
    _ensure_ec_success(response, action="跳过灰度")
    return response


def all_publish_by_record(
    *,
    base_url: str,
    cookie: str,
    region: str,
    env: str,
    cluster: str,
    record_id: int | str,
    clear_part: dict[str, bool] | None = None,
    momo_id: str = "",
    momo_name: str = "",
    timeout_s: float = 30.0,
    auto_refresh: bool = True,
) -> dict[str, Any]:
    response = _post_httpproxy_form(
        base_url=base_url,
        cookie=cookie,
        path="/record/allPublishByRecord",
        form={
            "id": str(record_id),
            "clearPart": json.dumps(clear_part or {cluster: True}, ensure_ascii=False),
        },
        region=region,
        env=env,
        cluster=cluster,
        momo_id=momo_id,
        momo_name=momo_name,
        timeout_s=timeout_s,
        auto_refresh=auto_refresh,
        action="全量发布",
    )
    _ensure_ec_success(response, action="全量发布")
    return response


def get_publish_check_by_cluster(
    *,
    base_url: str,
    cookie: str,
    region: str,
    env: str,
    cluster: str,
    record_id: int | str,
    momo_id: str = "",
    momo_name: str = "",
    timeout_s: float = 30.0,
    auto_refresh: bool = True,
) -> dict[str, Any]:
    response = _post_httpproxy_form(
        base_url=base_url,
        cookie=cookie,
        path="/record/getInstanceByCluster",
        form={"id": str(record_id)},
        region=region,
        env=env,
        cluster=cluster,
        momo_id=momo_id,
        momo_name=momo_name,
        timeout_s=timeout_s,
        auto_refresh=auto_refresh,
        action="全量发布校验",
    )
    result = _ensure_ec_success(response, action="全量发布校验")
    if not isinstance(result, dict):
        raise RuntimeError("全量发布校验 result 不是 object")
    return result


def complete_publish_record(
    *,
    base_url: str,
    cookie: str,
    region: str,
    env: str,
    cluster: str,
    record_id: int | str,
    momo_id: str = "",
    momo_name: str = "",
    timeout_s: float = 30.0,
    auto_refresh: bool = True,
) -> dict[str, Any]:
    response = _post_httpproxy_form(
        base_url=base_url,
        cookie=cookie,
        path="/record/complete",
        form={"id": str(record_id)},
        region=region,
        env=env,
        cluster=cluster,
        momo_id=momo_id,
        momo_name=momo_name,
        timeout_s=timeout_s,
        auto_refresh=auto_refresh,
        action="完成发布",
    )
    _ensure_ec_success(response, action="完成发布")
    return response
