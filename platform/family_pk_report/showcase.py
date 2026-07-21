"""家族 PK 向上汇报 — 三块式 Showcase 页（背景 / 演示 / 原理）。"""

from __future__ import annotations

import html
import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from playbook import load_playbook

REPORT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = REPORT_DIR / "config" / "showcase.json"
FAMILY_PK_DEMO_STEPS_PATH = REPORT_DIR / "config" / "family_pk_demo_steps.json"
ANNIVERSARY_EGG_DEMO_STEPS_PATH = REPORT_DIR / "config" / "anniversary_egg_demo_steps.json"
SOURCES_PATH = REPORT_DIR.parent / "config" / "sources.json"
MEDIA_DIR = REPORT_DIR / "media"
_CN_STEP_LABELS = ("", "一", "二", "三", "四", "五", "六", "七", "八", "九", "十")


def load_showcase_config() -> dict[str, Any]:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"invalid showcase config: {CONFIG_PATH}")
    return data


def load_family_pk_demo_steps() -> list[dict[str, Any]]:
    if not FAMILY_PK_DEMO_STEPS_PATH.is_file():
        return []
    with open(FAMILY_PK_DEMO_STEPS_PATH, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"invalid demo steps: {FAMILY_PK_DEMO_STEPS_PATH}")
    return data


def load_anniversary_egg_demo_steps() -> list[dict[str, Any]]:
    if not ANNIVERSARY_EGG_DEMO_STEPS_PATH.is_file():
        return []
    with open(ANNIVERSARY_EGG_DEMO_STEPS_PATH, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"invalid demo steps: {ANNIVERSARY_EGG_DEMO_STEPS_PATH}")
    return data


def load_cursor_bridge_config() -> dict[str, Any]:
    bridge: dict[str, Any] = {"host": "127.0.0.1", "port": 18765}
    if not SOURCES_PATH.is_file():
        return bridge
    with open(SOURCES_PATH, encoding="utf-8") as f:
        data = json.load(f)
    cfg = data.get("cursor_bridge") if isinstance(data, dict) else None
    if isinstance(cfg, dict):
        if isinstance(cfg.get("host"), str) and cfg["host"].strip():
            bridge["host"] = cfg["host"].strip()
        if isinstance(cfg.get("port"), int) and cfg["port"] > 0:
            bridge["port"] = cfg["port"]
    return bridge


def family_pk_step_demo_prompt(step: dict[str, Any], pk_date: str) -> str:
    custom = str(step.get("demoPrompt") or "").strip()
    if custom:
        return custom.replace("<pkDate>", pk_date)
    order = int(step.get("order") or 0)
    if 0 < order < len(_CN_STEP_LABELS):
        step_label = f"第{_CN_STEP_LABELS[order]}步"
    else:
        step_label = f"第{order}步"
    if order <= 1:
        title = str(step.get("title") or "").strip()
        return f"测试{pk_date}日家族PK，第 {order} 步 · {title}"
    return f"继续{step_label}操作"


def anniversary_egg_step_demo_prompt(step: dict[str, Any]) -> str:
    custom = str(step.get("demoPrompt") or "").strip()
    if custom:
        return custom
    order = int(step.get("order") or 0)
    if 0 < order < len(_CN_STEP_LABELS):
        step_label = f"第{_CN_STEP_LABELS[order]}步"
    else:
        step_label = f"第{order}步"
    if order <= 1:
        title = str(step.get("title") or "").strip()
        return f"测试3周年砸金蛋，第 {order} 步 · {title}"
    return f"继续{step_label}操作"


def _demo_step_tab_label(step: dict[str, Any]) -> str:
    short = str(step.get("tabLabel") or step.get("shortTitle") or "").strip()
    if short:
        return short
    title = str(step.get("title") or "").strip()
    if title.endswith("入表"):
        title = title[: -len("入表")].strip()
    order = int(step.get("order") or 0)
    return title or f"第 {order} 步"


def sync_media_to(out_dir: Path) -> Path:
    target = out_dir / "media"
    if MEDIA_DIR.is_dir():
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(MEDIA_DIR, target, ignore=shutil.ignore_patterns(".DS_Store", ".gitkeep"))
    else:
        target.mkdir(parents=True, exist_ok=True)
    return target


def _esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def _format_intro_text(text: str) -> str:
    parts = re.split(r"\*\*(.+?)\*\*", str(text))
    out: list[str] = []
    for index, part in enumerate(parts):
        if index % 2 == 1:
            out.append(f"<strong>{_esc(part)}</strong>")
        else:
            out.append(_esc(part))
    return "".join(out)


def _media_src(media_file: str, exports_dir: Path) -> Path:
    return exports_dir / "media" / media_file


def _render_media_item(
    media: dict[str, Any],
    exports_dir: Path,
    *,
    fallback_caption: str = "",
) -> str:
    media_type = str(media.get("type") or "image").lower()
    media_file = str(media.get("file") or "").strip()
    caption = _esc(media.get("caption") or fallback_caption or "")

    if not media_file:
        return f"""
        <div class="media-box placeholder">
          <div class="ph-inner">未配置 media.file</div>
          <p class="media-caption">{caption}</p>
        </div>
        """

    src_path = _media_src(media_file, exports_dir)
    rel = f"media/{media_file}"
    if not src_path.is_file():
        return f"""
        <div class="media-box placeholder">
          <div class="ph-inner">
            <strong>待录制</strong>
            <span>请将素材放到</span>
            <code>platform/family_pk_report/media/{_esc(media_file)}</code>
            <span>后重新生成</span>
          </div>
          <p class="media-caption">{caption}</p>
        </div>
        """

    if media_type == "video":
        return f"""
        <div class="media-box">
          <video controls playsinline preload="metadata" src="{_esc(rel)}"></video>
          <p class="media-caption">{caption}</p>
        </div>
        """

    return f"""
    <div class="media-box">
      <img src="{_esc(rel)}" alt="{caption}" loading="lazy" />
      <p class="media-caption">{caption}</p>
    </div>
    """


def _render_media_block(step: dict[str, Any], exports_dir: Path) -> str:
    return _render_media_item(step.get("media") or {}, exports_dir, fallback_caption=str(step.get("title") or ""))


UI_CSS_PATH = REPORT_DIR / "assets" / "showcase.ui.css"
EXTRA_CSS_PATH = REPORT_DIR / "assets" / "showcase.extra.css"

_HERO_CONSOLE_HTML = """
      <div class="hero-console" aria-hidden="true">
        <span class="signal-line one"></span><span class="signal-line two"></span>
        <div class="signal-card signal-a">
          <svg class="signal-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M6 19V9m6 10V5m6 14v-7"/><path d="M4 19h16"/></svg>
          <strong>参数与数据源</strong><small>SIGNAL INPUT</small>
          <span class="signal-dots"><i></i><i></i><i></i><i></i><i></i></span>
        </div>
        <div class="signal-card signal-b">
          <svg class="signal-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="4" width="6" height="6" rx="1"/><rect x="14" y="14" width="6" height="6" rx="1"/><path d="M10 7h4a3 3 0 0 1 3 3v4M7 10v7h7"/></svg>
          <strong>Workflow 装配</strong><small>PROCESS ENGINE</small>
          <span class="signal-dots"><i></i><i></i><i></i><i></i><i></i></span>
        </div>
        <div class="signal-card signal-c">
          <svg class="signal-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="m5 12 4 4L19 6"/><path d="M20 12a8 8 0 1 1-4-7"/></svg>
          <strong>全量验收</strong><small>PASS / FAIL VERIFIED</small>
          <span class="signal-dots"><i></i><i></i><i></i><i></i><i></i></span>
        </div>
      </div>
"""


