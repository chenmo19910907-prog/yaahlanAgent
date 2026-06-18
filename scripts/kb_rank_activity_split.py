#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""榜单与活动知识库拆分为 榜单.md / 活动.md，并提供归类规则供同步流水线复用。"""

from __future__ import annotations

import argparse
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent

KB_RANK_FILE = "榜单.md"
KB_ACTIVITY_FILE = "活动.md"

BUG_ENTRY_RE = re.compile(r"^####\s+YAAH-\d+", re.M)
HIGH_SEVERITY = frozenset({"严重", "阻碍", "1", "2"})

# 明确归入「榜单」的 ## 业务主题（其余默认「活动」）
RANK_SHEET_TITLES = frozenset(
    {
        "App分享",
        "Room页增加核心榜单独立入口、展示优化",
        "room页榜单调整",
        "test111",
        "全服榜单",
        "全服榜单查看滑动正常",
        "全站排行榜的飘屏通知",
        "房间榜单",
        "房间顶部榜单优化",
        "打榜冲刺",
        "排行榜",
        "排行榜荣誉墙",
        "揭榜",
        "新增币商客户榜单",
        "榜单",
        "榜单ui修改不跟版",
        "榜单ui调整",
        "榜单冲刺",
        "榜单冲刺对战对象优化",
        "榜单升级",
        "榜单排名外显",
        "榜单重构",
        "私聊/动态 送收礼计入到全服榜单计算中",
    }
)

RANK_TEXT_PATTERNS: Tuple[re.Pattern[str], ...] = (
    re.compile(r"榜单|排行榜|全服榜|打榜|揭榜|荣誉墙|榜种|上榜", re.I),
)

ACTIVITY_TEXT_PATTERNS: Tuple[re.Pattern[str], ...] = (
    re.compile(
        r"活动|周年庆|万圣节|世界杯|开斋|盲盒|宝藏猎人|摩天轮|年末盛典|"
        r"幸运之王|大乐透|轮盘|星座联盟|礼物代言人|谁是大赢家|"
        r"房主挑战赛|每日任务|活动运营|活动条|活动大入口|活动后台|"
        r"cp活动|cp玩法|自定义表情",
        re.I,
    ),
)


def classify_rank_or_activity(
    sheet: str,
    *,
    module: str = "",
    body: str = "",
) -> str:
    """返回 ``rank`` 或 ``activity``。"""
    title = (sheet or "").strip()
    if title in RANK_SHEET_TITLES:
        return "rank"
    if re.search(
        r"^活动[·运营]|活动运营·|榜单与活动·|周年庆|万圣节|世界杯|开斋|"
        r"CP摩天轮|cp活动|每日任务|宝藏猎人|大乐透|盲盒|年末盛典|"
        r"幸运之王|星座联盟|礼物代言人|谁是大赢家|房主挑战赛|"
        r"^VIP改版$|^iOS优化$|^优化点$|^优化需求$|^其他需求$|"
        r"^个人详情页$|^分区策略优化$|^房间功能回归$|^工会$|"
        r"^voga-mts|^取消头像|^启动app预加载|^大区定义|"
        r"^第一阶段$|^第二阶段$|^第三阶段$|^真人认证$|^自定义表情$",
        title,
        re.I,
    ):
        return "activity"
    if re.search(r"榜单|排行榜|全服榜|打榜|揭榜|荣誉墙|room页榜单", title, re.I):
        return "rank"
    blob = f"{sheet} {module} {body}"
    if any(p.search(blob) for p in ACTIVITY_TEXT_PATTERNS):
        return "activity"
    if any(p.search(title) for p in RANK_TEXT_PATTERNS):
        return "rank"
    if any(p.search(blob) for p in RANK_TEXT_PATTERNS):
        return "rank"
    return "activity"


