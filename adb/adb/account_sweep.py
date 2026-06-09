"""批量账号登录巡检：登录用固定脚本；首页/Me/房间/退出须 AI 读图。"""

from __future__ import annotations

import random
import time
from pathlib import Path
from typing import Any

from .activity import get_foreground_activity
from .ai_operate import AiOperateRequired, prepare_vision_cycle
from .auth.runner import (
    run_phone_auth_only,
    run_phone_login,
    run_register_profile,
)
from .chain import run_chain
from .device import AdbError, require_device
from .popup_analyze import analyze_scene_from_tunnel, fetch_recent_tunnel_items
from .phone_login_status import query_phone_login_status
from .post_login_verify import verify_and_dismiss_post_login
from .recorded_scripts import login_defaults
from .screenshot import screenshot_dir
from .tunnel_verify import (
    TunnelVerifyOptions,
    load_test_accounts,
    wait_for_tunnel,
)


def parse_phone_range(
    *,
    phones: list[str] | None = None,
    from_phone: str | None = None,
    to_phone: str | None = None,
    random_count: int | None = None,
    seed: int | None = None,
) -> list[str]:
    if phones:
        out = [p.strip() for p in phones if p.strip()]
        if out:
            return out
    if not from_phone:
        raise ValueError("须指定 --phones 或 --from/--to 手机号范围")
    start = int(from_phone)
    end = int(to_phone or from_phone)
    if end < start:
        start, end = end, start
    pool = [str(n) for n in range(start, end + 1)]
    if random_count is not None:
        if random_count <= 0:
            raise ValueError("--random 须 > 0")
        rng = random.Random(seed)
        k = min(random_count, len(pool))
        return rng.sample(pool, k)
    return pool


def momoid_from_index(phone: str) -> str | None:
    accounts = load_test_accounts()
    for entry in accounts.values():
        if not isinstance(entry, dict):
            continue
        if str(entry.get("phone", "")).strip() == phone:
            uid = str(entry.get("userId", "")).strip()
            return uid or None
    return None


def collect_probe_momoids() -> list[str]:
    ids: list[str] = []
    for entry in load_test_accounts().values():
        if isinstance(entry, dict):
            uid = str(entry.get("userId", "")).strip()
            if uid:
                ids.append(uid)
    return list(dict.fromkeys(ids))


def query_momoid_via_moa(phone: str) -> str | None:
    try:
        status = query_phone_login_status(phone)
    except AdbError:
        return None
    return status.get("userId")


def resolve_momoid_for_phone(
    phone: str,
    *,
    probe_since: int | None = None,
    login_keyword: str = "simpleUserInfo",
) -> tuple[str | None, str]:
    indexed = momoid_from_index(phone)
    if indexed:
        return indexed, "index"
    moa = query_momoid_via_moa(phone)
    if moa:
        return moa, "moa"
    if probe_since is not None:
        discovered = discover_momoid_since(
            start_time=probe_since,
            keyword=login_keyword,
            probe_ids=collect_probe_momoids(),
        )
        if discovered:
            return discovered, "tunnel-probe"
    return None, "unknown"


def discover_momoid_since(
    *,
    start_time: int,
    keyword: str,
    probe_ids: list[str],
) -> str | None:
    since_seconds = max(5, int(time.time()) - start_time + 3)
    key_low = keyword.lower()
    for mid in probe_ids:
        items, meta = fetch_recent_tunnel_items(momoid=mid, since_seconds=since_seconds)
        if not meta.get("tunnelOk"):
            continue
        for item in items:
            if key_low in str(item.get("url", "")).lower():
                return mid
    return None



