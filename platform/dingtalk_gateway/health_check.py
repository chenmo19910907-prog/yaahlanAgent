#!/usr/bin/env python3
"""网关健康检查：launchd / Bridge / MOA / 凭证。"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

GATEWAY_DIR = Path(__file__).resolve().parent
REPO_ROOT = GATEWAY_DIR.parent.parent

from env_loader import ENV_LOCAL, load_env_local, require_env

_SCRIPTS = REPO_ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from credential_probe import print_credential_probes  # noqa: E402
ERR_LOG = GATEWAY_DIR / "logs" / "gateway.err.log"
ERR_LOG_MAX_AGE_H = 24

_LOG_TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
_ERROR_MARKERS = (
    "Traceback",
    "RuntimeError",
    "Connection refused",
    "InternalServerError",
    " ERROR ",
)


def _check(name: str, ok: bool, detail: str) -> bool:
    mark = "OK" if ok else "FAIL"
    print(f"  [{mark}] {name}: {detail}")
    return ok


def _probe_sdk_bridge() -> tuple[bool, str]:
    try:
        from bridge_manager import init_sdk_bridge
        from cursor_runner import repo_cwd

        init_sdk_bridge(repo_cwd())
        return True, "Bridge 初始化成功"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def _parse_log_ts(line: str) -> datetime | None:
    match = _LOG_TS_RE.match(line)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def _recent_error_hint(log_path: Path, *, max_lines: int = 200, max_age_h: int = ERR_LOG_MAX_AGE_H) -> str | None:
    if not log_path.is_file():
        return None
    try:
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    cutoff = datetime.now() - timedelta(hours=max_age_h)
    for line in reversed(lines[-max_lines:]):
        if not any(marker in line for marker in _ERROR_MARKERS):
            continue
        ts = _parse_log_ts(line)
        if ts is not None and ts < cutoff:
            continue
        age_note = f"（{ts.strftime('%m-%d %H:%M')}）" if ts else ""
        return f"{line.strip()[:140]}{age_note}"
    return None


def _probe_sdk_deep() -> tuple[bool, str]:
    try:
        from cursor_runner import run_agent_prompt

        reply = run_agent_prompt(
            "只回复：gateway-ready，不要其它内容。",
            use_gateway_rules=False,
            enable_mcp=False,
        )
        return True, f"SDK pong 成功: {reply[:80]}"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def main() -> int:
    parser = argparse.ArgumentParser(description="钉钉网关健康检查")
    parser.add_argument(
        "--deep",
        action="store_true",
        help="server 未运行时执行 SDK Agent pong（较慢）",
    )
    args = parser.parse_args()

    load_env_local()
    ok_all = True
    print("=== 钉钉网关健康检查 ===")

    proc = subprocess.run(["pgrep", "-f", "dingtalk_gateway/server.py"], capture_output=True)
    server_running = proc.returncode == 0
    if not server_running:
        for _ in range(6):
            time.sleep(0.5)
            proc = subprocess.run(["pgrep", "-f", "dingtalk_gateway/server.py"], capture_output=True)
            if proc.returncode == 0:
                server_running = True
                break
    ok_all &= _check("server.py 进程", server_running, "运行中" if server_running else "未运行")

    try:
        require_env("CURSOR_API_KEY")
        ok_all &= _check("CURSOR_API_KEY", True, "已配置")
    except RuntimeError as exc:
        ok_all &= _check("CURSOR_API_KEY", False, str(exc))

    for name in ("DINGTALK_CLIENT_ID", "DINGTALK_CLIENT_SECRET"):
        try:
            require_env(name)
            ok_all &= _check(name, True, "已配置")
        except RuntimeError as exc:
            ok_all &= _check(name, False, str(exc))

    if server_running:
        ok_all &= _check("Cursor Bridge", True, "由 gateway 进程托管")
        recent = _recent_error_hint(ERR_LOG)
        if recent:
            ok_all &= _check("gateway.err.log", False, f"近期异常: {recent}")
        else:
            ok_all &= _check("gateway.err.log", True, "近期无异常栈")
        if args.deep:
            ok_all &= _check("SDK Agent pong (--deep)", True, "server 运行中，跳过独立 pong")
    else:
        bridge_ok, bridge_detail = _probe_sdk_bridge()
        ok_all &= _check("Cursor Bridge", bridge_ok, bridge_detail)
        if args.deep:
            deep_ok, deep_detail = _probe_sdk_deep()
            ok_all &= _check("SDK Agent pong (--deep)", deep_ok, deep_detail)

    moa_env = REPO_ROOT / "MOA" / ".env.local"
    ok_all &= _check("MOA/.env.local", moa_env.is_file(), "存在" if moa_env.is_file() else "缺失")

    ok_all &= _check(".env.local", ENV_LOCAL.is_file(), str(ENV_LOCAL))

    print()
    ok_all &= print_credential_probes()

    print()
    if ok_all:
        print("[PASS] 网关环境健康")
        return 0
    print("[WARN] 存在异常项，请按提示修复后 ./gateway_ctl.sh restart")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
