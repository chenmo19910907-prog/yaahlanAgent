"""钉钉网关快捷指令：能脚本化的操作不走 LLM。"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from help_catalog import build_help_message
from moa_health import probe_moa_cookie
from moa_registry_guard import should_route_moa_check
from route_patterns import (
    CATALOG_OPEN_RE,
    EXPORT_FILE_RE,
    HELP_RE,
    REPORT_NL_RE,
    REPORT_URL_RE,
    REPORT_VERSION_RE,
    VIP_UPGRADE_RE,
    normalize_report_prompt,
)
from task_session import TaskSession, run_subprocess_cancellable

GATEWAY_DIR = Path(__file__).resolve().parent
REPO_ROOT = GATEWAY_DIR.parent.parent


@dataclass
class RoutedResult:
    handled: bool
    output: str = ""
    files: list[Path] = field(default_factory=list)
    task_kind: str = ""


def try_route(user_text: str, session: TaskSession | None = None) -> RoutedResult:
    text = (user_text or "").strip()
    if not text:
        return RoutedResult(handled=False)

    normalized = normalize_report_prompt(text)
    if normalized:
        text = normalized

    if HELP_RE.match(text):
        return RoutedResult(handled=True, output=build_help_message(), task_kind="help")

    if CATALOG_OPEN_RE.match(text):
        code, stdout, stderr = run_subprocess_cancellable(
            [
                str(GATEWAY_DIR / ".venv/bin/python3"),
                str(GATEWAY_DIR / "catalog_export.py"),
                "--json",
            ],
            cwd=str(GATEWAY_DIR),
            session=session,
            timeout_s=120,
        )
        raw = (stdout or stderr or "").strip()
        if code != 0 or not raw:
            return RoutedResult(
                handled=True,
                output=raw or f"工具平台导出失败 exit={code}",
            )
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return RoutedResult(handled=True, output=raw)
        if not data.get("ok"):
            return RoutedResult(
                handled=True,
                output=f"[FAIL] {data.get('error') or '工具平台导出失败'}",
            )
        zip_name = str(data.get("zip_name") or "Yaahlan智能工具平台.zip")
        html_name = str(data.get("html_name") or "Yaahlan智能工具平台.html")
        summary = str(data.get("summary") or "").strip()
        modules = data.get("module_count")
        items = data.get("total_items")
        lines = [
            "[OK] 工具平台离线版已生成。",
            f"附件 {zip_name} 内含复制按钮版 HTML（{html_name}），请下载解压后用浏览器打开。",
            f"共 {modules} 个一级模块、{items} 项能力。",
        ]
        if summary:
            lines.extend(["", summary])
        zip_path = Path(str(data.get("zip") or ""))
        files = [zip_path] if zip_path.is_file() else []
        return RoutedResult(handled=True, output="\n".join(lines), files=files, task_kind="catalog")

    if should_route_moa_check(text):
        ok, detail = probe_moa_cookie()
        if ok:
            return RoutedResult(handled=True, output=f"✅ {detail}", task_kind="moa_check")
        return RoutedResult(handled=True, output=f"❌ {detail}", task_kind="moa_check")

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
            task_kind="export_file",
        )

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
            task_kind="vip_upgrade",
        )

    report_version = REPORT_VERSION_RE.match(text) or REPORT_NL_RE.match(text)
    report_url = REPORT_URL_RE.match(text)
    if report_version or report_url:
        cmd = [
            str(GATEWAY_DIR / ".venv/bin/python3"),
            str(GATEWAY_DIR / "report_generate.py"),
            "--json",
        ]
        if report_version:
            cmd.extend(["--version", report_version.group(1)])
        else:
            cmd.extend(["--url", report_url.group(1)])  # type: ignore[union-attr]
        code, stdout, stderr = run_subprocess_cancellable(
            cmd,
            cwd=str(GATEWAY_DIR),
            session=session,
            timeout_s=600,
        )
        raw = (stdout or stderr or "").strip()
        if code != 0 or not raw:
            return RoutedResult(
                handled=True,
                output=raw or f"测试报告生成失败 exit={code}",
            )
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return RoutedResult(handled=True, output=raw)
        if not data.get("ok"):
            return RoutedResult(
                handled=True,
                output=f"[FAIL] {data.get('error') or '测试报告生成失败'}",
            )
        version = str(data.get("version") or "")
        zip_name = str(data.get("zip_name") or "测试报告.zip")
        summary = str(data.get("summary") or "").strip()
        lines = [
            f"[OK] {version} 版本测试报告已生成。",
            f"附件：{zip_name}（含内网/外网 HTML，请下载解压后用浏览器打开）",
        ]
        if summary:
            lines.extend(["", summary])
        zip_path = Path(str(data.get("zip") or ""))
        files = [zip_path] if zip_path.is_file() else []
        return RoutedResult(handled=True, output="\n".join(lines), files=files, task_kind="report")

    return RoutedResult(handled=False)