def classify_bug_entry(title: str, body: str) -> str:
    """缺陷/线上问题条目归类。"""
    blob = f"{title} {body}"
    if re.search(r"/ 活动线 /|活动线 /", blob):
        return "activity"
    if re.search(
        r"【榜单】|榜单独立入口|room页.*榜单|核心榜单|月榜|周榜|小时榜|"
        r"财富.*榜|排行榜|全服榜|打榜|揭榜|荣誉墙|铭牌奖励",
        blob,
        re.I,
    ):
        if re.search(r"宝藏猎人|转盘|充值大转盘", title, re.I):
            return "activity"
        return "rank"
    bracket = re.search(r"【([^】]+)】", title)
    if bracket:
        inner = bracket.group(1)
        if re.search(r"活动|转盘|盛典|节|猎人|邀约|充值", inner, re.I):
            if not re.search(r"榜单|排行", inner, re.I):
                return "activity"
        return classify_rank_or_activity(inner, body=body)
    return classify_rank_or_activity(title, body=body)


def _parse_bug_entries(text: str) -> List[Tuple[str, str]]:
    """解析 bug/online 归档中的 #### YAAH- 条目。"""
    matches = list(BUG_ENTRY_RE.finditer(text))
    if not matches:
        return []
    entries: List[Tuple[str, str]] = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        chunk = text[start:end].strip()
        title_line = chunk.split("\n", 1)[0]
        title = title_line.replace("#### ", "", 1).strip()
        entries.append((title, chunk))
    return entries


def _entry_stats(entries: List[Tuple[str, str]]) -> dict:
    total = len(entries)
    high = 0
    closed = 0
    pending = 0
    platforms: Counter[str] = Counter()
    years: Counter[str] = Counter()
    for _title, body in entries:
        sev_m = re.search(r"\*\*严重度\*\*：([^·]+)", body)
        if sev_m and sev_m.group(1).strip() in HIGH_SEVERITY:
            high += 1
        status_m = re.search(r"\*\*状态\*\*：([^·]+)", body)
        if status_m:
            status = status_m.group(1).strip()
            if status == "已关闭":
                closed += 1
            elif status == "待处理":
                pending += 1
        plat_m = re.search(r"\*\*端\*\*：([^·]+)", body)
        if plat_m:
            platforms[plat_m.group(1).strip()] += 1
        created_m = re.search(r"\*\*创建\*\*：(\d{4})", body)
        if created_m:
            years[created_m.group(1)] += 1
    return {
        "total": total,
        "high": high,
        "closed": closed,
        "pending": pending,
        "platforms": platforms,
        "years": years,
    }


def _build_bug_archive(
    module_title: str,
    entries: List[Tuple[str, str]],
    *,
    online: bool = False,
) -> str:
    stats = _entry_stats(entries)
    kind = "历史线上问题" if online else "历史缺陷"
    lines = [
        f"# {module_title} · {kind}",
        "",
        f"> **文档类型**：Yaahlan {kind}知识库（由任务信息表自动提炼）",
        "> **用途**：回归测试、相似场景排查、模块风险参考（非逐条执行用例）"
        if not online
        else "> **用途**：现网问题回归、相似线上故障排查（非逐条执行用例）",
        "",
        "## 概览",
        "",
        "| 指标 | 值 |",
        "|------|-----|",
        f"| {'线上问题总数' if online else '缺陷总数'} | {stats['total']} |",
        f"| 严重/阻碍 | {stats['high']} |",
        f"| 已关闭 | {stats['closed']} |",
        f"| 待处理 | {stats['pending']} |",
        "",
    ]
    if stats["platforms"]:
        lines.extend(["### 端分布", ""])
        for platform, count in stats["platforms"].most_common(8):
            lines.append(f"- **{platform}**：{count}")
        lines.append("")

    high_entries = []
    for title, body in entries:
        sev_m = re.search(r"\*\*严重度\*\*：([^·]+)", body)
        if sev_m and sev_m.group(1).strip() in HIGH_SEVERITY:
            high_entries.append((title, body))
    if high_entries:
        header = "## 严重线上问题（优先回归）" if online else "## 严重缺陷（优先回归）"
        lines.extend([header, ""])
        for _title, body in high_entries[:30]:
            lines.append(body)
            lines.append("")
        if len(high_entries) > 30:
            lines.append(
                f"> 另有 {len(high_entries) - 30} 条严重/阻碍"
                f"{'线上问题' if online else '缺陷'}，见下方按年归档。"
            )
            lines.append("")

    by_year: Dict[str, List[str]] = defaultdict(list)
    for title, body in entries:
        created_m = re.search(r"\*\*创建\*\*：(\d{4})", body)
        year = created_m.group(1) if created_m else "未知"
        by_year[year].append(body)
    lines.extend(["## 按年归档", ""])
    for year in sorted(by_year, reverse=True):
        chunks = by_year[year]
        lines.append(f"### {year}（{len(chunks)}）")
        lines.append("")
        for body in chunks:
            lines.append(body)
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def split_bug_archive_file(
    src: Path,
    *,
    rank_out: Path,
    activity_out: Path,
    online: bool = False,
    remove_src: bool = True,
) -> Tuple[int, int]:
    text = src.read_text(encoding="utf-8")
    entries = _parse_bug_entries(text)
    rank_entries: List[Tuple[str, str]] = []
    activity_entries: List[Tuple[str, str]] = []
    for title, body in entries:
        if classify_bug_entry(title, body) == "rank":
            rank_entries.append((title, body))
        else:
            activity_entries.append((title, body))
    rank_out.write_text(
        _build_bug_archive("榜单", rank_entries, online=online),
        encoding="utf-8",
    )
    activity_out.write_text(
        _build_bug_archive("活动", activity_entries, online=online),
        encoding="utf-8",
    )
    if remove_src:
        src.unlink()
    return len(rank_entries), len(activity_entries)


