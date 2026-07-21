"""家族 PK 数据测试 — 向上汇报 HTML 生成。"""

from __future__ import annotations

import html
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from playbook import load_playbook, step_status_key
from showcase import load_showcase_config, render_showcase_html, sync_media_to

REPO_ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = Path(__file__).resolve().parent
EXPORTS_DIR = REPORT_DIR / "exports"
TMP_DIR = REPO_ROOT / ".tmp"
SAMPLE_SUMMARY_PATH = REPORT_DIR / "config" / "sample_summary.json"

OVERALL_META = {
    "通过": ("pass", "总体验收通过", "可进入上线评审"),
    "部分通过": ("warn", "部分通过", "核心流程通过，发钻实发需跟进"),
    "失败": ("fail", "验收失败", "需排查后重跑"),
}


def load_summary(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"invalid summary JSON: {path}")
    return data


def load_sample_summary() -> dict[str, Any]:
    if not SAMPLE_SUMMARY_PATH.is_file():
        raise FileNotFoundError(SAMPLE_SUMMARY_PATH)
    summary = load_summary(SAMPLE_SUMMARY_PATH)
    summary["_sourcePath"] = str(SAMPLE_SUMMARY_PATH)
    summary.setdefault("demo", True)
    return summary


def scan_summaries(tmp_dir: Path | None = None, *, include_demo: bool = True) -> list[dict[str, Any]]:
    base = tmp_dir or TMP_DIR
    items: list[dict[str, Any]] = []
    for path in sorted(base.glob("family_pk_test_result_*.json")):
        try:
            summary = load_summary(path)
            summary["_sourcePath"] = str(path)
            summary["demo"] = False
            items.append(summary)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
    items.sort(key=lambda x: str(x.get("executedAt") or x.get("pkDate") or ""), reverse=True)
    if include_demo and not items:
        items.append(load_sample_summary())
    return items


def _esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def _fmt_int(value: Any) -> str:
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return _esc(value)


def _step_badge(ok: bool | None, fail_count: int = 0) -> tuple[str, str]:
    if ok is True and fail_count == 0:
        return "pass", "通过"
    if ok is False or fail_count > 0:
        return "fail", "未通过"
    return "pending", "待验收"


def _aggregate_mismatches(mismatches: list[dict[str, Any]], limit: int = 12) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    names: dict[str, str] = {}
    for row in mismatches:
        fid = str(row.get("familyId") or "")
        if not fid:
            continue
        counter[fid] += 1
        names[fid] = str(row.get("familyName") or fid)
    rows = []
    for fid, count in counter.most_common(limit):
        rows.append({"familyId": fid, "familyName": names.get(fid, fid), "count": count})
    return rows


def _render_step_cards(summary: dict[str, Any], playbook: dict[str, Any]) -> str:
    blocks: list[str] = []
    for step in sorted(playbook.get("steps") or [], key=lambda s: int(s.get("order") or 0)):
        order = int(step.get("order") or 0)
        if order == 0 or order == 7:
            continue
        key = step_status_key(order)
        payload = summary.get(key) if key else None
        if key == "reward":
            contrib_fail = int(summary.get("contribFail") or 0)
            ok = contrib_fail == 0 and int((payload or {}).get("member_rows") or 0) > 0
            fail = contrib_fail
            total = int((payload or {}).get("member_rows") or 0)
            passed = int(summary.get("contribPass") or 0)
            note = f"成员 {total} · 榜单验收失败 {contrib_fail}"
        elif isinstance(payload, dict):
            ok = bool(payload.get("ok"))
            total = int(payload.get("total") or 0)
            passed = int(payload.get("pass") or 0)
            fail = int(payload.get("fail") or 0)
            note = _esc(payload.get("note") or "")
        else:
            ok, total, passed, fail, note = None, 0, 0, 0, "暂无数据"

        badge_cls, badge_text = _step_badge(ok, fail)
        ops = step.get("operations") or []
        ops_html = "".join(f"<li>{_esc(op)}</li>" for op in ops[:4])
        if len(ops) > 4:
            ops_html += f"<li class='muted'>…共 {len(ops)} 项操作</li>"

        blocks.append(
            f"""
            <article class="step-card {badge_cls}">
              <div class="step-head">
                <span class="step-no">Step {order}</span>
                <span class="badge {badge_cls}">{badge_text}</span>
              </div>
              <h3>{_esc(step.get('sheet') or step.get('note') or '')}</h3>
              <p class="step-note">{_esc(step.get('note') or '')}</p>
              <div class="step-stats">
                <span>样本 {_fmt_int(total)}</span>
                <span class="ok">通过 {_fmt_int(passed)}</span>
                <span class="bad">失败 {_fmt_int(fail)}</span>
              </div>
              <p class="step-extra">{note}</p>
              <details>
                <summary>自动化做了什么</summary>
                <ul>{ops_html}</ul>
              </details>
            </article>
            """
        )
    return "\n".join(blocks)


