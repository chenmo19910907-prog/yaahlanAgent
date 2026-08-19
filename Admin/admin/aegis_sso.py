"""Aegis SSO 自动登录模块。

支持：
- LDAP 方式（邮箱别名 + 密码 base64）
- 多平台 app key 配置
- 自动 token 交换（Yaahlan JWT / MSE Cookie / MDP Nova Cookie）
- 失败时自动重新登录

环境变量（写入 Admin/.env.local）：
  AEGIS_USERNAME=dingliang8401
  AEGIS_PASSWORD=<密码明文>
"""

from __future__ import annotations

import base64
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

AEGIS_SSO_BASE = "https://aegis.immomo.com/sso/login"

# 各平台 SSO App Key
APP_KEYS = {
    "yaahlan_staging": "c9f8406b-f2c6-4d21-b97e-ca624375ecee",
    "yaahlan_online": "b8584de3-7226-4c85-930e-ea8b0e878175",
    "moa_mse": "b39691dd-5364-4bd1-a2ee-f65cf6ffa1be",
    "mdp_nova_alpha": "9b385e46-e087-43a4-ac77-d70d08617151",
}

# Token 交换 API
TOKEN_EXCHANGE_URLS = {
    "yaahlan_staging": "https://lego-test.wemomo.com/api/session/auth/yaahlan",
    "yaahlan_online": "https://lego.wemomo.com/api/session/auth/yaahlan",
}

# 各平台默认 redirect URL
REDIRECT_URLS = {
    "yaahlan_staging": "https://test-s.immomo.com/fep/momo/yaahlan-fe/yaahlan-operation-manager-platform/",
    "yaahlan_online": "https://www.yaahlan.fun/fep/momo/yaahlan-fe/yaahlan-operation-manager-platform/",
    "moa_mse": "https://mse.wemomo.com/",
    "mdp_nova_alpha": "https://mdp-nova-alpha.wemomo.com/",
}

MDP_AUTH_API_BASE = "https://mdp-auth-api-alpha.wemomo.com"


def _follow_redirects_for_cookies(
    url: str,
    cookies: dict[str, str],
    max_hops: int = 5,
) -> None:
    """跟踪重定向链路，收集沿途所有 Set-Cookie。"""

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    opener = urllib.request.build_opener(NoRedirect)

    for _ in range(max_hops):
        if not url:
            break
        cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
        req = urllib.request.Request(
            url, method="GET",
            headers={"Cookie": cookie_str, "User-Agent": "Mozilla/5.0"},
        )
        try:
            resp = opener.open(req, timeout=10)
            for c in resp.headers.get_all("Set-Cookie") or []:
                name_val = c.split(";")[0].strip()
                if "=" in name_val:
                    k, v = name_val.split("=", 1)
                    cookies[k.strip()] = v.strip()
            break  # 200 = done
        except urllib.error.HTTPError as e:
            for c in e.headers.get_all("Set-Cookie") or []:
                name_val = c.split(";")[0].strip()
                if "=" in name_val:
                    k, v = name_val.split("=", 1)
                    cookies[k.strip()] = v.strip()
            if e.code in (301, 302, 303, 307):
                url = e.headers.get("Location", "")
            else:
                break
        except Exception:
            break


@dataclass
class SSOLoginResult:
    success: bool
    sso_token: str = ""
    jwt_token: str = ""
    momo_id: str = ""
    username: str = ""
    cookies: dict[str, str] | None = None
    error: str = ""


def _get_credentials() -> tuple[str, str]:
    """从环境变量获取 Aegis 登录凭证。"""
    username = os.environ.get("AEGIS_USERNAME", "").strip()
    password = os.environ.get("AEGIS_PASSWORD", "").strip()
    if not username:
        username = os.environ.get("ADMIN_AEGIS_USERNAME", "").strip()
    if not password:
        password = os.environ.get("ADMIN_AEGIS_PASSWORD", "").strip()
    if not username or not password:
        raise ValueError(
            "缺少 Aegis 登录凭证，请在 Admin/.env.local 中设置 AEGIS_USERNAME 和 AEGIS_PASSWORD"
        )
    return username, password