def _showcase_styles() -> str:
    parts: list[str] = []
    for css_path in (UI_CSS_PATH, EXTRA_CSS_PATH):
        if css_path.is_file():
            parts.append(css_path.read_text(encoding="utf-8"))
    return "\n".join(parts)


def _render_hero(title: str, subtitle: str) -> str:
    subtitle_html = f"<p>{_esc(subtitle)}</p>" if subtitle.strip() else ""
    return f"""
    <header class="hero">
      <div class="hero-copy">
        <h1>{_esc(title)}</h1>
        {subtitle_html}
      </div>
      {_HERO_CONSOLE_HTML}
    </header>
"""


def _render_section_intro(lead: str | list[str] | None = None) -> str:
    paragraphs: list[str] = []
    if isinstance(lead, list):
        paragraphs = [str(p).strip() for p in lead if str(p).strip()]
    else:
        text = str(lead or "").strip()
        if text:
            paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        return ""
    body = "".join(f"<p>{_esc(p)}</p>" for p in paragraphs)
    return f'<div class="section-intro">{body}</div>'


def _render_theory_compare_chart(block: dict[str, Any]) -> str:
    if not block:
        return ""
    headers = block.get("headers") or []
    head_html = "".join(f"<th>{_esc(h)}</th>" for h in headers)
    rows_html = ""
    for row in block.get("rows") or []:
        if not isinstance(row, list):
            continue
        cells = "".join(f"<td>{_esc(cell)}</td>" for cell in row)
        rows_html += f"<tr>{cells}</tr>"
    if not head_html or not rows_html:
        return ""
    return f"""
    <div class="theory-chart">
      <h3>{_esc(block.get('title'))}</h3>
      <table class="theory-compare-table">
        <thead><tr>{head_html}</tr></thead>
        <tbody>{rows_html}</tbody>
      </table>
    </div>
    """


def _render_effort_bar(segments: list[dict[str, Any]], *, field: str) -> str:
    bars = ""
    legend = ""
    for seg in segments:
        value = int(seg.get(field) or 0)
        color = str(seg.get("color") or "#2563eb")
        label = _esc(seg.get("label") or "")
        width = max(value, 0)
        bars += (
            f'<div class="effort-bar-seg" style="width:{width}%;background:{color}" '
            f'title="{label} {width}%">{width}%</div>'
        )
        legend += (
            f'<span class="effort-legend-item"><span class="effort-legend-dot" '
            f'style="background:{color}"></span>{label}</span>'
        )
    return f"""
    <div class="effort-bar-track">{bars}</div>
    <div class="effort-legend">{legend}</div>
    """


def _render_effort_chart(block: dict[str, Any]) -> str:
    if not block:
        return ""
    segments = block.get("segments") or []
    if not segments:
        return ""
    caption = block.get("caption") or ""
    caption_html = f'<p class="theory-chart-caption">{_esc(caption)}</p>' if caption else ""
    before_label = _esc(block.get("beforeLabel") or "现状")
    after_label = _esc(block.get("afterLabel") or "优化后")
    before_total = sum(int(s.get("before") or 0) for s in segments)
    after_total = sum(int(s.get("after") or 0) for s in segments)
    highlight = block.get("highlight") or ""
    highlight_html = f'<div class="effort-highlight">{_esc(highlight)}</div>' if highlight else ""
    return f"""
    <div class="theory-chart">
      <h3>{_esc(block.get('title'))}</h3>
      {caption_html}
      <div class="effort-chart-block">
        <div class="effort-chart-label"><span>{before_label}</span><span>{before_total}%</span></div>
        {_render_effort_bar(segments, field="before")}
      </div>
      <div class="effort-chart-block">
        <div class="effort-chart-label"><span>{after_label}</span><span>{after_total}%</span></div>
        {_render_effort_bar(segments, field="after")}
      </div>
      {highlight_html}
    </div>
    """


def _render_acceptance_chart(block: dict[str, Any]) -> str:
    if not block:
        return ""
    before_items = "".join(f"<li>{_esc(x)}</li>" for x in (block.get("before") or []))
    after_items = "".join(f"<li>{_esc(x)}</li>" for x in (block.get("after") or []))
    caption = block.get("caption") or ""
    caption_html = f'<p class="theory-chart-caption">{_esc(caption)}</p>' if caption else ""
    return f"""
    <div class="theory-chart">
      <h3>{_esc(block.get('title'))}</h3>
      {caption_html}
      <div class="acceptance-split">
        <div class="acceptance-col before">
          <h4>{_esc(block.get('beforeTitle') or '传统')}</h4>
          <ul>{before_items}</ul>
        </div>
        <div class="acceptance-col after">
          <h4>{_esc(block.get('afterTitle') or '流程化')}</h4>
          <ul>{after_items}</ul>
        </div>
      </div>
    </div>
    """


def _render_theory_visuals(visuals: dict[str, Any]) -> str:
    if not visuals:
        return ""
    parts = [
        _render_theory_compare_chart(visuals.get("compare") or {}),
    ]
    bottom = f"""
    <div class="theory-chart-grid">
      {_render_effort_chart(visuals.get("effort") or {})}
      {_render_acceptance_chart(visuals.get("acceptance") or {})}
    </div>
    """
    body = "".join(p for p in parts if p) + bottom
    if not body.strip():
        return ""
    return f'<div class="theory-visuals">{body}</div>'


def _render_theory_pillar(pillar: dict[str, Any]) -> str:
    title = _esc(pillar.get("title") or "")
    body = _esc(pillar.get("body") or pillar.get("statement") or "")
    return f"""
    <div class="theory-pillar">
      <h3>{title}</h3>
      <p>{body}</p>
    </div>
    """


def _render_theory_section(theory: dict[str, Any]) -> str:
    if not theory:
        return ""

    visuals_html = _render_theory_visuals(theory.get("visuals") or {})
    pillars = theory.get("pillars") or []
    if not visuals_html:
        if not pillars and (theory.get("body") or theory.get("statement")):
            pillars = [theory]
        pillars_html = "".join(_render_theory_pillar(p) for p in pillars)
        pillars_wrap = f'<div class="theory-pillars">{pillars_html}</div>' if pillars_html else ""
    else:
        pillars_wrap = ""

    return f"""
    <section class="section">
      {_render_section_intro(theory.get("lead"))}
      {visuals_html}
      {pillars_wrap}
    </section>
    """


def _render_flow_step_card(
    step: dict[str, Any],
    *,
    index_prefix: str = "",
    featured_names: set[str] | None = None,
    fallback_order: int = 0,
) -> str:
    featured = featured_names or set()
    order = int(step.get("order") or 0)
    if order <= 0:
        order = fallback_order
    title = str(step.get("title") or "")
    label = f"{index_prefix}{order}" if index_prefix else str(order)
    featured_cls = " featured" if title in featured else ""
    desc = step.get("description") or step.get("body") or ""
    return f"""<div class="flow-step{featured_cls}">
              <span class="step-index">{_esc(label)}</span>
              <strong>{_esc(title)}</strong>
              <span>{_esc(desc)}</span>
            </div>"""


