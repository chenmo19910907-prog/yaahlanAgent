"""从版本用例 xlsx 生成内网/外网测试总结 HTML 报告。"""

from __future__ import annotations

import base64
import functools
import html
import os
import platform
import re
import subprocess
import sys
import webbrowser
import zlib
from pathlib import Path


TECH_OPT_SECTION_LABEL = "优化需求"


def _is_tech_opt_need(title: str) -> bool:
    t = title.strip().rstrip("：:").strip()
    return t in (TECH_OPT_SECTION_LABEL, "技术优化需求")


_SUBITEM_PREFIX_RE = re.compile(r"^\s*(?:\d+\s*[)）\.、]|[-*•]\s+)\s*")
# 首表 I2：多行「缺陷链接 / 版本用例链接 / 回归用例链接」+ 未完成&已完成「阻碍～轻微」行（`format_sheet1_i2_text` 生成同结构）
_E2_DEFECT_URL_RE = re.compile(r"缺陷链接\s*[:：]\s*(https?://\S+)")
_E2_VERSION_CASE_URL_RE = re.compile(r"版本用例链接\s*[:：]\s*(https?://\S+)")
_E2_REGRESSION_URL_RE = re.compile(r"回归用例链接\s*[:：]\s*(https?://\S+)")
# 首表 I2：「未完成缺陷」「已完成缺陷」后各级数量（单行内用全角分号 `；` 连接，与 Excel 中格式一致）
_E2_DEFECT_LEVEL_LINE_RE = re.compile(r"(阻碍|严重|一般|轻微)\s*[:：]\s*(\d+)")
_E2_UNFINISHED_BLOCK_RE = re.compile(r"未完成缺陷\s*[:：]?\s*(.*?)(?=已完成缺陷)", re.DOTALL)
_E2_FINISHED_BLOCK_RE = re.compile(r"已完成缺陷\s*[:：]?\s*(.*)", re.DOTALL)
# 钉钉报告：缺陷 / 回归链接写死；版本用例链接由 REPORT_VERSION_CASE_URL 传入表格 URL
DEFAULT_DEFECT_TB_URL = (
    "https://alidocs.dingtalk.com/i/nodes/MNDoBb60VLrMNyOyCmdjOyrr8lemrZQ3"
)
DEFAULT_REGRESSION_CASE_URL = (
    "https://alidocs.dingtalk.com/i/nodes/a9E05BDRVQ6AzGLGtYyogmmmJ63zgkYA"
)
# xlsx 文件名常见「v2.4.4版本用例（…）」：标题里只保留【v2.4.4版本】，去掉用例说明与重复「版本」
_TITLE_USE_CASE_RE = re.compile(r"用例[（(][^）)]*[）)]")
# 标题行「【Yaahlan2.4.6版本】」：从文件名中取 x.y.z
# 不用尾随 \\b：「2.4.6」后紧跟中文「版」时 ASCII \\b 不成立，会误走回退分支
_YAAHLAN_SEMVER_IN_STEM = re.compile(r"(?i)(v?)(\d+\.\d+\.\d+)")


def _title_prefix_from_xlsx_stem(stem: str) -> str:
    s = _TITLE_USE_CASE_RE.sub("", stem.strip()).strip()
    if s.endswith("版本"):
        s = s[:-2].strip()
    return s if s else stem.strip()


def _yaahlan_version_s2_from_stem(stem: str) -> str:
    """内网/外网报告标题中 s2 文案：Yaahlan + 主版本号，与「【Yaahlan2.4.6版本】」格式一致。"""
    s = stem.strip()
    m = _YAAHLAN_SEMVER_IN_STEM.search(s)
    if m:
        return f"Yaahlan{m.group(2)}"
    tp = _title_prefix_from_xlsx_stem(s)
    return f"Yaahlan{tp}" if tp else "Yaahlan"


def version_s2_from_semver(semver: str) -> str:
    """由裸版本号（如 2.4.6）或已是 Yaahlan 前缀的文案生成标题 s2。"""
    s = semver.strip()
    if not s:
        return "Yaahlan"
    if s.lower().startswith("yaahlan"):
        return s
    m = _YAAHLAN_SEMVER_IN_STEM.search(s)
    if m:
        return f"Yaahlan{m.group(2)}"
    return f"Yaahlan{s}"


def guess_version_from_xlsx(xlsx_path: Path) -> str | None:
    """从版本用例表 sheet 名或前几行单元格提取 x.y.z（钉钉网关临时文件名无版本时回退）。"""
    try:
        from openpyxl import load_workbook
    except ModuleNotFoundError:
        return None
    try:
        wb = load_workbook(str(xlsx_path), data_only=True, read_only=True)
    except OSError:
        return None
    except Exception:  # openpyxl InvalidFileException 等
        return None
    try:
        for name in wb.sheetnames:
            m = _YAAHLAN_SEMVER_IN_STEM.search(name)
            if m:
                return m.group(2)
            ws = wb[name]
            for row in ws.iter_rows(min_row=1, max_row=6, values_only=True):
                if not row:
                    continue
                for cell in row:
                    if cell is None:
                        continue
                    m = _YAAHLAN_SEMVER_IN_STEM.search(str(cell))
                    if m:
                        return m.group(2)
    finally:
        wb.close()
    return None


def resolve_version_s2(xlsx_stem: str) -> str:
    """报告标题版本：环境变量 REPORT_VERSION_S2 优先，否则从 xlsx 文件名推导。"""
    override = os.environ.get("REPORT_VERSION_S2", "").strip()
    if override:
        return override
    return _yaahlan_version_s2_from_stem(xlsx_stem)


def _normalize_subitem(s: str) -> str:
    s = s.strip()
    s = _SUBITEM_PREFIX_RE.sub("", s)
    s = s.strip()
    cleaned = _clean_tech_opt_display_title(s)
    if _is_tech_opt_skip_title(cleaned):
        return ""
    return cleaned


# 版本用例表 D2：与 Excel 中公式一致，按 D/E 列第 7 行起统计用例条数与执行率
_D2_STATS_TITLE_EXPR = (
    'IF(ISERROR(FIND("（",SHEETSNAME(A1)&"（")),SHEETSNAME(A1),'
    'LEFT(SHEETSNAME(A1),FIND("（",SHEETSNAME(A1)&"（")-1))'
)
D2_STATS_FORMULA = (
    '=IF(COUNTA(D7:D10053)=0,'
    f'{_D2_STATS_TITLE_EXPR}&"：用例条数0条，实际执行"&COUNTA(E7:E10053)&"条，执行率0.00%",'
    'IF(COUNTA(E7:E10053)>COUNTA(D7:D10053),'
    f'{_D2_STATS_TITLE_EXPR}&"：用例条数"&COUNTA(E7:E10053)&"条，实际执行"&COUNTA(E7:E10053)&"条，执行率100.00%",'
    f'{_D2_STATS_TITLE_EXPR}&"：用例条数"&COUNTA(D7:D10053)&"条，实际执行"&COUNTA(E7:E10053)&"条，执行率"&'
    'TEXT(COUNTA(E7:E10053)/COUNTA(D7:D10053),"0.00%")))'
)
_D2_STATS_LINE_RE = re.compile(
    r"^(.+)：用例条数(\d+)条，实际执行(\d+)条，执行率([\d.]+%)$"
)
_D2_STATS_ROW_START = 7
_D2_STATS_ROW_END = 10053
_D2_TECH_OPT_ROW_START = 7
_D2_TECH_OPT_ROW_END = 990
_TECH_OPT_SHEET_NAMES = frozenset({"优化需求", "技术优化"})
_D2_TECH_OPT_FILTER = (
    '(B7:B990<>"")*(C7:C990="")*(D7:D990="")'
)
D2_TECH_OPT_FORMULA = (
    '="技术优化需求："&CHAR(10)&TEXTJOIN(CHAR(10),TRUE,'
    f"SEQUENCE(ROWS(FILTER(B7:B990,{_D2_TECH_OPT_FILTER})))&\") \"&"
    f'IF(IFERROR(FIND("【",FILTER(B7:B990,{_D2_TECH_OPT_FILTER})),9999)'
    f'<IFERROR(FIND("（",FILTER(B7:B990,{_D2_TECH_OPT_FILTER})),9999),'
    f'IF(IFERROR(FIND("【",FILTER(B7:B990,{_D2_TECH_OPT_FILTER})),9999)>=9999,'
    f'FILTER(B7:B990,{_D2_TECH_OPT_FILTER}),'
    f'LEFT(FILTER(B7:B990,{_D2_TECH_OPT_FILTER}),'
    f'IFERROR(FIND("【",FILTER(B7:B990,{_D2_TECH_OPT_FILTER})),9999)-1)),'
    f'IF(IFERROR(FIND("（",FILTER(B7:B990,{_D2_TECH_OPT_FILTER})),9999)>=9999,'
    f'FILTER(B7:B990,{_D2_TECH_OPT_FILTER}),'
    f'LEFT(FILTER(B7:B990,{_D2_TECH_OPT_FILTER}),'
    f'IFERROR(FIND("（",FILTER(B7:B990,{_D2_TECH_OPT_FILTER})),9999)-1))))'
)


