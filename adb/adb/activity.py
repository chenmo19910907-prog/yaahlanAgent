"""前台 Activity 探测（dumpsys），用于片段间验收，避免读图。"""

from __future__ import annotations

import re
import time
from typing import Any

from .device import run_adb

# Activity 短名 → 场景提示（Yaahlan 常见页）
_ACTIVITY_HINTS: dict[str, str] = {
    "RoomChatActivity": "in_room",
    "RoomSearchActivity": "search",
    "RoomSearchResultActivity": "search",
    "VisitorActivity": "visitor",
    "MainActivity": "home",
    "LoginActivity": "login",
    "RegisterInfoActivity": "register",
    "PhoneLoginActivity": "login",
    "LoginSendSmsCodeActivity": "login",
    "SplashActivity": "splash",
    "WebViewActivity": "webview",
    "NormalFlutterActivity": "flutter",
    "PersonalityIconActivity": "profile_edit",
    "ProfileActivity": "profile",
    "EditProfileActivity": "profile_edit",
    "NicknameEditActivity": "profile_edit",
    "UserProfileActivity": "profile",
    "SettingActivity": "settings",
    "SettingComposeActivity": "settings",
    "FeedPublishActivity": "feed_publish",
    "FeedAllTopicActivity": "feed_topics",
    "FeedTopicDetailActivity": "feed_topic",
    "ExhibitionHallComposeActivity": "collection_exhibition",
    "EventActivity": "event_center",
    "GameListActivity": "game_list",
    "RoomGameActivity": "room_game",
    "BlockListActivity": "blocklist",
    "GiftPanelActivity": "gift_panel",
    "SelectLanguageActivity": "settings",
    "AccountManagerActivity": "settings",
    "NotificationManagerActivity": "settings",
    "AboutUsActivity": "settings",
}

_RESUMED_PATTERNS = (
    re.compile(r"mResumedActivity:\s*ActivityRecord\{[^}]*\s+(\S+)/(\S+)\s"),
    re.compile(r"topResumedActivity=ActivityRecord\{[^}]*\s+(\S+)/(\S+)\s"),
    re.compile(r"mFocusedActivity:\s*ActivityRecord\{[^}]*\s+(\S+)/(\S+)\s"),
    re.compile(r"ResumedActivity:?\s*ActivityRecord\{[^}]*\s+(\S+)/(\S+)\s"),
)

_TOP_ACTIVITY_PATTERN = re.compile(
    r"ACTIVITY\s+(\S+)/(\S+)\s",
    re.MULTILINE,
)

_TOP_RESUMED_ACTIVITY_PATTERN = re.compile(
    r"ACTIVITY\s+(\S+)/(\S+)\s+\S+\s+pid=\d+\n"
    r"(?:.*\n){0,12}?"
    r"\s+mResumed=true\b",
    re.MULTILINE,
)

_FOCUS_PATTERN = re.compile(
    r"mCurrentFocus=Window\{[^}]+\s+u\d+\s+(\S+)/([^}\s]+)\}",
)


def _short_activity_name(activity: str) -> str:
    """com.pkg/.ui.MainActivity → MainActivity"""
    name = activity.rsplit(".", 1)[-1]
    if name.startswith("."):
        name = name[1:]
    return name


def _hint_for_activity(short_name: str) -> str:
    if short_name in _ACTIVITY_HINTS:
        return _ACTIVITY_HINTS[short_name]
    lower = short_name.lower()
    if "search" in lower:
        return "search"
    if "login" in lower:
        return "login"
    if "register" in lower:
        return "register"
    if "room" in lower and "chat" in lower:
        return "in_room"
    if "gift" in lower:
        return "gift_panel"
    if "webview" in lower or "flutter" in lower:
        return "webview"
    if "setting" in lower:
        return "settings"
    return "unknown"


def parse_resumed_activity(dumpsys_text: str) -> tuple[str, str] | None:
    """从 dumpsys activity 文本解析 package 与 activity。"""
    resumed = _TOP_RESUMED_ACTIVITY_PATTERN.search(dumpsys_text)
    if resumed:
        return resumed.group(1), resumed.group(2)
    focus_match = _FOCUS_PATTERN.search(dumpsys_text)
    if focus_match:
        return focus_match.group(1), focus_match.group(2)
    for pattern in _RESUMED_PATTERNS:
        match = pattern.search(dumpsys_text)
        if match:
            return match.group(1), match.group(2)
    top_match = _TOP_ACTIVITY_PATTERN.search(dumpsys_text)
    if top_match:
        return top_match.group(1), top_match.group(2)
    return None


