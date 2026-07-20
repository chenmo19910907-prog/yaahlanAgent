"""家族 PK 向上汇报 — 三块式 Showcase 页（背景 / 演示 / 原理）。"""

from __future__ import annotations

import html
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from playbook import load_playbook

REPORT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = REPORT_DIR / "config" / "showcase.json"
MEDIA_DIR = REPORT_DIR / "media"


def load_showcase_config() -> dict[str, Any]:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"invalid showcase config: {CONFIG_PATH}")
    return data


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


def _media_src(media_file: str, exports_dir: Path) -> Path:
    return exports_dir / "media" / media_file


def _render_media_block(step: dict[str, Any], exports_dir: Path) -> str:
    media = step.get("media") or {}
    media_type = str(media.get("type") or "image").lower()
    media_file = str(media.get("file") or "").strip()
    caption = _esc(media.get("caption") or step.get("title") or "")

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


def _showcase_styles() -> str:
    return """
    :root {
      --bg: #f4f6fb;
      --card: #ffffff;
      --text: #1f2937;
      --muted: #6b7280;
      --line: #e5e7eb;
      --brand: #2563eb;
      --brand-soft: #eff6ff;
      --pass: #059669;
    }
    * { box-sizing: border-box; }
    html { scroll-behavior: smooth; }
    body {
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "PingFang SC",
        "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.6;
    }
    .topbar {
      position: sticky; top: 0; z-index: 20;
      backdrop-filter: blur(10px);
      background: rgba(255,255,255,.92);
      border-bottom: 1px solid var(--line);
    }
    .topbar-inner {
      max-width: 1120px; margin: 0 auto; padding: 10px 20px;
      display: flex; flex-wrap: wrap; gap: 10px; align-items: center; justify-content: space-between;
    }
    .brand-mini { font-weight: 800; color: var(--brand); font-size: 14px; }
    .nav { display: flex; gap: 8px; flex-wrap: wrap; }
    .nav a {
      text-decoration: none; color: var(--muted); font-size: 13px; font-weight: 700;
      padding: 6px 12px; border-radius: 999px;
    }
    .nav a:hover { background: var(--brand-soft); color: var(--brand); }
    .wrap { max-width: 1120px; margin: 0 auto; padding: 24px 20px 64px; }
    .hero {
      background: linear-gradient(135deg, #1d4ed8 0%, #2563eb 45%, #3b82f6 100%);
      color: #fff; border-radius: 20px; padding: 36px 32px; margin-bottom: 28px;
      box-shadow: 0 20px 40px rgba(37, 99, 235, .25);
    }
    .hero .eyebrow { opacity: .85; font-size: 12px; letter-spacing: .08em; text-transform: uppercase; font-weight: 700; }
    .hero h1 { margin: 10px 0 8px; font-size: 32px; line-height: 1.2; }
    .hero p { margin: 0; opacity: .92; max-width: 760px; }
    .section {
      background: var(--card); border: 1px solid var(--line); border-radius: 18px;
      padding: 28px 28px 24px; margin-bottom: 24px;
    }
    .section-head { margin-bottom: 18px; }
    .section-head h2 { margin: 0 0 8px; font-size: 24px; }
    .section-head p { margin: 0; color: var(--muted); }
    .metric-grid {
      display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-top: 18px;
    }
    .metric {
      background: #f8fafc; border: 1px solid var(--line); border-radius: 12px; padding: 14px;
    }
    .metric .label { font-size: 12px; color: var(--muted); }
    .metric .value { font-size: 22px; font-weight: 800; margin-top: 4px; color: var(--brand); }
    .cols-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
    .list-card {
      background: #f8fafc; border-radius: 12px; padding: 16px 18px; border: 1px solid var(--line);
    }
    .list-card h3 { margin: 0 0 10px; font-size: 15px; }
    .list-card ul { margin: 0; padding-left: 18px; color: var(--muted); font-size: 14px; }
    .list-card li + li { margin-top: 6px; }
    .demo-step {
      display: grid; grid-template-columns: 1fr 1.1fr; gap: 20px; align-items: start;
      padding: 18px 0; border-bottom: 1px dashed var(--line);
    }
    .demo-step:last-child { border-bottom: none; padding-bottom: 0; }
    .demo-step.reverse { grid-template-columns: 1.1fr 1fr; }
    .demo-step.reverse .demo-text { order: 2; }
    .demo-step.reverse .demo-media { order: 1; }
    .step-tag {
      display: inline-block; background: var(--brand-soft); color: var(--brand);
      font-size: 12px; font-weight: 800; padding: 4px 10px; border-radius: 999px; margin-bottom: 8px;
    }
    .demo-text h3 { margin: 0 0 8px; font-size: 18px; }
    .demo-text p { margin: 0; color: var(--muted); font-size: 14px; }
    .media-box {
      border: 1px solid var(--line); border-radius: 14px; overflow: hidden; background: #0f172a;
    }
    .media-box img, .media-box video { display: block; width: 100%; max-height: 360px; object-fit: contain; background: #0f172a; }
    .media-caption { margin: 0; padding: 10px 12px; font-size: 12px; color: #cbd5e1; background: #111827; }
    .media-box.placeholder { background: #f1f5f9; min-height: 220px; display: flex; flex-direction: column; }
    .ph-inner {
      flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center;
      gap: 8px; padding: 24px; text-align: center; color: var(--muted); font-size: 13px;
    }
    .ph-inner code { background: #e2e8f0; padding: 2px 6px; border-radius: 6px; font-size: 12px; color: #334155; }
    .arch-layers { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 16px; }
    .arch-layer {
      border: 1px solid var(--line); border-radius: 12px; padding: 14px; background: #f8fafc;
    }
    .arch-layer h4 { margin: 0 0 8px; font-size: 14px; color: var(--brand); }
    .arch-layer ul { margin: 0; padding-left: 16px; font-size: 13px; color: var(--muted); }
    .flow-bar {
      background: #0f172a; color: #e2e8f0; border-radius: 10px; padding: 12px 14px;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; overflow-x: auto;
    }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    th, td { border-bottom: 1px solid var(--line); padding: 10px 8px; text-align: left; vertical-align: top; }
    th { color: var(--muted); font-weight: 700; }
    .platform-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; }
    .plat-card {
      border-left: 4px solid var(--brand); background: #f8fafc; border-radius: 10px; padding: 12px 14px;
    }
    .plat-card strong { display: block; margin-bottom: 4px; }
    .plat-card span { color: var(--muted); font-size: 13px; }
    .plat-card code { display: block; margin-top: 8px; font-size: 11px; color: #334155; word-break: break-all; }
    .principle-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; }
    .principle { border: 1px solid var(--line); border-radius: 12px; padding: 14px; }
    .principle strong { display: block; margin-bottom: 6px; }
    .principle p { margin: 0; color: var(--muted); font-size: 13px; }
    .appendix { margin-top: 8px; }
    .appendix a { color: var(--brand); font-weight: 700; text-decoration: none; }
    .badge { display: inline-block; padding: 4px 10px; border-radius: 999px; font-size: 12px; font-weight: 700; }
    .badge.pass { background: #d1fae5; color: var(--pass); }
    .badge.warn { background: #fef3c7; color: #d97706; }
    .badge.fail { background: #fee2e2; color: #dc2626; }
    .footer { text-align: center; color: var(--muted); font-size: 12px; margin-top: 8px; }
    @media (max-width: 960px) {
      .metric-grid, .cols-2, .demo-step, .demo-step.reverse, .arch-layers, .platform-grid, .principle-grid {
        grid-template-columns: 1fr;
      }
      .demo-step.reverse .demo-text, .demo-step.reverse .demo-media { order: unset; }
    }
    """


