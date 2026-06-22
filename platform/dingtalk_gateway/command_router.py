"""钉钉网关快捷指令：能脚本化的操作不走 LLM。"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

from help_catalog import build_help_message
from moa_health import probe_moa_cookie
from task_session import TaskSession, run_subprocess_cancellable

GATEWAY_DIR = Path(__file__).resolve().parent
REPO_ROOT = GATEWAY_DIR.parent.parent

EXPORT_FILE_RE = re.compile(
    r"^(?:导出|export)\s+(.+\.(?:csv|json|md))\s*$",
    re.I,
)
ENV_CHECK_RE = re.compile(r"^(?:环境检查|检查环境|doctor)\s*$", re.I)
MOA_CHECK_RE = re.compile(r"^(?:MOA检查|检查MOA|moa检查|moa\s*check)\s*$", re.I)
HELP_RE = re.compile(r"^(?:帮助|使用说明|help|\?|？)\s*$", re.I)
VIP_UPGRADE_RE = re.compile(
    r"^(?:用户\s*)?(\d{5,})\s*(?:升级|升到|升级到)\s*VIP?\s*(\d+)\s*$",
    re.I,
)


@dataclass
class RoutedResult:
    handled: bool
    output: str = ""


def try_route(user_text: str, session: TaskSession | None = None) -> RoutedResult:
    text = (user_text or "").strip()
    if not text:
        return RoutedResult(handled=False)

    if HELP_RE.match(text):
        return RoutedResult(handled=True, output=build_help_message())

    if MOA_CHECK_RE.match(text):
        ok, detail = probe_moa_cookie()
        if ok:
            return RoutedResult(handled=True, output=f"✅ {detail}")
        return RoutedResult(handled=True, output=f"❌ {detail}")

    m = EXPORT_FILE_RE.match(text)
    if m:
        rel = m.group(1).strip()
        path = Path(rel)
        if not path.is_absolute():
            path = (REPO_ROOT / rel).resolve()
        if not path.is_file():
            return RoutedResult(handled=True, output=f"文件不存在：{path}")
        code, stdout, stderr = run_subprocess_cancellable(
            [
                str(GATEWAY_DIR / ".venv/bin/python3"),
                str(GATEWAY_DIR / "export_file.py"),
                str(path),
            ],
            cwd=str(GATEWAY_DIR),
            session=session,
            timeout_s=300,
        )
        out = (stdout or stderr or "").strip()
        return RoutedResult(
            handled=True,
            output=out or f"导出结束 exit={code}",
        )

    if ENV_CHECK_RE.match(text):
        code, stdout, stderr = run_subprocess_cancellable(
            [sys.executable, str(REPO_ROOT / "scripts" / "doctor.py")],
            cwd=str(REPO_ROOT),
            session=session,
            timeout_s=120,
        )
        return RoutedResult(handled=True, output=(stdout or stderr or "").strip())

    m = VIP_UPGRADE_RE.match(text)
    if m:
        user_id, level = m.group(1), m.group(2)
        code, stdout, stderr = run_subprocess_cancellable(
            [
                sys.executable,
                str(REPO_ROOT / "MOA" / "moa_execute.py"),
                "--payload-file",
                str(REPO_ROOT / "MOA" / "templates" / "VIP-增加经验值.json"),
                "--vip-user-id",
                user_id,
                "--vip-level",
                level,
            ],
            cwd=str(REPO_ROOT),
            session=session,
            timeout_s=120,
        )
        out = (stdout or stderr or "").strip()
        return RoutedResult(
            handled=True,
            output=out or f"exit={code}",
        )

    return RoutedResult(handled=False)
