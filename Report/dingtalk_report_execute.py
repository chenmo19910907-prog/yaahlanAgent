#!/usr/bin/env python3
"""从钉钉 Excel URL 拉取版本用例表并生成内网/外网测试总结 HTML 报告。"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

_REPORT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_REPORT_ROOT))

from report.dingtalk_xlsx import (  # noqa: E402
    DingtalkExcelFetchError,
    dingtalk_url_to_xlsx,
    guess_output_stem,
    fetch_workbook_sheets,
    write_workbook_xlsx,
)
from report.generator import (  # noqa: E402
    DEFAULT_DEFECT_TB_URL,
    DEFAULT_REGRESSION_CASE_URL,
    _open_html_default_browser,
)

_DEFAULT_DELETE_DELAY_SEC = 5


def _venv_python() -> str:
    candidate = _REPORT_ROOT / ".venv" / "bin" / "python"
    return str(candidate) if candidate.is_file() else sys.executable


def _apply_dingtalk_env_from_cursor_mcp() -> None:
    """未显式设置时，从 .mcp.secrets.json / mcp.json 读取 dingtalk-excel-read 鉴权。"""
    keys = ("DINGTALK_AEGIS_KEY", "DINGTALK_AEGIS_SECRET", "DINGTALK_WORKID")
    if all(os.environ.get(k) for k in keys):
        return
    scripts_dir = _REPORT_ROOT.parent / "scripts"
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="从钉钉 Excel URL 生成测试报告")
    parser.add_argument("url", help="钉钉 Excel 完整 URL")
    parser.add_argument(
        "-o",
        "--output",
        help="输出 xlsx 路径（默认：桌面/{版本}版本用例_钉钉.xlsx）",
    )
    parser.add_argument(
        "--xlsx-only",
        action="store_true",
        help="仅下载为 xlsx，不生成 HTML 报告",
    )
    args = parser.parse_args(argv)
    _apply_dingtalk_env_from_cursor_mcp()

    try:
        if args.output:
            xlsx_path = Path(args.output).expanduser().resolve()
            dingtalk_url_to_xlsx(args.url, xlsx_path)
        else:
            import asyncio

            sheets = asyncio.run(fetch_workbook_sheets(args.url))
            stem = guess_output_stem(sheets)
            xlsx_path = Path.home() / "Desktop" / f"{stem}_钉钉.xlsx"
            write_workbook_xlsx(sheets, xlsx_path)
    except DingtalkExcelFetchError as e:
        print(f"拉取钉钉表格失败：{e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"处理失败：{e}", file=sys.stderr)
        return 2

    print(f"已保存 xlsx：{xlsx_path}", file=sys.stderr)
    if args.xlsx_only:
        return 0

    internal_html = xlsx_path.with_name(f"{xlsx_path.stem}_内网测试总结.html")
    external_html = xlsx_path.with_name(f"{xlsx_path.stem}_外网测试总结.html")

    env = {
        **os.environ,
        "COUNT_NO_BROWSER": "1",
        "REPORT_DEFECT_TB_URL": DEFAULT_DEFECT_TB_URL,
        "REPORT_REGRESSION_CASE_URL": DEFAULT_REGRESSION_CASE_URL,
        "REPORT_VERSION_CASE_URL": args.url.strip(),
    }
    proc = subprocess.run(
        [_venv_python(), str(_REPORT_ROOT / "report_execute.py"), str(xlsx_path)],
        env=env,
    )
    if proc.returncode != 0:
        return proc.returncode

    if not internal_html.is_file() or not external_html.is_file():
        print("报告 HTML 未生成，跳过打开与删除。", file=sys.stderr)
        return 2

    opened_ext = _open_html_default_browser(external_html)
    opened_in = _open_html_default_browser(internal_html)
    try:
        delay_sec = int(os.environ.get("REPORT_DELETE_DELAY_SEC", _DEFAULT_DELETE_DELAY_SEC))
    except ValueError:
        delay_sec = _DEFAULT_DELETE_DELAY_SEC
    if delay_sec < 0:
        delay_sec = _DEFAULT_DELETE_DELAY_SEC

    if opened_ext and opened_in:
        print("已用默认浏览器打开外网、内网报告（先外网后内网）。", file=sys.stderr)
    elif opened_ext or opened_in:
        print("已打开部分报告；未打开的文件请从浏览器历史或重新生成查看。", file=sys.stderr)
    else:
        print("未能自动打开浏览器，请手动打开上述 HTML。", file=sys.stderr)

    print(f"等待 {delay_sec} 秒后删除本地文件…", file=sys.stderr)
    time.sleep(delay_sec)

    for path in (xlsx_path, internal_html, external_html):
        try:
            if path.is_file():
                path.unlink()
                print(f"已删除：{path}", file=sys.stderr)
        except OSError as e:
            print(f"删除失败 {path}：{e}", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
