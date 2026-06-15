#!/usr/bin/env python3
"""检查本机用例生成与 MOA/Admin/Risk 环境是否就绪。"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        out[key.strip()] = val.strip().strip('"').strip("'")
    return out


def _check(name: str, ok: bool, detail: str) -> bool:
    mark = "OK" if ok else "FAIL"
    print(f"  [{mark}] {name}: {detail}")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description="环境自检（MOA / MCP / 用例目录）")
    parser.add_argument(
        "--run-moa-probe",
        action="store_true",
        help="尝试执行 MOA VIP 查询探活（需有效 Cookie）",
    )
    parser.add_argument(
        "--check-testcases",
        action="store_true",
        help="对 temporary_testcase/*.md 运行 check_testcase_md.py",
    )
    args = parser.parse_args()

    ok_all = True
    print("=== 基础环境 ===")
    py = sys.version_info
    ok_all &= _check(
        "Python",
        py >= (3, 8),
        f"{py.major}.{py.minor}.{py.micro}",
    )

    print("\n=== 本地配置 ===")
    moa_env = ROOT / "MOA" / ".env.local"
    moa_vars = _load_env_file(moa_env)
    ok_all &= _check(
        "MOA/.env.local",
        moa_env.is_file(),
        "存在" if moa_env.is_file() else "缺失，请 cp MOA/.env.example MOA/.env.local",
    )
    ok_all &= _check(
        "MOA_COOKIE",
        bool(moa_vars.get("MOA_COOKIE")),
        "已配置" if moa_vars.get("MOA_COOKIE") else "未填写",
    )

    admin_env = ROOT / "Admin" / ".env.local"
    admin_vars = _load_env_file(admin_env)
    _check(
        "Admin/.env.local",
        admin_env.is_file(),
        "存在" if admin_env.is_file() else "可选，推荐配置",
    )
    if admin_env.is_file():
        _check(
            "ADMIN_YAAHLAN_JWT",
            bool(admin_vars.get("ADMIN_YAAHLAN_JWT")),
            "已配置" if admin_vars.get("ADMIN_YAAHLAN_JWT") else "未填写",
        )

    risk_env = ROOT / "Risk" / ".env.local"
    print(
        f"  [{'OK' if risk_env.is_file() else 'SKIP'}] Risk/.env.local: "
        f"{'存在' if risk_env.is_file() else '非必须，默认 Risk/config.json'}"
    )

    print("\n=== Cursor MCP ===")
    from mcp_paths import MCP_EXAMPLE, MCP_LOCAL, MCP_SECRETS

    ok_all &= _check("mcp.example.json", MCP_EXAMPLE.is_file(), "存在" if MCP_EXAMPLE.is_file() else "缺失模板")
    if MCP_LOCAL.is_file():
        try:
            data = json.loads(MCP_LOCAL.read_text(encoding="utf-8"))
            servers = data.get("mcpServers") or data.get("servers") or {}
            for name in ("dingtalk-doc", "dingtalk-excel-read", "dingtalk-excel-write"):
                present = name in servers or any(name in k for k in servers)
                _check(f"MCP:{name}", present, "已登记" if present else "未找到")
        except json.JSONDecodeError as exc:
            ok_all &= _check("mcp.json", False, f"JSON 解析失败: {exc}")
    else:
        ok_all &= _check("mcp.json", False, f"缺失 {MCP_LOCAL}（可运行 python3 DingTalk/.cookie_sync_execute.py --merge-mcp）")
    _check(
        ".mcp.secrets.json",
        MCP_SECRETS.is_file(),
        "已配置" if MCP_SECRETS.is_file() else "未填写（Cookie/Token 本地文件）",
    )

    print("\n=== 用例工作区 ===")
    tmp = ROOT / "temporary_testcase"
    md_count = len(list(tmp.glob("*.md"))) if tmp.is_dir() else 0
    _check("temporary_testcase", tmp.is_dir(), f"{md_count} 个 .md")

    for sub, label in (
        ("testcase-kb", "testcase-kb"),
        ("bug-kb", "bug-kb"),
    ):
        p = ROOT / sub
        _check(label, p.is_dir(), "存在" if p.is_dir() else "缺失")

    if args.run_moa_probe and moa_vars.get("MOA_COOKIE"):
        print("\n=== MOA 探活 ===")
        cmd = [
            sys.executable,
            str(ROOT / "MOA" / "moa_execute.py"),
            "--payload-file",
            str(ROOT / "MOA" / "templates" / "VIP-增加经验值.json"),
            "--vip-user-id",
            "100465989",
            "--vip-query-current",
        ]
        env = {**os.environ, **moa_vars}
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(ROOT),
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
            )
            ok = proc.returncode == 0 and "vipLevel" in (proc.stdout or "")
            ok_all &= _check("MOA 查询", ok, "成功" if ok else (proc.stderr or proc.stdout)[:200])
        except subprocess.TimeoutExpired:
            ok_all &= _check("MOA 查询", False, "超时")
        except OSError as exc:
            ok_all &= _check("MOA 查询", False, str(exc))

    if args.check_testcases and md_count:
        print("\n=== 用例格式校验 ===")
        check_script = ROOT / "scripts" / "check_testcase_md.py"
        proc = subprocess.run(
            [sys.executable, str(check_script), "--dir", str(tmp)],
            cwd=str(ROOT),
        )
        if proc.returncode != 0:
            ok_all = False

    print()
    if ok_all:
        print("自检通过（可选项未计入 FAIL）")
        return 0
    print("存在 FAIL 项，请按 新手上手.md 处理")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