def _activity_payload(package: str, activity: str) -> dict[str, Any]:
    short_name = _short_activity_name(activity)
    hint = _hint_for_activity(short_name)
    return {
        "ok": True,
        "package": package,
        "activity": activity,
        "shortName": short_name,
        "hint": hint,
        "scene": hint,
    }


def _dumpsys_foreground(*, serial: str | None, mode: str) -> dict[str, Any]:
    if mode == "top":
        proc = run_adb(
            ["shell", "dumpsys", "activity", "top"],
            serial=serial,
            timeout_s=4.0,
            check=True,
        )
    elif mode == "focus":
        proc = run_adb(
            ["shell", "dumpsys", "window"],
            serial=serial,
            timeout_s=4.0,
            check=True,
        )
    else:
        proc = run_adb(
            ["shell", "dumpsys", "activity", "activities"],
            serial=serial,
            timeout_s=12.0,
            check=True,
        )
    text = proc.stdout.decode("utf-8", errors="replace")
    parsed = parse_resumed_activity(text)
    if parsed is None:
        return {
            "ok": False,
            "error": f"无法从 dumpsys {mode} 解析前台 Activity",
        }
    package, activity = parsed
    return _activity_payload(package, activity)


def get_foreground_activity(*, serial: str | None) -> dict[str, Any]:
    """优先 window focus（快且准），再 activity top / 全量 activities。"""
    for mode in ("focus", "top", "activities"):
        try:
            payload = _dumpsys_foreground(serial=serial, mode=mode)
        except (RuntimeError, OSError, ValueError):
            continue
        if payload.get("ok"):
            payload["probe"] = mode
            return payload
    return {
        "ok": False,
        "error": "无法从 dumpsys 解析 mResumedActivity",
    }


def _activity_matches(
    fa: dict[str, Any],
    *,
    hint: str | None = None,
    hints: list[str] | None = None,
    short_name: str | None = None,
    package: str | None = None,
) -> bool:
    if not fa.get("ok"):
        return False
    if package and str(fa.get("package", "")) != package:
        return False
    if short_name and str(fa.get("shortName", "")) != short_name:
        return False
    if hint and str(fa.get("hint", "")) != hint:
        return False
    if hints:
        return str(fa.get("hint", "")) in hints
    return bool(hint or short_name or package)


def wait_for_activity(
    *,
    serial: str | None,
    timeout_ms: int = 3000,
    poll_ms: int = 250,
    hint: str | None = None,
    hints: list[str] | None = None,
    short_name: str | None = None,
    package: str | None = None,
) -> dict[str, Any]:
    """轮询前台 Activity，命中即返回（比固定 sleep 更快且更准确）。"""
    if not any((hint, hints, short_name, package)):
        raise ValueError("wait_for_activity 须指定 hint、hints、short_name 或 package 之一")

    timeout_ms = max(0, int(timeout_ms))
    poll_ms = max(100, min(int(poll_ms), 1000))
    deadline = time.time() + timeout_ms / 1000.0
    expected: dict[str, Any] = {}
    if hint:
        expected["hint"] = hint
    if hints:
        expected["hints"] = list(hints)
    if short_name:
        expected["shortName"] = short_name
    if package:
        expected["package"] = package

    started = time.time()
    polls = 0
    last_fa: dict[str, Any] = {"ok": False, "error": "尚未探测"}

    while time.time() <= deadline:
        polls += 1
        last_fa = get_foreground_activity(serial=serial)
        if _activity_matches(
            last_fa,
            hint=hint,
            hints=hints,
            short_name=short_name,
            package=package,
        ):
            elapsed_ms = int((time.time() - started) * 1000)
            return {
                "ok": True,
                "matched": True,
                "elapsedMs": elapsed_ms,
                "polls": polls,
                "expected": expected,
                "foregroundActivity": last_fa,
            }
        remaining = deadline - time.time()
        if remaining <= 0:
            break
        time.sleep(min(poll_ms / 1000.0, remaining))

    elapsed_ms = int((time.time() - started) * 1000)
    return {
        "ok": False,
        "matched": False,
        "elapsedMs": elapsed_ms,
        "polls": polls,
        "expected": expected,
        "foregroundActivity": last_fa,
        "error": "wait_activity 超时",
    }
