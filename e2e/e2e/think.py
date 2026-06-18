"""思考：根据读屏 + 自然语言步骤 + 知识库，决定下一步操作。"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from .perceive import screen_summary
from .scene_gate import check_require_before, observe_tree_stale, ui_tree_unreliable
from .step_hints import case_modules, lookup_step_hint


@dataclass
class Plan:
    action: str
    reasoning: str
    target: str = ""
    center: list[int] | None = None
    tap_pct: list[float] | None = None
    text: str | None = None
    resource_id: str | None = None
    wait_sec: float = 0.0
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_VERB_PATTERNS: list[tuple[str, str]] = [
    (r"^(启动|打开)", "launch"),
    (r"^(清除|清数据)", "clear_app"),
    (r"^(点击|点|轻点|按)", "tap"),
    (r"^(输入|填写|填入)", "text"),
    (r"^(滑动|上滑|下滑|左滑|右滑)", "swipe"),
    (r"^(返回|后退)", "back"),
    (r"^(等待|稍等)", "wait"),
    (r"^(截图|截屏)", "capture"),
    (r"^(确认|验收|检查)", "verify"),
]


def _parse_intent(nl_step: str) -> tuple[str, str]:
    step = (nl_step or "").strip()
    if not step:
        return "abort", ""

    for pattern, action in _VERB_PATTERNS:
        match = re.match(pattern, step)
        if match:
            target = step[match.end() :].strip(" ：:，,")
            return action, target or step

    if "登录" in step or "首页" in step:
        return "tap", step
    return "tap", step


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", (s or "").casefold())


def _find_clickable(screen: dict[str, Any], target: str) -> dict[str, Any] | None:
    ui = screen.get("ui") if isinstance(screen.get("ui"), dict) else {}
    clickables = ui.get("clickables") if isinstance(ui.get("clickables"), list) else []
    if not clickables:
        return None

    target_norm = _norm(target)
    if not target_norm:
        return None

    scored: list[tuple[int, dict[str, Any]]] = []
    for item in clickables:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "")
        text = str(item.get("text") or "")
        rid = str(item.get("resourceId") or "")
        hay = _norm(f"{label} {text} {rid}")
        if hay == target_norm:
            return item
        score = 0
        if target_norm in hay:
            score += 10
        for token in re.split(r"[\s/]+", target):
            token = _norm(token)
            if len(token) >= 2 and token in hay:
                score += 3
        if score > 0:
            scored.append((score, item))

    if not scored:
        return None
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return scored[0][1]




def think_step(
    *,
    nl_step: str,
    screen: dict[str, Any],
    case: dict[str, Any] | None = None,
    kb_hints: list[str] | None = None,
) -> Plan:
    """单步思考：自然语言 → 结构化操作计划。"""
    case = case or {}
    intent, target = _parse_intent(nl_step)
    summary = screen_summary(screen)

    if intent == "abort":
        return Plan(action="abort", reasoning="空步骤", target=target)

    if re.search(r"确保.*英语|英语.*登录|切换.*英语.*登录", nl_step, re.I):
        return Plan(
            action="ensure_english",
            reasoning="登录前检测 UI 语言，非英语则切 English",
            target=nl_step,
        )

    if re.search(r"处理.*权限|权限弹窗", nl_step):
        return Plan(
            action="dismiss_permission",
            reasoning="定位权限弹窗：仅在前台使用应用时允许",
            target=nl_step,
        )

    if intent == "launch":
        app_key = "yaahlan"
        if "yaha" in _norm(nl_step) and "yaahlan" not in _norm(nl_step):
            app_key = "yaha"
        return Plan(
            action="launch",
            reasoning="冷启动目标 App（e2e driver）",
            target=target or nl_step,
            meta={"app": app_key, "waitMs": 4000},
        )

    if intent == "clear_app":
        return Plan(
            action="clear_app",
            reasoning="清除应用数据（等效退出登录）",
            target=target or nl_step,
            meta={"app": "yaahlan"},
        )

    if intent == "wait":
        sec = 2.0
        num = re.search(r"(\d+(?:\.\d+)?)\s*秒", nl_step)
        if num:
            sec = float(num.group(1))
        return Plan(action="wait", reasoning=f"等待 {sec}s", wait_sec=sec, target=target)

    if intent == "back":
        return Plan(action="back", reasoning="系统返回", target=target)

    if intent == "capture":
        from pathlib import Path

        account = case.get("account") if isinstance(case.get("account"), dict) else {}
        phone = str(account.get("phone") or "unknown").strip()
        modules = case_modules(case)
        step_hint = lookup_step_hint(modules, nl_step) or {}
        dest_name = str(step_hint.get("destName") or f"yaahlan-profile-{phone}.png")
        dest_path = step_hint.get("destPath")
        if not dest_path:
            dest_path = str(Path.home() / "Desktop" / dest_name)
        return Plan(
            action="capture",
            reasoning=f"截图保存到 {dest_path}",
            target=target or nl_step,
            meta={"destPath": str(dest_path), "maxEdge": int(step_hint.get("maxEdge") or 1170)},
        )

    if intent == "swipe":
        modules = case_modules(case)
        step_hint = lookup_step_hint(modules, nl_step) or {}
        swipe_cfg = step_hint.get("swipe") if isinstance(step_hint.get("swipe"), dict) else {}
        return Plan(
            action="swipe",
            reasoning=str(step_hint.get("note") or "滑动"),
            target=target,
            meta={"swipe": swipe_cfg},
        )

    if intent == "verify":
        return Plan(
            action="verify",
            reasoning="本步为验收描述，交由断言层",
            target=target or nl_step,
            meta={"rawStep": nl_step},
        )

    if intent == "text":
        value = target
        account = case.get("account") if isinstance(case.get("account"), dict) else {}
        modules = case_modules(case)
        step_hint = lookup_step_hint(modules, nl_step)
        if step_hint:
            gate = check_require_before(screen, step_hint)
            strict = bool(step_hint.get("strict")) and bool((case.get("metadata") or {}).get("strictLogin"))
            optional = bool(step_hint.get("optional")) and not strict
            if not gate.get("ok"):
                if optional:
                    return Plan(
                        action="skip",
                        reasoning=f"可选输入跳过：{gate.get('reason')}",
                        target=target,
                        meta={"sceneGate": gate, "optional": True},
                    )
                return Plan(
                    action="scene_blocked",
                    reasoning=f"步前门禁：{gate.get('reason')}（{_format_gate(gate)}）",
                    target=target,
                    meta={"sceneGate": gate},
                )
        if "手机号" in nl_step and account.get("phone"):
            value = str(account["phone"])
        if "验证码" in nl_step and account.get("verifyCode"):
            value = str(account["verifyCode"])
        clear_before = bool(step_hint.get("clearBefore")) if step_hint else False
        return Plan(
            action="text",
            reasoning=f"输入文本（{summary}）",
            target=target,
            text=value,
            meta={"clearBefore": clear_before},
        )

    if intent == "tap":
        modules = case_modules(case)
        step_hint = lookup_step_hint(modules, nl_step)
        unreliable = ui_tree_unreliable(screen) or observe_tree_stale(screen)
        strict = bool(step_hint.get("strict")) and bool((case.get("metadata") or {}).get("strictLogin"))

        if step_hint:
            gate = check_require_before(screen, step_hint)
            optional = bool(step_hint.get("optional")) and not strict
            if not gate.get("ok"):
                if optional:
                    label_probe = str(step_hint.get("label") or "")
                    if not (label_probe and _find_clickable(screen, label_probe)):
                        return Plan(
                            action="skip",
                            reasoning=f"可选步跳过：{gate.get('reason')}",
                            target=target,
                            meta={"sceneGate": gate, "optional": True},
                        )
                else:
                    return Plan(
                        action="scene_blocked",
                        reasoning=f"步前门禁：{gate.get('reason')}（{_format_gate(gate)}）",
                        target=target,
                        meta={"sceneGate": gate},
                    )

        if step_hint and strict and step_hint.get("resourceId"):
            unreliable = True

        if not unreliable:
            for probe in (target, str(step_hint.get("label") or "") if step_hint else ""):
                if not probe:
                    continue
                hit = _find_clickable(screen, probe)
                if hit:
                    rid = str(hit.get("resourceId") or "")
                    if ":id/post" in rid and step_hint and step_hint.get("resourceId") not in {None, "", "post"}:
                        continue
                    return Plan(
                        action="tap",
                        reasoning=f"在可点元素匹配「{probe}」：{hit.get('label', '')[:40]}",
                        target=target,
                        center=list(hit.get("center") or []) or None,
                        tap_pct=list(hit.get("tapPct") or []) or None,
                        resource_id=str(hit.get("resourceId") or "") or None,
                    )

        if step_hint:
            rid = str(step_hint.get("resourceId") or "") or None
            if step_hint.get("tapOnly"):
                rid = None
            tap_pct = step_hint.get("tapPct")
            pct = list(tap_pct) if isinstance(tap_pct, list) and len(tap_pct) >= 2 else None
            note = str(step_hint.get("note") or nl_step)
            return Plan(
                action="tap",
                reasoning=f"步骤提示回退（{'ui不可靠' if unreliable else '未匹配控件'}）：{note}",
                target=target,
                tap_pct=pct,
                resource_id=rid,
                meta={"stepHint": True},
            )

        hint_note = ""
        if kb_hints:
            hint_note = f"；知识库提示 {len(kb_hints)} 条"
        return Plan(
            action="need_agent",
            reasoning=f"未在 ui.clickables 匹配「{target}」{hint_note}；需 Agent 读图或 locate 纠偏",
            target=target,
            meta={"screenSummary": summary, "kbHints": (kb_hints or [])[:5]},
        )

    return Plan(
        action="unsupported",
        reasoning=f"暂未实现意图 {intent}",
        target=target,
    )


def _format_gate(gate: dict[str, Any]) -> str:
    actual = gate.get("actual") if isinstance(gate.get("actual"), dict) else {}
    return (
        f"hint={actual.get('hint', '—')}, scene={actual.get('scene', '—')}, "
        f"shortName={actual.get('shortName', '—')}"
    )