def _sheet_title_from_name(sheet_name: str) -> str:
    idx = sheet_name.find("（")
    if idx < 0:
        return sheet_name
    return sheet_name[:idx]


def _count_nonempty_column(ws, col: int, *, start_row: int, end_row: int) -> int:
    count = 0
    for row in ws.iter_rows(
        min_row=start_row,
        max_row=end_row,
        min_col=col,
        max_col=col,
        values_only=True,
    ):
        v = row[0]
        if v is not None and str(v).strip() != "":
            count += 1
    return count


def _cell_is_empty(value: object | None) -> bool:
    return value is None or str(value).strip() == ""


def _trim_tech_opt_item_title(text: str) -> str:
    """与优化需求 D2 公式一致：优先在【、（ 处截断标题。"""
    s = text.strip()
    idx_open_square = s.find("【")
    idx_open_paren = s.find("（")
    if idx_open_square >= 0 and (idx_open_paren < 0 or idx_open_square < idx_open_paren):
        return s[:idx_open_square].strip()
    if idx_open_paren >= 0:
        return s[:idx_open_paren].strip()
    return s


_TECH_OPT_META_LINE_RE = re.compile(
    r"^\s*(?:开发|产品|设计|测试|开\s*发|产\s*品)[：:\s]",
    re.I,
)
_TECH_OPT_TRAILING_ROLE_RE = re.compile(
    r"\s+(?:产品|开发|设计|测试)[：:]\s*\S.*$",
    re.I,
)
_TECH_OPT_LEADING_ENUM_RE = re.compile(
    r"^[一二三四五六七八九十百千]+[、.．)\s]+"
)
_TECH_OPT_TRAILING_STAFF_RE = re.compile(
    r"\s{4,}[\u4e00-\u9fff]{2,4}(?:、[\u4e00-\u9fff]{2,4})*\s*$"
)
_TECH_OPT_GENERIC_SKIP = frozenset(
    {
        "新老版本交互",
        "老版本历史功能回测",
        "定时任务",
        "失败与回滚",
        "幂等",
        "弱网",
        "性能",
    }
)


def _clean_tech_opt_display_title(text: str) -> str:
    """报告展示用：去掉序号前缀、行尾负责人姓名、产品/开发等元信息。"""
    s = text.strip()
    if not s:
        return ""
    first_line = s.splitlines()[0].strip()
    first_line = _TECH_OPT_LEADING_ENUM_RE.sub("", first_line).strip()
    first_line = _TECH_OPT_TRAILING_ROLE_RE.sub("", first_line).strip()
    first_line = _TECH_OPT_TRAILING_STAFF_RE.sub("", first_line).strip()
    return _trim_tech_opt_item_title(first_line)


def _is_tech_opt_meta_line(text: str) -> bool:
    s = _SUBITEM_PREFIX_RE.sub("", text.strip()).strip()
    if not s:
        return True
    return bool(_TECH_OPT_META_LINE_RE.match(s))


def _is_tech_opt_skip_title(title: str) -> bool:
    s = _SUBITEM_PREFIX_RE.sub("", title.strip()).strip()
    if not s:
        return True
    if s in _TECH_OPT_GENERIC_SKIP:
        return True
    return _is_tech_opt_meta_line(s)


def _is_tech_opt_header_row(b: object | None, c: object | None, d: object | None) -> bool:
    return not _cell_is_empty(b) and _cell_is_empty(c) and _cell_is_empty(d)


def compute_d2_tech_opt_text(ws) -> str:
    """按 D2_TECH_OPT_FORMULA 规则汇总 B 列分组标题行。"""
    headers: list[str] = []
    for row in ws.iter_rows(
        min_row=_D2_TECH_OPT_ROW_START,
        max_row=_D2_TECH_OPT_ROW_END,
        min_col=2,
        max_col=4,
        values_only=True,
    ):
        b, c, d = row
        if _is_tech_opt_header_row(b, c, d):
            title = _clean_tech_opt_display_title(str(b))
            if title and not _is_tech_opt_skip_title(title):
                headers.append(title)
    lines = [f"{TECH_OPT_SECTION_LABEL}："]
    for i, title in enumerate(headers, start=1):
        lines.append(f"{i}) {title}")
    return "\n".join(lines)


def _format_d2_stats_line(title: str, case_count: int, executed_count: int) -> str:
    """与钉钉 D2 公式一致：E>D 时用例条数取 E、执行率 100.00%；D 为空时执行率 0.00%。"""
    if case_count == 0:
        return f"{title}：用例条数0条，实际执行{executed_count}条，执行率0.00%"
    if executed_count > case_count:
        return (
            f"{title}：用例条数{executed_count}条，实际执行{executed_count}条，"
            f"执行率100.00%"
        )
    rate = executed_count / case_count
    return (
        f"{title}：用例条数{case_count}条，实际执行{executed_count}条，执行率{rate:.2%}"
    )


def _cap_d2_stats_text(text: str) -> str:
    """已缓存的 D2 文案若执行率超 100%，与公式规则对齐。"""
    lines = text.splitlines()
    if not lines:
        return text
    m = _D2_STATS_LINE_RE.match(lines[0].strip())
    if not m:
        return text
    title, case_s, exec_s, _rate_s = m.groups()
    capped = _format_d2_stats_line(title, int(case_s), int(exec_s))
    if len(lines) == 1:
        return capped
    return capped + "\n" + "\n".join(lines[1:])


def compute_d2_stats_text(ws, sheet_name: str) -> str:
    """按 D2_STATS_FORMULA 规则：COUNTA(D7:D10053)、COUNTA(E7:E10053)。"""
    title = _sheet_title_from_name(sheet_name)
    case_count = _count_nonempty_column(
        ws, 4, start_row=_D2_STATS_ROW_START, end_row=_D2_STATS_ROW_END
    )
    executed_count = _count_nonempty_column(
        ws, 5, start_row=_D2_STATS_ROW_START, end_row=_D2_STATS_ROW_END
    )
    return _format_d2_stats_line(title, case_count, executed_count)


_PASS_FAIL_NULL_ROW = 2
_RESULT_COL_HEADER_RE = re.compile(
    r"(测试组结果|测试组线上|开发自测)",
    re.I,
)
_SHEET1_NAMES = frozenset({"Sheet1", "sheet1"})