def _render_mismatch_section(summary: dict[str, Any]) -> str:
    mismatches = summary.get("dispatch", {}).get("mismatches") or []
    if not mismatches:
        return """
        <section class="panel">
          <h2>发钻实发差异</h2>
          <p class="empty ok-text">无不一致记录，应发与实发全部对齐。</p>
        </section>
        """

    grouped = _aggregate_mismatches(mismatches)
    group_rows = "".join(
        f"<tr><td>{_esc(r['familyName'])}</td><td>{_esc(r['familyId'])}</td>"
        f"<td class='bad'>{r['count']}</td></tr>"
        for r in grouped
    )
    detail_rows = "".join(
        f"<tr><td>{_esc(m.get('userId'))}</td><td>{_esc(m.get('familyName'))}</td>"
        f"<td>{_esc(m.get('expected'))}</td><td>{_esc(m.get('delta'))}</td>"
        f"<td class='bad'>{_esc(m.get('status'))}</td></tr>"
        for m in mismatches[:30]
    )
    more = ""
    if len(mismatches) > 30:
        more = f"<p class='muted'>仅展示前 30 条，共 {len(mismatches)} 条不一致，完整明细见钉钉表。</p>"

    return f"""
    <section class="panel">
      <h2>发钻实发差异</h2>
      <div class="grid-2">
        <div>
          <h3>按家族聚合（Top {len(grouped)}）</h3>
          <table>
            <thead><tr><th>家族</th><th>ID</th><th>不一致人数</th></tr></thead>
            <tbody>{group_rows}</tbody>
          </table>
        </div>
        <div>
          <h3>明细抽样</h3>
          <table>
            <thead><tr><th>userId</th><th>家族</th><th>应发</th><th>实发增量</th><th>验收</th></tr></thead>
            <tbody>{detail_rows}</tbody>
          </table>
          {more}
        </div>
      </div>
    </section>
    """


