#!/usr/bin/env python3
"""从 platform/工具台能力使用说明书.md 生成网页版说明书。"""

from __future__ import annotations

import html
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MD_PATH = REPO_ROOT / "platform" / "工具台能力使用说明书.md"
OUTPUT_DIR = REPO_ROOT / "platform" / "exports" / "catalog-manual"
OUTPUT_HTML = OUTPUT_DIR / "index.html"

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")
TABLE_SEP_RE = re.compile(r"^\|[\s\-:|]+\|$")
IMAGE_RE = re.compile(r"^!\[([^\]]*)\]\(([^)]+)\)\s*$")


def slugify(title: str) -> str:
    t = title.strip()
    t = re.sub(r"^\d+\.\s*", "", t)
    t = re.sub(r"[^\w\u4e00-\u9fff]+", "-", t, flags=re.UNICODE).strip("-").lower()
    return t or "section"


def inline_md(text: str) -> str:
    parts: list[str] = []
    i = 0
    while i < len(text):
        if text[i : i + 2] == "**":
            end = text.find("**", i + 2)
            if end != -1:
                parts.append(f"<strong>{html.escape(text[i + 2 : end])}</strong>")
                i = end + 2
                continue
        if text[i] == "`":
            end = text.find("`", i + 1)
            if end != -1:
                parts.append(f"<code>{html.escape(text[i + 1 : end])}</code>")
                i = end + 1
                continue
        parts.append(html.escape(text[i]))
        i += 1
    return "".join(parts)


def parse_table(lines: list[str], start: int) -> tuple[str, int]:
    rows: list[list[str]] = []
    i = start
    while i < len(lines):
        line = lines[i].strip()
        if not line.startswith("|"):
            break
        if TABLE_SEP_RE.match(line):
            i += 1
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        rows.append(cells)
        i += 1
    if not rows:
        return "", start
    thead = ""
    tbody_rows: list[str] = []
    for idx, row in enumerate(rows):
        tag = "th" if idx == 0 else "td"
        cells_html = "".join(f"<{tag}>{inline_md(c)}</{tag}>" for c in row)
        if idx == 0:
            thead = f"<thead><tr>{cells_html}</tr></thead>"
        else:
            tbody_rows.append(f"<tr>{cells_html}</tr>")
    table = f'<table class="data-table">{thead}<tbody>{"".join(tbody_rows)}</tbody></table>'
    return table, i


def parse_markdown(md: str) -> tuple[list[dict[str, str]], str]:
    lines = md.replace("\r\n", "\n").split("\n")
    toc: list[dict[str, str]] = []
    body: list[str] = []
    i = 0
    in_code = False
    code_buf: list[str] = []
    list_buf: list[str] = []
    list_ordered = False

    def flush_list() -> None:
        nonlocal list_buf, list_ordered
        if not list_buf:
            return
        tag = "ol" if list_ordered else "ul"
        body.append(f"<{tag}>" + "".join(f"<li>{inline_md(item)}</li>" for item in list_buf) + f"</{tag}>")
        list_buf = []

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith("```"):
            flush_list()
            if in_code:
                body.append(f"<pre><code>{html.escape(chr(10).join(code_buf))}</code></pre>")
                code_buf = []
                in_code = False
            else:
                in_code = True
            i += 1
            continue

        if in_code:
            code_buf.append(line)
            i += 1
            continue

        if not stripped:
            flush_list()
            i += 1
            continue

        hm = HEADING_RE.match(stripped)
        if hm:
            flush_list()
            level = len(hm.group(1))
            title = hm.group(2).strip()
            if level == 1:
                sid = "top"
            else:
                sid = slugify(title)
                toc.append({"id": sid, "title": title})
            tag = f"h{min(level, 4)}"
            body.append(f'<{tag} id="{sid}">{inline_md(title)}</{tag}>')
            i += 1
            continue

        if stripped.startswith("|") and "|" in stripped[1:]:
            flush_list()
            table_html, i = parse_table(lines, i)
            if table_html:
                body.append(table_html)
            continue

        if stripped.startswith(">"):
            flush_list()
            quote_lines: list[str] = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote_lines.append(lines[i].strip().lstrip(">").strip())
                i += 1
            body.append(f"<blockquote>{inline_md(' '.join(quote_lines))}</blockquote>")
            continue

        if re.match(r"^[-*]\s+", stripped):
            if list_ordered and list_buf:
                flush_list()
            list_ordered = False
            list_buf.append(re.sub(r"^[-*]\s+", "", stripped))
            i += 1
            continue

        if re.match(r"^\d+\.\s+", stripped):
            if not list_ordered and list_buf:
                flush_list()
            list_ordered = True
            list_buf.append(re.sub(r"^\d+\.\s+", "", stripped))
            i += 1
            continue

        if stripped == "---":
            flush_list()
            body.append("<hr/>")
            i += 1
            continue

        im = IMAGE_RE.match(stripped)
        if im:
            flush_list()
            alt = html.escape(im.group(1))
            src = html.escape(im.group(2).strip(), quote=True)
            cap = f"<figcaption>{alt}</figcaption>" if im.group(1) else ""
            body.append(
                f'<figure class="manual-figure"><img src="{src}" alt="{alt}" loading="lazy" />{cap}</figure>'
            )
            i += 1
            continue

        flush_list()
        body.append(f"<p>{inline_md(stripped)}</p>")
        i += 1

    flush_list()
    if in_code and code_buf:
        body.append(f"<pre><code>{html.escape(chr(10).join(code_buf))}</code></pre>")

    return toc, "\n".join(body)


