#!/usr/bin/env python3
"""公会盘古：读场景清单与 MSE 当前 configValue（预上线 stage）。"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
SCENARIOS_PATH = REPO / "workflow/config/guild_pangu_shift_scenarios.json"
WORKFLOWS_DIR = REPO / "workflow/workflows"
MSE_DIR = REPO / "MSE"


def _ensure_mse_path() -> None:
    p = str(MSE_DIR)
    if p not in sys.path:
        sys.path.insert(0, p)


def load_catalog() -> dict[str, Any]:
    with SCENARIOS_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise RuntimeError("guild_pangu_shift_scenarios.json 格式错误")
    return data


def scenario_by_key(catalog: dict[str, Any], key: str) -> dict[str, Any]:
    for item in catalog.get("scenarios") or []:
        if isinstance(item, dict) and str(item.get("key") or "") == key:
            return item
    raise KeyError(key)


def _parse_config_value(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return {}
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    return {}


def fetch_config_object(scenario: dict[str, Any]) -> dict[str, Any]:
    _ensure_mse_path()
    from mse.mutate import fetch_config_item, load_context  # noqa: WPS433

    catalog = load_catalog()
    env = catalog.get("env") or {}
    ctx = load_context(
        region=str(env.get("region") or "alpha"),
        env=str(env.get("env") or "alpha"),
        cluster=str(env.get("cluster") or "stage"),
        app_key=str(env.get("app_key") or ""),
    )
    config_key = str(scenario["config_key"])
    namespace = str(scenario["namespace"])
    item, _display = fetch_config_item(ctx, config_key=config_key, name_space=namespace)
    return _parse_config_value(item.get("configValue"))


def white_users_to_input(users: Any) -> str:
    if not isinstance(users, list):
        return ""
    parts = [str(u).strip() for u in users if str(u).strip()]
    return ",".join(parts)


def current_form_values(scenario_key: str) -> dict[str, Any]:
    catalog = load_catalog()
    scenario = scenario_by_key(catalog, scenario_key)
    cfg = fetch_config_object(scenario)
    fields = list(scenario.get("fields") or [])
    out: dict[str, Any] = {
        "scenario": scenario_key,
        "configKey": scenario.get("config_key"),
        "namespace": scenario.get("namespace"),
        "whiteUsers": white_users_to_input(cfg.get("whiteUsers")),
        "fixedTimeSec": str(cfg.get("fixedTimeSec") or ""),
        "expireTimeSec": str(cfg.get("expireTimeSec") or ""),
        "shiftTime": str(cfg.get("shiftTime") if cfg.get("shiftTime") is not None else ""),
        "fields": fields,
    }
    return out


def _workflow_usage_note(workflow_id: str) -> str:
    wid = str(workflow_id or "").strip()
    if not wid:
        return ""
    path = WORKFLOWS_DIR / f"{wid}.json"
    if not path.is_file():
        return ""
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return ""
    if not isinstance(data, dict):
        return ""
    return str(data.get("description") or "").strip()


def _scenario_usage_note(raw: dict[str, Any]) -> str:
    explicit = str(raw.get("usage_note") or raw.get("detail") or "").strip()
    if explicit:
        return explicit
    from_workflow = _workflow_usage_note(str(raw.get("workflow_id") or ""))
    if from_workflow:
        return from_workflow
    extra = str(raw.get("extra_note") or "").strip()
    example = str(raw.get("example") or "").strip()
    parts = [p for p in (extra, f"举例：{example}" if example else "") if p]
    return " ".join(parts)


def scenarios_for_web() -> dict[str, Any]:
    catalog = load_catalog()
    scenarios_out: list[dict[str, Any]] = []
    for raw in catalog.get("scenarios") or []:
        if not isinstance(raw, dict) or raw.get("read_only"):
            continue
        fields = list(raw.get("fields") or [])
        only_edit = list(raw.get("only_edit_fields") or raw.get("required_fields") or fields)
        scenarios_out.append(
            {
                "key": raw.get("key"),
                "docIndex": raw.get("doc_index"),
                "name": raw.get("name"),
                "onlyEditFields": only_edit,
                "example": str(raw.get("example") or "").strip(),
                "extraNote": str(raw.get("extra_note") or "").strip(),
                "usageNote": _scenario_usage_note(raw),
            }
        )
    env = catalog.get("env") or {}
    return {
        "docNote": catalog.get("doc_note") or "",
        "web_usage": catalog.get("web_usage") or {},
        "env": env,
        "scenarios": scenarios_out,
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="公会盘古 MSE 读当前值")
    parser.add_argument("--scenarios-json", action="store_true", help="输出场景清单（Web 用）")
    parser.add_argument("--scenario", default="", help="读指定场景当前表单值 JSON")
    args = parser.parse_args()
    if args.scenarios_json:
        print(json.dumps(scenarios_for_web(), ensure_ascii=False))
        return 0
    key = str(args.scenario or "").strip()
    if not key:
        print("需要 --scenario 或 --scenarios-json", file=sys.stderr)
        return 2
    print(json.dumps(current_form_values(key), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