def sso_login(
    platform: str = "yaahlan_staging",
    *,
    username: str | None = None,
    password: str | None = None,
) -> SSOLoginResult:
    """
    通过 Aegis SSO LDAP 方式登录指定平台。

    Args:
        platform: 平台名称（yaahlan_staging / yaahlan_online / moa_mse）
        username: 邮箱别名（为空则从环境变量读取）
        password: 密码明文（为空则从环境变量读取）

    Returns:
        SSOLoginResult 包含 sso_token、jwt_token 等
    """
    if not username or not password:
        username, password = _get_credentials()

    app_key = APP_KEYS.get(platform)
    if not app_key:
        return SSOLoginResult(success=False, error=f"未知平台: {platform}")

    redirect_url = REDIRECT_URLS.get(platform, "")

    # Step 1: POST Aegis SSO 登录
    login_url = f"{AEGIS_SSO_BASE}/{app_key}?redirect={urllib.parse.quote(redirect_url, safe='')}"
    encoded_password = base64.b64encode(password.encode()).decode()
    form_data = urllib.parse.urlencode({
        "email": username,
        "email_password": encoded_password,
        "key": app_key,
    }).encode()

    req = urllib.request.Request(
        login_url,
        data=form_data,
        method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        },
    )

    try:
        # 不跟踪重定向，手动处理
        opener = urllib.request.build_opener(urllib.request.HTTPRedirectHandler)

        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None

        opener = urllib.request.build_opener(NoRedirect)
        try:
            resp = opener.open(req, timeout=15)
            # 如果没有重定向（不应该发生），检查响应
            return SSOLoginResult(success=False, error="SSO 未返回重定向")
        except urllib.error.HTTPError as e:
            if e.code in (301, 302, 303, 307):
                location = e.headers.get("Location", "")
                cookies_raw = e.headers.get_all("Set-Cookie") or []
            else:
                return SSOLoginResult(success=False, error=f"SSO 登录失败: HTTP {e.code}")
    except Exception as e:
        return SSOLoginResult(success=False, error=f"SSO 请求异常: {e}")

    # 解析 redirect Location 中的 token
    sso_token = ""
    momo_id = ""
    token_match = re.search(r"[?&]token=([^&]+)", location)
    if token_match:
        sso_token = token_match.group(1)
    momoid_match = re.search(r"[?&]momoid=([^&]+)", location)
    if momoid_match:
        momo_id = momoid_match.group(1)

    if not sso_token:
        return SSOLoginResult(success=False, error=f"SSO 重定向中未找到 token: {location}")

    # 解析 cookies
    parsed_cookies: dict[str, str] = {}
    for cookie_str in cookies_raw:
        name_val = cookie_str.split(";")[0].strip()
        if "=" in name_val:
            k, v = name_val.split("=", 1)
            parsed_cookies[k.strip()] = v.strip()

    # Step 2: 对 Yaahlan 平台，用 token 换 JWT
    jwt_token = ""
    username_result = ""
    exchange_url = TOKEN_EXCHANGE_URLS.get(platform)
    if exchange_url:
        try:
            exchange_req = urllib.request.Request(
                f"{exchange_url}?token={sso_token}",
                method="GET",
                headers={"Accept": "application/json"},
            )
            with urllib.request.urlopen(exchange_req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
            if data.get("status") == 0 and data.get("data"):
                jwt_token = data["data"].get("jwtToken", "")
                username_result = data["data"].get("username", "")
                if not momo_id:
                    momo_id = data["data"].get("momoId", "")
        except Exception as e:
            return SSOLoginResult(
                success=False,
                sso_token=sso_token,
                error=f"Token 交换失败: {e}",
            )

    # Step 3: 对 MOA/MSE 平台，跟踪多跳重定向获取 session cookie
    if platform == "moa_mse":
        _follow_redirects_for_cookies(location, parsed_cookies, max_hops=5)

    # Step 3b: MDP Nova → callbackAegis 换取 alpha_mdp_aegis_token
    if platform == "mdp_nova_alpha":
        return _complete_mdp_nova_login(sso_token, momo_id, parsed_cookies)

    return SSOLoginResult(
        success=True,
        sso_token=sso_token,
        jwt_token=jwt_token,
        momo_id=momo_id,
        username=username_result,
        cookies=parsed_cookies,
    )


def _complete_mdp_nova_login(
    sso_token: str,
    momo_id: str,
    cookies: dict[str, str],
) -> SSOLoginResult:
    """SSO 成功后调用 MDP Auth callbackAegis，换取 alpha_mdp_aegis_token。"""
    if not sso_token or not momo_id:
        return SSOLoginResult(success=False, error="SSO 重定向缺少 token 或 momoid")

    callback_url = (
        f"{MDP_AUTH_API_BASE}/login/callbackAegis"
        f"?momoid={urllib.parse.quote(momo_id, safe='')}"
        f"&token={urllib.parse.quote(sso_token, safe='')}"
    )
    cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
    req = urllib.request.Request(
        callback_url,
        method="GET",
        headers={"Cookie": cookie_str, "User-Agent": "Mozilla/5.0"},
    )

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    opener = urllib.request.build_opener(NoRedirect)
    try:
        resp = opener.open(req, timeout=15)
        for c in resp.headers.get_all("Set-Cookie") or []:
            name_val = c.split(";")[0].strip()
            if "=" in name_val:
                k, v = name_val.split("=", 1)
                cookies[k.strip()] = v.strip()
    except urllib.error.HTTPError as e:
        for c in e.headers.get_all("Set-Cookie") or []:
            name_val = c.split(";")[0].strip()
            if "=" in name_val:
                k, v = name_val.split("=", 1)
                cookies[k.strip()] = v.strip()
        if e.code not in (200, 301, 302, 303, 307):
            body = e.read().decode("utf-8", errors="replace") if e.fp else str(e)
            return SSOLoginResult(success=False, error=f"callbackAegis 失败: HTTP {e.code}: {body[:200]}")
    except Exception as e:
        return SSOLoginResult(success=False, error=f"callbackAegis 请求异常: {e}")

    aegis_token = cookies.get("alpha_mdp_aegis_token", "").strip()
    if not aegis_token:
        return SSOLoginResult(success=False, error="callbackAegis 未返回 alpha_mdp_aegis_token")

    return SSOLoginResult(
        success=True,
        sso_token=sso_token,
        momo_id=momo_id,
        cookies=cookies,
    )


def refresh_mdp_nova_env() -> SSOLoginResult:
    """刷新 MDP Nova Cookie 并写入环境变量。"""
    result = sso_login("mdp_nova_alpha")
    if not result.success:
        return result

    aegis_token = (result.cookies or {}).get("alpha_mdp_aegis_token", "").strip()
    if not aegis_token:
        return SSOLoginResult(success=False, error="未获取 alpha_mdp_aegis_token")

    os.environ["MDP_AEGIS_TOKEN"] = aegis_token
    os.environ["MDP_CLOUD_AEGIS_TOKEN"] = aegis_token
    return result


def auto_refresh_mdp_nova(env_file: str | Path | None = None) -> SSOLoginResult:
    """一键刷新 MDP Nova Token 并持久化到 Admin/.env.local。"""
    result = refresh_mdp_nova_env()
    if not result.success:
        return result

    aegis_token = os.environ["MDP_AEGIS_TOKEN"]
    if env_file is None:
        repo_root = Path(__file__).resolve().parents[2]
        env_file = repo_root / "Admin" / ".env.local"

    update_env_local(env_file, {
        "MDP_AEGIS_TOKEN": aegis_token,
        "MDP_CLOUD_AEGIS_TOKEN": aegis_token,
    })
    return result


def refresh_yaahlan_env(platform: str = "yaahlan_staging") -> SSOLoginResult:
    """
    刷新 Yaahlan Admin 的 SSO Token 和 JWT，并写入环境变量。

    自动更新 ADMIN_SSO_TOKEN / ADMIN_YAAHLAN_JWT（staging）
    或 ADMIN_ONLINE_SSO_TOKEN / ADMIN_ONLINE_YAAHLAN_JWT（online）
    """
    result = sso_login(platform)
    if not result.success:
        return result

    if platform == "yaahlan_staging":
        os.environ["ADMIN_SSO_TOKEN"] = result.sso_token
        os.environ["ADMIN_YAAHLAN_JWT"] = result.jwt_token
    elif platform == "yaahlan_online":
        os.environ["ADMIN_ONLINE_SSO_TOKEN"] = result.sso_token
        os.environ["ADMIN_ONLINE_YAAHLAN_JWT"] = result.jwt_token

    return result


def refresh_moa_env() -> SSOLoginResult:
    """刷新 MOA/MSE 的 session cookie 并写入环境变量。"""
    result = sso_login("moa_mse")
    if not result.success:
        return result

    if result.cookies:
        cookie_str = "; ".join(f"{k}={v}" for k, v in result.cookies.items())
        os.environ["MOA_COOKIE"] = cookie_str

    return result


def update_env_local(
    env_file: str | Path,
    updates: dict[str, str],
) -> None:
    """更新 .env.local 文件中的指定 key=value。"""
    path = Path(env_file)
    if not path.exists():
        lines: list[str] = []
    else:
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)

    updated_keys: set[str] = set()
    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in updates:
                new_lines.append(f"{key}={updates[key]}\n")
                updated_keys.add(key)
                continue
        new_lines.append(line if line.endswith("\n") else line + "\n")

    for key, value in updates.items():
        if key not in updated_keys:
            new_lines.append(f"{key}={value}\n")

    path.write_text("".join(new_lines), encoding="utf-8")


