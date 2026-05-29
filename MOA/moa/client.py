"""HTTP 客户端与响应解析。"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any


def http_post_json(url: str, cookie: str, payload: dict[str, Any], timeout_s: float) -> dict[str, Any]:
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

    req = urllib.request.Request(url=url, data=body, method="POST", headers=headers)
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

    def __init__(self, entry_url: str, cookie: str, timeout_ms: int = 5000) -> None:
        self.entry_url = entry_url
        self.cookie = cookie
        self.timeout_s = max(timeout_ms, 1) / 1000.0

    def post(self, payload: dict[str, Any]) -> dict[str, Any]:
        return http_post_json(self.entry_url, self.cookie, payload, self.timeout_s)

    def post_expect_inner_ok(self, payload: dict[str, Any], *, action: str) -> Any:
        resp = self.post(payload)
        ec, em, _ = extract_ec_em_result(resp)
        if not outer_success(ec):
            raise RuntimeError(f"{action}失败(外层): ec={ec}, em={em}")
        inner_ec, inner_em, inner_result = extract_inner_result(resp)
        if inner_ec != 0:
            raise RuntimeError(f"{action}失败(业务): ec={inner_ec}, em={inner_em}")
        return inner_result
