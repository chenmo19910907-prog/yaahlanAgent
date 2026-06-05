"""前台 Activity 探测（dumpsys），用于片段间验收，避免读图。"""

from __future__ import annotations

import re
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
    "UserProfileActivity": "profile",
    "SettingActivity": "settings",
    "FeedPublishActivity": "feed_publish",
    "GiftPanelActivity": "gift_panel",
}

_RESUMED_PATTERNS = (
    re.compile(r"mResumedActivity:\s*ActivityRecord\{[^}]*\s+(\S+)/(\S+)\s"),
    re.compile(r"topResumedActivity=ActivityRecord\{[^}]*\s+(\S+)/(\S+)\s"),
    re.compile(r"mFocusedActivity:\s*ActivityRecord\{[^}]*\s+(\S+)/(\S+)\s"),
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
    return "unknown"


def parse_resumed_activity(dumpsys_text: str) -> tuple[str, str] | None:
    """从 dumpsys activity activities 文本解析 package 与 activity。"""
    for pattern in _RESUMED_PATTERNS:
        match = pattern.search(dumpsys_text)
        if match:
            return match.group(1), match.group(2)
    return None


def get_foreground_activity(*, serial: str | None) -> dict[str, Any]:
    proc = run_adb(
        ["shell", "dumpsys", "activity", "activities"],
        serial=serial,
        timeout_s=15.0,
        check=True,
    )
    text = proc.stdout.decode("utf-8", errors="replace")
    parsed = parse_resumed_activity(text)
    if parsed is None:
        return {
            "ok": False,
            "error": "无法从 dumpsys 解析 mResumedActivity",
        }

    package, activity = parsed
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
