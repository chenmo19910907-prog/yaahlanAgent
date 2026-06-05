"""冷启动开屏广告：落点验收 + Tunnel 抓包 + 误点进广告页恢复。"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from .actions import keyevent
from .activity import get_foreground_activity
from .apps import YAAHLAN
from .chain import run_chain
from .macros import apply_skip_flags, resolve_macro
from .popup_analyze import analyze_scene_from_tunnel, fetch_recent_tunnel_items
from .tunnel_verify import TunnelVerifyOptions, wait_for_tunnel

_YAAHLAN_PKG = str(YAAHLAN["package"])
_SAFE_HINTS = frozenset({"home", "login"})
_AD_STUCK_HINTS = frozenset({"webview", "splash"})


def _tunnel_hit_since(
    *,
    momoid: str,
    keyword: str,
    start_time: int,
    wait_seconds: int = 20,
    expect_ec: int = 200,
) -> dict[str, Any]:
    opts = TunnelVerifyOptions(
        momoid=momoid,
        keyword=keyword,
        wait_seconds=max(1, wait_seconds),
        poll_interval_ms=1500,
        expect_http_status=200,
        expect_response_ec=expect_ec,
        since_buffer_seconds=0,
    )
    return wait_for_tunnel(opts, start_time=start_time)


def verify_splash_landing(
    *,
    serial: str,
    momoid: str | None = None,
    start_time: int | None = None,
    tunnel_wait: int = 20,
    poll_activity_ms: int = 500,
    activity_wait_s: int = 12,
) -> dict[str, Any]:
    """
    验收开屏是否已结束、未误进广告 WebView。
    activity：hint 应为 home/login；webview/splash 视为卡在广告。
    tunnel（有 momoid）：应见到 getOpenScreenAd，且随后有 getUserConfigs/simpleUserInfo。
    """
    deadline = time.time() + max(1, activity_wait_s)
    fa: dict[str, Any] = {}
    while time.time() < deadline:
        fa = get_foreground_activity(serial=serial)
        hint = str(fa.get("hint", ""))
        pkg = str(fa.get("package", ""))
        if pkg == _YAAHLAN_PKG and hint in _SAFE_HINTS:
            break
        if hint in _AD_STUCK_HINTS:
            break
        time.sleep(max(0.1, poll_activity_ms / 1000.0))
    else:
        fa = get_foreground_activity(serial=serial)

    hint = str(fa.get("hint", ""))
    pkg = str(fa.get("package", ""))
    stuck_in_ad = hint in _AD_STUCK_HINTS
    activity_ok = fa.get("ok") and pkg == _YAAHLAN_PKG and hint in _SAFE_HINTS

    tunnel: dict[str, Any] = {}
    tunnel_ok: bool | None = None
    if momoid and start_time is not None:
        since = max(5, int(time.time()) - start_time + 3)
        items, meta = fetch_recent_tunnel_items(momoid=momoid, since_seconds=since)
        open_ad_items = [
            x
            for x in items
            if "getopenscreenad" in str(x.get("url", "")).lower()
        ]
        home_items = [
            x
            for x in items
            if any(
                k in str(x.get("url", "")).lower()
                for k in ("getuserconfigs", "simpleuserinfo", "redcount")
            )
        ]
        tunnel = {
            "openScreenAdSeen": bool(open_ad_items),
            "openScreenAdLatest": open_ad_items[-1].get("time") if open_ad_items else None,
            "homeApiSeen": bool(home_items),
            "homeApiLatest": home_items[-1].get("time") if home_items else None,
            "tunnelMeta": meta,
        }
        if not meta.get("tunnelOk"):
            tunnel_ok = False
            tunnel["error"] = "Tunnel 拉取失败"
        elif not items:
            tunnel_ok = None
            tunnel["skipped"] = "回溯窗口内无抓包，仅以 activity 验收"
        elif not tunnel.get("homeApiSeen"):
            home_wait = _tunnel_hit_since(
                momoid=momoid,
                keyword="getUserConfigs",
                start_time=start_time,
                wait_seconds=min(12, tunnel_wait),
            )
            tunnel["homeTunnelWait"] = home_wait
            tunnel["homeApiSeen"] = bool(home_wait.get("ok"))
            tunnel_ok = bool(home_wait.get("ok"))
        else:
            tunnel_ok = True

    popup_analysis: dict[str, Any] | None = None
    if momoid and start_time is not None:
        popup_analysis = analyze_scene_from_tunnel(
            momoid=momoid,
            scene="splash",
            since_seconds=max(30, int(time.time()) - start_time + 5),
        )

    ok = activity_ok and not stuck_in_ad and tunnel_ok is not False

    agent_hint = "开屏验收通过，可继续下一段。"
    if stuck_in_ad:
        agent_hint = (
            f"卡在广告页（hint={hint}）：先 BACK 或 macro 跳过开屏广告，"
            "再 splash verify --recover。"
        )
    elif not activity_ok:
        agent_hint = (
            f"落点异常（package={pkg}, hint={hint}）："
            "可能广告未播完就点击；capture 读图后 splash verify --recover，勿 force-stop。"
        )
    elif tunnel_ok is False:
        agent_hint = (
            "Tunnel 未见 getUserConfigs/simpleUserInfo：可能仍在前置页、误进广告或未就绪，"
            "splash verify --recover 或 capture 读图。"
        )
    elif tunnel_ok is None:
        agent_hint = (
            "activity 通过；Tunnel 窗口内无抓包，未做接口验收。"
            "有抓包时以 getUserConfigs 为准。"
        )

    return {
        "ok": ok,
        "foregroundActivity": fa,
        "stuckInAd": stuck_in_ad,
        "activityOk": activity_ok,
        "tunnelOk": tunnel_ok,
        "tunnel": tunnel,
        "popupAnalysis": popup_analysis,
        "agentHint": agent_hint,
    }


def recover_from_splash_ad(
    *,
    serial: str,
    screenshot_dir: Path,
    max_screenshots: int,
    use_adaptation: bool = True,
) -> dict[str, Any]:
    """误点进广告 WebView 时：BACK → 再跑跳过开屏广告。"""
    keyevent(code=4, serial=serial)
    time.sleep(0.4)
    keyevent(code=4, serial=serial)
    time.sleep(0.5)

    frag = resolve_macro("跳过开屏广告")
    steps = apply_skip_flags(list(frag.get("steps", [])), skip=set())
    chain_out = run_chain(
        serial=serial,
        steps=steps,
        capture="never",
        screenshot_dir=screenshot_dir,
        max_screenshots=max_screenshots,
        use_adaptation=use_adaptation,
    )
    time.sleep(0.5)
    fa = get_foreground_activity(serial=serial)
    return {
        "action": "recoverSplashAd",
        "stepsExecuted": chain_out.get("stepsExecuted"),
        "foregroundActivity": fa,
        "agentHint": "已 BACK 并重跑跳过开屏广告；请再执行 splash verify。",
    }


def verify_and_recover_splash(
    *,
    serial: str,
    screenshot_dir: Path,
    max_screenshots: int,
    momoid: str | None = None,
    start_time: int | None = None,
    recover: bool = True,
    tunnel_wait: int = 20,
    use_adaptation: bool = True,
) -> dict[str, Any]:
    first = verify_splash_landing(
        serial=serial,
        momoid=momoid,
        start_time=start_time,
        tunnel_wait=tunnel_wait,
    )
    if first.get("ok") or not recover:
        first["recovered"] = False
        return first

    recovery = recover_from_splash_ad(
        serial=serial,
        screenshot_dir=screenshot_dir,
        max_screenshots=max_screenshots,
        use_adaptation=use_adaptation,
    )
    second = verify_splash_landing(
        serial=serial,
        momoid=momoid,
        start_time=start_time,
        tunnel_wait=tunnel_wait,
    )
    second["recovered"] = True
    second["recovery"] = recovery
    if not second.get("ok"):
        second["agentHint"] = (
            f"{second.get('agentHint', '')} "
            "恢复后仍失败：capture 读图确认是否在广告 H5。"
        )
    return second
