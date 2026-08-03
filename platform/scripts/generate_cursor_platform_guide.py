#!/usr/bin/env python3
"""从钉钉文档缓存生成「Cursor 搭建智能工具平台」展示页 HTML。"""

from __future__ import annotations

import html
import json
import re
import socket
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CACHE = Path.home() / "Documents/cursor-mcp/dingDoc/cursor搭建智能测试工具平台"
CONTENT_FILE = "dQPGYqjpJYgLbY0YCZkZMpGDWakx1Z5N_content.json"
SOURCE_HTML = "dQPGYqjpJYgLbY0YCZkZMpGDWakx1Z5N.html"
OUTPUT_DIR = REPO_ROOT / "platform" / "exports" / "cursor-platform-guide"
OUTPUT_HTML = OUTPUT_DIR / "index.html"
# 必须用绝对路径：页面 URL 为 /platform-guide（无尾斜杠）时相对 images/ 会解析到 /images/
IMAGE_URL_PREFIX = "/platform-guide/images"
SOURCE_DOC_URL = (
    "https://alidocs.dingtalk.com/i/nodes/dQPGYqjpJYgLbY0YCZkZMpGDWakx1Z5N"
)

# 章节标题与导语优化（保留原意，统一表述）
SECTION_TITLES: dict[str, str] = {
    "一、知识库搭建": "知识库搭建",
    "二、MOA能力实现和使用": "MOA 能力",
    "三、风控请求方法实现和使用": "风控解除",
    "四、开发后台功能的实现和使用": "Admin 后台",
    "五、tunnel抓包能力的实现和使用": "Tunnel 抓包",
    "六、读取钉钉文档的能力和应用": "钉钉文档",
    "七、使用测试工具平台完成测试需求": "平台验收",
    "八、探索：在cursor搭建基于知识库和智能测试工具的依赖视觉反馈的自然语言安卓自动化测试系统": "ADB 视觉自动化",
}

SECTION_IDS: dict[str, str] = {
    "一、知识库搭建": "kb",
    "二、MOA能力实现和使用": "moa",
    "三、风控请求方法实现和使用": "risk",
    "四、开发后台功能的实现和使用": "admin",
    "五、tunnel抓包能力的实现和使用": "tunnel",
    "六、读取钉钉文档的能力和应用": "dingtalk-doc",
    "七、使用测试工具平台完成测试需求": "acceptance",
    "八、探索：在cursor搭建基于知识库和智能测试工具的依赖视觉反馈的自然语言安卓自动化测试系统": "adb-auto",
}

# 已有 block-desc 时可省略的原文段落（前缀匹配）
SKIP_PARAGRAPH_PREFIXES = (
    "为了能快速得到覆盖面全的知识库",
    "同样为了让Cursor更快的全面了解Yaahlan",
)

SECTION_INTROS: dict[str, str] = {
    "一、知识库搭建": "先把 Yaahlan 的用例与历史 Bug 沉淀为结构化知识库，让 Agent 有上下文可依。",
    "二、MOA能力实现和使用": "从单条 MOA 录入到自然语言造数、多 MOA 协同，逐步把常用操作脚本化。",
    "三、风控请求方法实现和使用": "解除登录风控、同步测试机信息，与设备知识库联动。",
    "四、开发后台功能的实现和使用": "Admin 查数与 MOA 造数组合，支持手机号、角色等多种身份指代。",
    "五、tunnel抓包能力的实现和使用": "抓包查数、问题分析、Mock 造数，与 MOA / Admin 串联验收。",
    "六、读取钉钉文档的能力和应用": "读取版本用例与需求文档，同步到知识库，支撑用例与 PRD 工作流。",
    "七、使用测试工具平台完成测试需求": "录制规则与 MOA，结合抓包完成活动验收与数值核对。",
    "八、探索：在cursor搭建基于知识库和智能测试工具的依赖视觉反馈的自然语言安卓自动化测试系统": "ADB 视觉自动化：截图 → 分析 → 操作 → 片段沉淀，与工具平台协同造数验收。",
}

PREFACE_OPTIMIZED = (
    "最初只是想用自然语言给 Yaahlan 账号「加数值」——接入 MOA 后效果超出预期。"
    "随后陆续扩展 Admin、Tunnel、钉钉文档、风控等能力，边用边沉淀，"
    "逐步搭成 <strong>Yaahlan 智能工具平台</strong>。"
    "多轮迭代下来，日常测试效率提升显著，能力仍在持续扩展。"
)

