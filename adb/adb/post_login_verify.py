"""登录后弹窗验收：签到半屏、运营层；抓包 + activity + 关弹窗。"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from .actions import keyevent, tap
from .activity import get_foreground_activity
from .apps import YAAHLAN
from .chain import run_chain
from .coords import pct_to_pixel
from .device import display_size
from .macros import resolve_macro
from .popup_analyze import (
    analyze_scene_from_tunnel,
    fetch_recent_tunnel_items,
)

_YAAHLAN_PKG = str(YAAHLAN["package"])
_SAFE_HINTS = frozenset({"home", "login"})
_STUCK_HINTS = frozenset({"webview", "splash"})
_EXIT_DIALOG_CANCEL_PCT = (0.35, 0.52)


def _smart_dismiss_post_login(
    *,
    serial: str,
    screenshot_dir: Path,
    max_screenshots: int,
    use_adaptation: bool,
    wait_ms: int = 800,
) -> dict[str, Any]:
    """
    仅当 hint=webview 时 BACK 关签到；已在 home 时不按 BACK（避免退出 App 二次确认连弹）。
    若误触退出对话框，点一次 Cancel。
    """
    if wait_ms > 0:
        time.sleep(wait_ms / 1000.0)

    backs = 0
    steps_log: list[str] = []
    for _ in range(4):
        fa = get_foreground_activity(serial=serial)
        hint = str(fa.get("hint", ""))
        if hint == "webview":
            keyevent(code=4, serial=serial)
            backs += 1
            steps_log.append("BACK(webview)")
            time.sleep(0.5)
            continue
        if hint in _SAFE_HINTS:
            break
        break

    if backs > 0:
        fa = get_foreground_activity(serial=serial)
        if fa.get("hint") in _SAFE_HINTS:
            w, h = display_size(serial)
            cx, cy = pct_to_pixel(w, h, *_EXIT_DIALOG_CANCEL_PCT)
            tap(x=cx, y=cy, serial=serial)
            steps_log.append("tap Cancel(exit-dialog)")
            time.sleep(0.35)

    return {"backs": backs, "steps": steps_log}


def _sign_in_popup_likely(items: list[dict[str, Any]]) -> dict[str, Any]:
    for item in sorted(items, key=lambda x: str(x.get("time", "")), reverse=True):
        if "sign/signinlist" not in str(item.get("url", "")).lower():
            continue
        resp = item.get("response") if isinstance(item.get("response"), dict) else {}
        data = resp.get("data") if isinstance(resp.get("data"), dict) else {}
        popup_url = str(data.get("signInPopupUrl", "") or "").strip()
        have_task = bool(data.get("haveTask"))
        return {
            "matched": True,
            "time": item.get("time"),
            "signInPopupUrl": popup_url or None,
            "haveTask": have_task,
            "popupLikely": bool(popup_url),
        }
    return {"matched": False, "popupLikely": False}


def _run_dismiss_script(
    script_name: str,
    *,
    serial: str,
    screenshot_dir: Path,
    max_screenshots: int,
    use_adaptation: bool,
    skip: set[str] | None = None,
) -> dict[str, Any]:
    spec = resolve_macro(script_name)
    result = run_chain(
        serial=serial,
        steps=list(spec.get("steps") or []),
        capture="never",
        screenshot_dir=screenshot_dir,
        max_screenshots=max_screenshots,
        use_adaptation=use_adaptation,
        skip=skip or set(),
        popup_gate_auto=False,
    )
    return {"script": script_name, "scriptId": spec.get("id"), "chain": result}


def dismiss_home_entry_popups(
    *,
    serial: str,
    screenshot_dir: Path,
    max_screenshots: int,
    use_adaptation: bool = True,
) -> dict[str, Any]:
    """
    已在首页或刚关完签到 WebView：关运营全屏 + Account Security / 众测等 Cancel。
    勿在冷启动回首页（无弹窗）时调用。
    """
    executed: list[dict[str, Any]] = []
    fa = get_foreground_activity(serial=serial)
    hint = str(fa.get("hint", ""))

    if hint == "webview":
        executed.append(
            _run_dismiss_script(
                "关闭签到弹窗",
                serial=serial,
                screenshot_dir=screenshot_dir,
                max_screenshots=max_screenshots,
                use_adaptation=use_adaptation,
            )
        )
        fa = get_foreground_activity(serial=serial)
        hint = str(fa.get("hint", ""))

    if hint == "home":
        executed.append(
            _run_dismiss_script(
                "关闭常见弹窗",
                serial=serial,
                screenshot_dir=screenshot_dir,
                max_screenshots=max_screenshots,
                use_adaptation=use_adaptation,
            )
        )
        fa = get_foreground_activity(serial=serial)

    ok = fa.get("ok") and str(fa.get("hint", "")) == "home"
    return {
        "ok": ok,
        "executed": executed,
        "foregroundActivity": fa,
        "agentHint": (
            "首页弹窗已处理，activity hint=home。"
            if ok
            else f"关弹窗后落点 hint={fa.get('hint')}；capture 读图。"
        ),
    }


def verify_and_dismiss_post_login(
    *,
    serial: str,
    screenshot_dir: Path,
    max_screenshots: int,
    momoid: str | None = None,
    login_start: int | None = None,
    use_adaptation: bool = True,
    force_dismiss: bool = False,
    dismiss_home_popups: bool = False,
) -> dict[str, Any]:
    """
    登录/注册进首页后验收：签到 WebView BACK；可选跑关闭常见弹窗。
    关弹窗：仅 webview 时 BACK；home 上禁止连按 BACK（会弹退出 App 二次确认）。
    """
    time.sleep(0.3)
    fa_before = get_foreground_activity(serial=serial)
    stuck_before = str(fa_before.get("hint", "")) in _STUCK_HINTS

    popup_analysis: dict[str, Any] | None = None
    sign_in_tunnel: dict[str, Any] = {"matched": False, "popupLikely": False}
    since = max(30, int(time.time()) - (login_start or int(time.time())) + 5)

    if momoid:
        items, tunnel_meta = fetch_recent_tunnel_items(
            momoid=momoid,
            since_seconds=since,
        )
        sign_in_tunnel = _sign_in_popup_likely(items)
        sign_in_tunnel["tunnelMeta"] = tunnel_meta
        popup_analysis = analyze_scene_from_tunnel(
            momoid=momoid,
            scene="login",
            since_seconds=since,
        )

    hint_before = str(fa_before.get("hint", ""))
    need_dismiss = force_dismiss or hint_before in _STUCK_HINTS

    dismiss_blocks: list[dict[str, Any]] = []
    smart = _smart_dismiss_post_login(
        serial=serial,
        screenshot_dir=screenshot_dir,
        max_screenshots=max_screenshots,
        use_adaptation=use_adaptation,
        wait_ms=800 if need_dismiss or hint_before in _SAFE_HINTS else 400,
    )
    if smart.get("backs") or smart.get("steps"):
        dismiss_blocks.append(
            {
                "action": "smartDismissPostLogin",
                "reason": "webview" if stuck_before else "wait-sign-in",
                "smartDismiss": smart,
            }
        )

    home_popup_dismiss: dict[str, Any] | None = None
    if dismiss_home_popups:
        home_popup_dismiss = dismiss_home_entry_popups(
            serial=serial,
            screenshot_dir=screenshot_dir,
            max_screenshots=max_screenshots,
            use_adaptation=use_adaptation,
        )
        if home_popup_dismiss.get("executed"):
            dismiss_blocks.extend(home_popup_dismiss["executed"])

    fa_after = get_foreground_activity(serial=serial)
    hint = str(fa_after.get("hint", ""))
    pkg = str(fa_after.get("package", ""))
    activity_ok = (
        fa_after.get("ok")
        and pkg == _YAAHLAN_PKG
        and hint in _SAFE_HINTS
    )
    ok = activity_ok and hint not in _STUCK_HINTS

    agent_hint = "登录后弹窗验收通过，可进 Me 或下一段 macro。"
    if not ok:
        if hint in _STUCK_HINTS:
            agent_hint = (
                f"仍卡在 {hint}（多为签到 H5 未关净）："
                "macro 关闭签到弹窗 或 capture 读图找关闭按钮。"
            )
        else:
            agent_hint = (
                f"落点异常 package={pkg} hint={hint}："
                "popup analyze --scene login --auto-dismiss 或 capture。"
            )
    elif need_dismiss:
        agent_hint = "已关签到/运营弹窗，可继续下一段。"
    elif dismiss_home_popups and home_popup_dismiss and home_popup_dismiss.get("ok"):
        agent_hint = "注册/登录进首页后已关弹窗，可继续下一段。"
    elif sign_in_tunnel.get("popupLikely"):
        agent_hint = "抓包显示可能有签到弹窗但未执行关弹窗（force_dismiss=false 且 activity 正常）。"

    return {
        "ok": ok,
        "needDismiss": need_dismiss,
        "dismissExecuted": dismiss_blocks,
        "foregroundActivityBefore": fa_before,
        "foregroundActivity": fa_after,
        "stuckBefore": stuck_before,
        "signInTunnel": sign_in_tunnel,
        "loginPopupAnalysis": popup_analysis,
        "homePopupDismiss": home_popup_dismiss,
        "agentHint": agent_hint,
    }