def split_prd_file(
    src: Path,
    *,
    rank_out: Path,
    activity_out: Path,
    remove_src: bool = True,
) -> Tuple[int, int]:
    return split_file(src, rank_out=rank_out, activity_out=activity_out, remove_src=remove_src)


def split_all_knowledge_bases() -> None:
    jobs = [
        ("prd-kb", split_prd_file, False),
        ("bug-kb", split_bug_archive_file, False),
    ]
    for folder, splitter, online in jobs:
        src = REPO_ROOT / folder / "榜单与活动.md"
        if not src.is_file():
            print(f"跳过 {folder}: 无 榜单与活动.md")
            continue
        rank_out = REPO_ROOT / folder / KB_RANK_FILE
        activity_out = REPO_ROOT / folder / KB_ACTIVITY_FILE
        if splitter is split_prd_file:
            n_rank, n_act = split_prd_file(src, rank_out=rank_out, activity_out=activity_out)
        else:
            n_rank, n_act = split_bug_archive_file(
                src, rank_out=rank_out, activity_out=activity_out, online=online
            )
        print(f"{folder}: 榜单 {n_rank} · 活动 {n_act}")


def sheet_anchor(sheet: str) -> str:
    s = unicodedata.normalize("NFKC", sheet).strip().lower()
    s = re.sub(r"[^\w\u4e00-\u9fff]+", "-", s, flags=re.UNICODE)
    s = re.sub(r"-+", "-", s).strip("-")
    return s[:80] or "sheet"


def _parse_header_and_sections(text: str) -> Tuple[str, Dict[str, str]]:
    """返回 (文首元数据块, {sheet标题: 正文})。"""
    lines = text.replace("\r\n", "\n").split("\n")
    first_h2 = next((i for i, ln in enumerate(lines) if ln.startswith("## ")), None)
    if first_h2 is None:
        raise ValueError("未找到 ## 章节")
    preamble = "\n".join(lines[:first_h2]).strip()

    sections: Dict[str, str] = {}
    current_title: str | None = None
    buf: List[str] = []

    for ln in lines[first_h2:]:
        if ln.startswith("## "):
            if current_title is not None:
                sections[current_title] = "\n".join(buf).strip()
            title = ln[3:].strip()
            if title == "目录":
                current_title = None
                buf = []
                continue
            current_title = title
            buf = []
            continue
        if current_title is not None:
            buf.append(ln)
    if current_title is not None:
        sections[current_title] = "\n".join(buf).strip()
    return preamble, sections


def _adapt_preamble(preamble: str, title: str) -> str:
    lines = preamble.split("\n")
    if lines and lines[0].startswith("# "):
        lines[0] = f"# {title}"
    return "\n".join(lines)