def auto_refresh_yaahlan(env_file: str | Path | None = None) -> SSOLoginResult:
    """
    一键刷新 Yaahlan Staging Token 并持久化到 .env.local。

    供其他模块在请求失败时调用。
    """
    result = refresh_yaahlan_env("yaahlan_staging")
    if not result.success:
        return result

    if env_file is None:
        repo_root = Path(__file__).resolve().parents[2]
        env_file = repo_root / "Admin" / ".env.local"

    update_env_local(env_file, {
        "ADMIN_SSO_TOKEN": result.sso_token,
        "ADMIN_YAAHLAN_JWT": result.jwt_token,
    })
    return result


def auto_refresh_moa(env_file: str | Path | None = None) -> SSOLoginResult:
    """
    一键刷新 MOA/MSE Cookie 并持久化到 .env.local。
    """
    result = refresh_moa_env()
    if not result.success:
        return result

    if result.cookies and env_file is None:
        repo_root = Path(__file__).resolve().parents[2]
        env_file = repo_root / "MOA" / ".env.local"

    if result.cookies:
        cookie_str = "; ".join(f"{k}={v}" for k, v in result.cookies.items())
        update_env_local(env_file, {"MOA_COOKIE": cookie_str})

    return result


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> int:
    """CLI 入口：手动刷新各平台 token/cookie。"""
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Aegis SSO 自动登录 / Token 刷新")
    parser.add_argument(
        "platform",
        nargs="?",
        default="yaahlan_staging",
        choices=list(APP_KEYS.keys()) + ["all"],
        help="目标平台（默认 yaahlan_staging）",
    )
    parser.add_argument("--username", help="Aegis 用户名（覆盖环境变量）")
    parser.add_argument("--password", help="Aegis 密码（覆盖环境变量）")
    parser.add_argument("--persist", action="store_true", default=True, help="写入 .env.local（默认开启）")
    parser.add_argument("--no-persist", action="store_true", help="不写入 .env.local")
    args = parser.parse_args()

    # 加载环境
    env_dir = Path(__file__).resolve().parents[1]
    if str(env_dir) not in sys.path:
        sys.path.insert(0, str(env_dir))
    from admin.env import load_local_env

    load_local_env(str(env_dir))

    platforms = list(APP_KEYS.keys()) if args.platform == "all" else [args.platform]
    all_ok = True

    for platform in platforms:
        print(f"\n{'='*50}")
        print(f"Platform: {platform}")
        print("=" * 50)

        result = sso_login(platform, username=args.username, password=args.password)
        if not result.success:
            print(f"  FAILED: {result.error}")
            all_ok = False
            continue

        print(f"  SSO Token: {result.sso_token[:30]}...")
        if result.jwt_token:
            print(f"  JWT Token: {result.jwt_token[:40]}...")
        if result.username:
            print(f"  Username:  {result.username}")
        if result.momo_id:
            print(f"  MomoId:    {result.momo_id}")
        if result.cookies:
            print(f"  Cookies:   {list(result.cookies.keys())}")

        if not args.no_persist:
            if platform == "yaahlan_staging":
                auto_refresh_yaahlan()
                print("  -> Persisted to Admin/.env.local (ADMIN_SSO_TOKEN, ADMIN_YAAHLAN_JWT)")
            elif platform == "yaahlan_online":
                refresh_yaahlan_env("yaahlan_online")
                repo_root = Path(__file__).resolve().parents[2]
                update_env_local(repo_root / "online" / ".env.local", {
                    "ADMIN_ONLINE_SSO_TOKEN": result.sso_token,
                    "ADMIN_ONLINE_YAAHLAN_JWT": result.jwt_token,
                })
                print("  -> Persisted to online/.env.local")
            elif platform == "moa_mse":
                auto_refresh_moa()
                print("  -> Persisted to MOA/.env.local (MOA_COOKIE)")
            elif platform == "mdp_nova_alpha":
                auto_refresh_mdp_nova()
                print("  -> Persisted to Admin/.env.local (MDP_AEGIS_TOKEN, MDP_CLOUD_AEGIS_TOKEN)")

    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
