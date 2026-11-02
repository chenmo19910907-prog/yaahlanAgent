"""MDP 道具离线下发（addPropTaskV2）+ Later custom_831 同轮自动审批。"""

from __future__ import annotations

import base64
import json
import re
import time
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .aegis_sso import AEGIS_SSO_BASE, _follow_redirects_for_cookies, _get_credentials
from .client import http_post_json
from .config import defaults
from .gift import mdp_gift_success as mdp_success
from .prop import fetch_prop_info_by_id

LATER_APP_KEY = "a1745e57-d3f2-4458-a93d-c671cb4b81ea"
LATER_CATEGORY = "custom_831"
DEFAULT_APP_ID = 2005
DEFAULT_USE_TYPE = 20
DEFAULT_PROP_PACKAGE_VALID_DAYS = 30

# type=0 装扮中心（我的装扮；口语「装扮商城」指到账后在商城/我的装扮可见，非背包）
# type=1 礼物面板背包
DELIVERY_CENTER = 0
DELIVERY_BACKPACK = 1

_AUDIT_APPROVED = 2

_VALIDITY_CONFIG_PATH = (
    Path(__file__).resolve().parents[1] / "config" / "prop_offline_validity_days.json"
)
_KNOWN_VALIDITY_BY_PROP: dict[str, str] | None = None


def _load_known_validity_by_prop() -> dict[str, str]:
    global _KNOWN_VALIDITY_BY_PROP
    if _KNOWN_VALIDITY_BY_PROP is not None:
        return _KNOWN_VALIDITY_BY_PROP
    out: dict[str, str] = {}
    if _VALIDITY_CONFIG_PATH.is_file():
        try:
            data = json.loads(_VALIDITY_CONFIG_PATH.read_text(encoding="utf-8"))
            raw = data.get("byPropId") if isinstance(data, dict) else None
            if isinstance(raw, dict):
                for k, v in raw.items():
                    pid = str(k or "").strip()
                    days = str(v or "").strip()
                    if pid and days:
                        out[pid] = days
        except (OSError, json.JSONDecodeError):
            pass
    _KNOWN_VALIDITY_BY_PROP = out
    return out


def parse_validity_map(raw: str) -> dict[str, str]:
    """解析 30006691:1,30004773=7 形式覆盖表。"""
    out: dict[str, str] = {}
    for part in re.split(r"[\s,，、]+", str(raw or "").strip()):
        if not part:
            continue
        if ":" in part:
            pid, days = part.split(":", 1)
        elif "=" in part:
            pid, days = part.split("=", 1)
        else:
            continue
        pid = pid.strip()
        days = days.strip()
        if pid and days:
            out[pid] = days
    return out


def _mdp_base_url() -> str:
    cfg = defaults("query_prop_info")
    return str(cfg.get("baseUrl") or "https://alpha-mdp-user-admin-api-stage.wemomo.com").rstrip("/")


def _parse_id_list(raw: str) -> list[str]:
    parts = re.split(r"[\s,，、]+", str(raw or "").strip())
    return [p for p in (x.strip() for x in parts) if p]


def _later_session_cookies() -> dict[str, str]:
    username, password = _get_credentials()
    redirect_url = "https://later.immomo.com/"
    login_url = (
        f"{AEGIS_SSO_BASE}/{LATER_APP_KEY}?redirect={urllib.parse.quote(redirect_url, safe='')}"
    )
    form_data = urllib.parse.urlencode(
        {
            "email": username,
            "email_password": base64.b64encode(password.encode()).decode(),
            "key": LATER_APP_KEY,
        }
    ).encode()

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    opener = urllib.request.build_opener(NoRedirect)
    req = urllib.request.Request(
        login_url,
        data=form_data,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": "Mozilla/5.0"},
    )
    cookies: dict[str, str] = {}
    try:
        opener.open(req, timeout=15)
    except urllib.error.HTTPError as e:
        location = e.headers.get("Location", "")
        _follow_redirects_for_cookies(location, cookies, max_hops=8)
        for c in e.headers.get_all("Set-Cookie") or []:
            nv = c.split(";")[0].strip()
            if "=" in nv:
                k, v = nv.split("=", 1)
                cookies[k.strip()] = v.strip()
    if not cookies:
        raise RuntimeError("Later SSO 登录失败：未获取 session Cookie")
    return cookies