def _render_flow_parallel_branches(
    branches: list[dict[str, Any]],
    *,
    index_prefix: str = "",
    featured_names: set[str] | None = None,
) -> str:
    rows: list[str] = []
    for branch in sorted(branches, key=lambda s: int(s.get("order") or 0)):
        order = int(branch.get("order") or 0)
        rows.append(
            f"""<div class="flow-parallel-branch">
              <div class="flow-arrow" aria-hidden="true">→</div>
              {_render_flow_step_card(branch, index_prefix=index_prefix, featured_names=featured_names, fallback_order=order)}
            </div>"""
        )
    return f'<div class="flow-parallel">{"".join(rows)}</div>'


def _render_flow_track(
    steps: list[dict[str, Any]],
    *,
    index_prefix: str = "",
    featured_names: set[str] | None = None,
) -> str:
    parts: list[str] = []
    ordered = sorted(steps, key=lambda s: int(s.get("order") or 0))
    for i, step in enumerate(ordered):
        if i > 0:
            parts.append('<div class="flow-arrow" aria-hidden="true">→</div>')
        order = int(step.get("order") or 0)
        if order <= 0:
            order = i + 1
        parts.append(
            _render_flow_step_card(
                step,
                index_prefix=index_prefix,
                featured_names=featured_names,
                fallback_order=order,
            )
        )
        branches = step.get("branches")
        if isinstance(branches, list) and branches:
            parts.append(
                _render_flow_parallel_branches(
                    branches,
                    index_prefix=index_prefix,
                    featured_names=featured_names,
                )
            )
    return f'<div class="flow-track">{"".join(parts)}</div>'


def _render_sub_panel_head(title: str, badge: str = "") -> str:
    badge_html = f'<span class="sub-badge">{_esc(badge)}</span>' if badge else ""
    return f"""<div class="sub-panel-head">{badge_html}<h3>{_esc(title)}</h3></div>"""


def _render_workflow_framework_block(block: dict[str, Any], *, block_cls: str) -> str:
    if not block:
        return ""
    badge = "流程" if block_cls == "ranking" else "抽奖"
    return f"""
    <div class="sub-panel {_esc(block_cls)}">
      {_render_sub_panel_head(str(block.get("title") or ""), badge)}
      {_render_flow_track(block.get("steps") or [], index_prefix="S")}
    </div>
    """


def _render_workflow_principle(principle: dict[str, Any]) -> str:
    if not principle:
        return ""
    lead = principle.get("lead") or ""
    lead_html = f'<p class="sub-lead">{_esc(lead)}</p>' if lead else ""
    return f"""
    <div class="sub-panel principle">
      {_render_sub_panel_head(str(principle.get("title") or "核心原理"), "原理")}
      {lead_html}
      {_render_flow_track(principle.get("steps") or [])}
    </div>
    """


def _render_workflow_platform(platform: dict[str, Any]) -> str:
    if not platform:
        return ""
    layers = platform.get("layers") or []
    layer_steps = [
        {"order": i + 1, "title": layer.get("name"), "description": layer.get("description")}
        for i, layer in enumerate(layers)
    ]
    tagline = platform.get("tagline") or ""
    tagline_html = f'<p class="sub-tagline">{_esc(tagline)}</p>' if tagline else ""
    body = platform.get("body") or ""
    body_html = f'<p class="sub-lead">{_esc(body)}</p>' if body else ""
    return f"""
    <div class="sub-panel platform">
      {_render_sub_panel_head(str(platform.get("title") or "智能工具平台"), "平台")}
      {tagline_html}
      {body_html}
      {_render_flow_track(layer_steps, featured_names={"工作流"})}
    </div>
    """


def _render_workflow_recording(recording: dict[str, Any]) -> str:
    if not recording:
        return ""
    lead = recording.get("lead") or ""
    lead_html = f'<p class="sub-lead">{_esc(lead)}</p>' if lead else ""

    process_steps = recording.get("process") or []
    process_html = ""
    if process_steps:
        process_html = _render_flow_track(process_steps, featured_names={"生成平台实现"})

    return f"""
    <div class="sub-panel recording">
      {_render_sub_panel_head(str(recording.get("title") or "工作流录制方法"), "录制")}
      {lead_html}
      {process_html}
    </div>
    """


def _render_workflows_section(section: dict[str, Any]) -> str:
    if not section:
        return ""
    platform_html = _render_workflow_platform(section.get("platform") or {})
    principle_html = _render_workflow_principle(section.get("principle") or {})
    recording_html = _render_workflow_recording(section.get("recording") or {})
    ranking = _render_workflow_framework_block(section.get("ranking") or {}, block_cls="ranking")
    lottery = _render_workflow_framework_block(section.get("lottery") or {}, block_cls="lottery")
    lead = section.get("lead") or ""
    return f"""
    <section class="section">
      {_render_section_intro(lead)}
      {platform_html}
      {principle_html}
      {recording_html}
      {ranking}
      {lottery}
    </section>
    """


def _render_sheet_preview_table(preview: dict[str, Any]) -> str:
    if not preview:
        return ""
    headers = preview.get("headers") or []
    rows = preview.get("rows") or []
    if not headers:
        return ""
    head_html = "".join(f"<th>{_esc(h)}</th>" for h in headers)
    body_html = ""
    for row in rows:
        cells = ""
        for ci, cell in enumerate(row):
            val = _esc(cell)
            cls = ""
            if ci == len(row) - 1 and str(cell) in {"通过", "✓"} or "通过" in str(cell):
                cls = ' class="pass"'
            cells += f"<td{cls}>{val}</td>"
        body_html += f"<tr>{cells}</tr>"
    caption = preview.get("caption") or "Sheet 预览"
    return f"""
    <div class="sheet-preview">
      <div class="sheet-preview-caption">{_esc(caption)}</div>
      <table>
        <thead><tr>{head_html}</tr></thead>
        <tbody>{body_html}</tbody>
      </table>
    </div>
    """


def _render_tool_support_block(step: dict[str, Any]) -> str:
    support = step.get("toolSupport")
    labels: list[str] = []
    if isinstance(support, str):
        raw = support.strip()
        if raw:
            if "\n" in raw:
                labels = [line.strip() for line in raw.splitlines() if line.strip()]
            else:
                labels = [raw]
    elif isinstance(support, list):
        for entry in support:
            if isinstance(entry, dict):
                label = str(entry.get("tool") or entry.get("name") or "").strip()
            else:
                label = str(entry).strip()
            if label:
                labels.append(label)
    if not labels:
        return '<p class="wf-record-summary">—</p>'
    if len(labels) == 1:
        return f'<p class="demo-tool-support-text">{_esc(labels[0])}</p>'
    items = "".join(f"<li>{_esc(label)}</li>" for label in labels)
    return f'<ul class="demo-tool-support-list">{items}</ul>'


def _render_workflow_record_block(step: dict[str, Any]) -> str:
    record = step.get("workflowRecord") or {}
    raw_script = str(record.get("script") or record.get("summary") or "").strip()
    prompts = record.get("prompts") or []
    parts: list[str] = []
    if raw_script:
        lines = [line.strip() for line in raw_script.splitlines() if line.strip()]
        script_html = "<br>".join(_esc(line) for line in lines)
        parts.append(f'<blockquote class="wf-record-script">{script_html}</blockquote>')
    if prompts:
        items = "".join(f"<li>{_esc(str(p))}</li>" for p in prompts)
        parts.append(f'<ul class="wf-record-prompts">{items}</ul>')
    if not parts:
        return '<p class="wf-record-summary">—</p>'
    return "".join(parts)


