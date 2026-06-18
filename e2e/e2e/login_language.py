"""登录流程：检测 UI 语言并在非英语时切换到 English。"""

from __future__ import annotations

import re
import subprocess
import time
from typing import Any

from .budget import StepBudget
from .perceive import perceive_for_step
from .think import Plan
from .adb_bridge import adb_execute, parse_json_stdout

_ENGLISH_MARKERS = (
    "login with google",
    "sign in with google",
    "get via sms",
    "phone number",
    "terms of service",
    "privacy policy",
    "i have read and agreed",
    "verify phone",
)
_NON_ENGLISH_MARKERS = (
    "用google",
    "短信获取",
    "手机号码",
    "我已阅读并同意",
    "验证手机号",
    "手机号登录",
    "请选择使用语言",
    "下一步",
)

_LANG_PAGE = "HomeSelectLanguageActivity"
_LOGIN_LANDING = "LoginActivity"
_PHONE_PAGES = frozenset(
    {
        "PhoneLoginActivity",
        "LoginSendSmsCodeActivity",
    }
)

_ENGLISH_ROW_TAP = [0.5, 0.356]
_LANG_NEXT_TAP = [0.5, 0.918]
_LANG_ENGLISH_RID = "tv_en"


def _perceive_for_locale(*, budget: StepBudget, wait_sec: float = 0.0) -> dict[str, Any]:
    if wait_sec > 0:
        args = [
            "observe",
            "--fast",
            "--ui-limit",
            str(budget.ui_limit),
            "--wait",
            str(wait_sec),
        ]
        timeout = max(budget.subprocess_timeout_s, 15.0) + wait_sec
        try:
            code, stdout, stderr = adb_execute(args, timeout_s=timeout)
        except subprocess.TimeoutExpired:
            return perceive_for_step(budget=budget)
        if code == 0:
            return parse_json_stdout(stdout)
    return perceive_for_step(budget=budget)


def _activity_short(screen: dict[str, Any]) -> str:
    activity = screen.get("activity") if isinstance(screen.get("activity"), dict) else {}
    return str(activity.get("shortName") or "")


def _device_serial() -> str | None:
    import os

    serial = os.environ.get("E2E_DEVICE_SERIAL", "").strip()
    return serial or None


def _fresh_uiautomator_xml(*, timeout_s: float = 3.0) -> str:
    serial = _device_serial()
    cmd = ["adb"]
    if serial:
        cmd.extend(["-s", serial])
    cmd.extend(["shell", "uiautomator", "dump", "/sdcard/e2e_ui.xml"])
    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s, check=False)
        cat = ["adb"]
        if serial:
            cat.extend(["-s", serial])
        cat.extend(["shell", "cat", "/sdcard/e2e_ui.xml"])
        proc = subprocess.run(cat, capture_output=True, text=True, timeout=timeout_s, check=False)
        return proc.stdout or ""
    except (subprocess.TimeoutExpired, OSError):
        return ""


def _fresh_uiautomator_text_blob(*, timeout_s: float = 3.0) -> str:
    """绕过 stale observe，直接 dump 当前屏文案。"""
    xml = _fresh_uiautomator_xml(timeout_s=timeout_s)
    texts: list[str] = []
    for match in re.finditer(r'text="([^"]+)"', xml):
        value = match.group(1).strip()
        if value:
            texts.append(value)
    return " ".join(texts).casefold()


def _merged_text_blob(screen: dict[str, Any]) -> str:
    parts = [_visible_text_blob(screen), _fresh_uiautomator_text_blob()]
    return " ".join(p for p in parts if p).strip()


def _clickables(screen: dict[str, Any]) -> list[dict[str, Any]]:
    ui = screen.get("ui") if isinstance(screen.get("ui"), dict) else {}
    items = ui.get("clickables") if isinstance(ui.get("clickables"), list) else []
    return [item for item in items if isinstance(item, dict)]


def _visible_text_blob(screen: dict[str, Any]) -> str:
    parts: list[str] = []
    for item in _clickables(screen):
        for key in ("label", "text"):
            value = str(item.get(key) or "").strip()
            if value:
                parts.append(value)
    return " ".join(parts).casefold()


def _on_language_picker(screen: dict[str, Any]) -> bool:
    blob = _merged_text_blob(screen)
    if "请选择使用语言" in blob:
        return True
    if "english" in blob and "中文" in blob and ("下一步" in blob or " next" in f" {blob}"):
        return True
    return _activity_short(screen) == _LANG_PAGE


