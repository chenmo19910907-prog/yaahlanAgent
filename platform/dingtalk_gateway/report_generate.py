#!/usr/bin/env python3
"""钉钉网关专用：从版本用例表生成 HTML 测试报告，供机器人发送到钉钉群。

本地 `Report/dingtalk_report_execute.py` 仍只生成本地 HTML，不走本脚本。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import uuid
import zipfile
from pathlib import Path

GATEWAY_DIR = Path(__file__).resolve().parent
REPO_ROOT = GATEWAY_DIR.parent.parent
REPORT_ROOT = REPO_ROOT / "Report"
REPORT_VENV_PY = REPORT_ROOT / ".venv" / "bin" / "python"
LOOKUP_PY = REPO_ROOT / "DingTalk" / "lookup_execute.py"
REPORT_EXPORT_DIR = GATEWAY_DIR / "exports" / "reports"

_VERSION_IN_NAME_RE = re.compile(r"(\d+\.\d+\.\d+)")


def _apply_dingtalk_excel_env() -> None:
    keys = ("DINGTALK_AEGIS_KEY", "DINGTALK_AEGIS_SECRET", "DINGTALK_WORKID")
    if all(os.environ.get(k) for k in keys):
        return
    scripts_dir = REPO_ROOT / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    try:
        from mcp_paths import load_mcp_env

        env = load_mcp_env("dingtalk-excel-read")
        for k in keys:
            if not os.environ.get(k) and env.get(k):
                os.environ[k] = str(env[k])
    except ImportError:
        return


def _report_python() -> str:
    return str(REPORT_VENV_PY) if REPORT_VENV_PY.is_file() else sys.executable


def _lookup_workbook_url(keyword: str) -> tuple[str, str]:
    proc = subprocess.run(
        [sys.executable, str(LOOKUP_PY), "--json", keyword],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(err or f"目录查找失败 exit={proc.returncode}")

    payload = json.loads(proc.stdout)
    if not isinstance(payload, list) or not payload:
        raise RuntimeError(f"未找到「{keyword}」对应的版本用例表")

    preferred = [
        item
        for item in payload
        if isinstance(item, dict)
        and "版本用例" in str(item.get("name") or "")
    ]
    item = preferred[0] if preferred else payload[0]
    name = str(item.get("name") or keyword)
    url = str(item.get("url") or "").strip()
    if not url:
        raise RuntimeError(f"目录项缺少 URL：{name}")
    return name, url


def _guess_version_label(
    *,
    version: str | None,
    workbook_name: str,
    xlsx_stem: str,
    xlsx_path: Path | None = None,
) -> str:
    if version:
        return version
    for text in (workbook_name, xlsx_stem):
        match = _VERSION_IN_NAME_RE.search(text)
        if match:
            return match.group(1)
    if xlsx_path is not None:
        if str(REPORT_ROOT) not in sys.path:
            sys.path.insert(0, str(REPORT_ROOT))
        from report.generator import guess_version_from_xlsx  # noqa: WPS433

        from_xlsx = guess_version_from_xlsx(xlsx_path)
        if from_xlsx:
            return from_xlsx
    return xlsx_stem


def _download_workbook(url: str, dest: Path) -> None:
    dingtalk_script = REPORT_ROOT / "dingtalk_report_execute.py"
    proc = subprocess.run(
        [_report_python(), str(dingtalk_script), "--xlsx-only", "-o", str(dest), url],
        cwd=str(REPORT_ROOT),
        env={**os.environ},
        capture_output=True,
        text=True,
        timeout=300,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(err or f"拉取钉钉用例表失败 exit={proc.returncode}")
    if not dest.is_file():
        raise RuntimeError(f"未生成 xlsx：{dest}")


def _generate_html_reports(
    xlsx_path: Path,
    *,
    version_case_url: str,
    version_s2: str | None = None,
) -> tuple[Path, Path, str]:
    if str(REPORT_ROOT) not in sys.path:
        sys.path.insert(0, str(REPORT_ROOT))
    from report.generator import (  # noqa: WPS433
        DEFAULT_DEFECT_TB_URL,
        DEFAULT_REGRESSION_CASE_URL,
    )

    env = {
        **os.environ,
        "COUNT_NO_BROWSER": "1",
        "REPORT_DEFECT_TB_URL": DEFAULT_DEFECT_TB_URL,
        "REPORT_REGRESSION_CASE_URL": DEFAULT_REGRESSION_CASE_URL,
        "REPORT_VERSION_CASE_URL": version_case_url,
    }
    if version_s2:
        env["REPORT_VERSION_S2"] = version_s2
    proc = subprocess.run(
        [_report_python(), str(REPORT_ROOT / "report_execute.py"), str(xlsx_path)],
        cwd=str(REPORT_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    if proc.returncode != 0:
        err = stderr or stdout
        raise RuntimeError(err or f"生成 HTML 报告失败 exit={proc.returncode}")

    internal_html = xlsx_path.with_name(f"{xlsx_path.stem}_内网测试总结.html")
    external_html = xlsx_path.with_name(f"{xlsx_path.stem}_外网测试总结.html")
    if not internal_html.is_file() or not external_html.is_file():
        raise RuntimeError("HTML 报告未生成完整（缺少内网或外网文件）")
    return internal_html, external_html, stdout


def _zip_reports(
    *,
    version_label: str,
    internal_html: Path,
    external_html: Path,
    work_dir: Path,
) -> Path:
    zip_name = f"{version_label}版本测试报告.zip"
    zip_path = work_dir / zip_name
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(
            internal_html,
            arcname=f"{version_label}版本_内网测试总结.html",
        )
        zf.write(
            external_html,
            arcname=f"{version_label}版本_外网测试总结.html",
        )
    return zip_path


def generate_reports(
    *,
    version: str | None = None,
    workbook_url: str | None = None,
) -> dict[str, str | Path]:
    _apply_dingtalk_excel_env()

    workbook_name = ""
    if workbook_url:
        url = workbook_url.strip()
    elif version:
        workbook_name, url = _lookup_workbook_url(version)
    else:
        raise ValueError("需要 version 或 workbook_url")

    work_dir = REPORT_EXPORT_DIR / uuid.uuid4().hex[:12]
    work_dir.mkdir(parents=True, exist_ok=True)

    xlsx_path = work_dir / "version_cases.xlsx"
    _download_workbook(url, xlsx_path)

    version_label = _guess_version_label(
        version=version,
        workbook_name=workbook_name,
        xlsx_stem=xlsx_path.stem,
        xlsx_path=xlsx_path,
    )
    if str(REPORT_ROOT) not in sys.path:
        sys.path.insert(0, str(REPORT_ROOT))
    from report.generator import version_s2_from_semver  # noqa: WPS433

    version_s2 = version_s2_from_semver(version_label)
    internal_html, external_html, summary = _generate_html_reports(
        xlsx_path,
        version_case_url=url,
        version_s2=version_s2,
    )
    zip_path = _zip_reports(
        version_label=version_label,
        internal_html=internal_html,
        external_html=external_html,
        work_dir=work_dir,
    )

    return {
        "ok": True,
        "version": version_label,
        "workbook_url": url,
        "zip": zip_path,
        "zip_name": zip_path.name,
        "internal_html": internal_html,
        "external_html": external_html,
        "summary": summary,
    }


def _format_success(result: dict[str, str | Path]) -> str:
    version = str(result.get("version") or "")
    zip_name = str(result.get("zip_name") or "")
    lines = [
        f"[OK] {version} 版本测试报告已生成。",
        f"附件：{zip_name}（含内网/外网 HTML，请下载解压后用浏览器打开）",
    ]
    summary = str(result.get("summary") or "").strip()
    if summary:
        lines.append("")
        lines.append(summary)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="钉钉网关：生成测试报告 HTML 并打包 zip")
    parser.add_argument("--version", help="版本号，如 2.4.5")
    parser.add_argument("--url", help="钉钉版本用例表 URL")
    parser.add_argument("--json", action="store_true", help="输出 JSON（供网关解析附件路径）")
    args = parser.parse_args(argv)

    if not args.version and not args.url:
        parser.error("需要 --version 或 --url")

    try:
        result = generate_reports(version=args.version, workbook_url=args.url)
    except Exception as exc:  # noqa: BLE001
        payload = {"ok": False, "error": str(exc)}
        if args.json:
            print(json.dumps(payload, ensure_ascii=False))
        else:
            print(f"[FAIL] {exc}", file=sys.stderr)
        return 1

    if args.json:
        serializable = {
            "ok": True,
            "version": result["version"],
            "workbook_url": result["workbook_url"],
            "zip": str(result["zip"]),
            "zip_name": result["zip_name"],
            "summary": result["summary"],
        }
        print(json.dumps(serializable, ensure_ascii=False))
        return 0

    print(_format_success(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
