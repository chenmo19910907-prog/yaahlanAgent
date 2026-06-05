"""结合 Tunnel 抓包分析关键节点是否可能出现弹窗。"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .recorded_scripts import scripts_root
from .tunnel_verify import TunnelVerifyOptions, filter_tunnel_items, wait_for_tunnel


def popup_signals_path() -> Path:
    return scripts_root() / "弹窗抓包信号.json"


def load_popup_signals() -> dict[str, Any]:
    data = json.loads(popup_signals_path().read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("弹窗抓包信号.json 根节点须为 object")
    return data


def _get_by_path(obj: Any, path: str) -> Any:
    cur = obj
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _eval_rule(item: dict[str, Any], rule: dict[str, Any]) -> bool:
    op = str(rule.get("op", "")).strip()
    expected = rule.get("value")
    actual = _get_by_path(item, str(rule.get("path", "")))

    if op == "exists":
        return actual is not None
    if op == "notEmpty":
        if actual is None:
            return False
        if isinstance(actual, (list, dict, str)):
            return len(actual) > 0
        return bool(actual)
    if op == "eq":
        try:
            return actual == expected or str(actual) == str(expected)
        except (TypeError, ValueError):
            return False
    if op == "ne":
        try:
            return actual != expected and str(actual) != str(expected)
        except (TypeError, ValueError):
            return True
    if op == "gt":
        try:
            return float(actual) > float(expected)
        except (TypeError, ValueError):
            return False
    return False


def _url_matches_patterns(url: str, patterns: list[str]) -> bool:
    low = url.lower()
    return any(p.lower() in low for p in patterns)


def _pick_latest_match(
    items: list[dict[str, Any]],
    signal: dict[str, Any],
) -> dict[str, Any] | None:
    patterns = signal.get("urlPatterns")
    if not isinstance(patterns, list) or not patterns:
        return None
    matched = [x for x in items if _url_matches_patterns(str(x.get("url", "")), patterns)]
    if not matched:
        return None
    return sorted(matched, key=lambda x: str(x.get("time", "")), reverse=True)[0]


def _rules_triggered(item: dict[str, Any], signal: dict[str, Any]) -> tuple[bool, list[str]]:
    rules = signal.get("rules")
    if not isinstance(rules, list) or not rules:
        return False, []

    hits: list[str] = []
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        if _eval_rule(item, rule):
            hits.append(str(rule.get("path", "")))

    mode = str(signal.get("ruleMode", "any"))
    if mode == "all":
        triggered = len(hits) == len(rules)
    else:
        triggered = len(hits) > 0
    return triggered, hits


def analyze_popup_signals(
    *,
    items: list[dict[str, Any]],
    scene: str,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = config or load_popup_signals()
    scenes = cfg.get("scenes")
    if not isinstance(scenes, dict):
        raise ValueError("弹窗抓包信号.json 缺少 scenes")

    scene_spec = scenes.get(scene)
    if not isinstance(scene_spec, dict):
        known = "、".join(sorted(scenes.keys()))
        raise ValueError(f"未知 scene {scene!r}，可选: {known}")

    weak_ui = scene_spec.get("weakUiPopups")
    weak_list = [str(x) for x in weak_ui] if isinstance(weak_ui, list) else []

    signal_results: list[dict[str, Any]] = []
    actionable: list[dict[str, Any]] = []

    for raw_signal in scene_spec.get("signals") or []:
        if not isinstance(raw_signal, dict):
            continue
        signal_id = str(raw_signal.get("id", ""))
        item = _pick_latest_match(items, raw_signal)
        if item is None:
            signal_results.append(
                {
                    "id": signal_id,
                    "matched": False,
                    "uiPopup": raw_signal.get("uiPopup"),
                    "confidence": raw_signal.get("confidence"),
                }
            )
            continue

        triggered, rule_hits = _rules_triggered(item, raw_signal)
        confidence = str(raw_signal.get("confidence", "low"))
        rules = raw_signal.get("rules")
        has_rules = isinstance(rules, list) and len(rules) > 0

        if has_rules:
            popup_likely = triggered
        else:
            popup_likely = confidence in ("high", "medium")

        entry: dict[str, Any] = {
            "id": signal_id,
            "matched": True,
            "popupLikely": popup_likely,
            "uiPopup": raw_signal.get("uiPopup"),
            "confidence": confidence,
            "time": item.get("time"),
            "url": item.get("url"),
            "httpStatus": item.get("status"),
            "responseEc": (item.get("response") or {}).get("ec")
            if isinstance(item.get("response"), dict)
            else None,
            "ruleHits": rule_hits,
            "dismissScript": raw_signal.get("dismissScript"),
        }
        if popup_likely and raw_signal.get("dismissScript"):
            actionable.append(entry)
        signal_results.append(entry)

    has_popup_signals = any(
        x.get("popupLikely") for x in signal_results if isinstance(x, dict)
    )
    need_screenshot = bool(weak_list) or has_popup_signals

    dismiss_scripts: list[str] = []
    default_dismiss = str(cfg.get("defaultDismissScript", "关闭常见弹窗"))
    for entry in actionable:
        script = str(entry.get("dismissScript") or "").strip()
        if script and script not in dismiss_scripts:
            dismiss_scripts.append(script)
    if (has_popup_signals or weak_list) and not dismiss_scripts and default_dismiss:
        dismiss_scripts.append(default_dismiss if scene != "me" else "关闭Me页弹窗")
    if scene == "me" and "关闭Me页弹窗" not in dismiss_scripts:
        dismiss_scripts = ["关闭Me页弹窗"]

    recommendation = "continue"
    if has_popup_signals or weak_list:
        recommendation = "dismiss_then_capture"
    if weak_list and not has_popup_signals:
        recommendation = "capture_first"

    return {
        "scene": scene,
        "sceneLabel": scene_spec.get("label", scene),
        "hasPopupSignals": has_popup_signals,
        "weakUiPopups": weak_list,
        "signals": signal_results,
        "actionableSignals": actionable,
        "recommendation": recommendation,
        "dismissScripts": dismiss_scripts,
        "dismissSkipWhenNoPopup": cfg.get("dismissSkipWhenNoPopup", "dismiss_popup_taps"),
        "needScreenshot": need_screenshot,
        "agentHint": _build_agent_hint(
            scene_label=str(scene_spec.get("label", scene)),
            has_popup_signals=has_popup_signals,
            weak_list=weak_list,
            dismiss_scripts=dismiss_scripts,
        ),
    }


def _build_agent_hint(
    *,
    scene_label: str,
    has_popup_signals: bool,
    weak_list: list[str],
    dismiss_scripts: list[str],
) -> str:
    parts = [f"节点「{scene_label}」："]
    if has_popup_signals:
        scripts = "、".join(dismiss_scripts) or "关闭常见弹窗"
        parts.append(f"抓包显示可能有运营/配置类弹窗，建议先 macro {scripts}，再 capture 读图。")
    if weak_list:
        parts.append(
            "以下弹窗抓包难覆盖，必须读截图确认："
            + "；".join(weak_list[:4])
            + ("…" if len(weak_list) > 4 else "")
        )
    if not has_popup_signals and not weak_list:
        parts.append("未发现明显弹窗信号，可直接后续操作；仍建议结束时 capture 抽检。")
    return "".join(parts)


def fetch_recent_tunnel_items(
    *,
    momoid: str,
    since_seconds: int,
    g_appid: str = "All",
    g_env: str = "alpha",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    start_time = int(time.time()) - max(1, since_seconds)
    opts = TunnelVerifyOptions(
        momoid=momoid,
        keyword="",
        wait_seconds=1,
        poll_interval_ms=500,
        expect_http_status=None,
        since_buffer_seconds=0,
        g_appid=g_appid,
        g_env=g_env,
    )
    from .tunnel_verify import _ensure_tunnel_import

    list_requests, normalize_request_list, tunnel_success = _ensure_tunnel_import()
    payload = list_requests(
        base_url="https://tunnel.wemomo.com",
        momoid=momoid,
        start_time=start_time,
        keyword="",
        g_appid=g_appid,
        g_env=g_env,
    )
    meta = {
        "tunnelEc": payload.get("ec"),
        "tunnelEm": payload.get("em"),
        "tunnelOk": tunnel_success(payload.get("ec")),
        "startTime": start_time,
        "itemCount": 0,
    }
    if not meta["tunnelOk"]:
        return [], meta
    items = normalize_request_list(payload)
    meta["itemCount"] = len(items)
    return items, meta


def dismiss_scripts_for_analysis(
    *,
    serial: str,
    analysis: dict[str, Any],
    screenshot_dir: Path,
    max_screenshots: int,
    use_adaptation: bool = True,
) -> list[dict[str, Any]]:
    """按场景执行关弹窗：login/home 无抓包信号时跳过 Cancel；me 保留 Cancel。"""
    from .chain import run_chain
    from .macros import apply_skip_flags, resolve_macro

    scripts = analysis.get("dismissScripts")
    if not isinstance(scripts, list) or not scripts:
        return []

    skip_keys: set[str] = set()
    scene = str(analysis.get("scene", ""))
    if scene == "me":
        skip_keys = set()
    elif not analysis.get("hasPopupSignals"):
        if scene in ("login", "home"):
            skip_keys.add(str(analysis.get("dismissSkipWhenNoPopup", "dismiss_popup_taps")))
        if scene == "home":
            skip_keys.add("dismiss_popup_back")

    blocks: list[dict[str, Any]] = []
    for name in scripts:
        script_name = (
            "关闭Me页弹窗"
            if scene == "me" and str(name) in ("关闭常见弹窗", "关闭Me页弹窗")
            else str(name)
        )
        frag = resolve_macro(script_name)
        steps = apply_skip_flags(list(frag.get("steps", [])), skip=skip_keys)
        out = run_chain(
            serial=serial,
            steps=steps,
            capture="never",
            screenshot_dir=screenshot_dir,
            max_screenshots=max_screenshots,
            use_adaptation=use_adaptation,
        )
        blocks.append(
            {
                "script": frag.get("name", name),
                "scriptId": frag.get("id", name),
                "skipKeys": sorted(skip_keys),
                "stepsExecuted": out.get("stepsExecuted"),
            }
        )
    return blocks


def analyze_scene_from_tunnel(
    *,
    momoid: str,
    scene: str,
    since_seconds: int = 120,
    g_appid: str = "All",
    g_env: str = "alpha",
) -> dict[str, Any]:
    items, meta = fetch_recent_tunnel_items(
        momoid=momoid,
        since_seconds=since_seconds,
        g_appid=g_appid,
        g_env=g_env,
    )
    analysis = analyze_popup_signals(items=items, scene=scene)
    analysis["momoid"] = momoid
    analysis["sinceSeconds"] = since_seconds
    analysis["tunnelMeta"] = meta
    return analysis