def _login_language_button_text(screen: dict[str, Any]) -> str:
    xml = _fresh_uiautomator_xml()
    match = re.search(
        r'resource-id="com\.immomo\.biz\.yaahlan:id/language"[^>]*text="([^"]*)"',
        xml,
    )
    if match:
        return match.group(1).strip()
    for item in _clickables(screen):
        rid = str(item.get("resourceId") or item.get("resourceIdShort") or "")
        if rid.endswith("/language") or rid.endswith(":language") or rid == "language":
            return str(item.get("text") or item.get("label") or "").strip()
    return ""


def is_english_login_ui(screen: dict[str, Any]) -> bool:
    """当前屏是否已是英语登录相关 UI。"""
    short = _activity_short(screen)
    if not short or "launcher" in short.casefold():
        return False
    if short not in {_LANG_PAGE, _LOGIN_LANDING, *_PHONE_PAGES}:
        return False

    if _on_language_picker(screen):
        return False

    lang_btn = _login_language_button_text(screen).casefold()
    if lang_btn == "english":
        return True
    if lang_btn in {"中文", "العربية"} or lang_btn.startswith("türk") or lang_btn.startswith("рус"):
        return False

    blob = _merged_text_blob(screen)
    if any(marker in blob for marker in _ENGLISH_MARKERS):
        return True
    if any(marker in blob for marker in _NON_ENGLISH_MARKERS):
        return False

    short = _activity_short(screen)
    if short in _PHONE_PAGES:
        return "phone number" in blob or "get via sms" in blob
    return False


def _plan_tap(
    *,
    reasoning: str,
    tap_pct: list[float] | None = None,
    resource_id: str | None = None,
    label: str | None = None,
) -> Plan:
    return Plan(
        action="tap",
        reasoning=reasoning,
        target=label or resource_id or "tap",
        tap_pct=tap_pct,
        resource_id=resource_id,
        meta={"loginLocale": True},
    )


def plan_next_english_switch(screen: dict[str, Any], *, last_action: str | None) -> Plan | None:
    """根据当前屏规划下一步切英语操作；None 表示无法继续。"""
    short = _activity_short(screen)

    if _on_language_picker(screen) or short == _LANG_PAGE:
        if last_action != "tap_english_row":
            return _plan_tap(
                reasoning="语言选择页：点选 English（tv_en）",
                tap_pct=_ENGLISH_ROW_TAP,
                resource_id=_LANG_ENGLISH_RID,
                label="English",
            )
        return _plan_tap(
            reasoning="语言选择页：点 Next/下一步",
            tap_pct=_LANG_NEXT_TAP,
            resource_id="confirm",
            label="Next",
        )

    if short == _LOGIN_LANDING and not is_english_login_ui(screen):
        return _plan_tap(
            reasoning="登录页非英语：打开语言选择",
            resource_id="language",
            label="language",
        )

    if short in _PHONE_PAGES and not is_english_login_ui(screen):
        return Plan(action="back", reasoning="手机登录子页非英语：返回登录页", meta={"loginLocale": True})

    return None


def run_until_english(
    *,
    budget: StepBudget | None = None,
    timeout_s: float = 2.5,
    max_rounds: int = 10,
) -> dict[str, Any]:
    """循环切英语，直到登录 UI 为英语或失败。"""
    from .act import execute_plan

    budget = budget or StepBudget()
    trace: list[dict[str, Any]] = []
    last_action: str | None = None
    prev_short = ""
    pending_wait = 0.0

    for round_idx in range(1, max_rounds + 1):
        screen = _perceive_for_locale(budget=budget, wait_sec=pending_wait)
        pending_wait = 0.0
        short = _activity_short(screen)
        if not short or "launcher" in short.casefold():
            launch_plan = Plan(
                action="launch",
                reasoning="App 不在前台，冷启动 Yaahlan",
                target="Yaahlan",
                meta={"app": "yaahlan", "waitMs": 4000},
            )
            launch_result = execute_plan(launch_plan, timeout_s=timeout_s)
            trace.append(
                {
                    "round": round_idx,
                    "plan": launch_plan.to_dict(),
                    "act": launch_result,
                    "activity": short,
                }
            )
            if not launch_result.get("ok"):
                return {
                    "ok": False,
                    "action": "ensure_english",
                    "error": launch_result.get("error") or "冷启动失败",
                    "trace": trace,
                }
            pending_wait = 3.0
            continue
        if short != prev_short:
            last_action = None
        prev_short = short

        if is_english_login_ui(screen):
            return {
                "ok": True,
                "action": "ensure_english",
                "rounds": round_idx,
                "trace": trace,
                "activity": _activity_short(screen),
            }

        plan = plan_next_english_switch(screen, last_action=last_action)
        if plan is None:
            return {
                "ok": False,
                "action": "ensure_english",
                "error": f"无法规划切英语步骤（activity={_activity_short(screen)}）",
                "trace": trace,
            }

        result = execute_plan(plan, timeout_s=timeout_s)
        entry = {
            "round": round_idx,
            "plan": plan.to_dict(),
            "act": result,
            "activity": _activity_short(screen),
        }
        trace.append(entry)

        if not result.get("ok"):
            return {
                "ok": False,
                "action": "ensure_english",
                "error": result.get("error") or "切英语执行失败",
                "trace": trace,
            }

        if plan.action == "tap" and (
            plan.target == "English" or plan.tap_pct == _ENGLISH_ROW_TAP
        ):
            last_action = "tap_english_row"
        elif plan.action == "tap" and (
            plan.resource_id == "confirm" or plan.tap_pct == _LANG_NEXT_TAP
        ):
            last_action = "tap_lang_next"
        elif plan.resource_id == "language":
            last_action = "open_language"
            pending_wait = 2.0
        elif plan.action == "wait" and plan.meta.get("loginLocale"):
            last_action = "wait_lang"
        else:
            last_action = plan.action

        sleep_sec = 0.5 if plan.resource_id == "language" else 0.35
        time.sleep(sleep_sec)

    return {
        "ok": False,
        "action": "ensure_english",
        "error": f"切英语超过 {max_rounds} 轮",
        "trace": trace,
    }


