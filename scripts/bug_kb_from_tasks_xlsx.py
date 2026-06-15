#!/usr/bin/env python3
"""从 Yaahlan 任务信息表 xlsx 提炼历史缺陷，生成 bug-kb/ 知识库。"""

from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
CELL_REF = re.compile(r"^([A-Z]+)(\d+)$")

MODULE_FILES: dict[str, str] = {
    "room": "房间.md",
    "room_pk": "房间PK.md",
    "gift": "礼物.md",
    "family": "家族.md",
    "theme_room": "主题房.md",
    "moments": "动态.md",
    "message": "消息.md",
    "face_auth": "人脸认证.md",
    "auth_login": "注册登录.md",
    "customer_service": "客服.md",
    "super_admin": "超管.md",
    "agency": "公会.md",
    "coin": "充值提现转账.md",
    "game": "游戏.md",
    "rank": "榜单.md",
    "activity": "活动.md",
    "vip": "特权VIP.md",
    "noble": "贵族.md",
    "profile": "个人主页.md",
    "dress": "装扮.md",
    "other": "其他.md",
}

MODULE_TITLES: dict[str, str] = {
    "room": "房间",
    "room_pk": "房间PK",
    "gift": "礼物",
    "family": "家族",
    "theme_room": "主题房",
    "moments": "动态",
    "message": "消息",
    "face_auth": "人脸认证",
    "auth_login": "注册登录",
    "customer_service": "客服",
    "super_admin": "超管",
    "agency": "公会",
    "coin": "充值提现转账",
    "game": "游戏",
    "rank": "榜单",
    "activity": "活动",
    "vip": "特权VIP",
    "noble": "贵族",
    "profile": "个人主页",
    "dress": "装扮",
    "other": "其他",
}

CLASSIFY_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"跨房\s*PK|跨房PK|房间PK|PK分区", re.I), "room_pk"),
    (re.compile(r"主题房|活动房", re.I), "theme_room"),
    (re.compile(r"公会|公会长|工会长|预提|主播薪资|AM系统", re.I), "agency"),
    (re.compile(r"家族|family", re.I), "family"),
    (re.compile(r"动态|Moment|moment|发布与浏览", re.I), "moments"),
    (re.compile(r"VIP|vip|特权", re.I), "vip"),
    (re.compile(r"贵族|noble", re.I), "noble"),
    (re.compile(r"真人认证|人脸|实名认证|id-auth", re.I), "face_auth"),
    (re.compile(r"客服|券包|快捷回复|帮助中心", re.I), "customer_service"),
    (re.compile(r"超管|审核后台|设备拉黑|工单", re.I), "super_admin"),
    (re.compile(r"游戏|gamebridge|大冒险|概率游戏|蠢鸟|足球", re.I), "game"),
    (re.compile(r"榜单|排行|月榜|周榜|小时榜|荣誉墙|打榜|揭榜|全服榜", re.I), "rank"),
    (re.compile(r"活动|活动条|摩天轮|每日任务|活动运营|转盘|抽奖|盛典|节", re.I), "activity"),
    (re.compile(r"充值|提现|转账|钻石|钱包|支付|币商|首充|明细", re.I), "coin"),
    (re.compile(r"礼物|背包|盲盒|送礼|勋章|徽章|展馆|装扮|头像框|商城|座驾", re.I), "gift"),
    (re.compile(r"私聊|群聊|IM|消息|好友|招呼|关系|CP|亲密度|谁看过我", re.I), "message"),
    (re.compile(r"个人主页|profile|资料页|资料卡|靓号", re.I), "profile"),
    (re.compile(r"注册|登录|注销|绑定|密码|账号安全|设备安全", re.I), "auth_login"),
    (re.compile(r"麦位|进房|语音房|房间|红包|宝箱|解散房间|管理员|小时榜", re.I), "room"),
]

HIGH_SEVERITY = {"严重", "阻碍", "1", "2"}


@dataclass
class BugRecord:
    bug_id: str
    title: str
    platform: str
    module_field: str
    status: str
    severity: str
    defect_type: str
    defect_category: str
    iteration: str
    remark: str
    solution: str
    created: str
    completed: str
    repro: str
    actual: str
    expected: str
    creator: str = ""
    executor: str = ""
    participants: str = ""
    qa_owner: str = ""
    product_owner: str = ""
    ui_reviewer: str = ""
    module_key: str = "other"

    @property
    def is_high_severity(self) -> bool:
        return self.severity in HIGH_SEVERITY

    @property
    def year(self) -> str:
        if self.created and len(self.created) >= 4:
            return self.created[:4]
        return "未知"


