#!/usr/bin/env python3
"""公会盘古：按业务场景改 MSE shiftTime 配置（预上线 stage）并可选发布。"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
SCENARIOS_PATH = REPO / "workflow/config/guild_pangu_shift_scenarios.json"
MSE = REPO / "MSE/mse_execute.py"


def _load_scenarios() -> dict[str, Any]:
    with SCENARIOS_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise RuntimeError("guild_pangu_shift_scenarios.json 格式错误")
    return data


def _scenario_by_key(data: dict[str, Any], key: str) -> dict[str, Any]:
    for item in data.get("scenarios") or []:
        if isinstance(item, dict) and str(item.get("key") or "") == key:
            return item
    raise RuntimeError(f"未知场景 key={key!r}，见 workflow/config/guild_pangu_shift_scenarios.json")


def _run_mse(args: list[str]) -> None:
    cmd = [sys.executable, str(MSE), *args]
    proc = subprocess.run(cmd, cwd=str(REPO), text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"mse_execute 失败（exit={proc.returncode}）")


def _optional_int(name: str, raw: str | None) -> int | None:
    if raw is None or str(raw).strip() == "":
        return None
    return int(str(raw).strip())


def _parse_white_users(raw: str | None) -> list[str] | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    parts = [p.strip() for p in text.replace("，", ",").split(",")]
    ids = [p for p in parts if p]
    return ids if ids else []


def main() -> int:
    parser = argparse.ArgumentParser(description="公会盘古 shiftTime 改参")
    parser.add_argument("--scenario", required=True, help="scenarios.json 中的 key")
    parser.add_argument("--fixed-time-sec", dest="fixed_time_sec", default="")
    parser.add_argument("--expire-time-sec", dest="expire_time_sec", default="")
    parser.add_argument("--shift-time", dest="shift_time", default="")
    parser.add_argument("--white-users", dest="white_users", default="")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-publish", action="store_true")
    args = parser.parse_args()

    catalog = _load_scenarios()
    scenario = _scenario_by_key(catalog, args.scenario)
    if scenario.get("read_only"):
        config_key = str(scenario["config_key"])
        namespace = str(scenario["namespace"])
        _run_mse(["--namespace", namespace, "--config-key", config_key])
        _run_mse(
            [
                "--namespace",
                namespace,
                "--config-key",
                config_key,
                "--share-link-only",
            ]
        )
        return 0

    fields = list(scenario.get("fields") or ["fixedTimeSec", "expireTimeSec"])
    required_fields = list(scenario.get("required_fields") or [])
    if not required_fields and "fixedTimeSec" in fields:
        required_fields = ["fixedTimeSec"]
    fixed = _optional_int("fixedTimeSec", args.fixed_time_sec or None)
    expire = _optional_int("expireTimeSec", args.expire_time_sec or None)
    shift = _optional_int("shiftTime", args.shift_time or None)
    white_users = _parse_white_users(args.white_users or None)

    if "fixedTimeSec" in required_fields and fixed is None:
        print("缺少 --fixed-time-sec", file=sys.stderr)
        return 2
    if "expireTimeSec" in required_fields and expire is None:
        if fixed is not None and "expireTimeSec" in fields:
            expire = fixed
        else:
            print("缺少 --expire-time-sec", file=sys.stderr)
            return 2
    elif expire is None and fixed is not None and "expireTimeSec" in fields:
        expire = fixed

    set_pairs: list[str] = []
    if fixed is not None and "fixedTimeSec" in fields:
        set_pairs.append(f"fixedTimeSec={fixed}")
    if expire is not None and "expireTimeSec" in fields:
        set_pairs.append(f"expireTimeSec={expire}")
    if shift is not None:
        set_pairs.append(f"shiftTime={shift}")
    if white_users is not None:
        set_pairs.append(f"whiteUsers={json.dumps(white_users, ensure_ascii=False)}")
    if not set_pairs:
        print("未指定任何可写字段", file=sys.stderr)
        return 2

    config_key = str(scenario["config_key"])
    namespace = str(scenario["namespace"])
    mse_args = ["--namespace", namespace, "--config-key", config_key]
    for pair in set_pairs:
        mse_args.extend(["--set", pair])
    if args.dry_run:
        mse_args.append("--dry-run")
    else:
        mse_args.append("--save")
        if not args.no_publish:
            mse_args.append("--publish")

    print(f"场景：{scenario.get('name')} → {namespace}/{config_key}")
    _run_mse(mse_args)
    if not args.dry_run:
        _run_mse(
            [
                "--namespace",
                namespace,
                "--config-key",
                config_key,
                "--share-link-only",
            ]
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
