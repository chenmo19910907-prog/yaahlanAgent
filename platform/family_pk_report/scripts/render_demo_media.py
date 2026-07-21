#!/usr/bin/env python3
"""从家族 PK 钉钉表拉取全量 Sheet 数据，生成演示用 SVG 预览图。"""

from __future__ import annotations

import json
import sys
from html import escape
from pathlib import Path
from typing import Any

REPORT_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = REPORT_DIR.parents[1]
GATEWAY_DIR = REPO_ROOT / "platform" / "dingtalk_gateway"
MEDIA_DIR = REPORT_DIR / "media"
SHOWCASE_CONFIG = REPORT_DIR / "config" / "showcase.json"

if str(GATEWAY_DIR) not in sys.path:
    sys.path.insert(0, str(GATEWAY_DIR))

from mse_workbook_utils import fetch_workbook_sheets  # noqa: E402

W_BASE = 960
TOP_BAR_H = 56
PAD_X = 16
TABLE_TOP = TOP_BAR_H + 8
BG = "#ffffff"
HEADER_BAR = "#f8fafc"
HEADER_BG = "#f1f5f9"
ROW_BG = "#ffffff"
ROW_ALT = "#fafbfc"
LINE = "#e2e8f0"
TEXT = "#334155"
MUTED = "#64748b"
PASS = "#059669"
WARN = "#d97706"

FAMILY_PK_SHEETS: list[tuple[str, str, str]] = [
    ("step01-mse-sync.svg", "参数表", "voga-common / familyPkConfig · merge 增量更新"),
    ("step02-family-list.svg", "家族列表", "76 家族 · 436 成员 · MENA 族长过滤"),
    ("step03-rank-tier.svg", "家族PK档位", "收礼榜 2026-07-11 · PK 2026-07-12 · 全量明细"),
    ("step04-match-verify.svg", "匹配验收", "MOA pkList · 38/38 通过 · 全量对战"),
    ("step05-member-pk.svg", "用户发钻测试", "436 成员 · 应发 191,363 钻 · 全量"),
    ("step06-dispatch-verify.svg", "发钻实发验收", "430/436 通过 · 全量查钻对比"),
    ("step07-test-result.svg", "测试结果", "2026-07-12 · 总体验收：部分通过"),
]


def _load_workbook_url() -> str:
    with open(SHOWCASE_CONFIG, encoding="utf-8") as f:
        data = json.load(f)
    ranking = (data.get("demos") or {}).get("ranking") or {}
    url = str(ranking.get("workbookUrl") or "").strip()
    if not url:
        raise RuntimeError(f"showcase.json 未配置 demos.ranking.workbookUrl: {SHOWCASE_CONFIG}")
    return url


def _load_lottery_workbook_url() -> str:
    with open(SHOWCASE_CONFIG, encoding="utf-8") as f:
        data = json.load(f)
    lottery = (data.get("demos") or {}).get("lottery") or {}
    url = str(lottery.get("workbookUrl") or "").strip()
    if not url:
        raise RuntimeError(f"showcase.json 未配置 demos.lottery.workbookUrl: {SHOWCASE_CONFIG}")
    return url


def _cell_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return f"{value:.6g}"
    return str(value).strip()


def _trim_row(row: list[Any]) -> list[str]:
    cells = [_cell_str(c) for c in row]
    while cells and cells[-1] == "":
        cells.pop()
    return cells


def _normalize_rows(raw_rows: list[list[Any]]) -> list[list[str]]:
    rows = [_trim_row(row) for row in raw_rows]
    return [row for row in rows if any(cell for cell in row)]


def _is_header_row(row: list[str]) -> bool:
    if not row:
        return False
    head = row[0]
    return head in {
        "区块",
        "PK日期",
        "MOA序",
        "家族ID",
        "步骤",
        "userId",
        "成员userId",
        "配置项",
        "验收项",
        "序号",
        "名称",
        "参数/项",
        "项",
        "砸蛋账号",
    }


def _is_meta_row(row: list[str]) -> bool:
    if not row:
        return False
    head = row[0]
    return head in {"验收摘要", "测算摘要", "测试摘要", "MOA来源", "规则说明", "发钻不一致明细"}