def _later_json_request(
    method: str,
    url: str,
    cookies: dict[str, str],
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
    headers = {
        "Cookie": cookie_str,
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
    }
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Later HTTP {e.code}: {raw[:500]}") from e
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Later 返回非 JSON: {raw[:300]}") from exc
    if not isinstance(obj, dict):
        raise RuntimeError(f"Later 返回格式异常: {raw[:300]}")
    return obj


def approve_later_wos(
    wos_id: str,
    *,
    category: str = LATER_CATEGORY,
    remark: str = "确认",
    cookies: dict[str, str] | None = None,
) -> dict[str, Any]:
    """GET approve-confirm(type=confirm) → POST approve。"""
    wid = str(wos_id or "").strip()
    if not wid:
        raise ValueError("Later wos_id 不能为空")
    sess = cookies if cookies is not None else _later_session_cookies()
    confirm_url = (
        f"https://later.immomo.com/v3/approve-confirm"
        f"?id={urllib.parse.quote(wid)}&category={urllib.parse.quote(category)}&type=confirm"
    )
    confirm_resp = _later_json_request("GET", confirm_url, sess)
    if confirm_resp.get("ec") != 200:
        raise RuntimeError(f"Later approve-confirm 失败: {confirm_resp}")

    approve_resp = _later_json_request(
        "POST",
        "https://later.immomo.com/v3/approve",
        sess,
        {"id": wid, "category": category, "type": "confirm", "content": remark},
    )
    if approve_resp.get("ec") != 200:
        raise RuntimeError(f"Later approve 失败: {approve_resp}")
    return {"confirm": confirm_resp, "approve": approve_resp}


def _extract_later_wos_id(extra: str) -> str | None:
    blob = extra or ""
    m = re.search(r'laterWosId\\":\\"(\d+)', blob) or re.search(r'"laterWosId":"(\d+)"', blob)
    return m.group(1) if m else None


def find_prop_task(
    *,
    task_id: str | None = None,
    task_name_prefix: str | None = None,
    user_id: str | None = None,
    app_id: int = DEFAULT_APP_ID,
    timeout_s: float = 30.0,
) -> dict[str, Any] | None:
    base = _mdp_base_url()
    body: dict[str, Any] = {"appId": app_id, "pageNo": 1, "pageSize": 20}
    if task_id:
        body["taskId"] = str(task_id).strip()
    if user_id:
        body["userId"] = str(user_id).strip()
    resp = http_post_json(
        f"{base}/propTaskIssueAdmin/queryPropTaskIssue",
        body,
        auth="mdp_nova",
        timeout_s=timeout_s,
    )
    if not mdp_success(resp.get("ec")):
        raise RuntimeError(f"queryPropTaskIssue 失败: {resp}")
    records = (resp.get("data") or {}).get("records") or []
    prefix = (task_name_prefix or "").strip()
    for rec in records:
        if not isinstance(rec, dict):
            continue
        if task_id and str(rec.get("taskId")) != str(task_id).strip():
            continue
        if prefix and not str(rec.get("taskName") or "").startswith(prefix):
            continue
        wos = _extract_later_wos_id(str(rec.get("extra") or ""))
        return {
            "taskId": rec.get("taskId"),
            "taskName": rec.get("taskName"),
            "type": rec.get("type"),
            "auditStatus": rec.get("auditStatus"),
            "laterWosId": wos,
            "laterUrl": f"https://later.immomo.com/v3/detail/{LATER_CATEGORY}/{wos}" if wos else None,
        }
    return None


def wait_audit_approved(
    task_id: str,
    *,
    timeout_s: float = 90.0,
    poll_interval_s: float = 2.0,
    app_id: int = DEFAULT_APP_ID,
) -> int:
    deadline = time.monotonic() + max(5.0, timeout_s)
    last = 0
    while time.monotonic() < deadline:
        info = find_prop_task(task_id=task_id, app_id=app_id)
        if info:
            last = int(info.get("auditStatus") or 0)
            if last == _AUDIT_APPROVED:
                return last
        time.sleep(poll_interval_s)
    return last


def build_prop_list_entries(
    prop_ids: list[str],
    *,
    validity_days_by_prop: dict[str, str] | None = None,
    default_validity_days: str | None = None,
) -> list[dict[str, Any]]:
    overrides = dict(validity_days_by_prop or {})
    known = _load_known_validity_by_prop()
    fallback = str(default_validity_days).strip() if default_validity_days else ""
    out: list[dict[str, Any]] = []
    for pid in prop_ids:
        info = fetch_prop_info_by_id(pid) or {}
        name = str(info.get("propName") or pid)
        days = (
            overrides.get(pid)
            or known.get(pid)
            or fallback
            or "7"
        )
        days = str(days).strip() or "7"
        out.append({"propId": pid, "propName": name, "validityPeriod": days, "num": 1})
    return out


def resolve_delivery_type(target: str) -> int:
    t = str(target or "").strip().lower()
    if t in {"backpack", "bag", "背包", "1"}:
        return DELIVERY_BACKPACK
    if t in {"center", "dress", "装扮中心", "装扮商城", "商城", "我的装扮", "0"}:
        return DELIVERY_CENTER
    raise ValueError(
        f"未知下发目标 {target!r}，可用：center（装扮中心/装扮商城）或 backpack（背包）"
    )


def issue_prop_offline_batch(
    *,
    user_ids: list[str],
    prop_ids: list[str],
    delivery_type: int = DELIVERY_CENTER,
    prop_package_valid_days: int = DEFAULT_PROP_PACKAGE_VALID_DAYS,
    validity_days_by_prop: dict[str, str] | None = None,
    default_validity_days: str | None = None,
    task_name_prefix: str | None = None,
    task_desc: str = "",
    auto_approve: bool = True,
    approve_remark: str = "确认",
    app_id: int = DEFAULT_APP_ID,
    use_type: int = DEFAULT_USE_TYPE,
    timeout_s: float = 30.0,
) -> dict[str, Any]:
    if not user_ids:
        raise ValueError("user_ids 不能为空")
    if not prop_ids:
        raise ValueError("prop_ids 不能为空")

    base = _mdp_base_url()
    prop_list = build_prop_list_entries(
        prop_ids,
        validity_days_by_prop=validity_days_by_prop,
        default_validity_days=(
            str(default_validity_days).strip() if default_validity_days is not None else None
        ),
    )
    later_cookies = _later_session_cookies() if auto_approve else None
    results: list[dict[str, Any]] = []

    for uid in user_ids:
        ts = int(time.time())
        prefix = (task_name_prefix or "agent-prop").strip()
        task_name = f"{prefix}-{uid}-{ts}"
        body: dict[str, Any] = {
            "appId": app_id,
            "type": delivery_type,
            "useType": use_type,
            "taskName": task_name,
            "taskDesc": task_desc or f"离线下发 type={delivery_type} user={uid}",
            "propList": prop_list,
            "userList": [uid],
            "whetherSendMsg": 0,
            "imMsg": "",
            "whetherSkip": 0,
            "skipUrl": "",
            "buttonMsg": "",
        }
        if delivery_type == DELIVERY_BACKPACK:
            body["propPackageValidDays"] = int(prop_package_valid_days)

        resp = http_post_json(
            f"{base}/propTaskIssueAdmin/addPropTaskV2",
            body,
            auth="mdp_nova",
            timeout_s=timeout_s,
        )
        if not mdp_success(resp.get("ec")):
            raise RuntimeError(f"addPropTaskV2 失败 user={uid}: {resp}")

        time.sleep(0.4)
        task_info = find_prop_task(task_name_prefix=task_name, user_id=uid, app_id=app_id)
        if not task_info:
            task_info = find_prop_task(task_name_prefix=f"{prefix}-{uid}", user_id=uid, app_id=app_id)

        approve_result: dict[str, Any] | None = None
        wos = (task_info or {}).get("laterWosId")
        audit = int((task_info or {}).get("auditStatus") or 0)

        if auto_approve and wos and audit != _AUDIT_APPROVED:
            approve_result = approve_later_wos(
                str(wos),
                remark=approve_remark,
                cookies=later_cookies,
            )
            audit = wait_audit_approved(str(task_info.get("taskId")), timeout_s=90.0)
            task_info = find_prop_task(task_id=str(task_info.get("taskId")), app_id=app_id) or task_info
            audit = int((task_info or {}).get("auditStatus") or audit)

        results.append(
            {
                "userId": uid,
                "taskName": task_name,
                "taskId": (task_info or {}).get("taskId"),
                "deliveryType": delivery_type,
                "laterWosId": wos,
                "laterUrl": (task_info or {}).get("laterUrl"),
                "auditStatus": audit,
                "auditApproved": audit == _AUDIT_APPROVED,
                "laterApprove": approve_result,
                "addPropTaskResponse": {"ec": resp.get("ec"), "em": resp.get("em")},
            }
        )

    return {
        "appId": app_id,
        "deliveryType": delivery_type,
        "propIds": prop_ids,
        "userIds": user_ids,
        "autoApprove": auto_approve,
        "results": results,
    }