SUBTITLE_OPTIMIZED: dict[str, str] = {
    "1、导入测试用例知识库": "导入历史版本全部测试用例；冲突以最新版本为准，拆模块持续调优。",
    "2、导入历史bug知识库": "同步导入历史 Bug，模块划分与用例库保持一致。",
    "1、MOA的导入": "首次用网页检查器粘贴完整请求；后续可直接贴截图 + 功能说明。",
    "2、使用自然语言完成MOA操作": "录入脚本后，用一句话完成查数、改数。",
    "3、将MOA操作与知识库中的数值做关联": "Agent 理解 VIP 等级、资料卡背景等业务语义，自动换算目标数值。",
    "4、多MOA协同操作": "复杂场景组合多条 MOA，批量造数、准备上传数据。",
    "1、录入风控请求方法": "登记解除设备 / 手机号风控的请求方式。",
    "2、将当前测试机信息导入知识库": "mmuid、机型等写入 test_devices，便于按设备指代账号。",
    "3、批量解除风控设备": "按持有人或全量解除登录风控。",
    "1、后台功能的导入": "与 MOA 类似：检查器导入或补充更多 Admin 接口。",
    "2、使用开发后台功能": "查公会、设客服等后台操作。",
    "3、MOA和开发后台联动操作": "跨模块编排：查号段 → 改分区 → 查在线。",
    "4、尝试更多可能性": "用「可能是谁的账号」等模糊身份指代用户。",
    "1、录入tunnel抓包请求，并说明请求详情": "登记 Tunnel 查询方式与字段含义。",
    "2、抓包能力应用": "分析失败原因、提取礼物 ID、Mock 分页数据等。",
    "1、增加读取钉钉文档目录能力": "脚本读取 alidocs 目录，录制常用文档链接。",
    "2、调用已登记目录中的任意文档": "查版本用例、同步知识库、查研发测试负责人等。",
    "1、根据活动期间CP贡献值下发钻石奖励，根据不同档位下方不同数量的奖励": "录制规则 + MOA + 抓包，分档验收奖励下发。",
    "2、测试送礼后账号各数值是否正确": "送礼前后对比榜单与资产数值。",
    "1、搭建测试环境": "截图识页、逐步操作、片段沉淀与设备坐标映射。",
    "2、拓展能力": "与工具平台协同：缺钻自动下发、多机联动、抓包验收。",
    "3、使用自动化工具造测试数据": "注册发动态、批量缔结 CP 并送礼造贡献值。",
    "4、优化方案": "提升视觉读取链路的每一步耗时。",
}

PROMPT_LABELS = {"a", "b", "c", "d", "e", "f", "g"}


def collect_text(nodes: list) -> str:
    parts: list[str] = []
    for node in nodes:
        if isinstance(node, str):
            parts.append(node)
        elif isinstance(node, list):
            parts.append(collect_text(node[2:] if len(node) > 2 else node[1:]))
    return "".join(parts)


def walk(node: object, out: list[dict[str, str]]) -> None:
    if isinstance(node, list) and node:
        tag = node[0]
        attrs = node[1] if len(node) > 1 and isinstance(node[1], dict) else {}
        children = node[2:] if len(node) > 2 else []
        if tag in ("h1", "h2", "h3", "h4", "h5", "p"):
            text = collect_text(children).strip()
            if text:
                out.append({"kind": "text", "tag": tag, "text": text})
            for child in children:
                walk(child, out)
        elif tag == "img":
            out.append(
                {
                    "kind": "img",
                    "src": str(attrs.get("src") or ""),
                    "name": str(attrs.get("name") or "image.png"),
                    "width": str(attrs.get("width") or ""),
                }
            )
        else:
            for child in children:
                walk(child, out)
    elif isinstance(node, list):
        for child in node:
            walk(child, out)


def load_items(cache_dir: Path) -> list[dict[str, str]]:
    content_path = cache_dir / CONTENT_FILE
    if not content_path.is_file():
        raise SystemExit(f"缺少缓存：{content_path}\n请先 parse_document 或提供 --cache-dir")
    data = json.loads(content_path.read_text(encoding="utf-8"))
    body = data["parts"]["00000000-0000-0000-0000-000000000001"]["data"]["body"]
    items: list[dict[str, str]] = []
    for node in body[2:]:
        walk(node, items)
    return items


def load_local_images(cache_dir: Path) -> list[str]:
    html_path = cache_dir / SOURCE_HTML
    if not html_path.is_file():
        return []
    text = html_path.read_text(encoding="utf-8")
    return re.findall(r'src="(images/[^"]+)"', text)


