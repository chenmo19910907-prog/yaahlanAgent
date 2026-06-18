"""后台工具：MOA 造数、Tunnel 抓包验收。"""

from __future__ import annotations

import json
import subprocess
import sys
from typing import Any

from .paths import repo_root


def _run_script(rel_path: str, args: list[str], *, timeout_s: float = 120.0) -> dict[str, Any]:
    entry = repo_root() / rel_path
    if not entry.is_file():
        raise FileNotFoundError(f"缺少脚本: {entry}")
    proc = subprocess.run(
        [sys.executable, str(entry), *args],
        cwd=str(repo_root()),
        capture_output=True,
        text=True,
        timeout=timeout_s,
        check=False,
    )
    stdout = proc.stdout.strip()
    parsed: Any = stdout
    if stdout.startswith("{"):
        try:
            parsed = json.loads(stdout[stdout.find("{") :])
        except json.JSONDecodeError:
            parsed = stdout
    return {
        "ok": proc.returncode == 0,
        "exitCode": proc.returncode,
        "stdout": parsed,
        "stderr": proc.stderr.strip(),
    }


def tunnel_verify(*, user_id: str, keyword: str = "", since: int = 3600) -> dict[str, Any]:
    args = ["--momoid", user_id, "--since", str(since)]
    if keyword:
        args.extend(["--keyword", keyword])
    rel = "Tunnel/tunnel_execute.py"
    return _run_script(rel, args)


def run_case_fixtures(case: dict[str, Any], *, phase: str) -> list[dict[str, Any]]:
    """执行用例 fixtures.before / fixtures.after。"""
    fixtures = case.get("fixtures") if isinstance(case.get("fixtures"), dict) else {}
    items = fixtures.get(phase) if isinstance(fixtures.get(phase), list) else []
    results: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("type") or "").strip()
        if kind == "tunnel" and item.get("userId"):
            results.append(
                {
                    "type": kind,
                    "result": tunnel_verify(
                        user_id=str(item["userId"]),
                        keyword=str(item.get("keyword") or ""),
                        since=int(item.get("since") or 3600),
                    ),
                }
            )
    return results