def build_html(toc: list[dict[str, str]], content: str, generated_at: str) -> str:
    toc_links = ['<a href="#top">概览</a>']
    for item in toc:
        tid = html.escape(item["id"], quote=True)
        title = html.escape(item["title"])
        toc_links.append(f'<a href="#{tid}">{title}</a>')

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>工具台能力 · 使用说明书</title>
  <link rel="stylesheet" href="/assets/fonts/misans/Normal/MiSans-Normal.min.css" />
  <style>
    :root {{
      --bg: #0b1020;
      --panel: rgba(18, 24, 42, 0.92);
      --text: #e8edf8;
      --muted: #9aa8c7;
      --accent: #5b8cff;
      --accent-soft: rgba(91, 140, 255, 0.14);
      --border: rgba(255, 255, 255, 0.08);
      --code-bg: rgba(0, 0, 0, 0.35);
      --shadow: 0 24px 80px rgba(0, 0, 0, 0.35);
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: "MiSans Normal", "PingFang SC", sans-serif;
      background: radial-gradient(1200px 600px at 10% -10%, rgba(91,140,255,.18), transparent 60%),
                  radial-gradient(900px 500px at 90% 0%, rgba(56,189,248,.08), transparent 55%),
                  var(--bg);
      color: var(--text);
      line-height: 1.75;
    }}
    .layout {{
      display: grid;
      grid-template-columns: 240px minmax(0, 820px);
      gap: 32px;
      max-width: 1180px;
      margin: 0 auto;
      padding: 32px 24px 80px;
    }}
    .toc {{
      position: sticky;
      top: 24px;
      align-self: start;
      padding: 18px 16px;
      border: 1px solid var(--border);
      border-radius: 16px;
      background: var(--panel);
      backdrop-filter: blur(12px);
      box-shadow: var(--shadow);
    }}
    .toc h2 {{
      font-size: 13px;
      letter-spacing: .08em;
      text-transform: uppercase;
      color: var(--muted);
      margin-bottom: 12px;
    }}
    .toc a {{
      display: block;
      color: var(--muted);
      text-decoration: none;
      font-size: 14px;
      padding: 8px 10px;
      border-radius: 10px;
      transition: .18s ease;
    }}
    .toc a:hover {{ color: var(--text); background: var(--accent-soft); }}
    main {{
      min-width: 0;
      border: 1px solid var(--border);
      border-radius: 20px;
      background: var(--panel);
      backdrop-filter: blur(12px);
      box-shadow: var(--shadow);
      padding: 28px 32px 36px;
    }}
    .eyebrow {{ color: var(--accent); font-size: 13px; letter-spacing: .06em; margin-bottom: 10px; }}
    h1 {{ font-size: clamp(26px, 4vw, 34px); margin-bottom: 16px; line-height: 1.3; }}
    h2 {{ font-size: 22px; margin: 28px 0 12px; color: #dbe4ff; border-bottom: 1px solid var(--border); padding-bottom: 8px; }}
    h3 {{ font-size: 17px; margin: 20px 0 10px; color: #c7d2ea; }}
    h4 {{ font-size: 15px; margin: 16px 0 8px; color: #b8c5e4; }}
    p {{ margin: 0 0 12px; color: var(--text); }}
    p strong {{ color: #fff; }}
    hr {{ border: none; border-top: 1px solid var(--border); margin: 20px 0; }}
    blockquote {{
      margin: 12px 0 16px;
      padding: 12px 16px;
      border-left: 3px solid var(--accent);
      border-radius: 0 12px 12px 0;
      background: var(--accent-soft);
      color: var(--muted);
      font-size: 15px;
    }}
    ul, ol {{ margin: 0 0 14px 22px; color: var(--text); }}
    li {{ margin-bottom: 6px; }}
    pre {{
      margin: 12px 0 16px;
      padding: 14px 16px;
      border-radius: 12px;
      background: var(--code-bg);
      border: 1px solid var(--border);
      overflow-x: auto;
      font-size: 13px;
      line-height: 1.55;
    }}
    code {{
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 0.92em;
      background: var(--code-bg);
      padding: 2px 6px;
      border-radius: 6px;
    }}
    pre code {{ background: transparent; padding: 0; }}
    .data-table {{
      width: 100%;
      border-collapse: collapse;
      margin: 12px 0 18px;
      font-size: 14px;
    }}
    .data-table th, .data-table td {{
      border: 1px solid var(--border);
      padding: 8px 10px;
      text-align: left;
      vertical-align: top;
    }}
    .data-table th {{ background: var(--accent-soft); color: #dbe4ff; white-space: nowrap; }}
    .data-table tr:nth-child(even) td {{ background: rgba(255,255,255,.02); }}
    .ascii {{
      white-space: pre;
      font-family: ui-monospace, Menlo, monospace;
      font-size: 12px;
      line-height: 1.45;
      color: var(--muted);
      overflow-x: auto;
      margin: 12px 0 16px;
      padding: 12px 14px;
      border-radius: 12px;
      border: 1px solid var(--border);
      background: var(--code-bg);
    }}
    .manual-figure {{
      margin: 16px 0 20px;
      border: 1px solid var(--border);
      border-radius: 14px;
      overflow: hidden;
      background: rgba(0, 0, 0, 0.25);
    }}
    .manual-figure img {{
      display: block;
      width: 100%;
      height: auto;
    }}
    .manual-figure figcaption {{
      padding: 10px 14px;
      font-size: 13px;
      color: var(--muted);
      border-top: 1px solid var(--border);
    }}
    .footer-note {{
      text-align: center;
      color: var(--muted);
      font-size: 13px;
      margin-top: 28px;
      grid-column: 1 / -1;
    }}
    @media (max-width: 960px) {{
      .layout {{ grid-template-columns: 1fr; }}
      .toc {{ position: static; }}
      .data-table {{ display: block; overflow-x: auto; }}
    }}
  </style>
</head>
<body>
  <div class="layout">
    <aside class="toc">
      <h2>目录</h2>
      {chr(10).join(toc_links)}
    </aside>
    <main>
      <p class="eyebrow">Yaahlan · 工具台能力</p>
      {content}
    </main>
    <p class="footer-note">生成于 {html.escape(generated_at)} · 源文件 platform/工具台能力使用说明书.md</p>
  </div>
</body>
</html>
"""


def main() -> int:
    if not MD_PATH.is_file():
        print(f"ERROR: missing {MD_PATH}", file=sys.stderr)
        return 1
    md = MD_PATH.read_text(encoding="utf-8")
    toc, content = parse_markdown(md)
    generated_at = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M %Z")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_HTML.write_text(build_html(toc, content, generated_at), encoding="utf-8")
    print(f"wrote: {OUTPUT_HTML}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