def is_example_prompt(tag: str, text: str) -> bool:
    if tag != "p":
        return False
    if text.startswith("（粘贴请求内容）"):
        return True
    if re.match(r"^[a-g]、", text):
        return False
    if tag == "h5" and re.match(r"^[a-g]、", text):
        return False
    # 短句操作描述
    if len(text) < 120 and any(
        kw in text
        for kw in (
            "MOA",
            "抓包",
            "解除",
            "查询",
            "升级",
            "下发",
            "判断",
            "送礼",
            "缔结",
            "1331111",
            "1000",
        )
    ):
        return True
    return False


def normalize_prompt(text: str) -> str:
    text = text.replace("（粘贴请求内容）", "").strip()
    text = text.replace("cursor", "Cursor").replace("yaahlan", "Yaahlan")
    text = text.replace("tunnel", "Tunnel").replace("moa", "MOA")
    return text


def slugify(text: str) -> str:
    return SECTION_IDS.get(text, re.sub(r"[^\w\u4e00-\u9fff]+", "-", text).strip("-").lower()[:48] or "section")


def render_items(items: list[dict[str, str]], local_images: list[str]) -> str:
    chunks: list[str] = []
    img_idx = 0
    current_h1 = ""

    chunks.append(
        f'<section class="hero" id="top">\n'
        f'  <p class="eyebrow">Yaahlan · 智能工具平台</p>\n'
        f'  <h1>用 Cursor 搭建智能工具平台</h1>\n'
        f'  <p class="lead">从 MOA 一句话造数，到 Admin / Tunnel / 钉钉文档 / ADB 自动化——能力逐步沉淀、持续生长。</p>\n'
        f'  <div class="hero-actions">\n'
        f'    <a class="btn primary" href="{html.escape(SOURCE_DOC_URL)}" target="_blank" rel="noopener">查看钉钉原文档</a>\n'
        f'    <a class="btn ghost" href="/keynote" target="_blank" rel="noopener">产品演示页</a>\n'
        f"  </div>\n"
        f"</section>\n"
    )

    for item in items:
        if item["kind"] == "img":
            src = local_images[img_idx] if img_idx < len(local_images) else ""
            img_idx += 1
            if src:
                chunks.append(
                    f'<figure class="shot"><img src="{html.escape(src)}" alt="操作示例" loading="lazy" /></figure>'
                )
            else:
                chunks.append(
                    '<figure class="shot shot-placeholder"><span>操作截图 · 见钉钉原文档</span></figure>'
                )
            continue

        tag = item["tag"]
        text = item["text"]

        if tag == "h5" and text.startswith("前言"):
            chunks.append(
                f'<section class="preface" id="preface">\n'
                f'  <h2>前言</h2>\n'
                f'  <p>{PREFACE_OPTIMIZED}</p>\n'
                f"</section>\n"
            )
            continue

        if tag == "h1":
            current_h1 = text
            sid = slugify(text)
            intro = SECTION_INTROS.get(text, "")
            chunks.append(f'<section class="chapter" id="{sid}">')
            chunks.append(f'  <p class="chapter-index">{html.escape(text.split("、")[0])}</p>')
            title = text.split("、", 1)[-1] if "、" in text else text
            chunks.append(f"  <h2>{html.escape(title)}</h2>")
            if intro:
                chunks.append(f'  <p class="chapter-intro">{html.escape(intro)}</p>')
            continue

        if tag == "h3":
            sub = SUBTITLE_OPTIMIZED.get(text, "")
            chunks.append(f'  <div class="block">')
            chunks.append(f'    <h3>{html.escape(text)}</h3>')
            if sub:
                chunks.append(f'    <p class="block-desc">{html.escape(sub)}</p>')
            continue

        if tag == "h5":
            label = text
            chunks.append(f'    <h4>{html.escape(label)}</h4>')
            continue

        if tag == "p":
            prompt = normalize_prompt(text)
            if is_example_prompt(tag, text):
                chunks.append(
                    f'    <blockquote class="prompt"><span class="prompt-label">示例提问</span>'
                    f"{html.escape(prompt)}</blockquote>"
                )
            elif prompt:
                chunks.append(f'    <p>{html.escape(prompt)}</p>')

    chunks.append("</section>" * max(1, sum(1 for i in items if i.get("tag") == "h1")))
    # close open blocks - simpler: rebuild with state machine

    return _render_with_state_machine(items, local_images)


