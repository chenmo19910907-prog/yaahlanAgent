"""大R API 验收报告：Markdown / HTML 可视化（含 case 详情 + 后端返回）。"""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from typing import Any


def _esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def _json_str(data: Any, *, compact: bool = False) -> str:
    if data is None:
        return "—"
    if isinstance(data, str):
        return data
    if compact:
        return json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return json.dumps(data, ensure_ascii=False, indent=2)


def _truncate_json(data: Any, max_lines: int = 30) -> str:
    text = _json_str(data)
    lines = text.split("\n")
    if len(lines) <= max_lines:
        return text
    return "\n".join(lines[:max_lines]) + f"\n... ({len(lines) - max_lines} more lines)"


def format_smoke_markdown(report: dict[str, Any], *, title: str = "大R后台 API 冒烟验收") -> str:
    passed = int(report.get("passed") or 0)
    failed = int(report.get("failed") or 0)
    total = passed + failed
    ok = bool(report.get("ok"))
    lines = [
        f"# {title}",
        "",
        f"- **结果**：{'✅ 通过' if ok else '❌ 失败'}（{passed}/{total}）",
        f"- **环境**：{report.get('baseUrl') or '—'}",
        f"- **前端**：{report.get('frontendUrl') or '—'}",
        "",
        "---",
        "",
    ]
    for idx, item in enumerate(report.get("checks") or [], 1):
        if not isinstance(item, dict):
            continue
        name = item.get("name") or "—"
        status = "✅ PASS" if item.get("ok") else "❌ FAIL"
        case_desc = item.get("case") or ""
        endpoint = item.get("endpoint") or ""
        assertion = item.get("assertion") or ""

        lines.append(f"## Case {idx}: {name} {status}")
        lines.append("")
        if case_desc:
            lines.append(f"**用例描述**：{case_desc}")
            lines.append("")
        if endpoint:
            lines.append(f"**接口**：`{endpoint}`")
            lines.append("")
        if assertion:
            lines.append(f"**断言**：{assertion}")
            lines.append("")
        req = item.get("request")
        if req:
            lines.append("<details><summary>请求 Body</summary>")
            lines.append("")
            lines.append("```json")
            lines.append(_json_str(req))
            lines.append("```")
            lines.append("</details>")
            lines.append("")
        resp = item.get("response")
        if resp:
            lines.append("<details><summary>后端返回</summary>")
            lines.append("")
            lines.append("```json")
            lines.append(_truncate_json(resp))
            lines.append("```")
            lines.append("</details>")
            lines.append("")
        lines.append("---")
        lines.append("")
    return "\n".join(lines)


