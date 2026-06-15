"""自动化测试报告（JSON + HTML，固定单文件覆盖写入）。"""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any

from .paths import REPORT_HTML_PATH, REPORT_JSON_PATH, REPORT_META_PATH, ensure_reports_dir

_TIMESTAMP_DIR = re.compile(r"^\d{8}-\d{6}$")


def _prune_legacy_timestamp_reports(reports_dir: Path) -> None:
    """移除历史按时间戳分子目录的报告（现改为单文件覆盖）。"""
    if not reports_dir.is_dir():
        return
    for child in reports_dir.iterdir():
        if child.is_dir() and _TIMESTAMP_DIR.match(child.name):
            shutil.rmtree(child, ignore_errors=True)


def _screenshot_links(case: dict[str, Any]) -> list[str]:
    links: list[str] = []
    for op in case.get("operations") or []:
        if not isinstance(op, dict):
            continue
        detail = op.get("detail")
        if not isinstance(detail, dict):
            continue
        shot = detail.get("screenshot")
        if isinstance(shot, dict) and shot.get("path"):
            links.append(str(shot["path"]))
    for vp in case.get("verifyPoints") or []:
        if not isinstance(vp, dict):
            continue
        detail = vp.get("detail")
        if isinstance(detail, dict) and detail.get("path"):
            links.append(str(detail["path"]))
    return links


def _render_case_html(case: dict[str, Any]) -> str:
    status = str(case.get("status") or "FAIL")
    badge_class = "pass" if status == "PASS" else "fail"
    account = case.get("account") if isinstance(case.get("account"), dict) else {}
    rows = []
    for op in case.get("operationFlow") or []:
        if not isinstance(op, dict):
            continue
        ok = "✓" if op.get("ok") else "✗"
        script = op.get("script") or ""
        rows.append(
            "<tr>"
            f"<td>{escape(str(op.get('step', '')))}</td>"
            f"<td>{escape(str(op.get('description', '')))}</td>"
            f"<td>{escape(str(op.get('action', '')))}</td>"
            f"<td>{escape(str(script))}</td>"
            f"<td>{ok}</td>"
            f"<td>{escape(str(op.get('message', '')))}</td>"
            "</tr>"
        )
    verify_rows = []
    for vp in case.get("verifyPoints") or []:
        if not isinstance(vp, dict):
            continue
        ok = "✓" if vp.get("ok") else "✗"
        verify_rows.append(
            "<tr>"
            f"<td>{escape(str(vp.get('id', '')))}</td>"
            f"<td>{escape(str(vp.get('name', '')))}</td>"
            f"<td>{escape(str(vp.get('method', '')))}</td>"
            f"<td>{ok}</td>"
            f"<td>{escape(str(vp.get('message', '')))}</td>"
            "</tr>"
        )
    shots = _screenshot_links(case)
    shot_html = "".join(
        f'<div><a href="file://{escape(p)}">{escape(Path(p).name)}</a></div>' for p in shots
    )
    return f"""
    <section class="case">
      <h3><span class="badge {badge_class}">{escape(status)}</span> {escape(str(case.get('caseId', '')))} — {escape(str(case.get('name', '')))}</h3>
      <p><b>模块</b>：{escape(str(case.get('module', '')))} · <b>优先级</b>：{escape(str(case.get('priority', 'P0')))}</p>
      <p><b>账号</b>：{escape(str(account.get('alias', '')))}（{escape(str(account.get('userId', '')))} / {escape(str(account.get('phone', '')))}）</p>
      <h4>操作流程</h4>
      <table>
        <thead><tr><th>步骤</th><th>说明</th><th>动作</th><th>脚本</th><th>结果</th><th>备注</th></tr></thead>
        <tbody>{''.join(rows) or '<tr><td colspan="6">无</td></tr>'}</tbody>
      </table>
      <h4>验收点</h4>
      <table>
        <thead><tr><th>ID</th><th>名称</th><th>方式</th><th>结果</th><th>详情</th></tr></thead>
        <tbody>{''.join(verify_rows) or '<tr><td colspan="5">无</td></tr>'}</tbody>
      </table>
      <h4>截图</h4>
      <div class="shots">{shot_html or '<span>无</span>'}</div>
    </section>
    """


def write_report(
    *,
    run_result: dict[str, Any],
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    reports_dir = ensure_reports_dir()
    _prune_legacy_timestamp_reports(reports_dir)

    payload: dict[str, Any] = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "meta": meta or {},
        "summary": {
            "status": run_result.get("status"),
            "passed": run_result.get("passed"),
            "caseCount": run_result.get("caseCount", 1),
            "passedCount": run_result.get("passedCount", 1 if run_result.get("passed") else 0),
            "failedCount": run_result.get("failedCount", 0 if run_result.get("passed") else 1),
        },
        "result": run_result,
    }

    REPORT_JSON_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    cases = run_result.get("cases")
    if not isinstance(cases, list):
        cases = [run_result]

    case_sections = "".join(_render_case_html(c) for c in cases if isinstance(c, dict))
    status = str(run_result.get("status") or "FAIL")
    badge_class = "pass" if status == "PASS" else "fail"
    suite_name = escape(str(run_result.get("suiteName") or ""))
    suite_line = (
        f"<p><b>套件</b>：{suite_name}（{escape(str(run_result.get('suiteId') or ''))}）</p>"
        if run_result.get("suiteId") or run_result.get("suiteName")
        else ""
    )
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>自动化测试报告</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 24px; color: #222; }}
    h1, h2, h3, h4 {{ margin: 0.6em 0 0.4em; }}
    .badge {{ display: inline-block; padding: 2px 8px; border-radius: 4px; color: #fff; font-size: 12px; }}
    .badge.pass {{ background: #1a7f37; }}
    .badge.fail {{ background: #cf222e; }}
    table {{ border-collapse: collapse; width: 100%; margin: 8px 0 16px; font-size: 14px; }}
    th, td {{ border: 1px solid #d0d7de; padding: 6px 8px; text-align: left; vertical-align: top; }}
    th {{ background: #f6f8fa; }}
    .case {{ border: 1px solid #d0d7de; border-radius: 8px; padding: 16px; margin: 16px 0; }}
    .meta {{ color: #57606a; font-size: 14px; }}
    .shots a {{ display: inline-block; margin-right: 12px; }}
  </style>
</head>
<body>
  <h1>自动化测试报告</h1>
  <p class="meta">生成时间：{escape(payload["generatedAt"])}</p>
  {suite_line}
  <p><span class="badge {badge_class}">{escape(status)}</span>
     通过 {escape(str(payload["summary"]["passedCount"]))} / {escape(str(payload["summary"]["caseCount"]))}</p>
  {case_sections}
</body>
</html>
"""
    REPORT_HTML_PATH.write_text(html, encoding="utf-8")

    meta_payload = {
        "reportDir": str(reports_dir.resolve()),
        "json": str(REPORT_JSON_PATH.resolve()),
        "html": str(REPORT_HTML_PATH.resolve()),
        "status": status,
        "summary": payload["summary"],
        "generatedAt": payload["generatedAt"],
    }
    REPORT_META_PATH.write_text(
        json.dumps(meta_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return {
        "reportDir": str(reports_dir.resolve()),
        "json": str(REPORT_JSON_PATH.resolve()),
        "html": str(REPORT_HTML_PATH.resolve()),
        "summary": payload["summary"],
        "status": status,
    }