def _sheet_case_layout(ws) -> tuple[int, int, list[int]]:
    """返回 (数据起始行, 预期结果列, 结果统计列列表)。"""
    header_row = 0
    for r in range(4, 10):
        label = ws.cell(r, 4).value
        if label is not None and "预期结果" in str(label):
            header_row = r
            break
    if header_row <= 0:
        return _D2_STATS_ROW_START, 4, [5, 6, 7, 8]

    result_cols: list[int] = []
    for col in range(1, 40):
        head = ws.cell(header_row, col).value
        if head is not None and _RESULT_COL_HEADER_RE.search(str(head)):
            result_cols.append(col)
    if not result_cols:
        result_cols = [5, 6, 7, 8]
    return header_row + 1, 4, result_cols


def compute_pass_fail_null(
    ws,
    result_col: int,
    *,
    case_col: int = 4,
    start_row: int = _D2_STATS_ROW_START,
    end_row: int = _D2_STATS_ROW_END,
) -> tuple[int, int, int]:
    """与用例表第 2 行统计一致：pass/fail 按结果列计数，null=用例条数-pass-fail。"""
    case_count = _count_nonempty_column(
        ws, case_col, start_row=start_row, end_row=end_row
    )
    pass_count = 0
    fail_count = 0
    for row in ws.iter_rows(
        min_row=start_row,
        max_row=end_row,
        min_col=result_col,
        max_col=result_col,
        values_only=True,
    ):
        v = row[0]
        if v is None or str(v).strip() == "":
            continue
        s = str(v).strip().lower()
        if s == "pass":
            pass_count += 1
        elif s == "fail":
            fail_count += 1
    null_count = max(0, case_count - pass_count - fail_count)
    return pass_count, fail_count, null_count


def format_pass_fail_null_cell(pass_count: int, fail_count: int, null_count: int) -> str:
    return f"pass: {pass_count}\nfail: {fail_count}\nnull: {null_count}"


def enrich_sheet_row2_pass_fail_null(ws) -> bool:
    """按各结果列回填第 2 行 pass/fail/null（与历史 Excel 公式口径一致）。"""
    data_start, case_col, result_cols = _sheet_case_layout(ws)
    if data_start <= 0:
        return False
    changed = False
    for col in result_cols:
        p, f, n = compute_pass_fail_null(
            ws,
            col,
            case_col=case_col,
            start_row=data_start,
        )
        text = format_pass_fail_null_cell(p, f, n)
        cell = ws.cell(_PASS_FAIL_NULL_ROW, col)
        if cell.value != text:
            cell.value = text
            changed = True
    return changed


def enrich_version_workbook(wb) -> int:
    """对所有需求 sheet 回填第 2 行 pass/fail/null，返回变更 sheet 数。"""
    updated = 0
    for name in wb.sheetnames:
        if name.strip() in _SHEET1_NAMES:
            continue
        ws = wb[name]
        if getattr(ws, "sheet_state", "visible") != "visible":
            continue
        if _is_tech_opt_sheet_name(name):
            continue
        if enrich_sheet_row2_pass_fail_null(ws):
            updated += 1
    return updated


def enrich_version_case_xlsx(xlsx_path: str | Path) -> int:
    """保存前/后均可调用：打开 xlsx 并回填各 sheet 第 2 行统计。"""
    from openpyxl import load_workbook

    path = Path(xlsx_path).expanduser().resolve()
    wb = load_workbook(path)
    count = enrich_version_workbook(wb)
    wb.save(path)
    return count


def _is_tech_opt_sheet_name(sheet_name: str) -> bool:
    name = sheet_name.strip()
    if name in _TECH_OPT_SHEET_NAMES:
        return True
    return "技术优化" in name or name.endswith("优化需求")


def _d2_needs_compute(raw: object | None) -> bool:
    if raw is None:
        return True
    if not isinstance(raw, str):
        return False
    s = raw.strip()
    return not s or s.startswith("=")


def _d2_looks_like_tech_opt_text(raw: str) -> bool:
    lines = [p.strip() for p in raw.splitlines() if p.strip()]
    if not lines:
        return False
    return _is_tech_opt_need(lines[0])


def resolve_sheet_d2_text(ws, sheet_name: str, d2_raw: object | None) -> str | None:
    """需求 sheet 始终从 D/E 列现算摘要；技术优化 sheet 仍按 B 列分组规则生成。"""
    if _is_tech_opt_sheet_name(sheet_name):
        if _d2_needs_compute(d2_raw):
            return compute_d2_tech_opt_text(ws)
        if isinstance(d2_raw, str) and _d2_looks_like_tech_opt_text(d2_raw):
            return str(d2_raw)
        return compute_d2_tech_opt_text(ws)
    return compute_d2_stats_text(ws, sheet_name)


def _report_link_overrides_from_env() -> tuple[str | None, str | None, str | None]:
    def _env(name: str) -> str | None:
        value = os.environ.get(name, "").strip()
        return value or None

    return (
        _env("REPORT_DEFECT_TB_URL"),
        _env("REPORT_VERSION_CASE_URL"),
        _env("REPORT_REGRESSION_CASE_URL"),
    )


def resolve_report_links(
    i2_raw: str | None,
) -> tuple[str | None, str | None, str | None]:
    """解析 I2 链接，环境变量非空时覆盖对应项。"""
    tb, ver, reg = _parse_sheet1_e2_urls(i2_raw)
    o_tb, o_ver, o_reg = _report_link_overrides_from_env()
    return (o_tb or tb, o_ver or ver, o_reg or reg)


def _parse_sheet1_e2_urls(raw: str | None) -> tuple[str | None, str | None, str | None]:
    """从 Sheet1 I2 文本解析缺陷(TB)、版本用例、回归用例三类 URL。"""
    if raw is None:
        return (None, None, None)
    text = str(raw).strip()
    if not text:
        return (None, None, None)

    def _m_url(pat: re.Pattern[str]) -> str | None:
        m = pat.search(text)
        return m.group(1).strip() if m else None

    return (
        _m_url(_E2_DEFECT_URL_RE),
        _m_url(_E2_VERSION_CASE_URL_RE),
        _m_url(_E2_REGRESSION_URL_RE),
    )


def _e2_defect_levels_from_block(block: str) -> dict[str, int]:
    d = {"阻碍": 0, "严重": 0, "一般": 0, "轻微": 0}
    for name, num_s in _E2_DEFECT_LEVEL_LINE_RE.findall(block):
        d[name] = int(num_s)
    return d


def _defect_levels_dict_empty() -> dict[str, int]:
    return {"阻碍": 0, "严重": 0, "一般": 0, "轻微": 0}


def _parse_i2_unfinished_finished_dicts(raw: str | None) -> tuple[dict[str, int], dict[str, int]]:
    """从 I2 原文解析「未完成 / 已完成」两段的各级数量（与表内用 `；` 连写或分行均可）。"""
    e = _defect_levels_dict_empty()
    if raw is None:
        return (e.copy(), e.copy())
    text = str(raw).strip()
    if not text:
        return (e.copy(), e.copy())
    unf_block_m = _E2_UNFINISHED_BLOCK_RE.search(text)
    fin_block_m = _E2_FINISHED_BLOCK_RE.search(text)
    unf_block = unf_block_m.group(1) if unf_block_m else ""
    fin_block = fin_block_m.group(1) if fin_block_m else ""
    return (
        _e2_defect_levels_from_block(unf_block),
        _e2_defect_levels_from_block(fin_block),
    )