def _render_tools_block(step: dict[str, Any]) -> str:
    usage = step.get("toolUsage") or []
    if usage:
        items: list[str] = []
        for entry in usage:
            if isinstance(entry, dict):
                tool = str(entry.get("tool") or entry.get("name") or "").strip()
                if tool in {"Workflow 编排", "Workflow编排"}:
                    continue
                action = _esc(str(entry.get("action") or entry.get("does") or ""))
                tool_esc = _esc(tool)
                if tool_esc and action:
                    items.append(f"<li><strong>{tool_esc}</strong>：{action}</li>")
            elif entry:
                text = str(entry).strip()
                if text.startswith("Workflow"):
                    continue
                items.append(f"<li>{_esc(text)}</li>")
        if items:
            return f'<ul class="demo-tool-list">{"".join(items)}</ul>'
    tools = step.get("tools") or step.get("capabilities") or []
    if not tools:
        return '<p class="wf-record-summary">—</p>'
    items = "".join(f"<li>{_esc(str(tool))}</li>" for tool in tools)
    return f'<ul class="demo-tool-list">{items}</ul>'


def _render_table_preview_block(step: dict[str, Any], exports_dir: Path) -> str:
    if step.get("media"):
        return f'<div class="demo-wf-media demo-wf-media-only">{_render_media_item(step.get("media") or {}, exports_dir, fallback_caption=str(step.get("title") or ""))}</div>'
    return '<p class="wf-record-summary">—</p>'


def _render_media_thumb(step: dict[str, Any], exports_dir: Path) -> str:
    thumb = step.get("mediaThumb") or {}
    if not isinstance(thumb, dict):
        return ""
    media_file = str(thumb.get("file") or "").strip()
    if not media_file:
        return ""
    src_path = _media_src(media_file, exports_dir)
    if not src_path.is_file():
        return ""
    rel = f"media/{media_file}"
    caption_raw = str(thumb.get("caption") or "客户端验收截图")
    caption = _esc(caption_raw)
    zoom_label = _esc(f"放大预览：{caption_raw}")
    return f"""
    <button type="button" class="demo-wf-step-thumb demo-zoom-trigger"
      data-zoom-src="{_esc(rel)}" data-zoom-caption="{caption}"
      aria-label="{zoom_label}">
      <img src="{_esc(rel)}" alt="{caption}" loading="lazy" />
    </button>
    """


def _render_demo_playbook_step(step: dict[str, Any], exports_dir: Path, *, pk_date: str = "") -> str:
    order = int(step.get("order") or 0)
    fw_label = _esc(step.get("frameworkLabel") or "")
    title = _esc(step.get("title") or "")
    thumb_html = _render_media_thumb(step, exports_dir)
    wide_cls = "demo-wf-part demo-wf-part-wide has-thumb" if thumb_html else "demo-wf-part demo-wf-part-wide"
    return f"""
    <article class="demo-wf-step">
      <header class="demo-wf-step-head">
        <span class="demo-wf-step-badge">第 {order} 步</span>
        <div class="demo-wf-step-main">
          <h4 class="demo-wf-step-title">{title}</h4>
          <span class="demo-wf-step-meta">（工作流：{fw_label}）</span>
        </div>
      </header>
      <div class="demo-wf-parts">
        <section class="demo-wf-part">
          <h5>工作流录制</h5>
          {_render_workflow_record_block(step)}
        </section>
        <section class="demo-wf-part">
          <h5>工具支持</h5>
          {_render_tool_support_block(step)}
        </section>
        <section class="{wide_cls}">
          <h5>平台实现</h5>
          <div class="demo-wf-part-wide-row">
            <div class="demo-wf-part-wide-main">{_render_tools_block(step)}</div>
            {thumb_html}
          </div>
        </section>
        <section class="demo-wf-part demo-wf-part-preview">
          <h5>表格预览</h5>
          {_render_table_preview_block(step, exports_dir)}
        </section>
      </div>
    </article>
    """


def _render_demo_playbook_steps(steps: list[dict[str, Any]], exports_dir: Path) -> str:
    if not steps:
        return ""
    items = "".join(
        _render_demo_playbook_step(s, exports_dir)
        for s in sorted(steps, key=lambda x: int(x.get("order") or 0))
    )
    return f'<h4 class="demo-steps-title">工作流分步演示</h4>{items}'


def _parse_labeled_detail_item(text: str) -> tuple[str, str]:
    s = str(text).strip()
    for sep in ("：", ":"):
        if sep in s:
            label, _, body = s.partition(sep)
            label = label.strip()
            body = body.strip()
            if label and body:
                return label, body
    return "", s


def _normalize_intro_point(item: Any) -> dict[str, str]:
    if isinstance(item, dict):
        label = str(item.get("label") or "").strip()
        text = str(item.get("text") or item.get("body") or "").strip()
        foot = str(item.get("foot") or item.get("meta") or "").strip()
        if not label and text:
            label, text = _parse_labeled_detail_item(text)
        return {"label": label, "text": text, "foot": foot}
    raw = str(item).strip()
    label, text = _parse_labeled_detail_item(raw)
    return {"label": label, "text": text or raw, "foot": ""}