def _render_with_state_machine(
    items: list[dict[str, str]], local_images: list[str], cache_dir: Path
) -> tuple[str, str]:
    out: list[str] = []
    img_idx = 0
    in_chapter = False
    in_block = False

    def close_block() -> None:
        nonlocal in_block
        if in_block:
            out.append("  </div>")
            in_block = False

    def close_chapter() -> None:
        nonlocal in_chapter
        close_block()
        if in_chapter:
            out.append("</section>")
            in_chapter = False

    out.append(
        f'<section class="hero" id="top">\n'
        f'  <p class="eyebrow">Yaahlan · 智能工具平台</p>\n'
        f'  <h1>用 Cursor 搭建智能工具平台</h1>\n'
        f'  <p class="lead">从 MOA 一句话造数，到 Admin / Tunnel / 钉钉文档 / ADB 自动化——能力逐步沉淀、持续生长。</p>\n'
        f'  <div class="hero-actions">\n'
        f'    <a class="btn primary" href="{html.escape(SOURCE_DOC_URL)}" target="_blank" rel="noopener">查看钉钉原文档</a>\n'
        f'    <a class="btn ghost" href="/keynote" target="_blank" rel="noopener">产品演示页</a>\n'
        f"  </div>\n"
        f"</section>"
    )

    toc: list[tuple[str, str]] = []

    for item in items:
        if item["kind"] == "img":
            src = local_images[img_idx] if img_idx < len(local_images) else ""
            img_idx += 1
            img_path = cache_dir / src if src else None
            if src and img_path and img_path.is_file():
                # 复制到输出目录，便于独立托管
                dest_dir = OUTPUT_DIR / "images"
                dest_dir.mkdir(parents=True, exist_ok=True)
                dest = dest_dir / Path(src).name
                if not dest.is_file():
                    dest.write_bytes(img_path.read_bytes())
                out.append(
                    f'<figure class="shot"><img src="{IMAGE_URL_PREFIX}/{html.escape(dest.name)}" alt="操作示例" loading="lazy" /></figure>'
                )
            else:
                out.append(
                    '<figure class="shot shot-placeholder"><span>操作截图 · 见钉钉原文档</span></figure>'
                )
            continue

        tag = item["tag"]
        text = item["text"]

        if tag == "h5" and text.startswith("前言"):
            out.append(
                f'<section class="preface" id="preface">\n'
                f"  <h2>前言</h2>\n"
                f"  <p>{PREFACE_OPTIMIZED}</p>\n"
                f"</section>"
            )
            continue

        if tag == "h1":
            close_chapter()
            sid = slugify(text)
            title = SECTION_TITLES.get(text, text.split("、", 1)[-1] if "、" in text else text)
            toc.append((title, sid))
            intro = SECTION_INTROS.get(text, "")
            out.append(f'<section class="chapter" id="{sid}">')
            out.append(f'  <p class="chapter-index">{html.escape(text.split("、")[0])}</p>')
            out.append(f"  <h2>{html.escape(title)}</h2>")
            if intro:
                out.append(f'  <p class="chapter-intro">{html.escape(intro)}</p>')
            in_chapter = True
            continue

        if tag == "h3":
            close_block()
            sub = SUBTITLE_OPTIMIZED.get(text, "")
            out.append('  <div class="block">')
            out.append(f"    <h3>{html.escape(text)}</h3>")
            if sub:
                out.append(f'    <p class="block-desc">{html.escape(sub)}</p>')
            in_block = True
            continue

        if tag == "h5":
            label = text
            if re.match(r"^[a-g]、", label):
                out.append(f'    <h4 class="sub-step">{html.escape(label)}</h4>')
            else:
                out.append(f'    <h4>{html.escape(label)}</h4>')
            continue

        if tag == "p":
            prompt = normalize_prompt(text)
            if not prompt:
                continue
            if any(prompt.startswith(prefix) for prefix in SKIP_PARAGRAPH_PREFIXES):
                continue
            if is_example_prompt(tag, text):
                out.append(
                    '    <blockquote class="prompt"><span class="prompt-label">示例提问</span>'
                    f"{html.escape(prompt)}</blockquote>"
                )
            else:
                out.append(f"    <p>{html.escape(prompt)}</p>")

    close_chapter()

    toc_html = "".join(
        f'      <a href="#{html.escape(sid)}">{html.escape(title)}</a>\n'
        for title, sid in toc
    )

    body = "\n".join(out)
    return toc_html, body


def detect_lan_base_url(port: int = 18766) -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            host = sock.getsockname()[0]
            if host and not host.startswith("127."):
                return f"http://{host}:{port}/platform-guide"
    except OSError:
        pass
    return f"http://127.0.0.1:{port}/platform-guide"