def _build_file(title: str, preamble: str, sections: Dict[str, str]) -> str:
    sheet_names = sorted(sections.keys())
    toc = ["## 目录", "", "以下为文内业务主题索引。", ""]
    for sn in sheet_names:
        toc.append(f"- {sn}")
    toc.append("")

    parts = [_adapt_preamble(preamble, title), "", "\n".join(toc), "---", ""]
    for sn in sheet_names:
        body = sections[sn].strip()
        parts.append(f"## {sn}")
        parts.append("")
        if body:
            parts.append(body)
            parts.append("")
    out = "\n".join(parts)
    return re.sub(r"\n{4,}", "\n\n\n", out).strip() + "\n"


def split_file(
    src: Path,
    *,
    rank_out: Path,
    activity_out: Path,
    remove_src: bool = True,
) -> Tuple[int, int]:
    text = src.read_text(encoding="utf-8")
    preamble, sections = _parse_header_and_sections(text)

    rank_sections: Dict[str, str] = {}
    activity_sections: Dict[str, str] = {}
    for title, body in sections.items():
        bucket = classify_rank_or_activity(title, body=body)
        if bucket == "rank":
            rank_sections[title] = body
        else:
            activity_sections[title] = body

    rank_out.write_text(
        _build_file("榜单", preamble, rank_sections),
        encoding="utf-8",
    )
    activity_out.write_text(
        _build_file("活动", preamble, activity_sections),
        encoding="utf-8",
    )
    if remove_src and src.resolve() != rank_out.resolve():
        src.unlink()
    return len(rank_sections), len(activity_sections)


def resplit_existing(rank_out: Path, activity_out: Path) -> Tuple[int, int]:
    """从已拆分的 榜单/活动 文件合并后按最新规则重分。"""
    sections: Dict[str, str] = {}
    preamble = ""
    for path in (rank_out, activity_out):
        if not path.is_file():
            continue
        pre, secs = _parse_header_and_sections(path.read_text(encoding="utf-8"))
        if not preamble:
            preamble = pre
        sections.update(secs)
    rank_sections: Dict[str, str] = {}
    activity_sections: Dict[str, str] = {}
    for title, body in sections.items():
        bucket = classify_rank_or_activity(title, body=body)
        if bucket == "rank":
            rank_sections[title] = body
        else:
            activity_sections[title] = body
    rank_out.write_text(_build_file("榜单", preamble, rank_sections), encoding="utf-8")
    activity_out.write_text(
        _build_file("活动", preamble, activity_sections), encoding="utf-8"
    )
    return len(rank_sections), len(activity_sections)


def main() -> int:
    ap = argparse.ArgumentParser(description="拆分各知识库 榜单与活动 → 榜单/活动")
    tc_root = REPO_ROOT / "testcase-kb"
    ap.add_argument(
        "--src",
        type=Path,
        default=tc_root / "榜单与活动.md",
    )
    ap.add_argument("--rank-out", type=Path, default=tc_root / KB_RANK_FILE)
    ap.add_argument("--activity-out", type=Path, default=tc_root / KB_ACTIVITY_FILE)
    ap.add_argument("--keep-src", action="store_true")
    ap.add_argument(
        "--resplit-existing",
        action="store_true",
        help="从已有 榜单.md + 活动.md 按规则重分",
    )
    ap.add_argument(
        "--all-kbs",
        action="store_true",
        help="拆分 prd-kb / bug-kb 中的 榜单与活动.md",
    )
    args = ap.parse_args()
    if args.all_kbs:
        split_all_knowledge_bases()
        return 0
    if args.resplit_existing:
        n_rank, n_act = resplit_existing(args.rank_out, args.activity_out)
        print(f"已重分: 榜单 {n_rank} 个主题, 活动 {n_act} 个主题")
        return 0
    if not args.src.is_file():
        raise SystemExit(f"找不到源文件: {args.src}")
    n_rank, n_act = split_file(
        args.src,
        rank_out=args.rank_out,
        activity_out=args.activity_out,
        remove_src=not args.keep_src,
    )
    print(f"已拆分: 榜单 {n_rank} 个主题, 活动 {n_act} 个主题")
    print(f"  → {args.rank_out}")
    print(f"  → {args.activity_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