def _resolve_intro_points(section: dict[str, Any]) -> list[dict[str, str]]:
    points = section.get("points") or []
    if points:
        return [_normalize_intro_point(p) for p in points if p]
    items = section.get("items") or []
    resolved: list[dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        label = str(item.get("title") or "").strip()
        paragraphs = [
            str(p).strip() for p in (item.get("paragraphs") or []) if str(p).strip()
        ]
        text = paragraphs[0] if paragraphs else ""
        if label and text:
            resolved.append({"label": label, "text": text, "foot": ""})
        elif text:
            resolved.append(_normalize_intro_point(text))
        elif label:
            resolved.append({"label": label, "text": "", "foot": ""})
    return [p for p in resolved if p.get("text") or p.get("label")]


def _highlight_intro_sheets(html_text: str) -> str:
    return re.sub(
        r"(Sheet「[^」]+」)",
        r'<span class="demo-intro-sheet">\1</span>',
        html_text,
    )


def _render_intro_point(point: dict[str, str], *, index: int = 0) -> str:
    label = point.get("label") or ""
    text = point.get("text") or ""
    foot = point.get("foot") or ""
    content = _highlight_intro_sheets(_format_intro_text(text))
    index_html = (
        f'<span class="demo-intro-point-index" aria-hidden="true">{index}</span>'
        if index > 0
        else ""
    )
    tag_html = f'<span class="demo-intro-point-tag">{_esc(label)}</span>' if label else ""
    head_html = ""
    if index_html or tag_html:
        head_html = f'<div class="demo-intro-point-head">{index_html}{tag_html}</div>'
    foot_html = f'<div class="demo-intro-point-foot">{_esc(foot)}</div>' if foot else ""
    return f"""
    <article class="demo-intro-point">
      {head_html}
      <p class="demo-intro-point-body">{content}</p>
      {foot_html}
    </article>
    """


def _render_intro_hub(hub: dict[str, Any]) -> str:
    if not hub:
        return ""
    lead = str(hub.get("lead") or "").strip()
    phases = [p for p in (hub.get("phases") or []) if isinstance(p, dict)]
    metrics = [m for m in (hub.get("metrics") or []) if isinstance(m, dict)]
    if not lead and not phases and not metrics:
        return ""
    lead_html = f'<p class="demo-intro-hub-lead">{_esc(lead)}</p>' if lead else ""
    phase_parts: list[str] = []
    for index, phase in enumerate(phases):
        if index > 0:
            phase_parts.append('<span class="demo-intro-hub-arrow" aria-hidden="true">→</span>')
        label = _esc(str(phase.get("label") or ""))
        hint = _esc(str(phase.get("hint") or ""))
        phase_parts.append(f"""
        <div class="demo-intro-hub-phase">
          <b>{label}</b>
          <span>{hint}</span>
        </div>
        """)
    flow_html = ""
    if phase_parts:
        flow_html = f'<div class="demo-intro-hub-flow">{"".join(phase_parts)}</div>'
    metric_html = ""
    if metrics:
        tiles = "".join(
            f"""<div class="demo-intro-hub-metric">
              <strong>{_esc(str(m.get("value") or ""))}</strong>
              <span>{_esc(str(m.get("label") or ""))}</span>
            </div>"""
            for m in metrics
        )
        metric_html = f'<div class="demo-intro-hub-metrics">{tiles}</div>'
    return f"""
    <section class="demo-intro-hub" aria-label="活动概览">
      {lead_html}
      {flow_html}
      {metric_html}
    </section>
    """


def _render_intro_section(section: dict[str, Any], exports_dir: Path) -> str:
    _ = exports_dir
    title = str(section.get("title") or "").strip()
    points = _resolve_intro_points(section)
    if not title or not points:
        return ""
    variant = str(section.get("variant") or "default").strip()
    section_cls = "demo-intro-section"
    if variant in {"rules", "pain"}:
        section_cls += f" demo-intro-section-{variant}"
    summary = str(section.get("summary") or "").strip()
    summary_html = (
        f'<p class="demo-intro-section-lead">{_esc(summary)}</p>' if summary else ""
    )
    points_html = "".join(
        _render_intro_point(p, index=i) for i, p in enumerate(points, 1)
    )
    return f"""
    <section class="{section_cls}">
      <header class="demo-intro-section-head">
        <h4>{_esc(title)}</h4>
        {summary_html}
      </header>
      <div class="demo-intro-points">{points_html}</div>
    </section>
    """


def _render_intro_sections(
    sections: list[dict[str, Any]],
    exports_dir: Path,
    *,
    hub: dict[str, Any] | None = None,
) -> str:
    blocks = [
        _render_intro_section(section, exports_dir)
        for section in sections
        if isinstance(section, dict)
    ]
    blocks = [b for b in blocks if b]
    if not blocks:
        return ""
    hub_html = _render_intro_hub(hub or {})
    return f'<div class="demo-detail-grid">{hub_html}{"".join(blocks)}</div>'


def _legacy_intro_sections(item: dict[str, Any]) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    rules = item.get("rules") or []
    pain_points = item.get("painPoints") or []
    if rules:
        sections.append({
            "title": str(item.get("rulesTitle") or "活动规则"),
            "variant": "rules",
            "points": [str(r).strip() for r in rules if str(r).strip()],
        })
    if pain_points:
        sections.append({
            "title": str(item.get("painTitle") or "测试难点"),
            "variant": "pain",
            "points": [str(p).strip() for p in pain_points if str(p).strip()],
        })
    return sections


def _render_demo_workbook_and_detail(
    item: dict[str, Any], *, block_cls: str, exports_dir: Path
) -> tuple[str, str]:
    intro_sections = item.get("introSections") or _legacy_intro_sections(item)
    workbook_html = ""
    detail_html = ""
    if intro_sections:
        detail_html = _render_intro_sections(
            intro_sections,
            exports_dir,
            hub=item.get("introHub") if isinstance(item.get("introHub"), dict) else None,
        )
    return workbook_html, detail_html


def _family_pk_step1_demo_prompt(steps: list[dict[str, Any]], pk_date: str) -> str:
    for step in steps:
        if int(step.get("order") or 0) == 1:
            return family_pk_step_demo_prompt(step, pk_date)
    return f"测试{pk_date}日家族PK，第 1 步"


def _render_lottery_intro_panel(
    item: dict[str, Any],
    *,
    exports_dir: Path,
    steps: list[dict[str, Any]] | None = None,
) -> str:
    demo_steps = steps or item.get("steps") or load_anniversary_egg_demo_steps()
    demo_prompt = _esc(_lottery_step1_demo_prompt(demo_steps, item))
    workbook_html, detail_html = _render_demo_workbook_and_detail(
        item, block_cls="lottery", exports_dir=exports_dir
    )
    return f"""
    <div class="demo-block lottery">
      <div class="demo-title-row">
        <h3 class="demo-title">{_esc(item.get('title'))}</h3>
        <button type="button" class="demo-run-btn" data-prompt="{demo_prompt}">演示</button>
      </div>
      {workbook_html}
      {detail_html}
    </div>
    """


def _lottery_step1_demo_prompt(steps: list[dict[str, Any]], item: dict[str, Any] | None = None) -> str:
    if item:
        custom = str(item.get("demoPrompt") or "").strip()
        if custom:
            return custom
    for step in steps:
        if int(step.get("order") or 0) == 1:
            return anniversary_egg_step_demo_prompt(step)
    return "测试3周年砸金蛋，第 1 步"


def _render_lottery_step_subtabs(item: dict[str, Any], exports_dir: Path) -> str:
    steps = item.get("steps") or load_anniversary_egg_demo_steps()
    if not steps:
        return _render_lottery_intro_panel(item, exports_dir=exports_dir, steps=[])
    nav_links = [
        '<a href="#lottery-intro" class="sub-tab-link active" data-sub-tab="intro">活动介绍</a>'
    ]
    panels = ['<div class="sub-tab-panel active" data-sub-tab="intro">']
    panels.append(_render_lottery_intro_panel(item, exports_dir=exports_dir, steps=steps))
    panels.append("</div>")
    for step in sorted(steps, key=lambda x: int(x.get("order") or 0)):
        order = int(step.get("order") or 0)
        if order <= 0:
            continue
        step_title = _esc(_demo_step_tab_label(step))
        nav_links.append(
            f'<a href="#lottery-step-{order}" class="sub-tab-link" '
            f'data-sub-tab="step-{order}">{step_title}</a>'
        )
        panels.append(
            f'<div class="sub-tab-panel" data-sub-tab="step-{order}">'
            f'{_render_demo_playbook_step(step, exports_dir)}'
            f"</div>"
        )
    nav_html = "".join(nav_links)
    panels_html = "".join(panels)
    return f"""
    <div class="sub-tabs" data-sub-tabs>
      <div class="sub-tab-bar">
        <nav class="nav sub-tab-nav">{nav_html}</nav>
      </div>
      {panels_html}
    </div>
    """


def _render_family_pk_intro_panel(
    item: dict[str, Any],
    *,
    pk_date: str,
    exports_dir: Path,
    steps: list[dict[str, Any]] | None = None,
) -> str:
    demo_steps = steps or item.get("steps") or load_family_pk_demo_steps()
    demo_prompt = _esc(_family_pk_step1_demo_prompt(demo_steps, pk_date))
    workbook_html, detail_html = _render_demo_workbook_and_detail(
        item, block_cls="ranking", exports_dir=exports_dir
    )
    return f"""
    <div class="demo-block ranking">
      <div class="demo-title-row">
        <h3 class="demo-title">{_esc(item.get('title'))}</h3>
        <button type="button" class="demo-run-btn" data-prompt="{demo_prompt}">演示</button>
      </div>
      {workbook_html}
      {detail_html}
    </div>
    """


def _render_family_pk_step_subtabs(item: dict[str, Any], exports_dir: Path, *, pk_date: str) -> str:
    steps = item.get("steps") or load_family_pk_demo_steps()
    if not steps:
        return _render_family_pk_intro_panel(item, pk_date=pk_date, exports_dir=exports_dir, steps=[])
    nav_links = [
        '<a href="#family-pk-intro" class="sub-tab-link active" data-sub-tab="intro">活动介绍</a>'
    ]
    panels = ['<div class="sub-tab-panel active" data-sub-tab="intro">']
    panels.append(_render_family_pk_intro_panel(item, pk_date=pk_date, exports_dir=exports_dir, steps=steps))
    panels.append("</div>")
    for step in sorted(steps, key=lambda x: int(x.get("order") or 0)):
        order = int(step.get("order") or 0)
        if order <= 0:
            continue
        step_title = _esc(_demo_step_tab_label(step))
        nav_links.append(
            f'<a href="#family-pk-step-{order}" class="sub-tab-link" '
            f'data-sub-tab="step-{order}">{step_title}</a>'
        )
        panels.append(
            f'<div class="sub-tab-panel" data-sub-tab="step-{order}">'
            f'{_render_demo_playbook_step(step, exports_dir, pk_date=pk_date)}'
            f"</div>"
        )
    nav_html = "".join(nav_links)
    panels_html = "".join(panels)
    return f"""
    <div class="sub-tabs" data-sub-tabs>
      <div class="sub-tab-bar">
        <nav class="nav sub-tab-nav">{nav_html}</nav>
      </div>
      {panels_html}
    </div>
    """


def _render_demo_block(item: dict[str, Any], *, block_cls: str, exports_dir: Path, pk_date: str = "") -> str:
    if not item:
        return ""
    if block_cls == "ranking":
        return _render_family_pk_step_subtabs(item, exports_dir, pk_date=pk_date or "2026-07-12")
    if block_cls == "lottery":
        return _render_lottery_step_subtabs(item, exports_dir)
    workbook_html, detail_html = _render_demo_workbook_and_detail(
        item, block_cls=block_cls, exports_dir=exports_dir
    )
    steps_html = _render_demo_playbook_steps(item.get("steps") or [], exports_dir)
    return f"""
    <div class="demo-block {_esc(block_cls)}">
      <h3 class="demo-title">{_esc(item.get('title'))}</h3>
      {workbook_html}
      {detail_html}
      {steps_html}
    </div>
    """


def _render_ranking_demo_tab(section: dict[str, Any], exports_dir: Path) -> str:
    if not section:
        return ""
    ranking_item = section.get("ranking") or {}
    pk_date = str(ranking_item.get("pkDate") or "2026-07-12").strip()
    ranking = _render_demo_block(
        ranking_item, block_cls="ranking", exports_dir=exports_dir, pk_date=pk_date
    )
    if not ranking:
        return ""
    return f"""
    <section class="section section-flush">
      {ranking}
    </section>
    """


def _render_lottery_demo_tab(section: dict[str, Any], exports_dir: Path) -> str:
    if not section:
        return ""
    lottery_item = section.get("lottery") or {}
    lottery = _render_demo_block(lottery_item, block_cls="lottery", exports_dir=exports_dir)
    if not lottery:
        return ""
    return f"""
    <section class="section section-flush">
      {lottery}
    </section>
    """


def _render_demos_section(section: dict[str, Any], exports_dir: Path) -> str:
    if not section:
        return ""
    return _render_ranking_demo_tab(section, exports_dir) + _render_lottery_demo_tab(section, exports_dir)


def _render_summary_section(section: dict[str, Any]) -> str:
    if not section:
        return ""
    points = "".join(f"<li>{_esc(p)}</li>" for p in (section.get("points") or []))
    return f"""
    <section class="section">
      {_render_section_intro(section.get("lead"))}
      <ul class="summary-list summary-cards">{points}</ul>
    </section>
    """


def _render_demo_steps(steps: list[dict[str, Any]], exports_dir: Path, *, detailed: bool = False) -> str:
    parts: list[str] = []
    for step in sorted(steps, key=lambda s: int(s.get("order") or 0)):
        order = int(step.get("order") or 0)
        reverse = order % 2 == 1
        cls = "demo-step reverse" if reverse else "demo-step"
        meta_html = ""
        if detailed:
            wf = step.get("workflowId")
            sheet = step.get("sheet")
            if wf or sheet:
                meta_html = f'<p class="step-meta">{_esc(wf or "")}{" · " if wf and sheet else ""}{_esc(sheet or "")}</p>'
        parts.append(
            f"""
            <article class="{cls}">
              <div class="demo-text">
                <span class="step-tag">Step {order}</span>
                <h3>{_esc(step.get('title'))}</h3>
                <p>{_esc(step.get('description'))}</p>
                {meta_html}
              </div>
              <div class="demo-media">{_render_media_block(step, exports_dir)}</div>
            </article>
            """
        )
    return "".join(parts)


def _render_playbook_table(playbook: dict[str, Any], *, skip_orders: set[int] | None = None) -> str:
    skip = skip_orders or {0}
    rows = ""
    for step in sorted(playbook.get("steps") or [], key=lambda s: int(s.get("order") or 0)):
        order = int(step.get("order") or 0)
        if order in skip:
            continue
        rows += (
            f"<tr><td>{order}</td><td>{_esc(step.get('workflowId'))}</td>"
            f"<td>{_esc(step.get('sheet'))}</td><td>{_esc(step.get('note'))}</td></tr>"
        )
    if not rows:
        return ""
    return f"""
    <table>
      <thead><tr><th>步骤</th><th>工作流 ID</th><th>产出 Sheet</th><th>说明</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
    """


def _render_ranking_taxonomy(taxonomy: dict[str, Any]) -> str:
    if not taxonomy:
        return ""

    pain_points = taxonomy.get("painPoints") or []
    if not pain_points:
        return ""

    pain_items = "".join(f"<li>{_esc(p)}</li>" for p in pain_points)

    return f"""
    <div class="taxonomy-block">
      <h3>{_esc(taxonomy.get('painTitle') or '测试难点')}</h3>
      <ul class="notes-list">{pain_items}</ul>
    </div>
    """


def _render_ranking_workflow_section(
    section: dict[str, Any],
    playbook: dict[str, Any],
    exports_dir: Path,
) -> str:
    if not section:
        return ""

    status = str(section.get("status") or "")
    status_cls = "shipped" if "落地" in status and "建设" not in status else "building"
    sheets = " · ".join(_esc(s) for s in (section.get("sheets") or []))
    summary = section.get("summary") or ""
    summary_html = f'<p class="flow-summary"><strong>汇报抽象 · 标准五步：</strong>{_esc(summary)}</p>' if summary else ""
    notes_html = "".join(f"<li>{_esc(n)}</li>" for n in (section.get("notes") or []))
    notes_block = f'<ul class="notes-list">{notes_html}</ul>' if notes_html else ""
    taxonomy_html = _render_ranking_taxonomy(section.get("taxonomy") or {})
    playbook_table = _render_playbook_table(playbook, skip_orders={0})
    steps_html = _render_demo_steps(section.get("steps") or [], exports_dir, detailed=True)

    return f"""
    <section class="section" id="ranking-workflow">
      {_render_section_intro(section.get("lead"))}
      {taxonomy_html}
      <div class="workflow-meta">
        <span>落地案例 · {_esc(section.get('example'))}</span>
        <span>Playbook · {_esc(section.get('playbook'))}</span>
        <span class="status-badge {status_cls}">{_esc(status)}</span>
      </div>
      {summary_html}
      <p class="sheet-row"><strong>钉钉 Sheet（7 张）：</strong>{sheets}</p>
      <h3 style="margin:18px 0 10px;font-size:16px">Playbook 步骤一览（家族 PK）</h3>
      {playbook_table}
      {notes_block}
      <h3 style="margin:22px 0 10px;font-size:16px">分步说明</h3>
      {steps_html}
    </section>
    """


def _render_lottery_workflow_section(section: dict[str, Any], exports_dir: Path) -> str:
    if not section:
        return ""

    status = str(section.get("status") or "")
    status_cls = "shipped" if "落地" in status and "建设" not in status else "building"
    sheets = " · ".join(_esc(s) for s in (section.get("sheets") or []))
    summary = section.get("summary") or ""
    summary_html = f'<p class="flow-summary">{_esc(summary)}</p>' if summary else ""
    steps_html = _render_demo_steps(section.get("steps") or [], exports_dir)

    return f"""
    <section class="section" id="lottery-workflow">
      {_render_section_intro(section.get("lead"))}
      <div class="workflow-meta">
        <span>案例 · {_esc(section.get('example'))}</span>
        <span>Playbook · {_esc(section.get('playbook'))}</span>
        <span class="status-badge {status_cls}">{_esc(status)}</span>
      </div>
      {summary_html}
      <p class="sheet-row"><strong>钉钉 Sheet：</strong>{sheets}</p>
      {steps_html}
    </section>
    """


def _render_activity_type_block(item: dict[str, Any], exports_dir: Path) -> str:
    type_id = str(item.get("id") or "")
    status = str(item.get("status") or "")
    status_cls = "shipped" if "落地" in status and "建设" not in status else "building"
    tags = "".join(f'<span class="tag">{_esc(t)}</span>' for t in (item.get("characteristics") or []))
    sheets = " · ".join(_esc(s) for s in (item.get("sheets") or []))
    summary = item.get("summary") or ""
    summary_html = f'<p class="flow-summary">{_esc(summary)}</p>' if summary else ""
    entry = item.get("entry") or ""
    entry_html = f'<div class="entry-box">{_esc(entry)}</div>' if entry else ""
    steps_html = _render_demo_steps(item.get("steps") or [], exports_dir)

    return f"""
    <div class="type-block {_esc(type_id)}">
      <div class="type-head">
        <div>
          <h3>{_esc(item.get('name'))} · {_esc(item.get('example'))}</h3>
          <p class="type-meta">Playbook · {_esc(item.get('playbook') or '')}</p>
        </div>
        <span class="status-badge {status_cls}">{_esc(status)}</span>
      </div>
      {summary_html}
      <div class="tag-row">{tags}</div>
      <p class="sheet-row"><strong>钉钉 Sheet：</strong>{sheets}</p>
      {entry_html}
      {steps_html}
    </div>
    """


def _render_activity_types_section(section: dict[str, Any], exports_dir: Path) -> str:
    if not section:
        return ""

    compare = section.get("compare") or {}
    headers = compare.get("headers") or []
    head_html = "".join(f"<th>{_esc(h)}</th>" for h in headers)
    body_html = ""
    for row in compare.get("rows") or []:
        if not isinstance(row, list):
            continue
        body_html += "<tr>" + "".join(f"<td>{_esc(c)}</td>" for c in row) + "</tr>"

    compare_html = ""
    if head_html and body_html:
        compare_html = f"""
        <div class="compare-table-wrap">
          <table>
            <thead><tr>{head_html}</tr></thead>
            <tbody>{body_html}</tbody>
          </table>
        </div>
        """

    types_html = "".join(
        _render_activity_type_block(t, exports_dir) for t in (section.get("types") or [])
    )

    return f"""
    <section class="section" id="categories">
      {_render_section_intro(section.get("lead"))}
      {compare_html}
      {types_html}
    </section>
    """


def _render_tab_nav(nav_items: list[dict[str, Any]], *, active_id: str) -> str:
    if not nav_items:
        return ""
    links: list[str] = []
    for item in nav_items:
        tab_id = str(item.get("id") or "").strip()
        if not tab_id:
            continue
        active = " active" if tab_id == active_id else ""
        links.append(
            f'<a href="#{_esc(tab_id)}" class="tab-link{active}" data-tab="{_esc(tab_id)}">'
            f'{_esc(item.get("label"))}</a>'
        )
    return f'<nav class="nav tab-nav">{"".join(links)}</nav>'


def _render_tab_panel(tab_id: str, content: str, *, active: bool = False) -> str:
    cls = "tab-panel active" if active else "tab-panel"
    return f'<div class="{cls}" data-tab="{_esc(tab_id)}" role="tabpanel">{content}</div>'


def _resolve_web_agent_urls(cfg: dict[str, Any]) -> tuple[str, str]:
    local = str(cfg.get("webAgentLocalUrl") or "http://127.0.0.1:18766").strip()
    remote = str(cfg.get("webAgentRemoteUrl") or cfg.get("webAgentUrl") or "").strip()
    return local, remote


def _render_image_lightbox() -> str:
    return """
    <div id="demo-image-lightbox" class="demo-lightbox" hidden aria-hidden="true"
      role="dialog" aria-modal="true" aria-label="图片预览">
      <div class="demo-lightbox-backdrop" data-lightbox-close></div>
      <figure class="demo-lightbox-panel">
        <img src="" alt="" />
        <figcaption class="demo-lightbox-caption"></figcaption>
      </figure>
      <button type="button" class="demo-lightbox-close" data-lightbox-close aria-label="关闭预览">&times;</button>
    </div>
    """


def _showcase_tab_script(
    default_tab: str,
    *,
    web_agent_local_url: str = "",
    web_agent_remote_url: str = "",
) -> str:
    default = _esc(default_tab)
    agent_local = _esc(web_agent_local_url.strip())
    agent_remote = _esc(web_agent_remote_url.strip())
    return f"""
    <script>
    (function () {{
      var WEB_AGENT_LOCAL_URL = "{agent_local}";
      var WEB_AGENT_REMOTE_URL = "{agent_remote}";
      var PROMPT_STORAGE_KEY = "web_agent_pending_prompt";

      function resolveWebAgentBase() {{
        var host = window.location.hostname || "";
        var isLocal = host === "127.0.0.1" || host === "localhost" || host === "";
        if (isLocal && WEB_AGENT_LOCAL_URL) return WEB_AGENT_LOCAL_URL;
        if (WEB_AGENT_REMOTE_URL) return WEB_AGENT_REMOTE_URL;
        if (WEB_AGENT_LOCAL_URL) return WEB_AGENT_LOCAL_URL;
        return window.location.origin;
      }}

      function showDemoToast(message) {{
        var el = document.getElementById("demo-toast");
        if (!el) {{
          el = document.createElement("div");
          el.id = "demo-toast";
          el.className = "demo-toast";
          el.setAttribute("role", "status");
          document.body.appendChild(el);
        }}
        el.textContent = message;
        el.classList.add("show");
        clearTimeout(showDemoToast._timer);
        showDemoToast._timer = setTimeout(function () {{
          el.classList.remove("show");
        }}, 2600);
      }}

      function fillWebAgentInput(text) {{
        if (!text) return;
        if (window.parent !== window) {{
          window.parent.postMessage({{ type: "web-agent-fill-prompt", text: text }}, "*");
          showDemoToast("已填入 Web Agent 输入框");
          return;
        }}
        var agentBase = resolveWebAgentBase().replace(/\\/$/, "");
        var chatUrl = agentBase + "/?prompt=" + encodeURIComponent(text);
        var payload = JSON.stringify({{ text: text, ts: Date.now() }});
        try {{
          localStorage.setItem(PROMPT_STORAGE_KEY, payload);
        }} catch (err) {{}}
        var win = window.open(chatUrl, "web_agent_chat");
        if (win) {{
          try {{ win.focus(); }} catch (err) {{}}
          showDemoToast("已打开 Web Agent 并填入提示语");
          return;
        }}
        showDemoToast("请切换到 Web Agent 标签页查看已填入的提示语");
      }}

      var lightbox = document.getElementById("demo-image-lightbox");
      var lightboxImg = lightbox ? lightbox.querySelector(".demo-lightbox-panel img") : null;
      var lightboxCaption = lightbox ? lightbox.querySelector(".demo-lightbox-caption") : null;

      function openImageLightbox(src, caption, alt) {{
        if (!lightbox || !lightboxImg || !src) return;
        lightboxImg.src = src;
        lightboxImg.alt = alt || caption || "预览图";
        if (lightboxCaption) {{
          lightboxCaption.textContent = caption || "";
          lightboxCaption.hidden = !caption;
        }}
        lightbox.hidden = false;
        lightbox.classList.add("open");
        lightbox.setAttribute("aria-hidden", "false");
        document.body.style.overflow = "hidden";
      }}

      function closeImageLightbox() {{
        if (!lightbox || !lightboxImg) return;
        lightbox.classList.remove("open");
        lightbox.hidden = true;
        lightbox.setAttribute("aria-hidden", "true");
        document.body.style.overflow = "";
        lightboxImg.removeAttribute("src");
      }}

      document.addEventListener("click", function (e) {{
        var zoomBtn = e.target.closest(".demo-zoom-trigger");
        if (zoomBtn) {{
          e.preventDefault();
          var img = zoomBtn.querySelector("img");
          openImageLightbox(
            zoomBtn.getAttribute("data-zoom-src") || "",
            zoomBtn.getAttribute("data-zoom-caption") || "",
            img ? img.getAttribute("alt") || "" : ""
          );
          return;
        }}
        if (e.target.closest("[data-lightbox-close]")) {{
          closeImageLightbox();
          return;
        }}
        var btn = e.target.closest(".demo-run-btn");
        if (!btn) return;
        var prompt = btn.getAttribute("data-prompt") || "";
        if (!prompt) return;
        fillWebAgentInput(prompt);
      }});

      document.addEventListener("keydown", function (e) {{
        if (e.key === "Escape" && lightbox && lightbox.classList.contains("open")) {{
          closeImageLightbox();
        }}
      }});

      function updateStickyOffsets() {{
        var tabBar = document.querySelector(".tab-bar");
        var tabBarH = tabBar ? tabBar.offsetHeight : 0;
        document.documentElement.style.setProperty("--sticky-sub-top", tabBarH + "px");
      }}
      updateStickyOffsets();
      window.addEventListener("resize", updateStickyOffsets);

      var links = document.querySelectorAll(".tab-link");
      var panels = document.querySelectorAll(".tab-panel");
      var known = new Set(Array.from(panels).map(function (p) {{ return p.getAttribute("data-tab"); }}));
      function activate(tabId) {{
        if (tabId === "platform") tabId = "workflows";
        if (tabId === "demos") tabId = "demo-ranking";
        if (!known.has(tabId)) tabId = "{default}";
        panels.forEach(function (p) {{
          p.classList.toggle("active", p.getAttribute("data-tab") === tabId);
        }});
        links.forEach(function (a) {{
          a.classList.toggle("active", a.getAttribute("data-tab") === tabId);
        }});
        updateStickyOffsets();
      }}
      links.forEach(function (a) {{
        a.addEventListener("click", function (e) {{
          e.preventDefault();
          var tabId = a.getAttribute("data-tab");
          activate(tabId);
          history.replaceState(null, "", "#" + tabId);
        }});
      }});
      window.addEventListener("hashchange", function () {{
        activate((location.hash || "#{default}").slice(1));
      }});
      activate((location.hash || "#{default}").slice(1));
      document.querySelectorAll("[data-sub-tabs]").forEach(function (root) {{
        var subLinks = root.querySelectorAll(".sub-tab-link");
        var subPanels = root.querySelectorAll(".sub-tab-panel");
        function activateSub(subId) {{
          if (!subId) subId = "intro";
          subPanels.forEach(function (p) {{
            p.classList.toggle("active", p.getAttribute("data-sub-tab") === subId);
          }});
          subLinks.forEach(function (a) {{
            a.classList.toggle("active", a.getAttribute("data-sub-tab") === subId);
          }});
          updateStickyOffsets();
        }}
        subLinks.forEach(function (a) {{
          a.addEventListener("click", function (e) {{
            e.preventDefault();
            activateSub(a.getAttribute("data-sub-tab"));
          }});
        }});
        activateSub("intro");
      }});
    }})();
    </script>
    """


def render_showcase_html(
    *,
    config: dict[str, Any] | None = None,
    playbook: dict[str, Any] | None = None,
    summaries: list[dict[str, Any]] | None = None,
    exports_dir: Path,
) -> str:
    cfg = config or load_showcase_config()
    _ = playbook, summaries  # 后续章节按需接入
    agent_local, agent_remote = _resolve_web_agent_urls(cfg)

    nav_items = cfg.get("nav") or []
    default_tab = str(nav_items[0].get("id") if nav_items else "background")
    nav_html = _render_tab_nav(nav_items, active_id=default_tab)

    workflows_cfg = cfg.get("workflows") or {}
    demos_cfg = cfg.get("demos") or {}
    tab_contents: dict[str, str] = {
        "background": _render_theory_section(cfg.get("theory") or {}),
        "workflows": _render_workflows_section(workflows_cfg),
        "demo-ranking": _render_ranking_demo_tab(demos_cfg, exports_dir),
        "demo-lottery": _render_lottery_demo_tab(demos_cfg, exports_dir),
        "summary": _render_summary_section(cfg.get("summary") or {}),
    }
    tab_panels: list[str] = []
    for item in nav_items:
        tab_id = str(item.get("id") or "").strip()
        if not tab_id:
            continue
        content = tab_contents.get(tab_id, "")
        if not content:
            continue
        tab_panels.append(_render_tab_panel(tab_id, content, active=tab_id == default_tab))
    tabs_html = f'<div class="tab-panels">{"".join(tab_panels)}</div>'

    title = str(cfg.get("title") or "")
    subtitle = str(cfg.get("subtitle") or "").strip()

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate" />
  <meta http-equiv="Pragma" content="no-cache" />
  <title>{_esc(title)}</title>
  <style>{_showcase_styles()}</style>
</head>
<body>
  <div class="wrap">
    {_render_hero(title, subtitle)}

    <div class="tab-bar">{nav_html}</div>

    {tabs_html}

    <p class="footer">Generated · family_pk_report · {_esc(datetime.now().strftime('%Y-%m-%d %H:%M'))}</p>
  </div>
  {_render_image_lightbox()}
  {_showcase_tab_script(default_tab, web_agent_local_url=agent_local, web_agent_remote_url=agent_remote)}
</body>
</html>
"""