def build_html(cache_dir: Path) -> str:
    items = load_items(cache_dir)
    local_images = load_local_images(cache_dir)
    toc_html, body = _render_with_state_machine(items, local_images, cache_dir)
    lan_url = detect_lan_base_url()

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>用 Cursor 搭建 Yaahlan 智能工具平台</title>
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
      --prompt-bg: rgba(91, 140, 255, 0.08);
      --shadow: 0 24px 80px rgba(0, 0, 0, 0.35);
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: "MiSans Normal", "PingFang SC", sans-serif;
      background: radial-gradient(1200px 600px at 10% -10%, rgba(91,140,255,.18), transparent 60%),
                  radial-gradient(900px 500px at 90% 0%, rgba(56,189,248,.08), transparent 55%),
                  var(--bg);
      color: var(--text);
      line-height: 1.7;
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
    main {{ min-width: 0; }}
    .hero, .preface, .chapter {{
      border: 1px solid var(--border);
      border-radius: 20px;
      background: var(--panel);
      backdrop-filter: blur(12px);
      box-shadow: var(--shadow);
      padding: 28px 32px;
      margin-bottom: 24px;
    }}
    .eyebrow {{
      color: var(--accent);
      font-size: 13px;
      letter-spacing: .06em;
      margin-bottom: 10px;
    }}
    .hero h1, .chapter h2, .preface h2 {{
      font-size: clamp(28px, 4vw, 36px);
      line-height: 1.25;
      margin-bottom: 12px;
    }}
    .lead, .chapter-intro, .block-desc {{
      color: var(--muted);
      font-size: 16px;
    }}
    .hero-actions {{ display: flex; flex-wrap: wrap; gap: 12px; margin-top: 20px; }}
    .btn {{
      display: inline-flex;
      align-items: center;
      padding: 10px 16px;
      border-radius: 999px;
      font-size: 14px;
      text-decoration: none;
      border: 1px solid var(--border);
      transition: .18s ease;
    }}
    .btn.primary {{ background: var(--accent); color: #fff; border-color: transparent; }}
    .btn.primary:hover {{ filter: brightness(1.08); }}
    .btn.ghost {{ color: var(--text); background: transparent; }}
    .btn.ghost:hover {{ background: var(--accent-soft); }}
    .chapter-index {{
      color: var(--accent);
      font-size: 13px;
      font-weight: 600;
      margin-bottom: 6px;
    }}
    .block {{ margin-top: 22px; padding-top: 8px; border-top: 1px solid var(--border); }}
    .block h3 {{ font-size: 20px; margin-bottom: 8px; }}
    .block h4, .block h4.sub-step {{
      font-size: 15px;
      color: #c7d2ea;
      margin: 14px 0 8px;
      font-weight: 600;
    }}
    .prompt {{
      margin: 10px 0 14px;
      padding: 14px 16px 14px 18px;
      border-left: 3px solid var(--accent);
      border-radius: 0 12px 12px 0;
      background: var(--prompt-bg);
      color: #dbe4ff;
      font-size: 15px;
    }}
    .prompt-label {{
      display: block;
      font-size: 12px;
      color: var(--accent);
      margin-bottom: 6px;
      letter-spacing: .04em;
    }}
    .shot {{
      margin: 16px 0;
      border-radius: 14px;
      overflow: hidden;
      border: 1px solid var(--border);
      background: rgba(0,0,0,.2);
    }}
    .shot img {{ display: block; width: 100%; height: auto; }}
    .shot-placeholder {{
      min-height: 120px;
      display: grid;
      place-items: center;
      color: var(--muted);
      font-size: 14px;
    }}
    .footer-note {{
      text-align: center;
      color: var(--muted);
      font-size: 13px;
      padding: 12px 0 24px;
    }}
    @media (max-width: 960px) {{
      .layout {{ grid-template-columns: 1fr; }}
      .toc {{ position: static; }}
    }}
  </style>
</head>
<body>
  <div class="layout">
    <aside class="toc">
      <h2>目录</h2>
      <a href="#top">概览</a>
      <a href="#preface">前言</a>
{toc_html}    </aside>
    <main>
{body}
      <p class="footer-note">整理自钉钉文档 · 文案已优化 · Yaahlan 智能工具平台</p>
    </main>
  </div>
</body>
</html>
"""


def main() -> int:
    cache_dir = DEFAULT_CACHE
    if len(sys.argv) > 1:
        cache_dir = Path(sys.argv[1]).expanduser().resolve()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_HTML.write_text(build_html(cache_dir), encoding="utf-8")
    print(f"generated {OUTPUT_HTML}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