def _format_i2_defect_level_row(levels: dict[str, int] | None) -> str:
    """与 Excel 调整版一致：一行内「阻碍：0；严重：0；一般：1；轻微：2」。"""
    d = levels if levels is not None else _defect_levels_dict_empty()
    return "；".join(f"{k}：{d.get(k, 0)}" for k in ("阻碍", "严重", "一般", "轻微"))


def format_sheet1_i2_text(
    *,
    defect_tb_url: str | None,
    version_case_url: str | None,
    regression_case_url: str | None,
    unf: dict[str, int] | None = None,
    fin: dict[str, int] | None = None,
) -> str:
    """生成与当前版本用例表 I2 相同结构的多行文本（缺陷/版本/回归 URL + 未完成&已完成统计）。"""
    lines: list[str] = [
        f"缺陷链接：{defect_tb_url or ''}",
        f"版本用例链接：{version_case_url or ''}",
        f"回归用例链接：{regression_case_url or ''}",
        f"未完成缺陷：{_format_i2_defect_level_row(unf)}",
        f"已完成缺陷：{_format_i2_defect_level_row(fin)}",
    ]
    return "\n".join(lines)


_SCHEDULE_DEFECT_FINISHED = frozenset({"已关闭", "已解决", "已修复", "关闭"})


def _normalize_schedule_severity(raw: object | None) -> str:
    s = str(raw or "").strip()
    for key in ("阻碍", "严重", "一般", "轻微"):
        if key in s:
            return key
    return "一般"


def _accumulate_defect_counts(
    unf: dict[str, int],
    fin: dict[str, int],
    *,
    status: str,
    severity: object | None,
) -> None:
    level = _normalize_schedule_severity(severity)
    if status in _SCHEDULE_DEFECT_FINISHED:
        fin[level] += 1
    else:
        unf[level] += 1


def defect_levels_from_schedule_xlsx(
    xlsx_path: str | Path,
    version: str,
    *,
    sheet_name: str = "缺陷列表",
    version_col: int = 2,
    status_col: int = 4,
    severity_col: int = 10,
) -> tuple[dict[str, int], dict[str, int]] | None:
    """从 Q3 排期等工作簿「缺陷列表」按版本汇总未完成/已完成各级缺陷。"""
    from openpyxl import load_workbook

    target = (version or "").strip()
    if not target:
        return None
    path = Path(xlsx_path).expanduser().resolve()
    if not path.is_file():
        return None
    try:
        wb = load_workbook(path, data_only=True, read_only=True)
    except OSError:
        return None
    try:
        if sheet_name not in wb.sheetnames:
            return None
        ws = wb[sheet_name]
        unf = _defect_levels_dict_empty().copy()
        fin = _defect_levels_dict_empty().copy()
        matched = 0
        for row in ws.iter_rows(min_row=2, values_only=True):
            if not row:
                continue
            ver = str(row[version_col - 1] or "").strip()
            if ver != target:
                continue
            matched += 1
            status = str(row[status_col - 1] or "").strip()
            _accumulate_defect_counts(
                unf,
                fin,
                status=status,
                severity=row[severity_col - 1] if len(row) >= severity_col else None,
            )
        if matched == 0:
            return None
        return unf, fin
    finally:
        wb.close()


def _apply_defect_levels_to_i2(
    i2_raw: str | None,
    levels: tuple[dict[str, int], dict[str, int]] | None,
    *,
    defect_tb_url: str | None = None,
) -> str | None:
    if levels is None:
        return i2_raw
    unf, fin = levels
    tb, ver_url, reg = _parse_sheet1_e2_urls(i2_raw)
    return format_sheet1_i2_text(
        defect_tb_url=defect_tb_url or tb or DEFAULT_DEFECT_TB_URL,
        version_case_url=ver_url,
        regression_case_url=reg or DEFAULT_REGRESSION_CASE_URL,
        unf=unf,
        fin=fin,
    )


def apply_schedule_defects_to_i2(
    i2_raw: str | None,
    schedule_path: str | Path,
    version: str,
) -> str | None:
    """用排期 xlsx「缺陷列表」统计替换 I2。"""
    return _apply_defect_levels_to_i2(
        i2_raw,
        defect_levels_from_schedule_xlsx(schedule_path, version),
    )


def apply_bug_url_defects_to_i2(
    i2_raw: str | None,
    version: str,
    bug_url: str | None = None,
) -> str | None:
    """从 bug 地址（AI 表格，见 schedule_links.json）按版本拉取缺陷统计写入 I2。"""
    from report.bug_notable import defect_levels_from_bug_url  # noqa: WPS433

    url = (bug_url or os.environ.get("REPORT_DEFECT_TB_URL") or DEFAULT_DEFECT_TB_URL).strip()
    try:
        levels = defect_levels_from_bug_url(version, url)
    except Exception as exc:  # noqa: BLE001
        print(f"从 bug 表拉取缺陷失败（沿用用例表 I2）：{exc}", file=sys.stderr)
        return i2_raw
    return _apply_defect_levels_to_i2(i2_raw, levels, defect_tb_url=url)


def reformat_raw_i2_like_excel(i2_raw: str | None) -> str:
    """从 I2 原文解析链接与数字后，按 `format_sheet1_i2_text` 规则重排为统一格式。"""
    tb, ver, reg = _parse_sheet1_e2_urls(i2_raw)
    unf, fin = _parse_i2_unfinished_finished_dicts(i2_raw)
    return format_sheet1_i2_text(
        defect_tb_url=tb,
        version_case_url=ver,
        regression_case_url=reg,
        unf=unf,
        fin=fin,
    )


def _parse_sheet1_e2_defect_stats(raw: str | None) -> tuple[int, int, int, int, int, int, int, str] | None:
    """解析 I2 中未完成/已完成缺陷统计，返回
    (发现缺陷总数, 1~4级数量, 已修复, 未修复, 缺陷修复率百分比字符串)。
    缺陷修复率按「已修复/发现缺陷×100」保留两位小数。"""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None

    unf, fin = _parse_i2_unfinished_finished_dicts(raw)

    unf_block_m = _E2_UNFINISHED_BLOCK_RE.search(text)
    fin_block_m = _E2_FINISHED_BLOCK_RE.search(text)

    unfixed = sum(unf.values())
    fixed = sum(fin.values())
    total = unfixed + fixed
    if total == 0 and not (unf_block_m or fin_block_m):
        return None

    l1 = unf["阻碍"] + fin["阻碍"]
    l2 = unf["严重"] + fin["严重"]
    l3 = unf["一般"] + fin["一般"]
    l4 = unf["轻微"] + fin["轻微"]

    if total == 0:
        rate_s = "0.00"
    else:
        rate_s = f"{(fixed / total) * 100:.2f}"

    return (total, l1, l2, l3, l4, fixed, unfixed, rate_s)


def _inject_defect_stats(html_out: str, stats: tuple[int, int, int, int, int, int, int, str] | None) -> str:
    """将 I2 缺陷统计写入模板中「发现缺陷」列表项（位于 bug 地址之前）。"""
    if stats is None:
        return html_out
    total, l1, l2, l3, l4, fixed, unfixed, rate_s = stats

    start = html_out.find('<span class="s1">发现缺陷</span>')
    label = _defect_link_label_span()
    end = html_out.find(label, start)
    if end < 0:
        end = html_out.find('<span class="s2">tb</span>', start)
    if start < 0 or end < 0 or start >= end:
        return html_out

    region = html_out[start:end]
    vals = [str(total), str(l1), str(l2), str(l3), str(l4), str(fixed), str(unfixed)]
    new_region = region
    for v in vals:
        if '<span class="s5">x</span>' not in new_region:
            return html_out
        new_region = new_region.replace('<span class="s5">x</span>', f'<span class="s5">{v}</span>', 1)
    if "缺陷修复率x" not in new_region:
        return html_out
    new_region = new_region.replace("缺陷修复率x", f"缺陷修复率{rate_s}", 1)

    return html_out[:start] + new_region + html_out[end:]


