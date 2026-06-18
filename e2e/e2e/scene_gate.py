"""页面状态门禁：步前 require / 步后 expect / 脏树检测。"""

from __future__ import annotations

from typing import Any


def activity_context(screen: dict[str, Any]) -> dict[str, str]:
    activity = screen.get("activity") if isinstance(screen.get("activity"), dict) else {}
    return {
        "hint": str(activity.get("hint") or "").strip(),
        "scene": str(activity.get("scene") or "").strip(),
        "shortName": str(activity.get("shortName") or "").strip(),
        "package": str(activity.get("package") or "").strip(),
    }


def _norm_list(value: Any) -> list[str]:
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return []


def _matches(ctx: dict[str, str], token: str) -> bool:
    token = token.strip()
    if not token:
        return False
    hay = f"{ctx['hint']} {ctx['scene']} {ctx['shortName']} {ctx['package']}".casefold()
    return token.casefold() in hay


def _format_ctx(ctx: dict[str, str]) -> str:
    return (
        f"hint={ctx['hint'] or '—'}, scene={ctx['scene'] or '—'}, "
        f"shortName={ctx['shortName'] or '—'}"
    )


def check_require_before(screen: dict[str, Any], step_hint: dict[str, Any] | None) -> dict[str, Any]:
    """步前：当前页是否允许执行该步。"""
    if not step_hint:
        return {"ok": True}

    ctx = activity_context(screen)
    required = _norm_list(step_hint.get("requireSceneBefore") or step_hint.get("requireScene"))
    forbidden = _norm_list(step_hint.get("forbidSceneBefore"))

    for token in forbidden:
        if _matches(ctx, token):
            return {
                "ok": False,
                "phase": "before",
                "reason": f"禁止在含「{token}」的页面执行",
                "expect": {"forbid": forbidden, "require": required},
                "actual": ctx,
            }

    if required and not any(_matches(ctx, r) for r in required):
        return {
            "ok": False,
            "phase": "before",
            "reason": f"步前 scene 不满足，需要其一 {required}",
            "expect": {"require": required},
            "actual": ctx,
        }

    return {"ok": True, "actual": ctx}


def check_expect_after(activity: dict[str, Any], step_hint: dict[str, Any] | None) -> dict[str, Any]:
    """步后：是否到达预期页面。"""
    if not step_hint:
        return {"ok": True}

    expected = _norm_list(step_hint.get("expectSceneAfter") or step_hint.get("expectScene"))
    if not expected:
        return {"ok": True}

    ctx = activity_context({"activity": activity})
    if any(_matches(ctx, token) for token in expected):
        return {"ok": True, "actual": ctx}

    return {
        "ok": False,
        "phase": "after",
        "reason": f"步后 scene 未到达，需要其一 {expected}",
        "expect": {"require": expected},
        "actual": ctx,
    }


def ui_tree_unreliable(screen: dict[str, Any]) -> bool:
    """UI dump 与 Activity 不一致时勿信 clickables。"""
    ctx = activity_context(screen)
    hint = ctx["hint"]
    short = ctx["shortName"]
    ui = screen.get("ui") if isinstance(screen.get("ui"), dict) else {}
    clickables = ui.get("clickables") if isinstance(ui.get("clickables"), list) else []
    if not clickables:
        return True

    rid_hay = " ".join(str(c.get("resourceId") or "") for c in clickables if isinstance(c, dict))
    has_compose = ":id/post" in rid_hay or ":id/publish_feed" in rid_hay

    if not has_compose:
        return hint in {"home", "unknown"} and len(clickables) <= 12

    compose_activities = {"PostActivity", "WebViewActivity"}
    if short in compose_activities or "post" in short.casefold():
        return False
    if hint in {"feed_publish", "webview"}:
        return False
    if hint == "home" and has_compose:
        return True
    return True