def _compute_col_widths(rows: list[list[str]]) -> list[int]:
    col_count = max((len(row) for row in rows), default=0)
    usable = W_BASE - PAD_X * 2
    if col_count <= 0:
        return []
    base = max(42, usable // col_count)
    widths = [base] * col_count
    widths[-1] += usable - base * col_count
    return widths


def _header(title: str, subtitle: str, width: int) -> str:
    sub = (
        f'<text x="{PAD_X}" y="44" fill="{MUTED}" font-size="12" font-family="system-ui">{escape(subtitle)}</text>'
        if subtitle
        else ""
    )
    return f"""
    <rect width="{width}" height="{TOP_BAR_H}" fill="{HEADER_BAR}"/>
    <line x1="0" y1="{TOP_BAR_H}" x2="{width}" y2="{TOP_BAR_H}" stroke="{LINE}"/>
    <text x="{PAD_X}" y="28" fill="{TEXT}" font-size="15" font-weight="700" font-family="system-ui">{escape(title)}</text>
    {sub}
    """


def _table(rows: list[list[str]], *, x: int = PAD_X, y: int = TABLE_TOP, col_widths: list[int]) -> tuple[str, int]:
    if not rows:
        return "", y
    parts: list[str] = []
    cy = y
    table_w = sum(col_widths)
    parts.append(
        f'<rect x="{x}" y="{cy}" width="{table_w}" height="0" fill="none" stroke="{LINE}" stroke-width="0"/>'
    )
    for ri, row in enumerate(rows):
        padded = row + [""] * (len(col_widths) - len(row))
        is_header = _is_header_row(padded)
        is_meta = _is_meta_row(padded)
        row_h = 28 if is_header else 26 if is_meta else 24
        if is_header:
            fill = HEADER_BG
        elif is_meta:
            fill = "#f8fafc"
        else:
            fill = ROW_BG if ri % 2 else ROW_ALT
        parts.append(f'<rect x="{x}" y="{cy}" width="{table_w}" height="{row_h}" fill="{fill}"/>')
        parts.append(
            f'<line x1="{x}" y1="{cy + row_h}" x2="{x + table_w}" y2="{cy + row_h}" stroke="{LINE}"/>'
        )
        cx = x
        for ci, cell in enumerate(padded[: len(col_widths)]):
            col_w = col_widths[ci]
            parts.append(
                f'<line x1="{cx}" y1="{cy}" x2="{cx}" y2="{cy + row_h}" stroke="{LINE}"/>'
            )
            if ci == len(col_widths) - 1:
                parts.append(
                    f'<line x1="{cx + col_w}" y1="{cy}" x2="{cx + col_w}" y2="{cy + row_h}" stroke="{LINE}"/>'
                )
            weight = ' font-weight="600"' if is_header else ""
            color = MUTED if is_header or is_meta else TEXT
            if cell == "通过":
                color = PASS
            elif cell in {"不一致", "查钻失败", "部分通过", "未通过"}:
                color = WARN
            elif cell.startswith("失败"):
                color = WARN
            clip_id = f"clip_{ri}_{ci}"
            parts.append(
                f'<clipPath id="{clip_id}"><rect x="{cx + 1}" y="{cy + 1}" '
                f'width="{col_w - 2}" height="{row_h - 2}"/></clipPath>'
            )
            parts.append(
                f'<text clip-path="url(#{clip_id})" x="{cx + 8}" y="{cy + 16}" fill="{color}" '
                f'font-size="11"{weight} font-family="system-ui, -apple-system, sans-serif">'
                f"{escape(cell)}</text>"
            )
            cx += col_w
        cy += row_h
    parts.append(
        f'<rect x="{x}" y="{y}" width="{table_w}" height="{cy - y}" fill="none" stroke="{LINE}"/>'
    )
    return "\n".join(parts), cy


def _badge(text: str, *, x: int, y: int, width: int, tone: str = "brand") -> str:
    colors = {"pass": PASS, "warn": WARN, "brand": "#2563eb"}
    c = colors.get(tone, colors["brand"])
    badge_w = min(width - PAD_X * 2, max(140, len(text) * 11 + 20))
    return (
        f'<text x="{x}" y="{y + 14}" fill="{c}" font-size="11" font-weight="600" '
        f'font-family="system-ui">{escape(text)}</text>'
    )


def sheet_to_svg(sheet_name: str, subtitle: str, rows: list[list[str]]) -> str:
    if not rows:
        raise RuntimeError(f"Sheet「{sheet_name}」无数据")
    col_widths = _compute_col_widths(rows)
    width = W_BASE
    title = f"{sheet_name} · 全量 {len(rows)} 行"
    body = _header(title, subtitle, width)
    table_html, bottom = _table(rows, col_widths=col_widths)
    body += table_html
    footer_y = bottom + 10
    body += (
        f'<text x="{PAD_X}" y="{footer_y + 14}" fill="{MUTED}" font-size="11" '
        f'font-family="system-ui">超出列宽的内容已截断 · 可上下左右滑动 · 与钉钉表一致</text>'
    )
    height = footer_y + 28
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}">
<rect width="{width}" height="{height}" fill="{BG}"/>
{body}
</svg>
"""


def render_family_pk_media(workbook_url: str) -> dict[str, str]:
    sheets = fetch_workbook_sheets(workbook_url)
    output: dict[str, str] = {}
    for filename, sheet_name, subtitle in FAMILY_PK_SHEETS:
        raw = sheets.get(sheet_name)
        if not raw:
            raise RuntimeError(f"钉钉表缺少 Sheet「{sheet_name}」")
        rows = _normalize_rows(raw)
        output[filename] = sheet_to_svg(sheet_name, subtitle, rows)
        print(f"rendered {filename}: {sheet_name} ({len(rows)} rows)")
    return output


def _filter_columns(rows: list[list[str]], columns: list[str] | None) -> list[list[str]]:
    if not columns or not rows:
        return rows
    header_idx = 0
    for i, row in enumerate(rows):
        if row and row[0] == columns[0]:
            header_idx = i
            break
    header = rows[header_idx]
    indices: list[int] = []
    picked_cols: list[str] = []
    for col in columns:
        if col in header:
            indices.append(header.index(col))
            picked_cols.append(col)
    if not indices:
        return rows
    out: list[list[str]] = []
    for i, row in enumerate(rows):
        if i < header_idx:
            continue
        if i == header_idx:
            out.append(picked_cols)
            continue
        out.append([row[j] if j < len(row) else "" for j in indices])
    return out


def _build_lottery_test_result_rows(smash_rows: list[list[str]]) -> list[list[str]]:
    header_idx = 0
    for i, row in enumerate(smash_rows):
        if row and row[0] == "序号":
            header_idx = i
            break
    header = smash_rows[header_idx]
    verdict_idx = header.index("验收结论") if "验收结论" in header else -1
    data_rows = smash_rows[header_idx + 1 :]
    total = len(data_rows)
    passed = 0
    failed = 0
    fail_samples: list[str] = []
    for row in data_rows:
        verdict = row[verdict_idx] if verdict_idx >= 0 and verdict_idx < len(row) else ""
        if verdict == "通过":
            passed += 1
        elif verdict:
            failed += 1
            if len(fail_samples) < 3:
                fail_samples.append(verdict.replace("失败：", ""))
    overall = "通过" if failed == 0 and total else "部分通过" if passed else "未通过"
    rows: list[list[str]] = [
        ["步骤", "样本", "通过", "失败", "结论"],
        ["批量砸蛋与到账验收", str(total), str(passed), str(failed), overall],
    ]
    if fail_samples:
        rows.append(["不一致摘要", "；".join(fail_samples), "", "", ""])
    rows.append(["数据来源", "Sheet「砸金蛋测试记录」", "", "", ""])
    return rows


LOTTERY_SHEETS: list[tuple[str, str, str, list[str] | None]] = [
    (
        "lottery-step01-mse-config.svg",
        "金蛋活动配置",
        "MSE activityConfig.Year3Anniversary · 全量参数",
        None,
    ),
    (
        "lottery-step02-chances.svg",
        "砸金蛋测试记录",
        "账号获次与砸蛋次数 · 全量记录",
        ["序号", "砸蛋账号", "砸蛋房间", "获次实得", "本次砸蛋次数", "记录写入时间"],
    ),
    (
        "lottery-step03-batch-smash.svg",
        "砸金蛋测试记录",
        "三维度砸蛋计数 · 全量记录",
        [
            "序号",
            "砸蛋账号",
            "砸蛋房间",
            "本次砸蛋次数",
            "房间内砸蛋次数",
            "用户砸蛋次数",
            "平台砸蛋次数",
            "记录写入时间",
        ],
    ),
    (
        "lottery-step04-pool-verify.svg",
        "砸金蛋测试记录",
        "金蛋等级与奖池奖励 · 全量记录",
        ["序号", "砸蛋账号", "本次砸蛋次数", "砸蛋时金蛋等级", "档次奖励", "神秘奖励", "验收结论"],
    ),
    (
        "lottery-step05-reward-verify.svg",
        "砸金蛋测试记录",
        "应得 vs 实际到账 · 全量记录",
        ["序号", "砸蛋账号", "档次奖励", "神秘奖励", "实际到账", "验收结论"],
    ),
]


def render_lottery_media(workbook_url: str) -> dict[str, str]:
    sheets = fetch_workbook_sheets(workbook_url)
    output: dict[str, str] = {}
    smash_rows: list[list[str]] | None = None
    for filename, sheet_name, subtitle, columns in LOTTERY_SHEETS:
        raw = sheets.get(sheet_name)
        if not raw:
            raise RuntimeError(f"钉钉表缺少 Sheet「{sheet_name}」")
        rows = _normalize_rows(raw)
        if sheet_name == "砸金蛋测试记录":
            smash_rows = rows
        if columns:
            rows = _filter_columns(rows, columns)
        output[filename] = sheet_to_svg(sheet_name, subtitle, rows)
        print(f"rendered {filename}: {sheet_name} ({len(rows)} rows)")
    if not smash_rows:
        raise RuntimeError("未读取到 Sheet「砸金蛋测试记录」")
    summary_rows = _build_lottery_test_result_rows(smash_rows)
    sample_count = summary_rows[1][1] if len(summary_rows) > 1 else "0"
    output["lottery-step06-test-result.svg"] = sheet_to_svg(
        "测试结果",
        f"由砸金蛋测试记录汇总 · {sample_count} 条样本",
        summary_rows,
    )
    print(f"rendered lottery-step06-test-result.svg: 测试结果 ({len(summary_rows)} rows)")
    return output


def main() -> int:
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    family_pk = render_family_pk_media(_load_workbook_url())
    for name, content in family_pk.items():
        path = MEDIA_DIR / name
        path.write_text(content, encoding="utf-8")
        print(f"wrote {path}")
    lottery = render_lottery_media(_load_lottery_workbook_url())
    for name, content in lottery.items():
        path = MEDIA_DIR / name
        path.write_text(content, encoding="utf-8")
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
