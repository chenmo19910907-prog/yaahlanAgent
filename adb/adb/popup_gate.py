"""关键页弹窗门禁：先截图读图判断，确认后再关弹窗（默认不盲点坐标）。"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from .actions import keyevent
from .activity import get_foreground_activity
from .chain import run_chain
from .macros import apply_skip_flags, resolve_macro
from .popup_analyze import (
    analyze_scene_from_tunnel,
    dismiss_scripts_for_analysis,
    load_popup_signals,
)
from .screenshot import capture_screenshot

_STUCK_HINTS = frozenset({"webview"})
_GATE_SCENES = frozenset({"home", "me", "room"})
_SCENE_FOR_HINT = {
    "in_room": "room",
}
_ME_DISMISS = "关闭Me页弹窗"
_DEFAULT_CAPTURE_MAX_EDGE = 1170


def infer_tab_from_step(step: dict[str, Any]) -> str | None:
    note = str(step.get("note", "")).lower()
    if "tab_profile" in note or note.strip() == "me":
        return "me"
    if "tab_room" in note or "tab_voice" in note or "切换房间" in note:
        return "room"
    if "tab_game" in note or "切换游戏" in note:
        return "game"
    if "tab_moment" in note or "切换动态" in note:
        return "moment"
    if "tab_message" in note or "切换消息" in note:
        return "message"
    return None


def resolve_gate_scene(
    *,
    hint: str,
    current_tab: str | None,
    explicit: str | None = None,
) -> str | None:
    if explicit and explicit != "auto":
        if explicit not in _GATE_SCENES:
            raise ValueError(f"未知 popup gate scene {explicit!r}，可选: home, me, room, auto")
        return explicit
    if hint in _STUCK_HINTS:
        return "home"
    if hint in _SCENE_FOR_HINT:
        return _SCENE_FOR_HINT[hint]
    if current_tab == "me":
        return "me"
    if hint == "home":
        return "home"
    return None


def _analysis_offline(scene: str) -> dict[str, Any]:
    cfg = load_popup_signals()
    scenes = cfg.get("scenes")
    spec = scenes.get(scene, {}) if isinstance(scenes, dict) else {}
    weak = spec.get("weakUiPopups")
    weak_list = [str(x) for x in weak] if isinstance(weak, list) else []
    dismiss = _ME_DISMISS if scene == "me" else str(cfg.get("defaultDismissScript", "关闭常见弹窗"))
    return {
        "scene": scene,
        "sceneLabel": spec.get("label", scene),
        "hasPopupSignals": False,
        "weakUiPopups": weak_list,
        "actionableSignals": [],
        "dismissScripts": [dismiss],
        "dismissSkipWhenNoPopup": cfg.get("dismissSkipWhenNoPopup", "dismiss_popup_taps"),
        "needScreenshot": True,
        "recommendation": "capture_first",
        "agentHint": f"scene={scene}：须读 screenshot 判断是否有弹窗，勿盲点 Cancel/BACK。",
    }


def _fetch_analysis(
    *,
    scene: str,
    momoid: str | None,
    since_seconds: int,
) -> dict[str, Any]:
    if momoid:
        return analyze_scene_from_tunnel(
            momoid=momoid,
            scene=scene,
            since_seconds=since_seconds,
        )
    return _analysis_offline(scene)


def _recover_webview(*, serial: str, max_back: int = 4) -> dict[str, Any]:
    """连续 BACK 退出误进的 H5/签到 WebView（非 Cancel 坐标）。"""
    last: dict[str, Any] = {}
    for _ in range(max(1, max_back)):
        keyevent(code=4, serial=serial)
        time.sleep(0.45)
        last = get_foreground_activity(serial=serial)
        if str(last.get("hint", "")) not in _STUCK_HINTS:
            break
    return last


def _dismiss_for_scene(
    *,
    serial: str,
    scene: str,
    analysis: dict[str, Any],
    screenshot_dir: Path,
    max_screenshots: int,
    use_adaptation: bool,
) -> list[dict[str, Any]]:
    if scene == "me":
        frag = resolve_macro(_ME_DISMISS)
        steps = list(frag.get("steps", []))
        out = run_chain(
            serial=serial,
            steps=steps,
            capture="never",
            screenshot_dir=screenshot_dir,
            max_screenshots=max_screenshots,
            use_adaptation=use_adaptation,
            popup_gate_auto=False,
        )
        return [
            {
                "script": frag.get("name", _ME_DISMISS),
                "scriptId": frag.get("id", "dismiss-me-popups"),
                "stepsExecuted": out.get("stepsExecuted"),
            }
        ]

    me_analysis = dict(analysis)
    if scene == "room":
        me_analysis["hasPopupSignals"] = True
        me_analysis.setdefault("dismissScripts", ["关闭常见弹窗"])

    return dismiss_scripts_for_analysis(
        serial=serial,
        analysis=me_analysis,
        screenshot_dir=screenshot_dir,
        max_screenshots=max_screenshots,
        use_adaptation=use_adaptation,
    )


def _capture_gate_shot(
    *,
    serial: str,
    screenshot_dir: Path,
    max_screenshots: int,
    max_edge: int | None,
    label: str,
) -> dict[str, Any]:
    cap = capture_screenshot(
        serial=serial,
        directory=screenshot_dir,
        max_keep=max(max_screenshots, 5),
        max_edge=max_edge,
    )
    cap["capturePoint"] = label
    return cap


def ensure_popups_cleared(
    *,
    serial: str,
    scene: str,
    screenshot_dir: Path,
    max_screenshots: int,
    momoid: str | None = None,
    since_seconds: int = 120,
    max_rounds: int = 2,
    max_edge: int | None = _DEFAULT_CAPTURE_MAX_EDGE,
    use_adaptation: bool = True,
    auto_dismiss: bool = False,
) -> dict[str, Any]:
    """
    弹窗门禁：
    - 默认（auto_dismiss=False）：仅截图，**不 tap/BACK**；home/me/room 弹窗由 Agent 读图后 tap Cancel。
    - auto_dismiss=True 或 CLI `--dismiss`：执行关弹窗脚本（legacy，首页/Me/房间建议不用）。
    """
    if scene not in _GATE_SCENES:
        raise ValueError(f"popup gate 不支持 scene={scene!r}")

    fa = get_foreground_activity(serial=serial)
    hint = str(fa.get("hint", ""))
    if hint in _STUCK_HINTS:
        fa = _recover_webview(serial=serial)
        hint = str(fa.get("hint", ""))

    analysis = _fetch_analysis(
        scene=scene,
        momoid=momoid,
        since_seconds=since_seconds,
    )

    cap_before = _capture_gate_shot(
        serial=serial,
        screenshot_dir=screenshot_dir,
        max_screenshots=max_screenshots,
        max_edge=max_edge,
        label=f"popup_gate_{scene}_before",
    )

    # 首页 / Me / 房间：弹窗由 Agent 读图点 Cancel，不自动 tap
    effective_dismiss = auto_dismiss

    if not effective_dismiss:
        weak = analysis.get("weakUiPopups") or []
        weak_text = "；".join(str(x) for x in weak[:3]) if weak else "见 scene 说明"
        return {
            "ok": False,
            "blocked": True,
            "phase": "capture",
            "scene": scene,
            "foregroundActivity": fa,
            "popupAnalysis": analysis,
            "screenshot": cap_before,
            "screenshotBeforeDismiss": cap_before,
            "screenshotAfterDismiss": None,
            "dismissExecuted": [],
            "requiresScreenshotReview": True,
            "autoDismiss": False,
            "agentHint": (
                f"已截图（未点击任何坐标）。请读 screenshot 判断 {scene} 页是否有弹窗"
                f"（常见：{weak_text}）。"
                f"确认需关闭时再执行：popup gate --scene {scene} --dismiss"
            ),
        }

    dismiss_blocks: list[dict[str, Any]] = []
    should_dismiss = bool(analysis.get("hasPopupSignals")) or scene in ("me", "room")
    if should_dismiss:
        dismiss_blocks = _dismiss_for_scene(
            serial=serial,
            scene=scene,
            analysis=analysis,
            screenshot_dir=screenshot_dir,
            max_screenshots=max_screenshots,
            use_adaptation=use_adaptation,
        )
        time.sleep(0.4)

    cap_after = _capture_gate_shot(
        serial=serial,
        screenshot_dir=screenshot_dir,
        max_screenshots=max_screenshots,
        max_edge=max_edge,
        label=f"popup_gate_{scene}_after",
    )

    final_fa = get_foreground_activity(serial=serial)
    final_hint = str(final_fa.get("hint", ""))
    ok = final_hint not in _STUCK_HINTS

    if scene == "me":
        agent_hint = (
            "Me 页已截图。读 screenshot，有弹窗则点 Cancel（勿 BACK）；"
            "或 `ai prepare --goal dismiss_me_popup`。"
            if ok
            else f"Me 页异常（hint={final_hint}）：读 screenshot，`ai prepare --goal recover`，勿 force-stop。"
        )
    elif ok:
        agent_hint = "关弹窗后已再截图；读 screenshotAfterDismiss 确认无弹窗后再继续下一段。"
    else:
        agent_hint = (
            f"仍卡在 {final_hint}：读 screenshot，必要时 BACK 或 recover，勿 force-stop。"
        )

    return {
        "ok": ok,
        "blocked": not ok,
        "phase": "dismiss",
        "scene": scene,
        "rounds": [{"dismissExecuted": dismiss_blocks}],
        "foregroundActivity": final_fa,
        "popupAnalysis": analysis,
        "screenshot": cap_after,
        "screenshotBeforeDismiss": cap_before,
        "screenshotAfterDismiss": cap_after,
        "dismissExecuted": dismiss_blocks,
        "requiresScreenshotReview": scene != "me",
        "autoDismiss": effective_dismiss,
        "agentHint": agent_hint,
    }


def auto_popup_gate_after_chain(
    *,
    serial: str,
    chain_result: dict[str, Any],
    screenshot_dir: Path,
    max_screenshots: int,
    momoid: str | None = None,
    since_seconds: int = 120,
    max_edge: int | None = _DEFAULT_CAPTURE_MAX_EDGE,
    use_adaptation: bool = True,
    auto_dismiss: bool = False,
) -> dict[str, Any] | None:
    """chain 结束后：落在 home/me/房内则先截图门禁（默认不盲点）。"""
    fa = get_foreground_activity(serial=serial)
    hint = str(fa.get("hint", ""))
    current_tab = chain_result.get("currentTab")
    tab = current_tab if isinstance(current_tab, str) else None

    scene = resolve_gate_scene(hint=hint, current_tab=tab)
    if scene is None:
        return None

    return ensure_popups_cleared(
        serial=serial,
        scene=scene,
        screenshot_dir=screenshot_dir,
        max_screenshots=max_screenshots,
        momoid=momoid,
        since_seconds=since_seconds,
        max_edge=max_edge,
        use_adaptation=use_adaptation,
        auto_dismiss=auto_dismiss,
    )