def login_observe_stale(screen: dict[str, Any]) -> bool:
    """登录 Activity 但 clickables 仍是权限弹窗或其它过期树。"""
    ctx = activity_context(screen)
    short = ctx["shortName"]
    if short not in {
        "LoginActivity",
        "PhoneLoginActivity",
        "LoginSendSmsCodeActivity",
    }:
        return False

    ui = screen.get("ui") if isinstance(screen.get("ui"), dict) else {}
    clickables = ui.get("clickables") if isinstance(ui.get("clickables"), list) else []
    labels: list[str] = []
    rid_parts: list[str] = []
    for item in clickables:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or item.get("text") or "").strip()
        if label:
            labels.append(label)
        rid = str(item.get("resourceId") or item.get("resourceIdShort") or "")
        if rid:
            rid_parts.append(rid)
    blob = " ".join(labels)
    rid_hay = " ".join(rid_parts).casefold()

    permission_markers = (
        "仅在前台使用应用时允许",
        "Allow only while using the app",
        "禁止",
        "Don't allow",
    )
    has_permission_ui = any(marker in blob for marker in permission_markers) or (
        "permission_allow" in rid_hay or "permissioncontroller" in rid_hay
    )
    if has_permission_ui:
        return True

    if short == "LoginActivity":
        login_rids = ("phone", "img_check", "bg_google", "language")
        if not any(token in rid_hay for token in login_rids):
            login_labels = ("Login with Google", "用Google", "I have read", "我已阅读")
            if not any(marker in blob for marker in login_labels):
                return True

    if short == "PhoneLoginActivity":
        phone_rids = ("input_phone", "ll_phone_sms", "tv_phone")
        landing_rids = ("bg_google", "img_check_terms", "facebook", ":id/phone")
        if any(token in rid_hay for token in landing_rids) and not any(
            token in rid_hay for token in phone_rids
        ):
            return True
    if short == "LoginSendSmsCodeActivity":
        if "input_code" not in rid_hay and (
            "bg_google" in rid_hay or "img_check_terms" in rid_hay
        ):
            return True
    return False


def home_observe_stale(screen: dict[str, Any]) -> bool:
    """首页 Activity 但 clickables 仍是登录页过期树。"""
    ctx = activity_context(screen)
    if ctx["shortName"] not in {"MainActivity", "UserFeedListActivity"}:
        return False

    ui = screen.get("ui") if isinstance(screen.get("ui"), dict) else {}
    clickables = ui.get("clickables") if isinstance(ui.get("clickables"), list) else []
    rid_parts: list[str] = []
    for item in clickables:
        if not isinstance(item, dict):
            continue
        rid = str(item.get("resourceId") or item.get("resourceIdShort") or "")
        if rid:
            rid_parts.append(rid)
    rid_hay = " ".join(rid_parts).casefold()

    login_markers = ("bg_google", "img_check_terms", "loginlogic", ":id/phone", ":id/email")
    home_markers = ("tab_game", "tab_profile", "tab_message", "tab_moment", "home_container", "main_tab")
    has_login_stale = any(marker in rid_hay for marker in login_markers)
    has_home = any(marker in rid_hay for marker in home_markers)
    return has_login_stale and not has_home


def observe_tree_stale(screen: dict[str, Any]) -> bool:
    return login_observe_stale(screen) or home_observe_stale(screen)


def should_retry_perceive(screen: dict[str, Any], *, prev_ui_hash: str | None) -> bool:
    """脏树或 uiHash 粘连时重试一次 observe。"""
    if observe_tree_stale(screen):
        return True
    ui_hash = str(screen.get("uiHash") or "")
    if ui_tree_unreliable(screen):
        return True
    if prev_ui_hash and ui_hash and ui_hash == prev_ui_hash:
        ctx = activity_context(screen)
        if ctx["hint"] not in {"feed_publish", "webview", "login"}:
            return True
        if ctx["shortName"] == "LoginActivity":
            return True
    return False