def _html_a_href(url: str, inner_text: str, *, a_class: str = "") -> str:
    esc_url = html.escape(url, quote=True)
    esc_inner = html.escape(inner_text)
    cls = f' class="{a_class}"' if a_class else ""
    return f'<a href="{esc_url}"{cls}>{esc_inner}</a>'


def _inject_report_links(
    html_out: str,
    *,
    defect_tb_url: str | None,
    version_case_url: str | None,
    regression_case_url: str | None,
) -> str:
    """将 I2 中的链接写入「用例地址」「bug 地址」及覆盖表格中两处详情占位。"""
    out = html_out

    if version_case_url:
        frag = _html_a_href(version_case_url, version_case_url, a_class="s7")
        out = out.replace(
            '<span class="s7">用例地址：x</span>',
            f'<span class="s7">用例地址：{frag}</span>',
            1,
        )

    if defect_tb_url:
        frag = _html_a_href(defect_tb_url, defect_tb_url, a_class="s8")
        label = _defect_link_label_span()
        placeholder = f'{label}<span class="s8">地址：x</span>'
        replacement = f'{label}<span class="s8">地址：{frag}</span>'
        if placeholder in out:
            out = out.replace(placeholder, replacement, 1)
        else:
            out = out.replace(
                '<span class="s2">tb</span><span class="s8">地址：x</span>',
                f'{label}<span class="s8">地址：{frag}</span>',
                1,
            )

    def _replace_first_between(start_m: str, end_m: str, old: str, new: str) -> None:
        nonlocal out
        i = out.find(start_m)
        if i < 0:
            return
        j = out.find(end_m, i + len(start_m))
        if j < 0:
            return
        region = out[i:j]
        if old not in region:
            return
        out = out[:i] + region.replace(old, new, 1) + out[j:]

    if version_case_url:
        vfrag = _html_a_href(version_case_url, version_case_url, a_class="s3")
        new_cell = f'<span class="s3">{vfrag}</span>'
        _replace_first_between("新功能覆盖", "原功能回归", '<span class="s3">x</span>', new_cell)

    if regression_case_url:
        rfrag = _html_a_href(regression_case_url, regression_case_url, a_class="s3")
        new_cell = f'<span class="s3">{rfrag}</span>'
        _replace_first_between("原功能回归", "分区测试", '<span class="s3">x</span>', new_cell)

    return out


