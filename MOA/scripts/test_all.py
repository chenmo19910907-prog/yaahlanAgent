#!/usr/bin/env python3
"""批量自测 templates/ 下所有 JSON 模板及 registry 关键 CLI 变体。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from moa.paths import moa_dir, templates_dir


@dataclass
class TestCase:
    name: str
    args: list[str]
    category: str = ""


def _repo_root() -> str:
    return os.path.dirname(moa_dir())


def build_direct_cases() -> list[TestCase]:
    root = templates_dir()
    files = sorted(
        f for f in os.listdir(root)
        if f.endswith(".json") and os.path.isfile(os.path.join(root, f))
    )
    return [
        TestCase(
            name=fname,
            args=["--payload-file", os.path.join("MOA/templates", fname)],
            category="direct-json",
        )
        for fname in files
    ]


def build_cli_cases() -> list[TestCase]:
    return [
        TestCase(
            name="room_exp_add",
            args=[
                "--payload-file", "MOA/templates/房间经验值-backdoor.json",
                "--service-url", "/service/voga-mts-room-backdoor",
                "--moa-method", "execute",
                "--room-id", "31668628",
                "--exp", "0",
            ],
            category="cli-variant",
        ),
        TestCase(
            name="room_query_current",
            args=[
                "--payload-file", "MOA/templates/房间经验值-backdoor.json",
                "--service-url", "/service/voga-mts-room-backdoor",
                "--moa-method", "execute",
                "--room-id", "31668628",
                "--query-current",
            ],
            category="cli-variant",
        ),
        TestCase(
            name="vip_query_current",
            args=[
                "--payload-file", "MOA/templates/VIP-增加经验值.json",
                "--vip-user-id", "100066819",
                "--vip-query-current",
            ],
            category="cli-variant",
        ),
        TestCase(
            name="family_query_current",
            args=[
                "--payload-file", "MOA/templates/家族-增加声望值.json",
                "--family-id", "101435",
                "--family-query-current",
            ],
            category="cli-variant",
        ),
        TestCase(
            name="family_fund_contrib_query",
            args=[
                "--payload-file", "MOA/templates/家族-增加基金贡献值.json",
                "--family-id", "101435",
                "--family-fund-contrib", "0",
            ],
            category="cli-variant",
        ),
        TestCase(
            name="diamond_query_cli",
            args=[
                "--payload-file", "MOA/templates/钻石-查询余额.json",
                "--diamond-query-user-id", "100465989",
            ],
            category="cli-variant",
        ),
        TestCase(
            name="charm_query_cli",
            args=[
                "--payload-file", "MOA/templates/魅力-查询等级.json",
                "--charm-query-user-id", "100182971",
            ],
            category="cli-variant",
        ),
        TestCase(
            name="wealth_query_cli",
            args=[
                "--payload-file", "MOA/templates/财富-查询等级.json",
                "--wealth-query-user-id", "100182971",
            ],
            category="cli-variant",
        ),
        TestCase(
            name="user_login_query_by_phone",
            args=[
                "--payload-file", "MOA/templates/用户-按手机号查userId.json",
                "--query-user-by-phone", "13311111150",
            ],
            category="cli-variant",
        ),
        TestCase(
            name="user_active_days_query",
            args=[
                "--payload-file", "MOA/templates/查询用户登录天数.json",
                "--expr", "100465989",
            ],
            category="cli-variant",
        ),
    ]


def run_case(repo: str, case: TestCase) -> tuple[bool, str, int | None]:
    cmd = [sys.executable, os.path.join("MOA", "moa_execute.py"), *case.args]
    try:
        proc = subprocess.run(
            cmd,
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return False, "timeout", None

    output = (proc.stdout or "") + (proc.stderr or "")
    ec_outer: int | None = None

    if proc.returncode != 0:
        err_line = proc.stderr.strip().splitlines()[-1] if proc.stderr else f"exit={proc.returncode}"
        return False, err_line, ec_outer

    decoder = json.JSONDecoder()
    idx = 0
    while idx < len(output):
        brace = output.find("{", idx)
        if brace < 0:
            break
        try:
            obj, end = decoder.raw_decode(output, brace)
            if isinstance(obj, dict) and "ec" in obj:
                ec_outer = obj.get("ec")
            idx = end
        except json.JSONDecodeError:
            idx = brace + 1

    if ec_outer is not None and ec_outer != 200:
        return False, f"ec={ec_outer}", ec_outer

    return True, "ok", ec_outer


def main() -> int:
    repo = _repo_root()
    direct = build_direct_cases()
    cli = build_cli_cases()
    all_cases = direct + cli

    ok_count = 0
    fail_items: list[tuple[str, str, str]] = []

    print(f"开始自测，共 {len(all_cases)} 项（JSON 直调 {len(direct)} + CLI 变体 {len(cli)}）\n")

    for case in all_cases:
        ok, msg, ec = run_case(repo, case)
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {case.name} ({case.category}) ec={ec} {msg}")
        if ok:
            ok_count += 1
        else:
            fail_items.append((case.name, case.category, msg))

    print(f"\n结果: {ok_count}/{len(all_cases)} 通过")
    if fail_items:
        print("\n失败清单:")
        for name, cat, msg in fail_items:
            print(f"  - {name} ({cat}): {msg}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
