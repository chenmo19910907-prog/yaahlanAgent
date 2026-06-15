#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
将 PRD 原始摘录（按版本文档）整理为 prd-kb 业务模块知识库。

与 testcase-kb 对齐：同父类型合并为单个 md，按业务主题组织，非逐篇 PRD 文档存档。
"""

from __future__ import annotations

import argparse
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from kb_index import MODULE_KEYWORDS, match_module_keys

_ROOT = Path(__file__).resolve().parent.parent

PRD_SKIP_NAME_RE = re.compile(r"待排期", re.I)

# 与 testcase-kb 文件名对齐
PRD_MODULE_FILES: Dict[str, str] = {
    "gift": "礼物.md",
    "room": "房间.md",
    "room_pk": "房间PK.md",
    "rank": "榜单.md",
    "activity": "活动.md",
    "family": "家族.md",
    "theme_room": "主题房.md",
    "moments": "动态.md",
    "message": "消息.md",
    "vip": "特权VIP.md",
    "noble": "贵族.md",
    "wealth": "财富等级.md",
    "auth_login": "注册登录.md",
    "face_auth": "人脸认证.md",
    "coin": "充值提现转账.md",
    "agency": "公会.md",
    "customer_service": "客服.md",
    "super_admin": "超管.md",
    "game": "游戏.md",
    "profile": "个人主页.md",
    "cp": "CP好友关系.md",
    "dress": "装扮.md",
    "mystery": "神秘人.md",
    "collector": "收藏展馆.md",
    "other": "其他.md",
}

MODULE_PRIORITY: Tuple[str, ...] = (
    "room_pk",
    "theme_room",
    "family",
    "cp",
    "collector",
    "mystery",
    "dress",
    "profile",
    "face_auth",
    "noble",
    "vip",
    "wealth",
    "coin",
    "customer_service",
    "super_admin",
    "agency",
    "game",
    "rank",
    "activity",
    "moments",
    "message",
    "gift",
    "room",
    "auth_login",
    "other",
)

DOC_TITLE_RE = re.compile(r"^#\s+(.+)$", re.M)
META_SOURCE_RE = re.compile(r"^>\s*\*\*来源\*\*：\[([^\]]+)\]", re.M)
META_VERSION_RE = re.compile(r"^>\s*\*\*版本\*\*：`([^`]+)`", re.M)
BODY_SECTION_RE = re.compile(r"^##\s+正文\s*$", re.M)

SECTION_HEAD_RE = re.compile(
    r"^(?:#{1,4}\s+.+|"
    r"\d+[、.．]\s*\S.{0,120}|"
    r"(?:原型图|需求链接|对照ui|通用逻辑)$)",
    re.I,
)

# 标题 / 正文关键词 → 模块（高置信优先）
TITLE_RULES: List[Tuple[re.Pattern[str], str]] = [
    (re.compile(r"团战\s*pk|1v1\s*pk|跨房\s*pk|房间\s*pk", re.I), "room_pk"),
    (re.compile(r"主题房", re.I), "theme_room"),
    (re.compile(r"家族", re.I), "family"),
    (re.compile(r"\bcp\b|cp\s*空间|cp\s*礼物|好友关系|亲密度", re.I), "cp"),
    (re.compile(r"客服|转单|快捷回复|券包|建联", re.I), "customer_service"),
    (re.compile(r"超管|审核后台|设备拉黑|工单", re.I), "super_admin"),
    (re.compile(r"公会|公会长|预提|分区策略|土语区", re.I), "agency"),
    (re.compile(r"游戏|概率游戏|大冒险|bridge", re.I), "game"),
    (re.compile(r"榜单|排行|月榜|周榜|小时榜|荣誉墙|打榜|全服榜", re.I), "rank"),
    (re.compile(r"活动|转盘|roadmap|ab实验|盛典|节|摩天轮", re.I), "activity"),
    (re.compile(r"动态|moment|点赞数", re.I), "moments"),
    (re.compile(r"im|私聊|群聊|消息|会话", re.I), "message"),
    (re.compile(r"礼物|送礼|背包|勋章|展馆|飘屏", re.I), "gift"),
    (re.compile(r"语音房|进房|麦位|房间|转麦|屏蔽词", re.I), "room"),
    (re.compile(r"充值|提现|转账|钱包|钻石|币商", re.I), "coin"),
    (re.compile(r"注册|登录|注销|昵称|性别", re.I), "auth_login"),
    (re.compile(r"真人认证|人脸", re.I), "face_auth"),
    (re.compile(r"贵族", re.I), "noble"),
    (re.compile(r"特权\s*vip|\bvip\b", re.I), "vip"),
    (re.compile(r"财富|魅力等级", re.I), "wealth"),
    (re.compile(r"个人主页|资料页|profile", re.I), "profile"),
    (re.compile(r"装扮", re.I), "dress"),
    (re.compile(r"神秘人", re.I), "mystery"),
    (re.compile(r"收藏展馆", re.I), "collector"),
    (re.compile(r"主播后台", re.I), "super_admin"),
]

KB_MODULE_FILE_RE = re.compile(
    r"^> \*\*文档类型\*\*：产品需求要点知识库"
)


@dataclass
class PrdSlice:
    module_key: str
    version: str
    source_name: str
    topic: str
    feature: str
    rules: List[str]
    version_tuple: Tuple[int, int, int]


def parse_version_tuple(label: str) -> Tuple[int, int, int]:
    m = re.search(r"v?(\d+)\.(\d+)\.(\d+)", label or "", re.I)
    if not m:
        return (0, 0, 0)
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def pick_module_key(text: str, *, doc_title: str = "") -> str:
    blob = f"{doc_title} {text}"
    for pat, key in TITLE_RULES:
        if pat.search(blob):
            return key
    hits = match_module_keys(blob)
    if hits:
        for key in MODULE_PRIORITY:
            if key in hits:
                return key
        return hits[0]
    return "other"


def split_body_sections(body: str) -> List[Tuple[str, str]]:
    lines = body.splitlines()
    sections: List[Tuple[str, str]] = []
    title = ""
    buf: List[str] = []

    def flush() -> None:
        nonlocal title, buf
        text = "\n".join(buf).strip()
        if text:
            sections.append((title, text))
        title = ""
        buf = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if buf:
                buf.append("")
            continue
        if SECTION_HEAD_RE.match(stripped):
            flush()
            title = re.sub(r"^#{1,4}\s+", "", stripped).strip()
            continue
        buf.append(line)
    flush()
    if not sections and body.strip():
        sections.append(("", body.strip()))
    return sections


def body_to_rules(text: str) -> List[str]:
    rules: List[str] = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s in {"原型图", "需求链接"}:
            continue
        s = re.sub(r"^\d+(?:\.\d+)?[、.．]\s*", "", s)
        if s:
            rules.append(s)
    return rules


def parse_raw_prd_file(path: Path) -> Optional[dict]:
    text = path.read_text(encoding="utf-8")
    if KB_MODULE_FILE_RE.search(text):
        return None
    if PRD_SKIP_NAME_RE.search(path.stem):
        return None

    title_m = DOC_TITLE_RE.search(text)
    doc_title = title_m.group(1).strip() if title_m else path.stem
    if PRD_SKIP_NAME_RE.search(doc_title):
        return None

    src_m = META_SOURCE_RE.search(text)
    source_name = src_m.group(1).strip() if src_m else doc_title
    ver_m = META_VERSION_RE.search(text)
    version = ver_m.group(1).strip() if ver_m else "—"

    body_m = BODY_SECTION_RE.search(text)
    body = text[body_m.end() :].strip() if body_m else text
    if body.startswith("#"):
        # 去掉可能残留的标题块
        parts = body.split("\n\n", 2)
        if len(parts) >= 3 and parts[0].startswith("#"):
            body = parts[2] if parts[1].startswith(">") else "\n\n".join(parts[1:])

    return {
        "doc_title": doc_title,
        "source_name": source_name,
        "version": version,
        "version_tuple": parse_version_tuple(version if version != "—" else doc_title),
        "body": body,
    }


def doc_to_slices(meta: dict) -> List[PrdSlice]:
    doc_title = meta["doc_title"]
    source_name = meta["source_name"]
    version = meta["version"]
    version_tuple = meta["version_tuple"]
    default_key = pick_module_key(doc_title, doc_title=doc_title)

    slices: List[PrdSlice] = []
    for topic, chunk in split_body_sections(meta["body"]):
        rules = body_to_rules(chunk)
        if not rules:
            continue
        mod = pick_module_key(f"{topic} {chunk}", doc_title=doc_title)
        if mod == "other" and default_key != "other":
            mod = default_key
        feature = topic or doc_title
        slices.append(
            PrdSlice(
                module_key=mod,
                version=version,
                source_name=source_name,
                topic=feature,
                feature=feature,
                rules=rules,
                version_tuple=version_tuple,
            )
        )
    return slices


def module_display_title(filename: str) -> str:
    return Path(filename).stem


def build_module_doc(module_key: str, slices: List[PrdSlice]) -> str:
    filename = PRD_MODULE_FILES[module_key]
    title = module_display_title(filename)
    slices_sorted = sorted(slices, key=lambda s: (s.version_tuple, s.topic, s.feature))

    topics = sorted({s.feature for s in slices_sorted if s.feature})
    lines = [
        f"# {title}",
        "",
        "> **文档类型**：产品需求要点知识库（由版本 PRD 整理，非逐篇文档存档）",
        "",
        "| 项 | 说明 |",
        "|---|---|",
        "| 组织方式 | `## 业务主题` → `### 功能点` → 规则要点列表 |",
        "| 版本口径 | 各条目标注来源版本与摘录文档；同主题以较新版本为准理解 |",
        "| 索引 | 下方目录为文内业务主题，便于跳转 |",
        "",
        "## 目录",
        "",
        "以下为文内业务主题索引。",
        "",
    ]
    for t in topics[:200]:
        lines.append(f"- {t}")
    lines.extend(["", "---", ""])

    last_heading = ""
    for sl in slices_sorted:
        heading = f"## {sl.version} · {sl.feature}" if sl.version != "—" else f"## {sl.feature}"
        if heading != last_heading:
            lines.extend([heading, ""])
            last_heading = heading
        lines.append(f"### {sl.feature}")
        lines.append("")
        if sl.version != "—":
            lines.append(f"> **版本**：`{sl.version}` · **摘录自**：`{sl.source_name}`")
        else:
            lines.append(f"> **摘录自**：`{sl.source_name}`")
        lines.append("")
        for rule in sl.rules:
            lines.append(f"- {rule}")
        lines.append("")

    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip() + "\n"


def is_raw_prd_file(path: Path) -> bool:
    if path.name == "README.md":
        return False
    if path.name in set(PRD_MODULE_FILES.values()):
        return False
    text = path.read_text(encoding="utf-8", errors="replace")
    return "> **文档类型**：产品需求文档（PRD）" in text or "## 正文" in text


def collect_slices(input_dir: Path) -> Dict[str, List[PrdSlice]]:
    by_module: Dict[str, List[PrdSlice]] = defaultdict(list)
    for path in sorted(input_dir.glob("*.md")):
        if not is_raw_prd_file(path):
            continue
        meta = parse_raw_prd_file(path)
        if not meta:
            continue
        for sl in doc_to_slices(meta):
            by_module[sl.module_key].append(sl)
    return by_module


def write_module_files(output_dir: Path, by_module: Dict[str, List[PrdSlice]]) -> List[str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: List[str] = []
    for key, filename in sorted(PRD_MODULE_FILES.items(), key=lambda x: x[1]):
        slices = by_module.get(key, [])
        if not slices:
            continue
        out_path = output_dir / filename
        out_path.write_text(build_module_doc(key, slices), encoding="utf-8")
        written.append(filename)
    return written


def remove_raw_doc_files(input_dir: Path, output_dir: Path) -> int:
    removed = 0
    module_names = set(PRD_MODULE_FILES.values()) | {"README.md"}
    for path in input_dir.glob("*.md"):
        if path.name in module_names:
            continue
        if path.resolve().parent != output_dir.resolve() and not is_raw_prd_file(path):
            continue
        if is_raw_prd_file(path) or (
            path.resolve().parent == output_dir.resolve() and path.name not in module_names
        ):
            if "> **文档类型**：产品需求要点知识库" in path.read_text(encoding="utf-8", errors="replace"):
                continue
            if is_raw_prd_file(path):
                path.unlink()
                removed += 1
    return removed


def write_readme(
    output_dir: Path,
    *,
    module_files: List[str],
    source_count: int,
    folder_url: str,
    skipped: Optional[List[str]] = None,
) -> None:
    now = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S %z")
    lines = [
        "# prd-kb · 产品需求知识库",
        "",
        "> **文档类型**：按业务模块整理的产品需求要点（非逐篇 PRD 文档）",
        f"> **来源目录**：[产品需求文档]({folder_url})",
        f"> **最近整理**：{now}",
        "",
        "与 `testcase-kb/`（验收要点）互补：本目录保留**产品侧需求规则与业务逻辑**，供 `prd-review`、用例生成前理解需求。",
        "「待排期需求」不纳入知识库。",
        "",
        "## 同步与整理",
        "",
        "```bash",
        "python3 DingTalk/prd_sync_execute.py --folder-id yaahlan-prd",
        "python3 scripts/prd_kb_build.py --input-dir prd-kb/.raw --output-dir prd-kb",
        "```",
        "",
        "## 统计",
        "",
        "| 指标 | 值 |",
        "|------|-----|",
        f"| 模块文件 | {len(module_files)} |",
        f"| 来源 PRD 篇数 | {source_count} |",
        "",
        "## 模块索引",
        "",
        "| 模块 | 文件 |",
        "|------|------|",
    ]
    for fn in sorted(module_files):
        lines.append(f"| {module_display_title(fn)} | [`{fn}`]({fn}) |")
    if skipped:
        lines.extend(["", "## 已排除", ""])
        for name in skipped:
            lines.append(f"- {name}")
    lines.append("")
    (output_dir / "README.md").write_text("\n".join(lines), encoding="utf-8")


def build_from_dir(
    input_dir: Path,
    output_dir: Path,
    *,
    folder_url: str = "",
    remove_raw: bool = True,
) -> Tuple[List[str], int]:
    by_module = collect_slices(input_dir)
    source_count = sum(
        1 for p in input_dir.glob("*.md") if is_raw_prd_file(p) and parse_raw_prd_file(p)
    )
    module_files = write_module_files(output_dir, by_module)
    removed = remove_raw_doc_files(input_dir, output_dir) if remove_raw else 0
    if input_dir.resolve() != output_dir.resolve():
        removed += remove_raw_doc_files(output_dir, output_dir) if remove_raw else 0
    write_readme(
        output_dir,
        module_files=module_files,
        source_count=source_count,
        folder_url=folder_url or "https://alidocs.dingtalk.com/i/nodes/14lgGw3P8vveoPlPC2PdN56v85daZ90D",
        skipped=["待排期需求"],
    )
    return module_files, removed


def main() -> int:
    ap = argparse.ArgumentParser(description="PRD 原始摘录 → 业务模块知识库")
    ap.add_argument(
        "--input-dir",
        type=Path,
        default=_ROOT / "prd-kb",
        help="原始 PRD md 目录（默认 prd-kb，迁移时用；同步后一般为 prd-kb/.raw）",
    )
    ap.add_argument(
        "--output-dir",
        type=Path,
        default=_ROOT / "prd-kb",
    )
    ap.add_argument("--no-remove-raw", action="store_true", help="保留输入目录中的逐篇 PRD 文件")
    ap.add_argument("--folder-url", default="")
    args = ap.parse_args()

    modules, removed = build_from_dir(
        args.input_dir,
        args.output_dir,
        folder_url=args.folder_url,
        remove_raw=not args.no_remove_raw,
    )
    print(f"已写入 {len(modules)} 个模块文件 → {args.output_dir}")
    for m in modules:
        print(f"  - {m}")
    if removed:
        print(f"已删除 {removed} 个逐篇 PRD 文件")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