def _open_html_default_browser(html_path: Path) -> bool:
    """用系统默认浏览器/应用打开本地 HTML；macOS 用 `open`，比 webbrowser 在部分终端里更稳。"""
    path = html_path.resolve()
    if not path.is_file():
        return False
    system = platform.system()
    try:
        if system == "Darwin":
            r = subprocess.run(
                ["open", str(path)],
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
            return r.returncode == 0
        if system == "Windows":
            os.startfile(str(path))  # type: ignore[attr-defined]
            return True
        r = subprocess.run(
            ["xdg-open", str(path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if r.returncode == 0:
            return True
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"系统命令打开失败（{e}），尝试 webbrowser…", file=sys.stderr)
    try:
        return bool(webbrowser.open(path.as_uri()))
    except OSError as e:
        print(f"webbrowser 打开失败：{e}", file=sys.stderr)
        return False


# 测试覆盖表：内嵌模板用「相邻单元格一边透明」省线，但 Gmail/Outlook/部分企业邮会丢格线或最右侧线；统一实线 + 可伸缩宽度后黏贴到邮件里更稳
# 与模板中 p.p3 / p.p4 等一致：10.5pt 宋体正文色；子元素 span.s2、span.s5 等仍用各自类里的 Helvetica
_COVERAGE_TABLE_FONT = (
    "font: 10.5pt/1.35 'Songti SC', 'PingFang SC', 'Hiragino Sans GB', 'STSong', 'SimSun', 'Microsoft YaHei', "
    "serif; color: #0d0e11; "
)
_COVERAGE_TABLE_CSS_FOR_EMAIL = f"""    table.t1 {{ width: 100%; max-width: 746px; border-collapse: collapse; table-layout: fixed; border: 1px solid #858889; -webkit-text-size-adjust: 100%; mso-fareast-font-family: 'Songti SC', SimSun, serif; {_COVERAGE_TABLE_FONT} }}
    td.td1, td.td2, td.td3, td.td4, td.td5, td.td6, td.td7, td.td8 {{ border: 1px solid #858889; padding: 4.0px 7.0px 4.0px 7.0px; vertical-align: top; box-sizing: border-box; font: inherit; }}
    td.td1, td.td5 {{ width: 46.4px; }}
    td.td2, td.td6 {{ width: 118.5px; }}
    td.td3, td.td7 {{ width: 37.6px; }}
    td.td4, td.td8 {{ width: 482.4px; min-width: 0; word-wrap: break-word; }}
    """
_COVERAGE_TABLE_TAG_LEGACY = '<table width="746.0" cellspacing="0" cellpadding="0" class="t1">'
_COVERAGE_TABLE_TAG_FOR_EMAIL = (
    '<table class="t1" width="100%" border="1" bordercolor="#858889" cellspacing="0" '
    "cellpadding=\"0\" style=\"max-width:746px;border:1px solid #858889;border-collapse:collapse;"
    "mso-fareast-font-family:'Songti SC',SimSun,serif;"
    f"{_COVERAGE_TABLE_FONT.rstrip()}"
    '">'
)


def _coverage_table_css_block_from_template() -> str | None:
    """从内嵌模板取出「table.t1 … td.td8」这段旧 CSS，供与生成结果做 str.replace；模板改版式时若结构仍含 table.t1 / ul.ul2 可自动适配。"""
    text = _report_template_html()
    i = text.find("    table.t1 {")
    j = text.find("    ul.ul2 {", i)
    if i < 0 or j < 0 or j <= i:
        return None
    return text[i:j]


def _inject_email_table_style_fallback(html: str) -> str:
    """未匹配到内嵌模版权重子串时，在 </head> 前追加高优先级规则（旧版已生成 HTML 重跑时可能用到）。"""
    font_s = _COVERAGE_TABLE_FONT.rstrip()
    inj = (
        '  <style type="text/css">\n'
        "  /* count.py: 邮件格线 + 与正文一致的中文字体（见 _COVERAGE_TABLE_FONT） */\n"
        f"  table.t1 {{ width: 100% !important; max-width: 746px !important; border-collapse: collapse !important; border: 1px solid #858889 !important; mso-fareast-font-family: 'Songti SC', SimSun, serif !important; {font_s} }}\n"
        "  table.t1 td.td1, table.t1 td.td2, table.t1 td.td3, table.t1 td.td4, table.t1 td.td5, table.t1 td.td6, table.t1 td.td7, table.t1 td.td8 { border: 1px solid #858889 !important; padding: 4.0px 7.0px; vertical-align: top; box-sizing: border-box; font: inherit !important; }\n"
        "  </style>\n"
    )
    if "</head>" in html:
        return html.replace("</head>", inj + "</head>", 1)
    return html


def _harden_coverage_table_for_email(html: str) -> str:
    """为抄送邮件等场景强化「一、测试覆盖情况」表格外框与格线，避免最右侧/透明边在部分客户端不显示。"""
    out = html
    legacy = _coverage_table_css_block_from_template()
    if legacy and legacy in out:
        out = out.replace(legacy, _COVERAGE_TABLE_CSS_FOR_EMAIL, 1)
    else:
        out = _inject_email_table_style_fallback(out)
    if _COVERAGE_TABLE_TAG_LEGACY in out:
        out = out.replace(_COVERAGE_TABLE_TAG_LEGACY, _COVERAGE_TABLE_TAG_FOR_EMAIL, 1)
    return out


# 外网「功能开放前 checklist」表：仅写一份 *外网测试总结.html*，线色 #858 与内网表邮件版一致，便于发邮件/复制
_EXTERNAL_CHECKLIST_TABLE_FONT = (
    "font: 14px/1.35 'Songti SC', 'PingFang SC', 'Hiragino Sans GB', 'STSong', 'SimSun', 'Microsoft YaHei', "
    "serif; color: #0d0e11; "
)
_EXTERNAL_CHECKLIST_TABLE_BORDER = "#858889"  # 同内网表 _harden
_EXTERNAL_CHECKLIST_TABLE_TAG_LEGACY = '<table width="362.0" cellspacing="0" cellpadding="0" class="t1">'


def _external_checklist_table_css_hardened(table_border: str) -> str:
    return f"""    table.t1 {{ width: 100%; max-width: 362px; border-collapse: collapse; table-layout: fixed; border: 1px solid {table_border}; -webkit-text-size-adjust: 100%; mso-fareast-font-family: 'Songti SC', SimSun, serif; {_EXTERNAL_CHECKLIST_TABLE_FONT} }}
    td.td1, td.td2, td.td3, td.td4 {{ border: 1px solid {table_border}; padding: 4.0px 8.0px 4.0px 8.0px; vertical-align: top; box-sizing: border-box; font: inherit; }}
    td.td1, td.td3 {{ width: 185.6px; }}
    td.td2, td.td4 {{ width: 141.4px; min-width: 0; word-wrap: break-word; }}
    """


def _external_checklist_table_tag_hardened(table_border: str) -> str:
    return (
        f'<table class="t1" width="100%" border="1" bordercolor="{table_border}" cellspacing="0" '
        f'cellpadding="0" style="max-width:362px;border:1px solid {table_border};border-collapse:collapse;'
        "mso-fareast-font-family:'Songti SC',SimSun,serif;"
        f"{_EXTERNAL_CHECKLIST_TABLE_FONT.rstrip()}"
        '">'
    )


def _external_checklist_table_css_block_from_template() -> str | None:
    """从外网模板取「功能开放前 checklist」table.t1 ～ td4 的 CSS 片段（后接 ul.ul1）。"""
    text = _external_report_template_html()
    i = text.find("    table.t1 {")
    j = text.find("    ul.ul1 {", i)
    if i < 0 or j < 0 or j <= i:
        return None
    return text[i:j]


def _inject_external_email_table_style_fallback(html: str, table_border: str) -> str:
    fnt = _EXTERNAL_CHECKLIST_TABLE_FONT.rstrip()
    b = table_border
    inj = (
        '  <style type="text/css">\n'
        "  /* count.py: 外网 checklist 表格线（不依赖 border-color: transparent） */\n"
        f"  table.t1 {{ width: 100% !important; max-width: 362px !important; border-collapse: collapse !important; border: 1px solid {b} !important; mso-fareast-font-family: 'Songti SC', SimSun, serif !important; {fnt} }}\n"
        f"  table.t1 td.td1, table.t1 td.td2, table.t1 td.td3, table.t1 td.td4 {{ border: 1px solid {b} !important; padding: 4.0px 8.0px; vertical-align: top; box-sizing: border-box; font: inherit !important; }}\n"
        "  </style>\n"
    )
    if "</head>" in html:
        return html.replace("</head>", inj + "</head>", 1)
    return html


def _harden_external_checklist_table(html: str, table_border: str) -> str:
    """将外网「功能开放前 checklist」的透明/断裂边线改为实线，颜色由 `table_border` 指定（默认用 `_EXTERNAL_CHECKLIST_TABLE_BORDER` 与内网表一致）。"""
    out = html
    legacy = _external_checklist_table_css_block_from_template()
    if legacy and legacy in out:
        out = out.replace(legacy, _external_checklist_table_css_hardened(table_border), 1)
    else:
        out = _inject_external_email_table_style_fallback(out, table_border)
    if _EXTERNAL_CHECKLIST_TABLE_TAG_LEGACY in out:
        out = out.replace(_EXTERNAL_CHECKLIST_TABLE_TAG_LEGACY, _external_checklist_table_tag_hardened(table_border), 1)
    return out


# 内嵌报告 HTML 骨架（样式 + 覆盖表格 + 尾部占位），zlib+base64；改版式需同步更新此串或从 1.html 重新生成
_REPORT_TEMPLATE_ZLIB_B64 = "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"


_DEFECT_LINK_LABEL = "bug"


def _defect_link_label_span() -> str:
    return f'<span class="s2">{_DEFECT_LINK_LABEL}</span>'


@functools.lru_cache(maxsize=1)
def _report_template_html() -> str:
    text = zlib.decompress(base64.b64decode(_REPORT_TEMPLATE_ZLIB_B64.encode("ascii"))).decode(
        "utf-8"
    )
    return text.replace('<span class="s2">tb</span>', _defect_link_label_span())


def _build_dynamic_section_html(
    *,
    new_need_count: int,
    optimize_need_count: int,
    new_titles: list[str],
    tech_opt_items: list[str],
) -> str:
    _p8 = _p8_blank_paragraph()
    parts: list[str] = [
        _p8,
        '<ul class="ul1">\n',
        '  <li class="li9"><span class="s4"></span><span class="s1">本次版本共</span>'
        f'<span class="s5">{new_need_count}</span><span class="s1">个新需求及</span>'
        f'<span class="s5">{optimize_need_count}</span><span class="s1">个优化需求</span></li>\n',
        "</ul>\n",
        _p8,
    ]
    for i, title in enumerate(new_titles, start=1):
        t = html.escape(title)
        parts.append(
            f'<p class="p10"><span class="s5">{i}.</span><span class="s1">{t}</span></p>\n'
        )
    if tech_opt_items:
        n = len(new_titles) + 1
        parts.append(
            f'<p class="p10"><span class="s5">{n}.</span><span class="s1">{TECH_OPT_SECTION_LABEL}：</span></p>\n'
        )
        for j, item in enumerate(tech_opt_items, start=1):
            parts.append(
                f'<p class="p11"><span class="s5">{j}</span><span class="s1">）{html.escape(item)}</span></p>\n'
            )
    # 与模板中 p12 空白段一致，便于衔接「用例地址」所在 p13
    parts.append('<p class="p12"><span class="s1">\u00a0</span></p>\n')
    return "".join(parts)


def _p8_blank_paragraph() -> str:
    """与动态区、模板中 p8 一致，占一行高以形成空行。"""
    return '<p class="p8"><span class="s1">\u00a0</span></p>\n'


def _insert_internal_report_title_spacers(html: str) -> str:
    """标题行 与「一、测试覆盖情况」之间、「一、测试覆盖情况」与覆盖表格之间各加一空行（与 p8 样式一致）。"""
    blank = _p8_blank_paragraph()
    a = "内网测试已完成，结果总结如下：</span></p>\n<p class=\"p2\"><span class=\"s1\"><b>一、测试覆盖情况</b>"
    b = "内网测试已完成，结果总结如下：</span></p>\n" + blank + "<p class=\"p2\"><span class=\"s1\"><b>一、测试覆盖情况</b>"
    if a in html:
        html = html.replace(a, b, 1)
    c = "<b>一、测试覆盖情况</b><b></b></span></p>\n<table "
    d = "<b>一、测试覆盖情况</b><b></b></span></p>\n" + blank + "<table "
    if c in html:
        html = html.replace(c, d, 1)
    return html


def _insert_external_checklist_title_spacer(html: str) -> str:
    """在「功能开放前 checklist」与下方表格之间加一空行（与内网 p8 空行一致）。"""
    a = (
        '<p class="p6"><span class="s8"><b>功能开放前</b></span><span class="s1">checklist</span></p>\n<table'
    )
    b = (
        '<p class="p6"><span class="s8"><b>功能开放前</b></span><span class="s1">checklist</span></p>\n'
        + _p8_blank_paragraph()
        + "<table"
    )
    if a in html:
        return html.replace(a, b, 1)
    return html


def _render_full_report_html(
    *,
    title_prefix: str,
    new_need_count: int,
    optimize_need_count: int,
    new_titles: list[str],
    tech_opt_items: list[str],
) -> str:
    t = html.escape(title_prefix)
    title_line = (
        f'<p class="p1"><span class="s1"><b>【</b></span><span class="s2">{t}</span>'
        f'<span class="s1"><b>版本】</b>内网测试已完成，结果总结如下：</span></p>\n'
    )
    dynamic = _build_dynamic_section_html(
        new_need_count=new_need_count,
        optimize_need_count=optimize_need_count,
        new_titles=new_titles,
        tech_opt_items=tech_opt_items,
    )
    tpl = _report_template_html()
    out = tpl.replace("{{TITLE}}", title_line, 1).replace("{{DYNAMIC}}", dynamic, 1)
    return _insert_internal_report_title_spacers(out)


# 外网测试总结 HTML（与「*_外网测试总结.html」版式一致）；改版式需同步更新此串或从样例 HTML 重新生成
_EXTERNAL_REPORT_TEMPLATE_ZLIB_B64 = "eNrFWF1T20YUfc+v2KoPebJk2cY2xvZDjSfJlJIUu2H6xMjSYlSEpEprHIZhxkkGGkhoSRvIlDAJnTZMO9MC7UxSUiCdyV8JkuEpf6GrXX8IIzu2cYkfpNXq3nvOnrt7tev4R4PXU9kvb6TBBJpSwI0vPhm6lgKMj+NGgymOG8wOgqvZz4ZAiPXzHJceZgAzgZAe47hiscgWg6xm5LnsCOd4hzgTGbKIWAlJTPJS3OlzblCQkpcAiE9BJADH2we/LsjTCSalqQiqyJed0SEDRPqUYBC8hUjAASBOCIYJUaKAxn1RpnWUDJpRoGcs0TSpL5KRApNxjt5r0VRhCiaYK1CFhoA0w+We0kRNoAqMGjKCBtPoRSxuQsOUNdXlGAhH+9gQtTYdYgBhYg18ANBZnQezU4KRl9UY8LN+/dbZ6wAYx2FjgA+RvssZTc0jGWRSl7FAmqIZMfCxX/JDnh8AviLMTcrI5+D4cDq0SVh7O1eFDLQBSQIIipzHRl8VTCSPz/ScR7g3PK5CZRoiWRTAMCzAbslEzkkmyAY9yTQBJ78aeLQ34O6MtIXb33vcrsTn/b2fkm0JwPM9Ac7KU9BsDTkAcoI4mTe0gir5qiKNkx9lo8isIgc7qQaRzodMQELnAuk8wQS07yJAXSM1dUFlTZxeJ6hvEhqqrOZjQNVU+N5UUN8A9W1RaLoOjdPcll3IRSHSWwp9LSg00dcRwUPjcIcat4zumjY0eqSrLNTmS3trj0JFG6HcM7BroftrUZt9IroO7ZTNs87UAgk5BbIIL4CiLKGJGAiGA3SV5TRDgoYTVhF0EytfbVUcJRZJdTceb2TCLjeym4kBU1NkqdZZtSWynbm6IV1ZaXYfALogSWQ4NA9RcnW1XUQDdaIhng11TdTfCVFkCCrOgIG3eh2RDXalqr89VV2keqJsqCtl/e0p24psF+oWFLag4DmryCai9HzOfjsGJNkUXSYBDxNRNkSFzP04R/rxmYWjh5Z4TpNm8E0HoiKYZoLReSYZd9ZetcN0OnLJt6WVOJfDJwvnXYNFgEnOzt5Mj2SuXR8eywTm5jytaJzy4j174/e3pYdONOuXtfLhQ/vF/eOdVevvv6ztB/a9lXcHD8r7P9hPN+zSPm5YW3eO9u6/O1ivBuX0U3wD3nytpWfHdw9paELc4V7nT4IUlKoTlpaeZBS52oV3Ko2RnY4mI7PXdk82Svafdyji8dZC+cla+dGvR69d1Gdnh9OjYyPpz8eGrg1/6sikyE4qCkpvyVhPnlqH33u+xQc2cQKKk84caebejPxI+spIOkOS7ObfQDTUSLSvOdGjvWXrux0smX133lp44U5yJbJblUDlSHkKrq9dXcI4SY83G+MT7c8xAjxry8+en/z87cmPv10g/VOvIkzyjffAKtf6Ygk3wkVdi8U6KNmPXluLy00XOu8xe8hKIp9iQApkgiGfYQaIUFGwiYhrW4KpPFdqHX2mQVFlsiNaiYhCyKANpymBaXIwwZaaXveSeKZqg63qI4wwbXKueHJIej9WwBsr6l16yksv7dLtpiL2M0muRYE83tnCq6FJyWokjVtGB5oFOxvH7V3rn63yH2vl1edt8mkFHmof3L1QL3rUtIDbq7v28ra9N19eWbjYseOKUoX9QAoc7S3aa6/szT1r59XJ/HL5cPv/U6DfK/sUubR+/O83H0wEa3vdfvzyaH/fWvrpgoff3uTH98rejSPV9/Qmzu8R+M1mky0Uf3bP5z9jzlXR6J/e/wEGSoi7"


@functools.lru_cache(maxsize=1)
def _external_report_template_html() -> str:
    return zlib.decompress(base64.b64decode(_EXTERNAL_REPORT_TEMPLATE_ZLIB_B64.encode("ascii"))).decode(
        "utf-8"
    )


def _render_external_report_html(
    *,
    version_s2: str,
    version_case_url: str | None,
    regression_case_url: str | None,
) -> str:
    """外网报告：标题版本号与内网同源（xlsx 文件名推导）；I2 版本用例/回归链接插入对应列表项。"""
    tpl = _external_report_template_html()
    html_out = tpl.replace("{{VERSION_S2}}", html.escape(version_s2))
    new_frag = (
        " " + _html_a_href(version_case_url, version_case_url, a_class="s1") if version_case_url else ""
    )
    reg_frag = (
        " " + _html_a_href(regression_case_url, regression_case_url, a_class="s1")
        if regression_case_url
        else ""
    )
    html_out = html_out.replace("{{NEW_REQ_LINK}}", new_frag).replace("{{REGRESSION_LINK}}", reg_frag)
    # 原模板两处独立 ul 会在浏览器里拉出空行；合并为同一 ul 下的连续 li
    html_out = html_out.replace(
        '</li>\n</ul>\n<ul class="ul1">\n  <li class="li3"><span class="s3"></span><span class="s1">回归</span>',
        '</li>\n  <li class="li3"><span class="s3"></span><span class="s1">回归</span>',
        1,
    )
    return _insert_external_checklist_title_spacer(html_out)


def _report_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _project_root() -> Path:
    return _report_root().parent


def _find_venv_python() -> str | None:
    for candidate in (
        _report_root() / ".venv" / "bin" / "python",
        _project_root() / ".venv-xlsx" / "bin" / "python",
        _project_root() / ".venv" / "bin" / "python",
    ):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def _resolve_xlsx_path_and_print_i2_flags(argv: list[str], base_dir: Path) -> tuple[str, bool] | None:
    """从 argv 得到 xlsx 路径与是否只输出 I2 文本。失败时打印错误并返回 None。"""
    want_print_i2 = "--print-i2" in argv
    rest = [a for a in argv[1:] if a != "--print-i2"]
    if rest:
        xlsx_path = rest[0]
        if not os.path.isabs(xlsx_path):
            xlsx_path = str((base_dir / xlsx_path).resolve())
        if not os.path.exists(xlsx_path):
            print(f"找不到文件：{xlsx_path}", file=sys.stderr)
            return None
        return (xlsx_path, want_print_i2)
    xlsx_candidates = sorted(base_dir.glob("*.xlsx"))
    if not xlsx_candidates:
        print(
            f"在目录 {base_dir} 下未找到任何 .xlsx 文件；请指定路径，例如：\n"
            "  python3 Report/report_execute.py /path/to/v2.4.4版本用例.xlsx",
            file=sys.stderr,
        )
        return None
    return (str(xlsx_candidates[0]), want_print_i2)


def main() -> int:
    try:
        from openpyxl import load_workbook
    except ModuleNotFoundError:
        venv_python = _find_venv_python()
        if venv_python:
            entry = str(_report_root() / "report_execute.py")
            os.execv(venv_python, [venv_python, entry, *sys.argv[1:]])
        print(
            "未安装 openpyxl。请先执行：\n"
            "  python3 -m venv Report/.venv\n"
            "  source Report/.venv/bin/activate\n"
            "  python -m pip install -r Report/requirements.txt",
            file=sys.stderr,
        )
        return 2

    base_dir = Path.cwd()
    resolved = _resolve_xlsx_path_and_print_i2_flags(sys.argv, base_dir)
    if resolved is None:
        return 2
    xlsx_path, want_print_i2 = resolved

    try:
        enrich_version_case_xlsx(xlsx_path)
    except OSError as e:
        print(f"回填用例统计失败（继续生成报告）：{e}", file=sys.stderr)

    try:
        wb = load_workbook(xlsx_path, data_only=True, read_only=True)
    except PermissionError:
        print(f"无法读取文件（可能正在被 Excel 占用）：{xlsx_path}", file=sys.stderr)
        return 2
    except OSError as e:
        print(f"读取 Excel 失败：{e}", file=sys.stderr)
        return 2

    # 某些 xlsx 首个 sheet 可能是 hidden 的「AI生成」草稿（I2 为空），
    # 真正的汇总数据在后续 visible sheet 上。若无 Sheet1，优先选 I2 非空的 visible sheet。
    def _pick_i2_sheet_name() -> str:
        if "Sheet1" in wb.sheetnames:
            return "Sheet1"
        visible_names = [
            n for n in wb.sheetnames
            if getattr(wb[n], "sheet_state", "visible") == "visible"
        ]
        for n in visible_names:
            if wb[n]["I2"].value is not None:
                return n
        if visible_names:
            return visible_names[0]
        return wb.sheetnames[0]

    sheet1_name = _pick_i2_sheet_name()
    i2_raw = wb[sheet1_name]["I2"].value

    defect_ver = (
        os.environ.get("REPORT_DEFECT_SCHEDULE_VERSION", "").strip()
        or guess_version_from_xlsx(Path(xlsx_path))
        or ""
    )
    schedule_xlsx = os.environ.get("REPORT_DEFECT_SCHEDULE_XLSX", "").strip()
    if schedule_xlsx and defect_ver:
        merged_i2 = apply_schedule_defects_to_i2(i2_raw, schedule_xlsx, defect_ver)
        if merged_i2:
            i2_raw = merged_i2
    elif defect_ver:
        merged_i2 = apply_bug_url_defects_to_i2(i2_raw, defect_ver)
        if merged_i2:
            i2_raw = merged_i2

    if want_print_i2:
        print(reformat_raw_i2_like_excel(i2_raw))
        return 0

    lines: list[str] = []
    new_titles: list[str] = []
    tech_opt_items: list[str] = []
    new_need_count = 0
    optimize_need_count = 0
    idx = 1
    for name in wb.sheetnames:
        ws = wb[name]
        if getattr(ws, "sheet_state", "visible") != "visible":
            continue
        raw = resolve_sheet_d2_text(ws, name, ws["D2"].value)
        if raw is None:
            continue
        if not raw.strip():
            continue

        parts = [p.strip() for p in raw.splitlines()]
        parts = [p for p in parts if p]
        if not parts:
            continue

        first = parts[0]
        rest = parts[1:]

        heading = (
            f"{TECH_OPT_SECTION_LABEL}："
            if _is_tech_opt_need(first)
            else first
        )
        lines.append(f"{idx}. {heading}")
        if _is_tech_opt_need(first) and rest:
            normalized_rest = []
            for item in rest:
                n = _normalize_subitem(item)
                if n:
                    normalized_rest.append(n)
            for j, item in enumerate(normalized_rest, start=1):
                lines.append(f" {j}）{item}")
            optimize_need_count += len(normalized_rest)
            tech_opt_items.extend(normalized_rest)
        elif not _is_tech_opt_need(first):
            new_need_count += 1
            new_titles.append(first)
        idx += 1

    print(f"本次版本共{new_need_count}个新需求及{optimize_need_count}个优化需求")
    print("\n".join(lines))

    xlsx_file = Path(xlsx_path)
    title_s2_version = resolve_version_s2(xlsx_file.stem)
    out_html = _render_full_report_html(
        title_prefix=title_s2_version,
        new_need_count=new_need_count,
        optimize_need_count=optimize_need_count,
        new_titles=new_titles,
        tech_opt_items=tech_opt_items,
    )
    defect_stats = _parse_sheet1_e2_defect_stats(i2_raw)
    out_html = _inject_defect_stats(out_html, defect_stats)
    defect_tb_url, version_case_url, regression_case_url = resolve_report_links(i2_raw)
    out_html = _inject_report_links(
        out_html,
        defect_tb_url=defect_tb_url,
        version_case_url=version_case_url,
        regression_case_url=regression_case_url,
    )
    out_html = _harden_coverage_table_for_email(out_html)

    html_path = xlsx_file.with_name(f"{xlsx_file.stem}_内网测试总结.html")
    try:
        html_path.write_text(out_html, encoding="utf-8")
    except OSError as e:
        print(f"写入 HTML 失败：{e}", file=sys.stderr)
        return 2
    print(f"已生成：{html_path}", file=sys.stderr)

    ext_src = _render_external_report_html(
        version_s2=title_s2_version,
        version_case_url=version_case_url,
        regression_case_url=regression_case_url,
    )
    ext_html = _harden_external_checklist_table(ext_src, _EXTERNAL_CHECKLIST_TABLE_BORDER)
    ext_path = xlsx_file.with_name(f"{xlsx_file.stem}_外网测试总结.html")
    try:
        ext_path.write_text(ext_html, encoding="utf-8")
    except OSError as e:
        print(f"写入外网 HTML 失败：{e}", file=sys.stderr)
        return 2
    print(
        f"已生成：{ext_path}（外网表线色同内网邮件，可直接复制到邮箱）",
        file=sys.stderr,
    )

    if os.environ.get("COUNT_NO_BROWSER", "").strip().lower() not in ("1", "true", "yes"):
        opened_ext = _open_html_default_browser(ext_path)
        opened_in = _open_html_default_browser(html_path)
        if opened_in and opened_ext:
            print("已用默认浏览器打开外网、内网报告（先外网后内网）。", file=sys.stderr)
        elif opened_in or opened_ext:
            print(
                "已打开部分报告；未能自动打开的文件请手动在访达/资源管理器中打开。",
                file=sys.stderr,
            )
        else:
            print("未能自动打开，请手动在访达/资源管理器中打开上述 HTML。", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
