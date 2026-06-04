"""录制流程：导航阶段（截图+知识库）与执行阶段（纯脚本、不截图）。"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from .apps import YAAHLAN, YAHA
from .chain import run_chain
from .device import run_adb
from .macros import apply_skip_flags
from .recorded_scripts import load_flow_file, load_fragment, scripts_root
from .screenshot import capture_screenshot


def flows_dir() -> Path:
    return scripts_root() / "流程"


def list_flow_files() -> list[Path]:
    d = flows_dir()
    if not d.is_dir():
        return []
    return sorted(d.glob("*.json"))


def load_flow(name: str) -> dict[str, Any]:
    data = load_flow_file(name)
    _apply_app_defaults(data)
    return data


def _apply_app_defaults(flow: dict[str, Any]) -> None:
    """未写 appPackage 时固定为 Yaahlan，避免误启 com.immomo.yaha (Yaha)。"""
    app_key = flow.get("app", "yaahlan")
    if app_key not in ("yaahlan", "yaha"):
        raise ValueError(f"未知 app {app_key!r}，仅支持 yaahlan | yaha")
    target = YAAHLAN if app_key == "yaahlan" else YAHA
    flow.setdefault("appPackage", target["package"])
    flow.setdefault("appActivity", target["activity"])
    flow.setdefault("launchWaitMs", target["launch_wait_ms"])
    flow.setdefault("appLabel", target["label"])
    flow.setdefault("launchMode", target.get("launch_mode", "activity"))


def _format_bootstrap(bootstrap: dict[str, Any]) -> str:
    kind = bootstrap.get("type", "")
    if kind == "noop":
        return "无需操作（已到入口）"
    if kind == "launch_app":
        pkg = bootstrap.get("package") or ""
        return f"启动应用 {pkg or '(flow.appPackage)'}"
    if kind in ("macro", "script"):
        key = bootstrap.get("id") or bootstrap.get("name", "")
        return f"录制片段 {key}"
    if kind == "key":
        return f"按键 {bootstrap.get('code', '')} (BACK=4)"
    if kind == "chain":
        return f"步骤文件 {bootstrap.get('path', '')}"
    return str(bootstrap)


def build_locate_payload(flow: dict[str, Any], *, screenshot: dict[str, Any]) -> dict[str, Any]:
    entry = flow.get("entry") or {}
    states = flow.get("states") or {}
    state_list = [
        {
            "id": sid,
            "description": spec.get("description", ""),
            "bootstrap": _format_bootstrap(spec.get("bootstrap") or {}),
        }
        for sid, spec in states.items()
        if isinstance(spec, dict)
    ]
    recorded = flow.get("recorded") or {}
    return {
        "phase": "navigate",
        "flow": flow.get("name"),
        "description": flow.get("description", ""),
        "screenshot": screenshot,
        "kbRef": flow.get("kbRef", []),
        "entry": {
            "description": entry.get("description", ""),
            "signals": entry.get("signals", []),
        },
        "states": state_list,
        "recorded": {
            "type": recorded.get("type"),
            "id": recorded.get("id") or recorded.get("name"),
            "name": flow.get("name"),
            "capture": recorded.get("capture", "never"),
        },
        "agentInstruction": (
            "1) 读 screenshot 判断当前属于哪个 state（对照 entry.signals 与 states.description）。"
            "2) 若已满足 entry，执行: flow run <name> [--text ...]（录制段不截图）。"
            "3) 否则: flow bootstrap <name> --from <state_id>，再 flow locate 重复，直到可 run。"
        ),
    }


def run_locate(
    *,
    name: str,
    serial: str,
    screenshot_dir: Path,
    max_screenshots: int,
) -> dict[str, Any]:
    flow = load_flow(name)
    cap = capture_screenshot(
        serial=serial,
        directory=screenshot_dir,
        max_keep=max_screenshots,
    )
    payload = build_locate_payload(flow, screenshot=cap)
    payload["phase"] = "navigate"
    return payload


def _launch_app(
    *,
    serial: str,
    package: str,
    activity: str,
    wait_ms: int,
    force_stop: list[str] | None = None,
    bootstrap_launch_mode: str = "activity",
) -> dict[str, Any]:
    stopped: list[str] = []
    for pkg in force_stop or []:
        run_adb(["shell", "am", "force-stop", pkg], serial=serial, check=True)
        stopped.append(pkg)
    launch_mode = bootstrap_launch_mode or "activity"
    if launch_mode == "launcher":
        run_adb(
            [
                "shell",
                "monkey",
                "-p",
                package,
                "-c",
                "android.intent.category.LAUNCHER",
                "1",
            ],
            serial=serial,
            check=True,
        )
        component = f"{package} (LAUNCHER)"
    else:
        if "/" in activity or activity.startswith("."):
            component = f"{package}/{activity.lstrip('/')}"
        else:
            component = f"{package}/{activity}"
        run_adb(
            ["shell", "am", "start", "-n", component],
            serial=serial,
            check=True,
        )
    if wait_ms > 0:
        time.sleep(wait_ms / 1000.0)
    out: dict[str, Any] = {
        "action": "launch_app",
        "component": component,
        "waitMs": wait_ms,
    }
    if stopped:
        out["forceStopped"] = stopped
    return out


def run_bootstrap(
    *,
    name: str,
    from_state: str,
    serial: str,
    screenshot_dir: Path,
    max_screenshots: int,
    skip: set[str],
    capture_end: bool = True,
    use_adaptation: bool = True,
) -> dict[str, Any]:
    flow = load_flow(name)
    states = flow.get("states") or {}
    if from_state not in states:
        known = ", ".join(states)
        raise ValueError(f"未知 state {from_state!r}，本流程可选: {known}")
    spec = states[from_state]
    if not isinstance(spec, dict):
        raise ValueError(f"state {from_state} 配置无效")
    bootstrap = spec.get("bootstrap")
    if not isinstance(bootstrap, dict):
        raise ValueError(f"state {from_state} 缺少 bootstrap")

    kind = bootstrap.get("type")
    result: dict[str, Any] = {
        "phase": "navigate",
        "flow": name,
        "fromState": from_state,
        "bootstrap": bootstrap,
    }

    if kind == "noop":
        result["noop"] = True
        result["message"] = bootstrap.get("message", "已在入口附近，请直接 flow run")
    elif kind == "launch_app":
        pkg = bootstrap.get("package") or flow.get("appPackage")
        act = bootstrap.get("activity") or flow.get("appActivity")
        if not pkg or not act:
            raise ValueError("launch_app 需要 package/activity 或流程级 appPackage/appActivity")
        wait_ms = int(bootstrap.get("wait_ms", flow.get("launchWaitMs", 4000)))
        force_stop = list(bootstrap.get("force_stop") or flow.get("launchForceStop") or [])
        if str(pkg) == YAAHLAN["package"] and YAHA["package"] not in force_stop:
            force_stop = [YAHA["package"], *force_stop]
        result["launch"] = _launch_app(
            serial=serial,
            package=str(pkg),
            activity=str(act),
            wait_ms=wait_ms,
            force_stop=force_stop,
            bootstrap_launch_mode=str(
                bootstrap.get("launch_mode") or flow.get("launchMode", "activity")
            ),
        )
    elif kind in ("macro", "script"):
        script_key = str(bootstrap.get("id") or bootstrap["name"])
        macro_spec = load_fragment(script_key, text=None)
        steps = apply_skip_flags(list(macro_spec.get("steps", [])), skip=skip)
        chain_out = run_chain(
            serial=serial,
            steps=steps,
            capture="never",
            screenshot_dir=screenshot_dir,
            max_screenshots=max_screenshots,
            use_adaptation=use_adaptation,
        )
        result["script"] = macro_spec.get("name", script_key)
        result["scriptId"] = script_key
        result["stepsExecuted"] = chain_out.get("stepsExecuted")
        if chain_out.get("adaptation"):
            result["adaptation"] = chain_out["adaptation"]
    elif kind == "key":
        from .actions import keyevent

        code = int(bootstrap["code"])
        keyevent(code=code, serial=serial)
        ms = int(bootstrap.get("sleep_ms", 500))
        if ms > 0:
            time.sleep(ms / 1000.0)
        result["key"] = code
    elif kind == "chain":
        from .chain import load_steps_file

        path = Path(str(bootstrap["path"]))
        if not path.is_absolute():
            path = (scripts_root().parent / path).resolve()
        steps, _ = load_steps_file(path)
        chain_out = run_chain(
            serial=serial,
            steps=steps,
            capture="never",
            screenshot_dir=screenshot_dir,
            max_screenshots=max_screenshots,
            use_adaptation=use_adaptation,
        )
        result["stepsFile"] = str(path)
        result["stepsExecuted"] = chain_out.get("stepsExecuted")
        if chain_out.get("adaptation"):
            result["adaptation"] = chain_out["adaptation"]
    else:
        raise ValueError(f"不支持的 bootstrap.type: {kind!r}")

    if capture_end:
        cap = capture_screenshot(
            serial=serial,
            directory=screenshot_dir,
            max_keep=max_screenshots,
        )
        cap["capturePoint"] = "bootstrap_end"
        result["screenshot"] = cap
    else:
        result["screenshot"] = None

    result["next"] = f"flow locate {name}"
    return result


def run_recorded(
    *,
    name: str,
    serial: str,
    screenshot_dir: Path,
    max_screenshots: int,
    skip: set[str],
    text: str | None = None,
    verify_end: bool = False,
    use_adaptation: bool = True,
) -> dict[str, Any]:
    """执行录制段：默认全程不截图（由 Agent 在 locate 阶段已对齐入口）。"""
    flow = load_flow(name)
    recorded = flow.get("recorded")
    if not isinstance(recorded, dict):
        raise ValueError(f"流程 {name} 缺少 recorded 配置")

    capture = "end" if verify_end else str(recorded.get("capture", "never"))
    kind = recorded.get("type")
    result: dict[str, Any] = {
        "phase": "recorded",
        "flow": name,
        "capture": capture,
    }

    if kind in ("macro", "script"):
        script_key = str(recorded.get("id") or recorded["name"])
        macro_spec = load_fragment(script_key, text=text)
        steps = apply_skip_flags(list(macro_spec.get("steps", [])), skip=skip)
        chain_out = run_chain(
            serial=serial,
            steps=steps,
            capture=capture,  # type: ignore[arg-type]
            screenshot_dir=screenshot_dir,
            max_screenshots=max_screenshots,
            use_adaptation=use_adaptation,
        )
        result.update(chain_out)
        result["script"] = macro_spec.get("name", script_key)
        result["scriptId"] = script_key
        result["description"] = macro_spec.get("description", "")
        if text is not None:
            result["text"] = text
    elif kind == "chain":
        from .chain import load_steps_file

        path = Path(str(recorded["path"]))
        if not path.is_absolute():
            path = (scripts_root().parent / path).resolve()
        steps, file_cap = load_steps_file(path)
        if capture == "never" and file_cap != "never":
            capture = file_cap if verify_end else "never"
        chain_out = run_chain(
            serial=serial,
            steps=steps,
            capture=capture,  # type: ignore[arg-type]
            screenshot_dir=screenshot_dir,
            max_screenshots=max_screenshots,
            use_adaptation=use_adaptation,
        )
        result.update(chain_out)
        result["stepsFile"] = str(path)
    else:
        raise ValueError(f"不支持的 recorded.type: {kind!r}")

    result["agentInstruction"] = (
        "录制段已执行；若 --verify 则结束时有一张截图可核对，否则未截图。"
    )
    return result


def list_flows_summary() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for path in list_flow_files():
        try:
            flow = load_flow(path.stem)
        except (ValueError, json.JSONDecodeError, OSError):
            continue
        recorded = flow.get("recorded") or {}
        items.append(
            {
                "id": flow.get("id"),
                "name": flow.get("name", path.stem),
                "description": flow.get("description", ""),
                "recordedScript": recorded.get("id") or recorded.get("name"),
                "recordedCapture": recorded.get("capture", "never"),
                "kbRef": flow.get("kbRef", []),
            }
        )
    return items
