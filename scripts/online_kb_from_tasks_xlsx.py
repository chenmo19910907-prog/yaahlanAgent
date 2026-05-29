#!/usr/bin/env python3
"""从 Yaahlan 任务信息表 xlsx 提炼历史线上问题，生成 online-kb/ 知识库。"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from bug_kb_from_tasks_xlsx import (
    MODULE_FILES,
    MODULE_TITLES,
    BugRecord,
    classify_bug,
    load_sheet_rows,
    build_field_map,
    pick,
    parse_remark_sections,
    render_bug_entry,
)

ONLINE_CATEGORY_RE = re.compile(r"/ 线上问题(?: /|$)")
ONLINE_TITLE_RE = re.compile(
    r"【线上问题】|【线上包】|【线上】|「线上问题|\[线上问题\]|线上也有这个问题|"
    r"Hotfix|hotfix|紧急修复|现网问题|生产问题",
    re.I,
)
ONLINE_TITLE_EXCLUDE_RE = re.compile(
    r"线上音乐|本地音乐|添加线上/|添加线上音乐|公会薪资线上化",
    re.I,
)


def is_online_issue(*, defect_category: str, title: str, remark: str) -> bool:
    if defect_category and ONLINE_CATEGORY_RE.search(defect_category):
        if "公会薪资线上化" in defect_category:
            return False
        return True
    if ONLINE_TITLE_EXCLUDE_RE.search(title):
        return False
    if ONLINE_TITLE_RE.search(title):
        return True
    if remark and ONLINE_TITLE_RE.search(remark[:300]):
        return True
    return False


def load_online_issues(xlsx_path: Path) -> list[BugRecord]:
    rows = load_sheet_rows(xlsx_path)
    field_map = build_field_map(rows[1])
    issues: list[BugRecord] = []
    for row_num in range(2, max(rows) + 1):
        row = rows[row_num]
        if pick(row, field_map, "任务类型") != "缺陷":
            continue
        title = pick(row, field_map, "标题")
        remark = pick(row, field_map, "备注")
        defect_category = pick(row, field_map, "缺陷分类")
        if not is_online_issue(defect_category=defect_category, title=title, remark=remark):
            continue
        repro, actual, expected = parse_remark_sections(remark)
        module_field = pick(row, field_map, "所属模块")
        record = BugRecord(
            bug_id=pick(row, field_map, "任务ID") or f"ROW-{row_num}",
            title=title,
            platform=pick(row, field_map, "所属平台") or "未知",
            module_field=module_field,
            status=pick(row, field_map, "任务状态"),
            severity=pick(row, field_map, "严重程度") or "未知",
            defect_type=pick(row, field_map, "缺陷类型") or "未知",
            defect_category=defect_category,
            iteration=pick(row, field_map, "迭代"),
            remark=remark,
            solution=pick(row, field_map, "解决方案"),
            created=pick(row, field_map, "创建时间")[:10],
            completed=pick(row, field_map, "完成时间")[:10],
            repro=repro,
            actual=actual,
            expected=expected,
        )
        record.module_key = classify_bug(title, module_field, remark)
        issues.append(record)
    return issues


def render_online_entry(record: BugRecord) -> list[str]:
    lines = render_bug_entry(record)
    if record.defect_category:
        lines.insert(3, f"- **分类**：{record.defect_category}")
    return lines


def render_module_doc(module_key: str, records: list[BugRecord]) -> str:
    title = MODULE_TITLES[module_key]
    high = [r for r in records if r.is_high_severity]
    by_year: dict[str, list[BugRecord]] = defaultdict(list)
    for record in records:
        by_year[record.year].append(record)

    lines = [
        f"# {title} · 历史线上问题",
        "",
        "> **文档类型**：Yaahlan 线上问题知识库（由任务信息表自动提炼）",
        "> **用途**：现网问题回归、相似线上故障排查（非逐条执行用例）",
        "",
        "## 概览",
        "",
        "| 指标 | 值 |",
        "|------|-----|",
        f"| 线上问题总数 | {len(records)} |",
        f"| 严重/阻碍 | {len(high)} |",
        f"| 已关闭 | {sum(1 for r in records if r.status == '已关闭')} |",
        f"| 待处理 | {sum(1 for r in records if r.status == '待处理')} |",
        "",
    ]

    platform_counter = Counter(r.platform for r in records)
    if platform_counter:
        lines.extend(["### 端分布", ""])
        for platform, count in platform_counter.most_common(8):
            lines.append(f"- **{platform}**：{count}")
        lines.append("")

    if high:
        lines.extend(["## 严重线上问题（优先回归）", ""])
        for record in sorted(high, key=lambda r: r.created, reverse=True)[:30]:
            lines.extend(render_online_entry(record))
        if len(high) > 30:
            lines.append(f"> 另有 {len(high) - 30} 条严重/阻碍线上问题，见下方按年归档。")
            lines.append("")

    lines.extend(["## 按年归档", ""])
    for year in sorted(by_year, reverse=True):
        year_records = sorted(by_year[year], key=lambda r: r.created, reverse=True)
        lines.append(f"### {year}（{len(year_records)}）")
        lines.append("")
        for record in year_records:
            lines.extend(render_online_entry(record))

    return "\n".join(lines).rstrip() + "\n"


def render_readme(issues: list[BugRecord], source_path: Path, generated_at: str) -> str:
    by_module: dict[str, list[BugRecord]] = defaultdict(list)
    for issue in issues:
        by_module[issue.module_key].append(issue)

    by_cat = Counter(i.defect_category for i in issues if i.defect_category)

    lines = [
        "# online-kb · 线上问题知识库",
        "",
        "> **文档类型**：历史线上问题归档（由钉钉/Teambition 任务信息表提炼）",
        f"> **数据来源**：`{source_path}`",
        f"> **生成时间**：{generated_at}",
        "",
        "## 说明",
        "",
        "本目录归档 Yaahlan 项目 **线上问题**（生产/现网反馈缺陷的子集），按业务模块拆分，供：",
        "",
        "- 发版回归时重点核对现网历史故障场景",
        "- 排查用户反馈是否与已知线上问题重复",
        "- 生成测试用例时补充现网异常参考",
        "",
        "**纳入规则**（满足其一）：",
        "",
        "- `缺陷分类` 路径含 `/ 线上问题`（如 `2025-yaahlan版本问题汇总 / 线上问题`）",
        "- 标题/备注标注 `【线上问题】`、`【线上包】`、`【线上】`、`线上也有` 等",
        "",
        "与 [`bug-kb/`](../bug-kb/README.md) 的关系：bug-kb 含全部缺陷；online-kb 为其中 **线上问题** 子集。",
        "",
        "## 统计",
        "",
        "| 指标 | 值 |",
        "|------|-----|",
        f"| 线上问题总数 | {len(issues)} |",
        f"| 已关闭 | {sum(1 for i in issues if i.status == '已关闭')} |",
        f"| 待处理 | {sum(1 for i in issues if i.status == '待处理')} |",
        f"| 严重/阻碍 | {sum(1 for i in issues if i.is_high_severity)} |",
        "",
        "### 缺陷分类 Top",
        "",
    ]
    for category, count in by_cat.most_common(8):
        lines.append(f"- **{category}**：{count}")
    lines.extend(["", "### 端分布", ""])
    for platform, count in Counter(i.platform for i in issues).most_common(12):
        lines.append(f"- **{platform}**：{count}")
    lines.extend(["", "### 模块索引", "", "| 模块 | 文件 | 数量 |", "|------|------|------|"])
    for module_key in sorted(by_module, key=lambda k: (-len(by_module[k]), k)):
        filename = MODULE_FILES[module_key]
        lines.append(
            f"| {MODULE_TITLES[module_key]} | [`{filename}`]({filename}) | {len(by_module[module_key])} |"
        )
    lines.extend(
        [
            "",
            "## 维护",
            "",
            "```bash",
            "python3 scripts/online_kb_from_tasks_xlsx.py \\",
            f"  --source '{source_path}'",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def generate_kb(source: Path, output_dir: Path) -> dict[str, int]:
    issues = load_online_issues(source)
    if not issues:
        raise ValueError("未解析到任何线上问题记录")

    by_module: dict[str, list[BugRecord]] = defaultdict(list)
    for issue in issues:
        by_module[issue.module_key].append(issue)

    output_dir.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    (output_dir / "README.md").write_text(render_readme(issues, source, generated_at), encoding="utf-8")

    counts: dict[str, int] = {}
    for module_key, records in by_module.items():
        filename = MODULE_FILES.get(module_key, "其他.md")
        (output_dir / filename).write_text(render_module_doc(module_key, records), encoding="utf-8")
        counts[filename] = len(records)
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description="从 Yaahlan 任务信息表生成线上问题知识库")
    parser.add_argument(
        "--source",
        default="/Users/user/Desktop/【yaahlan】任务信息表_20260529.xlsx",
        help="任务信息表 xlsx 路径",
    )
    parser.add_argument(
        "--output",
        default=str(Path(__file__).resolve().parent.parent / "online-kb"),
        help="输出目录（默认 online-kb）",
    )
    args = parser.parse_args()

    source = Path(args.source).expanduser()
    output = Path(args.output)
    if not source.is_file():
        print(f"找不到源文件: {source}", file=sys.stderr)
        return 1

    try:
        counts = generate_kb(source, output)
    except ValueError as exc:
        print(f"生成失败: {exc}", file=sys.stderr)
        return 2

    total = sum(counts.values())
    print(f"generated README + {len(counts)} module files under {output}")
    for name in sorted(counts, key=lambda n: (-counts[n], n)):
        print(f"  {name}: {counts[name]}")
    print(f"total online issues: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