def render_showcase_html(
    *,
    config: dict[str, Any] | None = None,
    playbook: dict[str, Any] | None = None,
    summaries: list[dict[str, Any]] | None = None,
    exports_dir: Path,
) -> str:
    cfg = config or load_showcase_config()
    pb = playbook or load_playbook()
    runs = summaries or []

    nav_links = "".join(
        f'<a href="#{ _esc(item.get("id")) }">{ _esc(item.get("label")) }</a>'
        for item in (cfg.get("nav") or [])
    )

    bg = cfg.get("background") or {}
    metrics = "".join(
        f'<div class="metric"><div class="label">{_esc(m.get("label"))}</div>'
        f'<div class="value">{_esc(m.get("value"))}</div></div>'
        for m in (bg.get("metrics") or [])
    )
    pain = "".join(f"<li>{_esc(x)}</li>" for x in (bg.get("painPoints") or []))
    goals = "".join(f"<li>{_esc(x)}</li>" for x in (bg.get("goals") or []))

    demo = cfg.get("demo") or {}
    demo_steps_html: list[str] = []
    for step in sorted(demo.get("steps") or [], key=lambda s: int(s.get("order") or 0)):
        order = int(step.get("order") or 0)
        reverse = order % 2 == 1
        cls = "demo-step reverse" if reverse else "demo-step"
        demo_steps_html.append(
            f"""
            <article class="{cls}">
              <div class="demo-text">
                <span class="step-tag">Step {order}</span>
                <h3>{_esc(step.get('title'))}</h3>
                <p>{_esc(step.get('description'))}</p>
              </div>
              <div class="demo-media">{_render_media_block(step, exports_dir)}</div>
            </article>
            """
        )

    impl = cfg.get("implementation") or {}
    arch = impl.get("architecture") or {}
    layers = "".join(
        f"""<div class="arch-layer"><h4>{_esc(layer.get('name'))}</h4><ul>{
            ''.join(f'<li>{_esc(i)}</li>' for i in (layer.get('items') or []))
        }</ul></div>"""
        for layer in (arch.get("layers") or [])
    )

    platform = impl.get("platform") or {}
    plat_cards = "".join(
        f"""<div class="plat-card">
          <strong>{_esc(m.get('name'))}</strong>
          <span>{_esc(m.get('role'))}</span>
          <code>{_esc(m.get('entry'))}</code>
        </div>"""
        for m in (platform.get("modules") or [])
    )

    principles = "".join(
        f"""<div class="principle"><strong>{_esc(p.get('title'))}</strong><p>{_esc(p.get('body'))}</p></div>"""
        for p in (impl.get("principles") or [])
    )

    step_rows = ""
    for step in sorted(pb.get("steps") or [], key=lambda s: int(s.get("order") or 0)):
        order = int(step.get("order") or 0)
        step_rows += (
            f"<tr><td>{order}</td><td>{_esc(step.get('workflowId'))}</td>"
            f"<td>{_esc(step.get('sheet'))}</td><td>{_esc(step.get('note'))}</td></tr>"
        )

    history_rows = ""
    for item in runs:
        pk_date = _esc(item.get("pkDate"))
        overall = str(item.get("overall") or "")
        badge_cls = {"通过": "pass", "部分通过": "warn", "失败": "fail"}.get(overall, "pending")
        report_name = f"family_pk_report_{item.get('pkDate')}.html"
        history_rows += (
            f"<tr><td>{pk_date}</td><td><span class='badge {badge_cls}'>{_esc(overall)}</span></td>"
            f"<td>{_esc(item.get('executedAt'))}</td>"
            f"<td><a href='{_esc(report_name)}'>数据报告</a></td></tr>"
        )
    appendix = ""
    if history_rows:
        appendix = f"""
        <div class="appendix section">
          <div class="section-head"><h2>附录 · 历次验收数据报告</h2>
          <p>由第七步自动产出的 JSON 生成的 pass/fail 明细页，供需要下钻数据时使用。</p></div>
          <table>
            <thead><tr><th>PK 日期</th><th>结论</th><th>执行时间</th><th>链接</th></tr></thead>
            <tbody>{history_rows}</tbody>
          </table>
        </div>
        """

    catalog_hint = _esc(platform.get("catalogHint") or "python3 platform/open_catalog.py")

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{_esc(cfg.get('title'))}</title>
  <style>{_showcase_styles()}</style>
