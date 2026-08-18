"""HTTP 客户端与响应解析。"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
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
    """判断是否为认证/授权失败（需要刷新 MOA Cookie）。"""
    if code in (401, 403):
        return True
    if code == 302 and "aegis" in (body or "").lower():
        return True
    return _is_auth_body(body)


def _current_moa_cookie(fallback: str) -> str:
    refreshed = os.environ.get("MOA_COOKIE", "").strip()
    return refreshed or fallback


def _try_auto_refresh_moa() -> bool:
    """通过 Aegis SSO 刷新 MOA Cookie，成功返回 True。"""
    repo_root = Path(__file__).resolve().parents[2]
    admin_dir = repo_root / "Admin"
    if str(admin_dir) not in sys.path:
        sys.path.insert(0, str(admin_dir))
    try:
        from admin.aegis_sso import auto_refresh_moa
        from admin.env import load_local_env

        load_local_env(str(admin_dir))
        sys.stderr.write("[Auto-Refresh] MOA Cookie 过期，正在通过 Aegis SSO 重新登录...\n")
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


def _rebuild_request_with_cookie(req: urllib.request.Request, cookie: str) -> urllib.request.Request:
    headers = dict(req.headers)
    headers["Cookie"] = cookie
    return urllib.request.Request(
        url=req.full_url,
        data=req.data,
        method=req.get_method(),
        headers=headers,
    )


def _build_post_request(url: str, cookie: str, payload: dict[str, Any]) -> urllib.request.Request:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        "Cookie": cookie,
    }
    for env_key, header_key in (
        ("MOA_REQUEST_SOURCE", "request-source"),
        ("MOA_ORIGIN", "Origin"),
        ("MOA_REFERER", "Referer"),
        ("MOA_USER_AGENT", "User-Agent"),
    ):
        value = os.environ.get(env_key)
        if value:
            headers[header_key] = value
    return urllib.request.Request(url=url, data=body, method="POST", headers=headers)


def http_post_json(
    url: str,
    cookie: str,
    payload: dict[str, Any],
    timeout_s: float,
    *,
    auto_refresh: bool = True,
    _retried: bool = False,
) -> dict[str, Any]:
    cookie = _current_moa_cookie(cookie)
    req = _build_post_request(url, cookie, payload)
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace") if e.fp else str(e)
        if not _retried and auto_refresh and _is_auth_error(e.code, raw):
            if _try_auto_refresh_moa():
                new_cookie = _current_moa_cookie(cookie)
                return http_post_json(
                    url,
                    new_cookie,
                    payload,
                    timeout_s,
                    auto_refresh=auto_refresh,
                    _retried=True,
                )
        raise RuntimeError(f"HTTP {e.code}: {raw}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"网络错误: {e}") from e

    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as e:
        if not _retried and auto_refresh and _is_auth_body(raw):
            if _try_auto_refresh_moa():
                new_cookie = _current_moa_cookie(cookie)
                return http_post_json(
                    url,
                    new_cookie,
                    payload,
                    timeout_s,
                    auto_refresh=auto_refresh,
                    _retried=True,
                )
        raise RuntimeError(f"返回不是合法 JSON: {raw[:1000]}") from e
    if not isinstance(obj, dict):
        raise RuntimeError("返回 JSON 不是 object")
    return obj


def extract_ec_em_result(resp: dict[str, Any]) -> tuple[int | None, str | None, Any]:
    ec = resp.get("ec")
    em = resp.get("em")
    result = resp.get("result")
    if isinstance(ec, bool):
        ec = int(ec)
    if ec is not None and not isinstance(ec, int):
        try:
            ec = int(ec)
        except (TypeError, ValueError):
            ec = None
    if em is not None and not isinstance(em, str):
        em = str(em)
    return ec, em, result


def outer_success(ec: int | None) -> bool:
    return ec in (0, 200)


def extract_inner_result(resp: dict[str, Any]) -> tuple[int, str, Any]:
    inner = resp.get("result")
    if not isinstance(inner, dict):
        raise RuntimeError("业务返回 result 字段不是 object")
    try:
        inner_ec = int(inner.get("ec"))
    except (TypeError, ValueError) as e:
        raise RuntimeError(f"无法解析业务 ec: {inner.get('ec')}") from e
    inner_em = inner.get("em")
    return inner_ec, inner_em if isinstance(inner_em, str) else str(inner_em), inner.get("result")


def parse_current_exp_from_inner(inner_result: Any) -> int:
    try:
        return int(float(inner_result))
    except (TypeError, ValueError) as e:
        raise RuntimeError(f"无法解析当前经验值: {inner_result}") from e


class MoaClient:
    """封装 MOA 入口，复合流程复用同一连接配置。"""

    def __init__(
        self,
        entry_url: str,
        cookie: str,
        timeout_ms: int = 5000,
        *,
        auto_refresh: bool = True,
    ) -> None:
        self.entry_url = entry_url
        self.cookie = cookie
        self.timeout_s = max(timeout_ms, 1) / 1000.0
        self.auto_refresh = auto_refresh

    def post(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = http_post_json(
            self.entry_url,
            self.cookie,
            payload,
            self.timeout_s,
            auto_refresh=self.auto_refresh,
        )
        latest = _current_moa_cookie(self.cookie)
        if latest:
            self.cookie = latest
        return result

    def post_expect_inner_ok(self, payload: dict[str, Any], *, action: str) -> Any:
        resp = self.post(payload)
        ec, em, _ = extract_ec_em_result(resp)
        if not outer_success(ec):
            raise RuntimeError(f"{action}失败(外层): ec={ec}, em={em}")
        inner_ec, inner_em, inner_result = extract_inner_result(resp)
        if inner_ec != 0:
            raise RuntimeError(f"{action}失败(业务): ec={inner_ec}, em={inner_em}")
        return inner_result