_LOGIN_TAP_STEPS = frozenset(
    {
        "勾选协议",
        "点击手机号登录",
        "点击手机号输入框",
        "点击Get via SMS",
        "点击验证码输入框",
    }
)

# 纯输入步：只需 Activity 门禁，勿全量 observe（否则 stale 树每步 observe --wait 卡 ~30s）
_LOGIN_TEXT_STEPS = frozenset(
    {
        "输入手机号",
        "输入验证码",
    }
)

_LOGIN_PREP_STEPS = _LOGIN_TAP_STEPS | _LOGIN_TEXT_STEPS


def permission_dialog_visible_fresh() -> bool:
    """用 uiautomator 判断定位权限弹窗是否挡住登录（单次 dump）。"""
    xml = _fresh_uiautomator_xml()
    if not xml:
        return False
    lowered = xml.casefold()
    return (
        "permission_allow_foreground_only" in lowered
        or "仅在前台使用应用时允许" in xml
        or "allow only while using the app" in lowered
    )


def unblock_login_screen(
    *,
    budget: StepBudget,
    screen: dict[str, Any] | None = None,
    max_rounds: int = 2,
) -> dict[str, Any]:
    """登录关键步：先快路径 observe，仅 stale/权限时再 --wait 刷新。"""
    from .perceive import perceive_fresh, perceive_for_step
    from .scene_gate import observe_tree_stale

    last: dict[str, Any] | None = screen
    for _ in range(max_rounds):
        if permission_dialog_visible_fresh():
            dismiss_location_permission_if_present()
            time.sleep(0.5)
            last = None
            continue
        if last is None:
            last = perceive_for_step(budget=budget)
        if not observe_tree_stale(last):
            return last
        fresh = perceive_fresh(budget=budget, wait_sec=0.8)
        if not observe_tree_stale(fresh):
            return fresh
        dismiss_location_permission_if_present()
        time.sleep(0.3)
        last = None

    return perceive_for_step(budget=budget)


_FRESH_PERCEIVE_STEPS = _LOGIN_TAP_STEPS

_NAV_FAST_STEPS = frozenset(
    {
        "点击我的底栏",
        "点击个人资料头像",
        "点击Game底栏",
    }
)


def dismiss_location_permission_if_present() -> dict[str, Any]:
    """若定位权限弹窗存在则点击「仅在前台使用应用时允许」。"""
    from . import driver

    xml = _fresh_uiautomator_xml()
    if not xml:
        return {"ok": False, "action": "dismiss_permission", "error": "uiautomator dump 失败"}

    patterns = [
        r'resource-id="[^"]*permission_allow_foreground_only_button"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
        r'text="仅在前台使用应用时允许"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
        r'text="Allow only while using the app"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
    ]
    for pattern in patterns:
        match = re.search(pattern, xml)
        if not match:
            continue
        x1, y1, x2, y2 = map(int, match.groups())
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        try:
            out = driver.tap_xy(cx, cy)
            time.sleep(0.5)
            return {
                "ok": True,
                "action": "dismiss_permission",
                "tapped": [cx, cy],
                "tap": out,
            }
        except RuntimeError as exc:
            return {"ok": False, "action": "dismiss_permission", "error": str(exc)}

    return {"ok": True, "action": "dismiss_permission", "skipped": True, "reason": "无定位权限弹窗"}