</head>
<body>
  <header class="topbar">
    <div class="topbar-inner">
      <div class="brand-mini">{_esc(cfg.get('title'))}</div>
      <nav class="nav">{nav_links}</nav>
    </div>
  </header>

  <div class="wrap">
    <header class="hero">
      <div class="eyebrow">Test Automation Showcase</div>
      <h1>{_esc(cfg.get('title'))}</h1>
      <p>{_esc(cfg.get('subtitle'))}</p>
    </header>

    <section class="section" id="background">
      <div class="section-head">
        <h2>{_esc(bg.get('title'))}</h2>
        <p>{_esc(bg.get('lead'))}</p>
      </div>
      <div class="metric-grid">{metrics}</div>
      <div class="cols-2" style="margin-top:16px">
        <div class="list-card">
          <h3>痛点</h3>
          <ul>{pain}</ul>
        </div>
        <div class="list-card">
          <h3>建设目标</h3>
          <ul>{goals}</ul>
        </div>
      </div>
    </section>

    <section class="section" id="demo">
      <div class="section-head">
        <h2>{_esc(demo.get('title'))}</h2>
        <p>{_esc(demo.get('lead'))}</p>
      </div>
      {''.join(demo_steps_html)}
    </section>

    <section class="section" id="implementation">
      <div class="section-head">
        <h2>{_esc(impl.get('title'))}</h2>
        <p>{_esc(impl.get('lead'))}</p>
      </div>

      <h3 style="margin:0 0 10px;font-size:16px">整体架构</h3>
      <div class="arch-layers">{layers}</div>
      <div class="flow-bar">{_esc(arch.get('flow'))}</div>

      <h3 style="margin:22px 0 10px;font-size:16px">标准工作流（Playbook）</h3>
      <table>
        <thead><tr><th>步骤</th><th>工作流 ID</th><th>产出 Sheet</th><th>说明</th></tr></thead>
        <tbody>{step_rows}</tbody>
      </table>

      <h3 style="margin:22px 0 10px;font-size:16px">{_esc(platform.get('title') or '工具平台能力')}</h3>
      <p class="muted" style="color:var(--muted);font-size:13px;margin:0 0 12px">
        本地打开工具台：<code>{catalog_hint}</code>
        · 合并 Admin / MOA / Workflow 等模块能力，支持搜索与一键执行
      </p>
      <div class="platform-grid">{plat_cards}</div>

      <h3 style="margin:22px 0 10px;font-size:16px">设计原则</h3>
      <div class="principle-grid">{principles}</div>
    </section>

    {appendix}

    <p class="footer">Generated · family_pk_report · {_esc(datetime.now().strftime('%Y-%m-%d %H:%M'))}</p>
  </div>
</body>
</html>
"""
