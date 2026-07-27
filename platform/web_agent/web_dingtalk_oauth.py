"""钉钉 H5 OAuth 免登：authCode → userid → Web Cookie 会话。"""

from __future__ import annotations

import json
import logging
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

WEB_AGENT_DIR = Path(__file__).resolve().parent
GATEWAY_DIR = WEB_AGENT_DIR.parent / "dingtalk_gateway"

if str(GATEWAY_DIR) not in sys.path:
    sys.path.insert(0, str(GATEWAY_DIR))
if str(WEB_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_AGENT_DIR))

from env_loader import load_env_local  # noqa: E402
from web_otp_auth import WebAuthUser, get_web_otp_store  # noqa: E402

logger = logging.getLogger("web-agent")

GETUSERINFO_URL = "https://oapi.dingtalk.com/topapi/v2/user/getuserinfo"


def _env_bool(name: str, default: bool = True) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw not in ("0", "false", "no", "off")


def dingtalk_oauth_enabled() -> bool:
    """是否启用钉钉 OAuth 免登（需 ClientId + CorpId）。"""
    if not _env_bool("WEB_AGENT_DINGTALK_OAUTH", True):
        return False
    load_env_local()
    client_id = os.environ.get("DINGTALK_CLIENT_ID", "").strip()
    corp_id = os.environ.get("DINGTALK_CORP_ID", "").strip()
    return bool(client_id and corp_id)


def dingtalk_oauth_public_config() -> dict[str, object]:
    """供前端 JSAPI 使用的公开配置（不含 Secret）。"""
    load_env_local()
    enabled = dingtalk_oauth_enabled()
    return {
        "enabled": enabled,
        "clientId": os.environ.get("DINGTALK_CLIENT_ID", "").strip() if enabled else "",
        "corpId": os.environ.get("DINGTALK_CORP_ID", "").strip() if enabled else "",
    }


def _get_app_access_token() -> str:
    from alidocs_upload import get_access_token  # noqa: WPS433

    return get_access_token()


def _post_topapi(url: str, payload: dict[str, object]) -> dict[str, object]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"钉钉接口 HTTP {exc.code}: {body[:300]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"钉钉接口网络错误: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("钉钉接口返回非 JSON") from exc
    if not isinstance(raw, dict):
        raise RuntimeError("钉钉接口返回格式异常")
    return raw


def resolve_user_from_auth_code(auth_code: str) -> tuple[WebAuthUser | None, str | None]:
    """用免登 authCode 解析钉钉用户；返回 (user, error_message)。"""
    if not dingtalk_oauth_enabled():
        return None, "钉钉 OAuth 免登未启用"
    code = (auth_code or "").strip()
    if not code:
        return None, "缺少 authCode"

    try:
        access_token = _get_app_access_token()
    except (RuntimeError, OSError, urllib.error.URLError) as exc:
        logger.warning("OAuth 获取 access_token 失败: %s", exc)
        return None, "钉钉应用凭证未配置或无效"

    url = f"{GETUSERINFO_URL}?access_token={access_token}"
    try:
        data = _post_topapi(url, {"code": code})
    except RuntimeError as exc:
        logger.warning("OAuth getuserinfo 失败: %s", exc)
        return None, str(exc)

    errcode = int(data.get("errcode") or 0)
    if errcode != 0:
        errmsg = str(data.get("errmsg") or "未知错误")
        logger.warning("OAuth getuserinfo errcode=%s msg=%s", errcode, errmsg)
        if errcode in (40078, 40079, 40080):
            return None, "免登授权码无效或已过期，请关闭页面重试"
        return None, f"钉钉身份验证失败：{errmsg}"

    result = data.get("result")
    if not isinstance(result, dict):
        return None, "钉钉返回用户信息为空"

    staff_id = str(result.get("userid") or "").strip()
    if not staff_id:
        return None, "未能解析钉钉用户 ID"

    display_name = ""
    for key in ("name", "nick", "nickname"):
        value = str(result.get(key) or "").strip()
        if value:
            display_name = value
            break

    return WebAuthUser(staff_id=staff_id, display_name=display_name), None


def login_with_auth_code(auth_code: str) -> tuple[str | None, WebAuthUser | None, str | None]:
    """authCode 换用户并创建 Web 会话。返回 (token, user, error)。"""
    user, err = resolve_user_from_auth_code(auth_code)
    if user is None:
        return None, None, err or "钉钉登录失败"
    return get_web_otp_store().create_session_for_staff(
        user.staff_id,
        display_name=user.display_name,
    )