def format_smoke_html(report: dict[str, Any], *, title: str = "大R后台 API 冒烟验收") -> str:
    passed = int(report.get("passed") or 0)
    failed = int(report.get("failed") or 0)
    total = max(passed + failed, 1)
    ok = bool(report.get("ok"))
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    pass_pct = round(passed * 100 / total)

    check_sections: list[str] = []
    for idx, item in enumerate(report.get("checks") or [], 1):
        if not isinstance(item, dict):
            continue
        name = _esc(item.get("name") or "—")
        item_ok = bool(item.get("ok"))
        badge = (
            '<span class="badge pass">PASS</span>'
            if item_ok
            else '<span class="badge fail">FAIL</span>'
        )
        case_desc = _esc(item.get("case") or "")
        endpoint = _esc(item.get("endpoint") or "")
        assertion = _esc(item.get("assertion") or "")

        req_html = ""
        req = item.get("request")
        if req:
            req_html = f"""<details class="code-block">
  <summary>请求 Body</summary>
  <pre>{_esc(_json_str(req))}</pre>
</details>"""

        resp_html = ""
        resp = item.get("response")
        if resp:
            resp_html = f"""<details class="code-block">
  <summary>后端返回</summary>
  <pre>{_esc(_truncate_json(resp, max_lines=50))}</pre>
</details>"""

        section_cls = "case-section ok" if item_ok else "case-section bad"
        check_sections.append(f"""
<div class="{section_cls}">
  <div class="case-header">
    <span class="case-num">Case {idx}</span>
    <span class="case-name">{name}</span>
    {badge}
  </div>
  {'<div class="case-desc">' + case_desc + '</div>' if case_desc else ''}
  <div class="case-meta">
    {'<div class="meta-row"><span class="meta-label">接口</span><code>' + endpoint + '</code></div>' if endpoint else ''}
    {'<div class="meta-row"><span class="meta-label">断言</span><span>' + assertion + '</span></div>' if assertion else ''}
  </div>
  <div class="case-body">
    {req_html}
    {resp_html}
  </div>
</div>""")

    frontend = report.get("frontendUrl") or ""
    frontend_link = (
        f'<a href="{_esc(frontend)}" target="_blank" rel="noopener">{_esc(frontend)}</a>'
        if frontend
        else "—"
    )

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{_esc(title)}</title>
  <style>
    :root {{
      --bg: #0f1419;
      --card: #1a2332;
      --text: #e7ebf1;
      --muted: #8b949e;
      --pass: #3fb950;
      --fail: #f85149;
      --accent: #58a6ff;
      --border: #30363d;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.6;
      padding: 24px;
    }}
    .wrap {{ max-width: 1060px; margin: 0 auto; }}
    h1 {{ margin: 0 0 8px; font-size: 1.5rem; }}
    .meta-info {{ color: var(--muted); font-size: 0.9rem; margin-bottom: 20px; }}
    .meta-info a {{ color: var(--accent); }}
    .cards {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
      gap: 12px;
      margin-bottom: 28px;
    }}
    .card {{
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 16px;
    }}
    .card .label {{ color: var(--muted); font-size: 0.8rem; }}
    .card .value {{ font-size: 1.6rem; font-weight: 700; margin-top: 4px; }}
    .card.overall.pass .value {{ color: var(--pass); }}
    .card.overall.fail .value {{ color: var(--fail); }}
    .bar {{
      height: 8px;
      background: var(--border);
      border-radius: 4px;
      overflow: hidden;
      margin-top: 8px;
    }}
    .bar > span {{
      display: block; height: 100%;
      background: linear-gradient(90deg, var(--pass), #56d364);
      width: {pass_pct}%;
    }}
    .case-section {{
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 18px 20px;
      margin-bottom: 16px;
    }}
    .case-section.bad {{
      border-color: var(--fail);
      background: rgba(248, 81, 73, 0.04);
    }}
    .case-header {{
      display: flex; align-items: center; gap: 10px;
      margin-bottom: 6px;
    }}
    .case-num {{
      color: var(--muted); font-size: 0.8rem; font-weight: 600;
    }}
    .case-name {{
      font-weight: 700; font-size: 1rem;
    }}
    .badge {{
      display: inline-block;
      padding: 2px 10px;
      border-radius: 999px;
      font-size: 0.75rem;
      font-weight: 700;
      margin-left: auto;
    }}
    .badge.pass {{ background: rgba(63, 185, 80, 0.2); color: var(--pass); }}
    .badge.fail {{ background: rgba(248, 81, 73, 0.2); color: var(--fail); }}
    .case-desc {{
      color: var(--text); font-size: 0.9rem; margin-bottom: 8px;
    }}
    .case-meta {{
      margin-bottom: 10px;
    }}
    .meta-row {{
      display: flex; align-items: baseline; gap: 8px;
      font-size: 0.85rem; margin-bottom: 3px;
    }}
    .meta-label {{
      color: var(--muted); min-width: 40px;
    }}
    .meta-row code {{
      background: #21262d; padding: 2px 6px; border-radius: 4px;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 0.82rem; color: var(--accent);
    }}
    .case-body {{
      display: flex; flex-direction: column; gap: 8px;
    }}
    details.code-block {{
      border: 1px solid var(--border);
      border-radius: 6px;
      overflow: hidden;
    }}
    details.code-block summary {{
      padding: 8px 12px;
      background: #21262d;
      cursor: pointer;
      font-size: 0.82rem;
      font-weight: 600;
      color: var(--muted);
    }}
    details.code-block summary:hover {{
      color: var(--text);
    }}
    details.code-block pre {{
      margin: 0;
      padding: 12px 14px;
      background: #161b22;
      white-space: pre-wrap;
      word-break: break-word;
      font-size: 0.78rem;
      color: #c9d1d9;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      max-height: 400px;
      overflow-y: auto;
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <h1>{_esc(title)}</h1>
    <div class="meta-info">
      生成时间：{_esc(now)} · API：{_esc(report.get("baseUrl"))}<br />
      前端入口：{frontend_link}
    </div>
    <div class="cards">
      <div class="card overall {'pass' if ok else 'fail'}">
        <div class="label">总结果</div>
        <div class="value">{'通过' if ok else '失败'}</div>
      </div>
      <div class="card">
        <div class="label">通过</div>
        <div class="value" style="color:var(--pass)">{passed}</div>
      </div>
      <div class="card">
        <div class="label">失败</div>
        <div class="value" style="color:var(--fail)">{failed}</div>
      </div>
      <div class="card">
        <div class="label">通过率</div>
        <div class="value">{pass_pct}%</div>
        <div class="bar"><span></span></div>
      </div>
    </div>
    {''.join(check_sections) if check_sections else '<p>无检查项</p>'}
  </div>
</body>
</html>
"""