def _base_styles() -> str:
    return """
    :root {
      --bg: #f4f6fb;
      --card: #ffffff;
      --text: #1f2937;
      --muted: #6b7280;
      --line: #e5e7eb;
      --brand: #2563eb;
      --pass: #059669;
      --warn: #d97706;
      --fail: #dc2626;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "PingFang SC",
        "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
      background: linear-gradient(180deg, #eef2ff 0%, var(--bg) 220px);
      color: var(--text);
      line-height: 1.55;
    }
    .wrap { max-width: 1120px; margin: 0 auto; padding: 28px 20px 56px; }
    .hero {
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 28px 28px 22px;
      box-shadow: 0 10px 30px rgba(37, 99, 235, 0.08);
    }
    .hero-top { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; justify-content: space-between; }
    .eyebrow { color: var(--brand); font-size: 13px; font-weight: 700; letter-spacing: .04em; text-transform: uppercase; }
    h1 { margin: 8px 0 6px; font-size: 28px; }
    .subtitle { color: var(--muted); margin: 0; }
    .badge {
      display: inline-flex; align-items: center; padding: 6px 12px; border-radius: 999px;
      font-size: 13px; font-weight: 700;
    }
    .badge.pass { background: #d1fae5; color: var(--pass); }
    .badge.warn { background: #fef3c7; color: var(--warn); }
    .badge.fail { background: #fee2e2; color: var(--fail); }
    .badge.pending { background: #e5e7eb; color: #374151; }
    .kpi-grid {
      display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; margin-top: 22px;
    }
    .kpi {
      background: #f8fafc; border: 1px solid var(--line); border-radius: 12px; padding: 14px 16px;
    }
    .kpi .label { color: var(--muted); font-size: 12px; }
    .kpi .value { font-size: 24px; font-weight: 800; margin-top: 4px; }
    .links { margin-top: 16px; display: flex; flex-wrap: wrap; gap: 10px; }
    .links a {
      color: var(--brand); text-decoration: none; background: #eff6ff; border-radius: 8px;
      padding: 8px 12px; font-size: 13px; font-weight: 600;
    }
    section.panel {
      margin-top: 22px; background: var(--card); border: 1px solid var(--line);
      border-radius: 16px; padding: 22px 24px;
    }
    section.panel h2 { margin: 0 0 14px; font-size: 20px; }
    section.panel h3 { margin: 0 0 10px; font-size: 16px; }
    .steps-grid {
      display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px;
    }
    .step-card {
      border: 1px solid var(--line); border-radius: 12px; padding: 14px; background: #fcfdff;
    }
    .step-card.pass { border-color: #a7f3d0; }
    .step-card.fail { border-color: #fecaca; background: #fffafa; }
    .step-head { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
    .step-no { font-size: 12px; color: var(--muted); font-weight: 700; }
    .step-card h3 { margin: 8px 0 6px; font-size: 15px; }
    .step-note, .step-extra { color: var(--muted); font-size: 13px; margin: 0 0 8px; }
    .step-stats { display: flex; gap: 10px; font-size: 12px; font-weight: 700; }
    .step-stats .ok { color: var(--pass); }
    .step-stats .bad { color: var(--fail); }
    details { margin-top: 8px; font-size: 13px; }
    details summary { cursor: pointer; color: var(--brand); font-weight: 600; }
    details ul { margin: 8px 0 0; padding-left: 18px; color: var(--muted); }
    .grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    th, td { border-bottom: 1px solid var(--line); padding: 8px 6px; text-align: left; }
    th { color: var(--muted); font-weight: 700; }
    .bad { color: var(--fail); font-weight: 700; }
    .ok-text { color: var(--pass); font-weight: 700; }
    .muted { color: var(--muted); font-size: 13px; }
    .capability-list { display: grid; gap: 10px; }
    .cap-item {
      border-left: 4px solid var(--brand); padding: 10px 12px; background: #f8fafc; border-radius: 8px;
    }
    .cap-item strong { display: block; margin-bottom: 4px; }
    .history-table td a { color: var(--brand); font-weight: 600; text-decoration: none; }
    .footer { margin-top: 24px; color: var(--muted); font-size: 12px; text-align: center; }
    @media (max-width: 960px) {
      .kpi-grid, .steps-grid, .grid-2 { grid-template-columns: 1fr; }
    }
    """


def render_report_html(summary: dict[str, Any], playbook: dict[str, Any] | None = None) -> str:
    pb = playbook or load_playbook()
    overall = str(summary.get("overall") or "未知")
    badge_cls, headline, subline = OVERALL_META.get(overall, ("pending", overall, ""))
    is_demo = bool(summary.get("demo"))
    demo_banner = ""
    if is_demo:
        demo_banner = """
        <p class="subtitle" style="margin-top:12px;padding:10px 12px;background:#eff6ff;border-radius:8px;color:#1d4ed8">
          <strong>示例报告</strong> — 数据来自 config/sample_summary.json，用于演示页附录；真实验收请跑完工作流后扫描 .tmp 生成。
        </p>
        """

    families = summary.get("families") or {}
    dispatch = summary.get("dispatch") or {}
    reward = summary.get("reward") or {}
    pk_date = _esc(summary.get("pkDate"))
    rank_date = _esc(summary.get("rankDate"))
    executed_at = _esc(summary.get("executedAt"))
    workbook_url = summary.get("workbookUrl") or ""
    workbook_title = _esc(summary.get("workbookTitle") or f"{pk_date}家族PK数据测试")

    link_html = ""
    if workbook_url:
        link_html = f'<a href="{_esc(workbook_url)}" target="_blank" rel="noopener">钉钉测试表 · {workbook_title}</a>'

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>家族PK数据测试报告 · {pk_date}</title>
  <style>{_base_styles()}</style>
