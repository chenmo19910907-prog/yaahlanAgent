#!/usr/bin/env python3
"""
将 Yaahlan 半月结算薪测试报告（Markdown）转换为 HTML，展示格式与钉钉文档风格一致。

用法：
  # 转换指定报告（默认输出到同目录同名的 .html）
  python scripts/md_report_to_html.py docs/yaahlan_salary/cycle_salary/reports/yaahlan_cycle_salary_test_report_20260612.md

  # 指定输出路径
  python scripts/md_report_to_html.py --out report.html docs/.../yaahlan_cycle_salary_test_report_20260612.md

  # 转换该目录下最新一份报告
  python scripts/md_report_to_html.py --latest
"""

import argparse
import os
import re
import sys


# 钉钉文档风格 + 图标与美观样式
H2_ICONS = {
    "概要": "📋",
    "执行结果明细": "📊",
    "用例计算明细（步骤与数值）": "📝",
    "失败说明与排查建议": "⚠️",
}

HTML_HEAD = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>%(title)s</title>
  <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
  <style>
    :root { --pass: #1a7f37; --fail: #cf222e; --link: #0969da; --border: #d0d7de; --bg-muted: #f6f8fa; --bg-card: #fafbfc; --radius: 8px; --shadow: 0 1px 3px rgba(0,0,0,0.06); --shadow-sm: 0 2px 8px rgba(0,0,0,0.08); }
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif; margin: 0; padding: 20px 24px; color: #24292f; line-height: 1.6; max-width: 1600px; margin-left: auto; margin-right: auto; background: #fff; }
    body > main { padding-top: 4px; }
    h1 { font-size: 1.75em; font-weight: 700; margin-top: 0; margin-bottom: 24px; color: #111; display: flex; align-items: center; gap: 10px; padding-bottom: 16px; border-bottom: 3px solid var(--border); }
    h1 .title-icon { font-size: 1.15em; opacity: 0.9; }
    h2 { font-size: 1.35em; font-weight: 700; margin-top: 36px; margin-bottom: 16px; color: #111; padding: 14px 18px; background: linear-gradient(135deg, var(--bg-card) 0%%, #f0f4f8 100%%); border-left: 5px solid var(--link); border-radius: 0 var(--radius) var(--radius) 0; scroll-margin-top: 20px; display: flex; align-items: center; gap: 10px; box-shadow: var(--shadow); }
    h2 .h2-icon { font-size: 1.15em; opacity: 0.9; }
    h3 { font-size: 1.18em; font-weight: 700; margin-top: 28px; margin-bottom: 12px; color: #111; padding: 10px 14px; background: linear-gradient(90deg, rgba(9,105,218,0.06) 0%%, transparent 100%%); border-radius: var(--radius); scroll-margin-top: 20px; border-left: 3px solid #0969da; }
    h3:target { background: linear-gradient(90deg, rgba(9,105,218,0.14) 0%%, transparent 100%%); padding: 10px 14px; margin-left: -14px; margin-right: -14px; border-radius: var(--radius); }
    h4 { font-size: 1.06em; font-weight: 700; margin-top: 18px; margin-bottom: 8px; color: #222; padding-left: 6px; border-left: 2px solid #57606a; }
    table { border-collapse: collapse; width: 100%%; margin: 14px 0; font-size: 14px; border-radius: var(--radius); overflow: hidden; box-shadow: var(--shadow); }
    th, td { border: 1px solid var(--border); padding: 10px 14px; text-align: left; }
    th { background: linear-gradient(180deg, #eaeef2 0%%, #e1e6eb 100%%); font-weight: 600; color: #111; }
    tr:nth-child(even) { background: #fafbfc; }
    tr:hover { background: #f0f4f8; }
    table a { color: var(--link); text-decoration: none; font-weight: 500; }
    table a:hover { text-decoration: underline; }
    .report-results-table { box-shadow: var(--shadow-sm); width: 100%%; table-layout: auto; border-radius: var(--radius); }
    .report-results-table thead th { position: sticky; top: 0; background: linear-gradient(180deg, #e1e6eb 0%%, #d8dde4 100%%) !important; z-index: 2; box-shadow: 0 1px 0 var(--border); white-space: normal; line-height: 1.4; }
    .report-results-table td.pass { color: var(--pass); font-weight: 600; }
    .report-results-table td.pass::before { content: "✓ "; font-weight: 700; }
    .report-results-table td.fail { color: var(--fail); font-weight: 600; }
    .report-results-table td.fail::before { content: "✗ "; font-weight: 700; }
    .report-results-table th:nth-child(4), .report-results-table td:nth-child(4) { min-width: 14em; max-width: 26em; word-break: break-word; line-height: 1.5; }
    .report-results-table th:nth-child(11), .report-results-table td:nth-child(11) { min-width: 5.5em; white-space: nowrap; }
    .report-results-table th:nth-child(12), .report-results-table td:nth-child(12) { min-width: 12em; max-width: 22em; word-break: break-word; line-height: 1.5; }
    .report-results-table .remark-expected-zero { color: #57606a; font-size: 0.95em; }
    .report-need-confirm { color: #cf222e; font-weight: 600; }
    .report-results-table th, .report-results-table td { white-space: normal; word-break: break-word; }
    .report-results-table thead th { white-space: nowrap; }
    #section-summary + ul { background: var(--bg-card); padding: 16px 20px 16px 24px; border-radius: var(--radius); border: 1px solid var(--border); margin-top: 8px; }
    #section-summary + ul li { margin: 6px 0; padding-left: 4px; }
    ul { margin: 10px 0; padding-left: 24px; }
    li { margin: 5px 0; }
    pre { background: linear-gradient(180deg, #f8f9fa 0%%, #f1f3f5 100%%); border: 1px solid var(--border); border-radius: var(--radius); padding: 14px; overflow-x: auto; font-size: 13px; }
    code { font-family: "SF Mono", Consolas, monospace; }
    pre:not(.mermaid) code { background: none; padding: 0; }
    .mermaid { display: block; background: linear-gradient(180deg, #fafbfc 0%%, #f0f4f8 100%%); padding: 24px 28px; margin: 16px 0; border-radius: var(--radius); border: 1px solid var(--border); box-shadow: var(--shadow); }
    .mermaid svg { max-width: 100%%; height: auto; }
    p + .mermaid { margin-top: 8px; }
    p { margin: 10px 0; }
    strong { font-weight: 600; }
    hr { border: none; border-top: 2px solid var(--border); margin: 28px 0; }
    .report-collapse { margin: 16px 0; border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; box-shadow: var(--shadow); background: #fff; }
    .report-collapse-summary { cursor: pointer; padding: 12px 18px; font-size: 1.02em; font-weight: 600; color: #111; background: linear-gradient(135deg, var(--bg-muted) 0%%, #eef2f6 100%%); list-style: none; display: flex; align-items: center; gap: 8px; user-select: none; }
    .report-collapse-summary::-webkit-details-marker { display: none; }
    .report-collapse-summary::before { content: "▶"; font-size: 0.85em; color: var(--link); transition: transform 0.2s; }
    .report-collapse[open] .report-collapse-summary::before { transform: rotate(90deg); }
    .report-collapse-summary:hover { background: linear-gradient(135deg, #eef2f6 0%%, #e2e8ef 100%%); }
    .report-collapse > *:not(summary) { padding: 0 18px 16px; }
    .report-collapse .mermaid { margin-left: -18px; margin-right: -18px; padding-left: 18px; padding-right: 18px; }
    .nav-toc { display: flex; flex-wrap: wrap; gap: 10px 18px; margin-bottom: 24px; padding: 16px 20px; background: linear-gradient(135deg, var(--bg-muted) 0%%, #eef2f6 100%%); border-radius: var(--radius); border: 1px solid var(--border); font-size: 14px; }
    .nav-toc a { color: var(--link); text-decoration: none; font-weight: 500; display: inline-flex; align-items: center; gap: 6px; padding: 6px 12px; border-radius: 6px; transition: background 0.15s; }
    .nav-toc a:hover { background: rgba(9,105,218,0.08); text-decoration: none; }
    .nav-toc .nav-icon { font-size: 1.1em; opacity: 0.9; }
    .back-to-top { position: fixed; bottom: 28px; right: 28px; padding: 12px 18px; background: linear-gradient(135deg, var(--link) 0%%, #0550ae 100%%); color: #fff; border-radius: var(--radius); text-decoration: none; font-size: 14px; font-weight: 500; box-shadow: var(--shadow-sm); display: none; z-index: 100; transition: transform 0.15s, box-shadow 0.15s; border: none; }
    .back-to-top:hover { color: #fff; transform: translateY(-2px); box-shadow: 0 4px 12px rgba(9,105,218,0.35); }
    .back-to-top.visible { display: inline-flex; align-items: center; gap: 6px; }
    .back-to-top .bt-icon { font-size: 1.2em; }
  </style>
</head>
<body id="top">
<main>
"""

# 紧接在 h1 之后插入的导航
NAV_TOC_HTML = """
<nav class="nav-toc" aria-label="报告导航">
  <a href="#section-summary"><span class="nav-icon" aria-hidden="true">📋</span>概要</a>
  <a href="#section-results"><span class="nav-icon" aria-hidden="true">📊</span>执行结果明细</a>
  <a href="#section-cases"><span class="nav-icon" aria-hidden="true">📝</span>用例计算明细</a>
  <a href="#section-failure"><span class="nav-icon" aria-hidden="true">⚠️</span>失败说明与排查建议</a>
</nav>
"""

HTML_TAIL = """
</main>
<a href="#top" class="back-to-top" id="back-to-top" aria-label="返回顶部"><span class="bt-icon" aria-hidden="true">↑</span>返回顶部</a>
<script>
  mermaid.initialize({
    startOnLoad: true,
    theme: 'base',
    themeVariables: {
      primaryColor: '#e8f4fc',
      primaryBorderColor: '#0969da',
      primaryTextColor: '#24292f',
      lineColor: '#57606a',
      secondaryColor: '#f6f8fa',
      tertiaryColor: '#fff'
    },
    flowchart: {
      useMaxWidth: true,
      nodeSpacing: 48,
      rankSpacing: 36,
      padding: 16,
      curve: 'basis',
      diagramPadding: 12
    }
  });
  (function(){
    var bt = document.getElementById('back-to-top');
    if (bt) {
      window.addEventListener('scroll', function(){
        bt.classList.toggle('visible', window.scrollY > 400);
      });
    }
  })();
</script>
</body>
</html>
"""


def _escape(s):
    if not s:
        return ""
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _allow_br(escaped_text):
    """在已转义文本中恢复 <br> 为合法 HTML，使报告中分段换行生效。"""
    if not escaped_text:
        return escaped_text
    return (
        escaped_text.replace("&lt;br&gt;", "<br/>")
        .replace("&lt;br/&gt;", "<br/>")
        .replace("&lt;br /&gt;", "<br/>")
    )


def _inline_md(text):
    """简单把 **x** 转为 <strong>x</strong>，保留其余原文（已 escape）。"""
    return re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)


def _table_cell(text):
    """表格单元格：转义后恢复 <br> 以支持换行，再处理 ** 加粗。供执行结果明细等所有表格单元格统一使用。"""
    return _inline_md(_allow_br(_escape(text)))


def _slug_for_anchor(s):
    """生成可用于 HTML id 的 slug：仅保留字母数字下划线，若以数字开头则加前缀。"""
    if not s:
        return ""
    slug = re.sub(r"[^a-zA-Z0-9_-]", "_", s.strip())
    slug = re.sub(r"_+", "_", slug).strip("_")
    if slug and slug[0].isdigit():
        slug = "case-" + slug
    return slug or "anchor"


# 用例计算明细中可收起/展开的区块标题（点击标题切换展示内容）
COLLAPSE_H4_TITLES = {"计算过程（流程图）", "数据快照"}


def md_to_html(md_text: str) -> str:
    """将 Markdown 转为 HTML，结构对齐钉钉文档（标题、表格、列表、代码块、Mermaid）；计算过程（流程图）与数据快照为可收起块。"""
    lines = md_text.replace("\r\n", "\n").split("\n")
    out = []
    i = 0
    in_code = False
    code_lang = ""
    code_buf = []
    last_h2_text = ""  # 用于判断当前表格是否为「执行结果明细」表
    in_collapsible = False  # 当前是否在可收起块内，遇到下一同级或更高级标题时关闭

    def flush_code():
        nonlocal code_buf, code_lang
        if not code_buf:
            return
        raw = "\n".join(code_buf)
        if code_lang.strip().lower() == "mermaid":
            out.append('<pre class="mermaid">')
            out.append(_escape(raw))
            out.append("</pre>")
        else:
            out.append("<pre><code>")
            out.append(_escape(raw))
            out.append("</code></pre>")
        code_buf = []
        code_lang = ""

    while i < len(lines):
        line = lines[i]
        if in_code:
            if line.strip() == "```":
                flush_code()
                in_code = False
            else:
                code_buf.append(line)
            i += 1
            continue
        if line.strip().startswith("```"):
            in_code = True
            code_lang = line.strip()[3:].strip()
            code_buf = []
            i += 1
            continue
        stripped = line.strip()
        if not stripped:
            out.append("<p></p>")
            i += 1
            continue
        if stripped.startswith("# "):
            flush_code()
            if in_collapsible:
                out.append("</details>")
                in_collapsible = False
            title_text = stripped[2:].strip()
            out.append('<h1><span class="title-icon" aria-hidden="true">📄</span>')
            out.append(_inline_md(_escape(title_text)))
            out.append("</h1>")
            out.append(NAV_TOC_HTML)
            i += 1
            continue
        if stripped.startswith("## "):
            flush_code()
            if in_collapsible:
                out.append("</details>")
                in_collapsible = False
            last_h2_text = stripped[3:].strip()
            h2_id = {
                "概要": "section-summary",
                "执行结果明细": "section-results",
                "用例计算明细（步骤与数值）": "section-cases",
                "失败说明与排查建议": "section-failure",
            }.get(last_h2_text) or _slug_for_anchor(last_h2_text)
            h2_icon = H2_ICONS.get(last_h2_text, "▸")
            out.append(f'<h2 id="{_escape(h2_id)}"><span class="h2-icon" aria-hidden="true">{h2_icon}</span>')
            out.append(_inline_md(_escape(last_h2_text)))
            out.append("</h2>")
            i += 1
            continue
        if stripped.startswith("### "):
            flush_code()
            if in_collapsible:
                out.append("</details>")
                in_collapsible = False
            h3_content = stripped[4:].strip()
            # 用例明细标题：支持 "用例 N：case_name" 或 "N. case_name / 中文名 / English"，给 h3 加 id 便于锚定
            case_id = ""
            if "用例" in h3_content and "：" in h3_content:
                case_id = _slug_for_anchor(h3_content.split("：", 1)[-1].strip())
            else:
                m = re.match(r"^\d+\.\s*(.+?)\s*/\s*", h3_content)
                if m:
                    case_id = _slug_for_anchor(m.group(1))
            if case_id:
                out.append(f'<h3 id="{_escape(case_id)}">')
            else:
                out.append("<h3>")
            out.append(_inline_md(_escape(h3_content)))
            out.append("</h3>")
            i += 1
            continue
        if stripped.startswith("#### "):
            flush_code()
            h4_title = stripped[5:].strip()
            if in_collapsible:
                out.append("</details>")
                in_collapsible = False
            if h4_title in COLLAPSE_H4_TITLES:
                out.append('<details class="report-collapse">')
                out.append(f'<summary class="report-collapse-summary">{_escape(h4_title)}</summary>')
                in_collapsible = True
            else:
                out.append("<h4>")
                out.append(_inline_md(_escape(h4_title)))
                out.append("</h4>")
            i += 1
            continue
        if stripped.startswith("|") and "|" in stripped[1:]:
            flush_code()
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                row = [c.strip() for c in lines[i].split("|")[1:-1]]
                rows.append(row)
                i += 1
            if not rows:
                i += 1
                continue
            def _is_separator(row):
                return row and all(re.match(r"^[\s\-:]+$", c) for c in row)
            is_results_table = last_h2_text == "执行结果明细" and len(rows[0]) >= 3
            if is_results_table:
                header_row = rows[0]
                def _norm(s):
                    return (s or "").replace("<br>", " ").replace("<br/>", " ").strip()
                conclusion_col_idx = next(
                    (i for i, c in enumerate(header_row) if _norm(c) == "结论"),
                    None,
                )
                case_name_col_idx = next(
                    (i for i, c in enumerate(header_row) if _norm(c) in ("用例", "用例名")),
                    None,
                )
                out.append('<table class="report-results-table">')
                out.append("<thead><tr>")
                for cell in rows[0]:
                    out.append("<th>")
                    out.append(_table_cell(cell))
                    out.append("</th>")
                out.append("</tr></thead><tbody>")
                for r_idx, row in enumerate(rows[1:], 1):
                    if _is_separator(row):
                        continue
                    out.append("<tr>")
                    for c_idx, cell in enumerate(row):
                        td_class = ""
                        if conclusion_col_idx is not None and c_idx == conclusion_col_idx:
                            cell_stripped = (cell or "").strip()
                            if cell_stripped == "通过":
                                td_class = ' class="pass"'
                            elif cell_stripped == "失败":
                                td_class = ' class="fail"'
                        out.append(f"<td{td_class}>")
                        if case_name_col_idx is not None and c_idx == case_name_col_idx and cell:
                            # 锚点用本列「用例」(case_name)，与下文 h3 的 id 一致；列1 是用例组会错误指向同组首用例
                            anchor = _slug_for_anchor(cell)
                            out.append(f'<a href="#{_escape(anchor)}">')
                            out.append(_table_cell(cell))
                            out.append("</a>")
                        elif c_idx == 11 and (
                            (cell or "").strip() == "final_salary_missing_but_expected_zero"
                            or ("final_salary 表无记录且期望为0" in (cell or "") and "（按规则不结算，符合预期）" in (cell or ""))
                        ):
                            out.append(
                                '<span class="remark-expected-zero" title="当日按规则不结算，故 final_salary 表无记录，与期望一致">'
                            )
                            out.append("final_salary 表无记录且期望为0<br>（按规则不结算，符合预期）")
                            out.append("</span>")
                        else:
                            out.append(_table_cell(cell))
                        out.append("</td>")
                    out.append("</tr>")
                out.append("</tbody></table>")
            else:
                out.append("<table>")
                for r_idx, row in enumerate(rows):
                    if _is_separator(row):
                        continue
                    tag = "th" if r_idx == 0 else "td"
                    out.append("<tr>")
                    for c_idx, cell in enumerate(row):
                        out.append(f"<{tag}>")
                        if last_h2_text == "执行结果明细" and r_idx > 0 and c_idx == 2 and cell:
                            anchor = _slug_for_anchor(cell)
                            out.append(f'<a href="#{_escape(anchor)}">')
                            out.append(_table_cell(cell))
                            out.append("</a>")
                        else:
                            out.append(_table_cell(cell))
                        out.append(f"</{tag}>")
                    out.append("</tr>")
                out.append("</table>")
            continue
        if stripped.startswith("- "):
            flush_code()
            out.append("<ul>")
            while i < len(lines) and lines[i].strip().startswith("- "):
                content = lines[i].strip()[2:].strip()
                out.append("<li>")
                out.append(_inline_md(_escape(content)))
                out.append("</li>")
                i += 1
            out.append("</ul>")
            continue
        flush_code()
        out.append("<p>")
        if "【需确认】" in stripped:
            out.append('<span class="report-need-confirm">')
        out.append(_inline_md(_escape(stripped)))
        if "【需确认】" in stripped:
            out.append("</span>")
        out.append("</p>")
        i += 1
    flush_code()
    if in_collapsible:
        out.append("</details>")
    return "\n".join(out)


def main():
    parser = argparse.ArgumentParser(description="将 Markdown 测试报告转为 HTML（格式与钉钉文档一致）")
    parser.add_argument("md_file", nargs="?", default=None, help="输入的 .md 报告路径")
    parser.add_argument(
        "--out", "-o", default=None, help="输出 .html 路径（默认与 md 同目录同名 .html）"
    )
    parser.add_argument(
        "--latest",
        action="store_true",
        help="使用 docs/yaahlan_salary/cycle_salary/reports/ 下最新一份报告",
    )
    args = parser.parse_args()

    root = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..")
    )
    if args.latest:
        report_dir = os.path.join(
            root, "docs", "yaahlan_salary", "cycle_salary", "reports"
        )
        if not os.path.isdir(report_dir):
            print(f"目录不存在: {report_dir}", file=sys.stderr)
            sys.exit(1)
        md_files = [
            os.path.join(report_dir, f)
            for f in os.listdir(report_dir)
            if f.endswith(".md") and f.startswith("yaahlan_cycle_salary_test_report_")
        ]
        if not md_files:
            print("未找到报告文件", file=sys.stderr)
            sys.exit(1)
        md_path = max(md_files, key=os.path.getmtime)
    elif args.md_file:
        md_path = os.path.abspath(args.md_file)
        if not os.path.isfile(md_path):
            print(f"文件不存在: {md_path}", file=sys.stderr)
            sys.exit(1)
    else:
        parser.print_help()
        sys.exit(1)

    with open(md_path, "r", encoding="utf-8") as f:
        md_text = f.read()

    title = os.path.splitext(os.path.basename(md_path))[0]
    if args.out:
        out_path = os.path.abspath(args.out)
    else:
        out_path = os.path.splitext(md_path)[0] + ".html"

    html_body = md_to_html(md_text)
    html = (HTML_HEAD % {"title": _escape(title)}) + html_body + HTML_TAIL

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"已生成: {out_path}")


if __name__ == "__main__":
    main()