def _tunnel_wait(
    *,
    momoid: str,
    keyword: str,
    start_time: int,
    wait_seconds: int = 25,
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


def _ensure_logout(serial: str, shot_dir: Path, max_screenshots: int) -> None:
    fa = get_foreground_activity(serial=serial)
    if fa.get("hint") == "login":
        return
    payload = prepare_vision_cycle(
        goal="logout",
        serial=serial,
        screenshot_dir=shot_dir,
        max_screenshots=max_screenshots,
        note="sweep 每账号前须已到 login 页。",
    )
    if payload.get("ok"):
        return
    payload["agentHint"] = (
        "批量 sweep 前须 Agent 完成退出：`ai prepare --goal logout` → "
        "读 screenshot → tap Cancel/设置/Log out → activity hint=login。"
        "勿 macro 退出登录、勿 force-stop。"
    )
    raise AiOperateRequired(payload)


def _ensure_me_via_ai(
    serial: str,
    shot_dir: Path,
    max_screenshots: int,
) -> dict[str, Any]:
    payload = prepare_vision_cycle(
        goal="enter_me",
        serial=serial,
        screenshot_dir=shot_dir,
        max_screenshots=max_screenshots,
    )
    if not payload.get("ok"):
        payload["agentHint"] = (
            "Me 验收须 Agent 读图：`ai prepare --goal enter_me` → "
            "点 Me 底栏 → 弹窗点 Cancel → capture 确认。"
        )
        raise AiOperateRequired(payload)
    return payload


def sweep_one_account(
    phone: str,
    *,
    serial: str | None = None,
    shot_dir: Path | None = None,
    max_screenshots: int = 2,
    check_me: bool = False,
    login_keyword: str = "simpleUserInfo",
    me_keyword: str = "personalHomePageUserInfo",
    tunnel_wait: int = 25,
    verify_code: str | None = None,
) -> dict[str, Any]:
    serial = serial or require_device(None)
    shot_dir = shot_dir or screenshot_dir(None)
    code = verify_code or login_defaults()["verifyCode"]

    row: dict[str, Any] = {
        "phone": phone,
        "verifyCode": code,
        "ok": False,
    }

    try:
        _ensure_logout(serial, shot_dir, max_screenshots)
        login_start = int(time.time())

        try:
            phone_status = query_phone_login_status(phone)
        except AdbError as exc:
            row["phoneLoginStatusError"] = str(exc)
            phone_status = {"registered": True, "route": "login", "userId": None}
        row["phoneLoginStatus"] = phone_status
        route = phone_status.get("route") or (
            "login" if phone_status.get("registered") else "register"
        )
        row["route"] = route

        if route == "register":
            run_phone_auth_only(
                phone,
                serial=serial,
                shot_dir=shot_dir,
                max_screenshots=max_screenshots,
            )
            fa_reg = get_foreground_activity(serial=serial)
            row["afterVerifyActivity"] = fa_reg
            if fa_reg.get("shortName") != "RegisterInfoActivity":
                row["agentHint"] = (
                    "MOA 未注册但未到 RegisterInfoActivity；"
                    f"当前 {fa_reg.get('shortName')}。"
                )
                return row
            run_register_profile(
                phone,
                serial=serial,
                shot_dir=shot_dir,
                max_screenshots=max_screenshots,
            )
            reg_end = int(time.time())
            reg_status = query_phone_login_status(phone)
            row["registeredUserId"] = reg_status.get("userId")
            post_login = verify_and_dismiss_post_login(
                serial=serial,
                screenshot_dir=shot_dir,
                max_screenshots=max_screenshots,
                momoid=reg_status.get("userId"),
                login_start=reg_end - 5,
                force_dismiss=True,
                dismiss_home_popups=True,
            )
            row["postLogin"] = post_login
            fa_home = post_login.get("foregroundActivity") or get_foreground_activity(
                serial=serial
            )
            row["loginActivity"] = fa_home
            row["loginOk"] = fa_home.get("hint") == "home"
            row["ok"] = row["loginOk"] and bool(reg_status.get("registered"))
            row["agentHint"] = (
                "注册成功并已关首页弹窗，activity hint=home。"
                if row["ok"]
                else f"注册后 hint={fa_home.get('hint')}；查 postLogin.homePopupDismiss。"
            )
            return row

        run_phone_login(
            phone,
            serial=serial,
            shot_dir=shot_dir,
            max_screenshots=max_screenshots,
            include_post_login_popup=False,
            popup_gate_auto=False,
        )

        momoid, momoid_source = resolve_momoid_for_phone(
            phone,
            probe_since=login_start,
            login_keyword=login_keyword,
        )
        if not momoid and phone_status.get("userId"):
            momoid = str(phone_status["userId"])
            momoid_source = "moa-pre-check"
        row["momoid"] = momoid
        row["momoidSource"] = momoid_source

        post_login = verify_and_dismiss_post_login(
            serial=serial,
            screenshot_dir=shot_dir,
            max_screenshots=max_screenshots,
            momoid=momoid,
            login_start=login_start,
        )
        row["postLogin"] = post_login

        fa_login = post_login.get("foregroundActivity") or get_foreground_activity(
            serial=serial
        )
        row["loginActivity"] = fa_login

        login_tunnel: dict[str, Any] | None = None
        if momoid:
            login_tunnel = _tunnel_wait(
                momoid=momoid,
                keyword=login_keyword,
                start_time=login_start,
                wait_seconds=tunnel_wait,
            )
            row["loginTunnel"] = login_tunnel
        else:
            row["loginTunnel"] = {
                "ok": False,
                "error": "无法解析 momoid（索引/MOA/tunnel-probe 均失败）",
            }

        login_ok = bool(post_login.get("ok")) and fa_login.get("hint") == "home"
        if momoid and login_tunnel is not None:
            if login_tunnel.get("ok"):
                pass
            elif login_tunnel.get("matchedCount", 0) == 0 and login_ok:
                row["loginTunnelNote"] = "无抓包，以 activity/postLogin 为准"
            else:
                login_ok = False
        row["loginOk"] = login_ok

        me_ok = True
        if check_me and login_ok:
            me_start = int(time.time())
            me_prepare = _ensure_me_via_ai(serial, shot_dir, max_screenshots)
            row["meAiPrepare"] = me_prepare

            if momoid:
                me_analysis = analyze_scene_from_tunnel(
                    momoid=momoid,
                    scene="me",
                    since_seconds=max(30, int(time.time()) - me_start + 5),
                )
            else:
                me_analysis = {
                    "scene": "me",
                    "weakUiPopups": ["Crowd Testing", "Account Security"],
                    "agentHint": "无 momoid；Me 弹窗请 AI 读图点 Cancel",
                }
            row["mePopupAnalysis"] = me_analysis

            fa_me = get_foreground_activity(serial=serial)
            row["meActivity"] = fa_me

            me_tunnel: dict[str, Any] | None = None
            if momoid:
                me_tunnel = _tunnel_wait(
                    momoid=momoid,
                    keyword=me_keyword,
                    start_time=me_start,
                    wait_seconds=tunnel_wait,
                )
                row["meTunnel"] = me_tunnel
            else:
                row["meTunnel"] = {"ok": False, "error": "无 momoid，跳过 Me 抓包验收"}

            me_ok = fa_me.get("hint") in ("home", "profile", "settings", "unknown") and (
                me_tunnel is None or me_tunnel.get("ok")
            )
            row["meOk"] = me_ok

        row["ok"] = login_ok and (not check_me or me_ok)
        if not login_ok:
            row["agentHint"] = "登录失败：查 loginActivity/postLogin/loginTunnel。"
        elif check_me and not me_ok:
            row["agentHint"] = "Me 验收失败：用 ai prepare --goal enter_me 读图操作。"
        else:
            row["agentHint"] = "本账号登录验收通过，可接下一段。"

    except AiOperateRequired as exc:
        row["requiresAiVision"] = True
        row["aiPayload"] = exc.payload
        row["agentHint"] = str(exc)
    except AdbError as exc:
        row["error"] = str(exc)
        row["agentHint"] = f"ADB 异常：{exc}"
    except ValueError as exc:
        row["error"] = str(exc)
        row["agentHint"] = str(exc)

    return row


def sweep_accounts(
    phones: list[str],
    *,
    serial: str | None = None,
    check_me: bool = False,
    login_keyword: str = "simpleUserInfo",
    me_keyword: str = "personalHomePageUserInfo",
    tunnel_wait: int = 25,
) -> dict[str, Any]:
    serial = serial or require_device(None)
    shot_dir = screenshot_dir(None)
    results = [
        sweep_one_account(
            phone,
            serial=serial,
            shot_dir=shot_dir,
            check_me=check_me,
            login_keyword=login_keyword,
            me_keyword=me_keyword,
            tunnel_wait=tunnel_wait,
        )
        for phone in phones
    ]
    ok_count = sum(1 for r in results if r.get("ok"))
    ai_count = sum(1 for r in results if r.get("requiresAiVision"))
    return {
        "action": "accountsSweep",
        "phones": phones,
        "total": len(results),
        "passed": ok_count,
        "failed": len(results) - ok_count,
        "requiresAiVision": ai_count,
        "loginKeyword": login_keyword,
        "meKeyword": me_keyword,
        "checkMe": check_me,
        "workflow": (
            "每账号：MOA 查手机号 userId → 有 ID 走登录 / 无 ID 走注册 → "
            "postLogin 或 RegisterInfo 验收 → tunnel；（--me 时 AI 进 Me）"
        ),
        "results": results,
        "agentHint": (
            f"完成 {ok_count}/{len(results)}；"
            f"{ai_count} 项需 AI 读图（见 requiresAiVision / aiPayload）。"
        ),
    }