</head>
<body>
  <div class="wrap">
    <header class="hero">
      <div class="hero-top">
        <div>
          <div class="eyebrow">Family PK · Automated Data Test</div>
          <h1>家族 PK 数据测试验收报告</h1>
          <p class="subtitle">PK 日期 {pk_date} · 收礼榜 {rank_date} · 执行于 {executed_at}</p>
        </div>
        <span class="badge {badge_cls}">{_esc(overall)}</span>
      </div>
      <p class="subtitle"><strong>{headline}</strong> — {subline}</p>
      {demo_banner}
      <div class="kpi-grid">
        <div class="kpi"><div class="label">覆盖家族</div><div class="value">{_fmt_int(families.get('families'))}</div></div>
        <div class="kpi"><div class="label">覆盖成员</div><div class="value">{_fmt_int(families.get('members'))}</div></div>
        <div class="kpi"><div class="label">应发钻合计</div><div class="value">{_fmt_int(reward.get('expected_total') or dispatch.get('expected_total'))}</div></div>
        <div class="kpi"><div class="label">实发不一致</div><div class="value bad">{_fmt_int(summary.get('mismatchCount') or dispatch.get('fail'))}</div></div>
      </div>
      <div class="links">{link_html}</div>
    </header>

    <section class="panel">
      <h2>六步自动化验收进度</h2>
      <p class="muted">从 MSE 参数同步到发钻实发对比，全流程由工作流 + MOA + 钉钉表串联，无需人工逐条核对。</p>
      <div class="steps-grid">
        {_render_step_cards(summary, pb)}
      </div>
    </section>

    {_render_mismatch_section(summary)}

    <section class="panel">
      <h2>测试自动化能力说明</h2>
      <p class="muted">面向跨部门同步：本方案将家族 PK 复杂数据链路沉淀为可重复执行的标准流程。</p>
      <div class="capability-list">
        <div class="cap-item">
          <strong>配置驱动</strong>
          MSE `familyPkConfig` 自动同步至钉钉参数表，改参后可 merge 更新并重跑后续步骤。
        </div>
        <div class="cap-item">
          <strong>全量家族覆盖</strong>
          Admin 拉取全量家族与成员，自动过滤非 MENA 族长；单次可覆盖 { _fmt_int(families.get('members')) } 名成员。
        </div>
        <div class="cap-item">
          <strong>MOA 造数 + 验收</strong>
          收礼榜随机造数、匹配重跑、成员 PK 边界纠偏、结算发奖与贡献榜回写，均由 MOA 脚本批量完成。
        </div>
        <div class="cap-item">
          <strong>结构化产出</strong>
          七张 Sheet + JSON 摘要 + 本 HTML 报告，便于测试、开发、产品同一页面对齐结论。
        </div>
      </div>
    </section>

    <p class="footer">Generated by auto-generate-testcase · family_pk_report · { _esc(datetime.now().strftime('%Y-%m-%d %H:%M')) }</p>
  </div>
</body>
</html>
"""


def write_report(summary_path: Path, out_dir: Path | None = None) -> Path:
    summary = load_summary(summary_path)
    playbook = load_playbook()
    html_text = render_report_html(summary, playbook)
    target_dir = out_dir or EXPORTS_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    pk_date = str(summary.get("pkDate") or "unknown")
    out_path = target_dir / f"family_pk_report_{pk_date}.html"
    out_path.write_text(html_text, encoding="utf-8")
    return out_path


def write_report_from_summary(summary: dict[str, Any], out_dir: Path | None = None) -> Path:
    playbook = load_playbook()
    html_text = render_report_html(summary, playbook)
    target_dir = out_dir or EXPORTS_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    pk_date = str(summary.get("pkDate") or "unknown")
    suffix = "_demo" if summary.get("demo") else ""
    out_path = target_dir / f"family_pk_report_{pk_date}{suffix}.html"
    out_path.write_text(html_text, encoding="utf-8")
    return out_path


def write_all_reports(tmp_dir: Path | None = None, out_dir: Path | None = None) -> list[Path]:
    summaries = scan_summaries(tmp_dir)
    paths: list[Path] = []
    for item in summaries:
        if item.get("demo"):
            paths.append(write_report_from_summary(item, out_dir))
            continue
        source = item.get("_sourcePath")
        if not source:
            continue
        paths.append(write_report(Path(source), out_dir))
    return paths


def write_hub(tmp_dir: Path | None = None, out_dir: Path | None = None) -> Path:
    summaries = scan_summaries(tmp_dir)
    playbook = load_playbook()
    config = load_showcase_config()
    target_dir = out_dir or EXPORTS_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    sync_media_to(target_dir)
    for item in summaries:
        if item.get("demo"):
            write_report_from_summary(item, target_dir)
    html_text = render_showcase_html(
        config=config,
        playbook=playbook,
        summaries=summaries,
        exports_dir=target_dir,
    )
    out_path = target_dir / "index.html"
    out_path.write_text(html_text, encoding="utf-8")
    return out_path