def _col_row(ref: str) -> tuple[str, int]:
    match = CELL_REF.match(ref)
    if not match:
        raise ValueError(f"无效单元格: {ref}")
    return match.group(1), int(match.group(2))


def load_sheet_rows(xlsx_path: Path) -> dict[int, dict[str, str]]:
    with zipfile.ZipFile(xlsx_path) as zf:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in zf.namelist():
            root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for si in root.findall("m:si", NS):
                texts = [node.text or "" for node in si.findall(".//m:t", NS)]
                shared.append("".join(texts))
        sheet = ET.fromstring(zf.read("xl/worksheets/sheet1.xml"))
        rows: dict[int, dict[str, str]] = {}
        for cell in sheet.findall(".//m:sheetData/m:row/m:c", NS):
            ref = cell.get("r")
            if not ref:
                continue
            col, row = _col_row(ref)
            cell_type = cell.get("t")
            value_node = cell.find("m:v", NS)
            value = value_node.text if value_node is not None else ""
            if cell_type == "s" and value:
                value = shared[int(value)]
            rows.setdefault(row, {})[col] = str(value).strip()
    return rows


def build_field_map(header_row: dict[str, str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for col, raw_name in header_row.items():
        name = raw_name.replace("\x83", "").strip()
        mapping[col] = name
    return mapping


def pick(row: dict[str, str], field_map: dict[str, str], *keywords: str) -> str:
    for col, name in field_map.items():
        for keyword in keywords:
            if keyword in name:
                return row.get(col, "")
    return ""


def clean_markdown_text(text: str) -> str:
    text = text.replace("\\.", ".")
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def parse_remark_sections(remark: str) -> tuple[str, str, str]:
    if not remark:
        return "", "", ""

    patterns = {
        "repro": re.compile(r"\*\*重现步骤\*\*\s*(.*?)(?=\*\*测试结果\*\*|\*\*期望结果\*\*|$)", re.S | re.I),
        "actual": re.compile(r"\*\*测试结果\*\*\s*(.*?)(?=\*\*期望结果\*\*|$)", re.S | re.I),
        "expected": re.compile(r"\*\*期望结果\*\*\s*(.*)$", re.S | re.I),
    }
    sections = {key: "" for key in patterns}
    for key, pattern in patterns.items():
        match = pattern.search(remark)
        if match:
            sections[key] = clean_markdown_text(match.group(1))
    if not any(sections.values()):
        return "", clean_markdown_text(remark), ""
    return sections["repro"], sections["actual"], sections["expected"]


def classify_bug(title: str, module_field: str, remark: str) -> str:
    if module_field.strip():
        blob = module_field
    else:
        blob = f"{title} {remark[:200]}"
    for pattern, module_key in CLASSIFY_RULES:
        if pattern.search(blob):
            return module_key
    return "other"


_CATEGORY_TYPE_KEYWORDS = frozenset(
    {"版本线", "非版本线", "活动线", "线上问题", "待优化问题", "马甲包", "遗留问题"}
)
_VERSION_LIKE = re.compile(r"版本|yaahlan\d|\d+\.\d+", re.I)


def parse_defect_category(category: str) -> dict[str, str]:
    """解析缺陷分类路径，提取汇总根、归属类型、版本号等。"""
    raw = category.strip()
    if not raw:
        return {}

    parts = [part.strip() for part in re.split(r"\s*/\s*", raw) if part.strip()]
    if not parts:
        return {"full": raw}

    result: dict[str, str] = {"full": raw, "summary_root": parts[0]}
    category_type = ""
    version = ""
    sub_category = ""

    if len(parts) == 1:
        return result

    second = parts[1]
    if second in _CATEGORY_TYPE_KEYWORDS:
        category_type = second
        if len(parts) >= 3:
            tail = parts[-1]
            if _VERSION_LIKE.search(tail):
                version = tail
            else:
                sub_category = tail
    elif _VERSION_LIKE.search(second):
        version = second
    else:
        category_type = second
        if len(parts) >= 3:
            tail = parts[-1]
            if _VERSION_LIKE.search(tail):
                version = tail
            else:
                sub_category = tail

    if category_type:
        result["category_type"] = category_type
    if version:
        result["version"] = version
    if sub_category:
        result["sub_category"] = sub_category
    return result


def render_category_lines(record: BugRecord) -> list[str]:
    if not record.defect_category:
        return []

    parsed = parse_defect_category(record.defect_category)
    lines = [f"- **缺陷分类**：{parsed['full']}"]
    details: list[str] = []
    if parsed.get("category_type"):
        details.append(f"归属 {parsed['category_type']}")
    if parsed.get("version"):
        details.append(f"版本 {parsed['version']}")
    if parsed.get("sub_category"):
        details.append(f"子类 {parsed['sub_category']}")
    if parsed.get("summary_root") and len(parsed["full"].split("/")) > 1:
        details.append(f"汇总 {parsed['summary_root']}")
    if details:
        lines.append(f"- **版本归属**：{' · '.join(details)}")
    return lines


def record_from_row(row: dict[str, str], field_map: dict[str, str], row_num: int) -> BugRecord:
    title = pick(row, field_map, "标题")
    remark = pick(row, field_map, "备注")
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
        defect_category=pick(row, field_map, "缺陷分类"),
        iteration=pick(row, field_map, "迭代"),
        remark=remark,
        solution=pick(row, field_map, "解决方案"),
        created=pick(row, field_map, "创建时间")[:10],
        completed=pick(row, field_map, "完成时间")[:10],
        repro=repro,
        actual=actual,
        expected=expected,
        creator=pick(row, field_map, "创建者"),
        executor=pick(row, field_map, "执行者"),
        participants=pick(row, field_map, "参与者"),
        qa_owner=pick(row, field_map, "QA负责人"),
        product_owner=pick(row, field_map, "产品负责人"),
        ui_reviewer=pick(row, field_map, "UI验收人"),
    )
    record.module_key = classify_bug(title, module_field, remark)
    return record


def load_bugs(xlsx_path: Path) -> list[BugRecord]:
    rows = load_sheet_rows(xlsx_path)
    field_map = build_field_map(rows[1])
    bugs: list[BugRecord] = []
    for row_num in range(2, max(rows) + 1):
        row = rows[row_num]
        if pick(row, field_map, "任务类型") != "缺陷":
            continue
        bugs.append(record_from_row(row, field_map, row_num))
    return bugs


def summarize_one_line(record: BugRecord) -> str:
    for candidate in (record.actual, record.expected, record.title):
        if candidate:
            return candidate[:160]
    return record.title[:160]


def render_personnel_line(record: BugRecord) -> str:
    parts: list[str] = []
    if record.creator:
        parts.append(f"提交 {record.creator}")
    if record.executor:
        parts.append(f"处理 {record.executor}")
    if record.participants:
        parts.append(f"参与 {record.participants}")
    if record.qa_owner:
        parts.append(f"QA {record.qa_owner}")
    if record.product_owner:
        parts.append(f"产品 {record.product_owner}")
    if record.ui_reviewer:
        parts.append(f"UI验收 {record.ui_reviewer}")
    return " · ".join(parts)


def render_bug_entry(record: BugRecord) -> list[str]:
    lines = [
        f"#### {record.bug_id} · {record.title}",
        "",
        f"- **端**：{record.platform} · **严重度**：{record.severity} · **状态**：{record.status}"
        f" · **类型**：{record.defect_type} · **迭代**：{record.iteration or '-'}",
    ]
    if record.created:
        lines[-1] += f" · **创建**：{record.created}"
    personnel = render_personnel_line(record)
    if personnel:
        lines.append(f"- **人员**：{personnel}")
    lines.extend(render_category_lines(record))
    summary = summarize_one_line(record)
    if summary and summary != record.title:
        lines.append(f"- **摘要**：{summary}")
    if record.repro:
        lines.append(f"- **重现**：{record.repro[:300]}")
    if record.actual:
        lines.append(f"- **现象**：{record.actual[:300]}")
    if record.expected:
        lines.append(f"- **期望**：{record.expected[:300]}")
    if record.solution:
        lines.append(f"- **解决方案**：{record.solution[:200]}")
    lines.append("")
    return lines


def render_module_doc(module_key: str, records: list[BugRecord]) -> str:
    title = MODULE_TITLES[module_key]
    high = [r for r in records if r.is_high_severity]
    by_year: dict[str, list[BugRecord]] = defaultdict(list)
    for record in records:
        by_year[record.year].append(record)

    lines = [
        f"# {title} · 历史缺陷",
        "",
        "> **文档类型**：Yaahlan 历史 Bug 知识库（由任务信息表自动提炼）",
        "> **用途**：回归测试、相似场景排查、模块风险参考（非逐条执行用例）",
        "",
        "## 概览",
        "",
        f"| 指标 | 值 |",
        f"|------|-----|",
        f"| 缺陷总数 | {len(records)} |",
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
        lines.extend(["## 严重缺陷（优先回归）", ""])
        for record in sorted(high, key=lambda r: r.created, reverse=True)[:30]:
            lines.extend(render_bug_entry(record))
        if len(high) > 30:
            lines.append(f"> 另有 {len(high) - 30} 条严重/阻碍缺陷，见下方按年归档。")
            lines.append("")

    lines.extend(["## 按年归档", ""])
    for year in sorted(by_year, reverse=True):
        year_records = sorted(by_year[year], key=lambda r: r.created, reverse=True)
        lines.append(f"### {year}（{len(year_records)}）")
        lines.append("")
        for record in year_records:
            lines.extend(render_bug_entry(record))

    return "\n".join(lines).rstrip() + "\n"


def render_readme(bugs: list[BugRecord], source_path: Path, generated_at: str) -> str:
    by_module: dict[str, list[BugRecord]] = defaultdict(list)
    for bug in bugs:
        by_module[bug.module_key].append(bug)

    lines = [
        "# bug-kb · Bug 知识库",
        "",
        "> **文档类型**：历史缺陷归档（由钉钉/Teambition 任务信息表提炼）",
        f"> **数据来源**：`{source_path}`",
        f"> **生成时间**：{generated_at}",
        "",
        "## 说明",
        "",
        "本目录归档 Yaahlan 项目历史 **缺陷（任务类型=缺陷）**，按业务模块拆分，供：",
        "",
        "- 版本回归时查阅同模块历史问题",
        "- 生成测试用例时补充异常/边界参考",
        "- 排查相似现象是否已有历史记录",
        "",
        "每条缺陷保留：**任务ID、标题、端、严重度、状态、迭代、缺陷分类、版本归属、人员、现象/期望**"
        "（缺陷分类含版本线/线上问题等路径；人员含提交/处理/参与等；现象从备注解析）。",
        "模块文件按标题与备注关键词自动推断（`所属模块` 字段在源表中几乎为空）。",
        "",
        "## 统计",
        "",
        f"| 指标 | 值 |",
        f"|------|-----|",
        f"| 缺陷总数 | {len(bugs)} |",
        f"| 已关闭 | {sum(1 for b in bugs if b.status == '已关闭')} |",
        f"| 待处理 | {sum(1 for b in bugs if b.status == '待处理')} |",
        f"| 严重/阻碍 | {sum(1 for b in bugs if b.is_high_severity)} |",
        "",
        "### 端分布",
        "",
    ]
    for platform, count in Counter(b.platform for b in bugs).most_common(12):
        lines.append(f"- **{platform}**：{count}")

    version_counter: Counter[str] = Counter()
    category_type_counter: Counter[str] = Counter()
    for bug in bugs:
        parsed = parse_defect_category(bug.defect_category)
        if parsed.get("version"):
            version_counter[parsed["version"]] += 1
        if parsed.get("category_type"):
            category_type_counter[parsed["category_type"]] += 1

    if category_type_counter:
        lines.extend(["", "### 缺陷归属 Top", ""])
        for category_type, count in category_type_counter.most_common(8):
            lines.append(f"- **{category_type}**：{count}")

    if version_counter:
        lines.extend(["", "### 版本归属 Top", ""])
        for version, count in version_counter.most_common(12):
            lines.append(f"- **{version}**：{count}")

    lines.extend(["", "### 模块索引", "", "| 模块 | 文件 | 数量 |", "|------|------|------|"])
    for module_key in sorted(by_module, key=lambda k: (-len(by_module[k]), k)):
        filename = MODULE_FILES[module_key]
        lines.append(f"| {MODULE_TITLES[module_key]} | [`{filename}`]({filename}) | {len(by_module[module_key])} |")
    lines.extend(
        [
            "",
            "## 维护",
            "",
            "```bash",
            "python3 scripts/bug_kb_from_tasks_xlsx.py \\",
            f"  --source '{source_path}'",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def generate_kb(source: Path, output_dir: Path) -> dict[str, int]:
    bugs = load_bugs(source)
    if not bugs:
        raise ValueError("未解析到任何缺陷记录")

    by_module: dict[str, list[BugRecord]] = defaultdict(list)
    for bug in bugs:
        by_module[bug.module_key].append(bug)

    output_dir.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    readme = render_readme(bugs, source, generated_at)
    (output_dir / "README.md").write_text(readme, encoding="utf-8")

    counts: dict[str, int] = {}
    for module_key, records in by_module.items():
        filename = MODULE_FILES.get(module_key, "其他.md")
        content = render_module_doc(module_key, records)
        (output_dir / filename).write_text(content, encoding="utf-8")
        counts[filename] = len(records)
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description="从 Yaahlan 任务信息表生成 Bug 知识库")
    parser.add_argument(
        "--source",
        default="/Users/user/Desktop/【yaahlan】任务信息表_20260529 15.37.14.xlsx",
        help="任务信息表 xlsx 路径",
    )
    parser.add_argument(
        "--output",
        default=str(Path(__file__).resolve().parent.parent / "bug-kb"),
        help="输出目录（默认 bug-kb）",
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
    print(f"total bugs: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
