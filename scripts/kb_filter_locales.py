#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 testcase-kb 知识库移除土语、俄语相关用例。

规则：
- 整 Sheet：土耳其政策整改、土语区分区策略 等
- 整模块：翻译|土语、多语言|俄语、土耳其协议 等
- 步骤/预期：仅删除与土语、俄语、土耳其语、土语区、俄语区相关的行
- 保留国家名「土耳其」等非语言类描述（如国家列表排序）
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent / "testcase-kb"
SCRIPTS = Path(__file__).resolve().parent

_SPEC_OPT = importlib.util.spec_from_file_location(
    "content_opt",
    SCRIPTS / "content_optimize_kb_docs.py",
)
content_opt = importlib.util.module_from_spec(_SPEC_OPT)
sys.modules["content_opt"] = content_opt
assert _SPEC_OPT.loader is not None
_SPEC_OPT.loader.exec_module(content_opt)

_SPEC_SPLIT = importlib.util.spec_from_file_location(
    "content_split",
    SCRIPTS / "content_split_merge_kb.py",
)
csm = importlib.util.module_from_spec(_SPEC_SPLIT)
sys.modules["content_split"] = csm
assert _SPEC_SPLIT.loader is not None
_SPEC_SPLIT.loader.exec_module(csm)

CaseBlock = content_opt.CaseBlock
extract_blocks = content_opt.extract_blocks
normalize_lines = content_opt.normalize_lines

STEP_RE = re.compile(r"^- \*\*步骤\*\*：(.+)$")
EXPECT_RE = re.compile(r"^  - \*\*预期\*\*：(.+)$")

# 整 Sheet 丢弃
SHEET_DROP_RE = re.compile(
    r"土耳其政策整改|土语区分区策略",
    re.I,
)

# 整模块 / 来源文件 丢弃
MODULE_DROP_RE = re.compile(
    r"土耳其协议|"
    r"多语言\s*[|｜]\s*(俄语|土语)|"
    r"翻译\s*[|｜]\s*(俄语|土语)|"
    r"^(俄语|土语)$|"
    r"语言为俄语|语言为土语|"
    r"设为俄语|设为土语|"
    r"push.*俄语|push.*土语",
    re.I,
)

SOURCE_DROP_RE = re.compile(
    r"土耳其政策整改|土语区分区策略",
    re.I,
)

# 步骤文本：与土语/俄语测试相关则整段删除
STEP_DROP_RE = re.compile(
    r"^(土语|俄语)$|"
    r"土语区|俄语区|"
    r"(系统|app|客户端)?语言(设为|为|选择).*(土语|俄语)|"
    r"(土语|俄语)\s*区|"
    r"切换.*(土语|俄语)区|"
    r"搜索.*(土语|俄语)区|"
    r"(土语|俄语)区房间|"
    r"土耳其\s*IP|土耳其ip|土耳其语|土耳其政策|"
    r"非土耳其.*土耳其语|"
    r"语言为(土语|俄语)",
    re.I,
)

# 预期行：仅语言相关则删除
EXPECT_DROP_RE = re.compile(
    r"^(土语|俄语|土耳其语)$|"
    r"^(展示)?(土语|俄语)(push|版|协议|消息)?|"
    r"土语区|俄语区|"
    r"土耳其语版本|"
    r"不出现土耳其语|"
    r"土语取英语|"
    r"土语下展示|"
    r".*土语.*俄语.*|.*俄语.*土语.*",
    re.I,
)


def _step_text(line: str) -> str:
    m = STEP_RE.match(line.strip())
    return m.group(1).strip() if m else ""


def _expect_text(line: str) -> str:
    m = EXPECT_RE.match(line)
    return m.group(1).strip() if m else ""


def should_drop_block(b: CaseBlock) -> bool:
    if SHEET_DROP_RE.search(b.sheet or ""):
        return True
    if SOURCE_DROP_RE.search(b.source_file or ""):
        return True
    for name in (b.module, b.parent_module):
        n = (name or "").strip()
        if not n:
            continue
        if n in ("俄语", "土语"):
            return True
        if MODULE_DROP_RE.search(n):
            return True
    return False


def sanitize_expect_text(text: str) -> str:
    """从混合语言描述中去掉土语/俄语提及，若删空则标记丢弃。"""
    t = text
    t = re.sub(r"[、,，]\s*土\s*语", "", t)
    t = re.sub(r"[、,，]\s*俄\s*语", "", t)
    t = re.sub(r"俄语\s*土语|土语\s*俄语", "", t)
    t = re.sub(r"(阿语、英语、)俄语土语(也展示英语)", r"\1\2", t)
    t = re.sub(r"英、阿、土、俄语", "英、阿", t)
    t = re.sub(r"有英、阿、土、俄语", "有英、阿", t)
    t = re.sub(r"\(英文、土语等\)", "(英文等)", t)
    t = re.sub(r"英文、土语等", "英文等", t)
    t = re.sub(r"\s+", " ", t).strip(" 、,，")
    if EXPECT_DROP_RE.search(t):
        return ""
    if re.search(r"^(土语|俄语)$", t):
        return ""
    return t


def sanitize_step_text(text: str) -> str:
    t = text
    t = re.sub(r"\(英文、土语等\)", "(英文等)", t)
    t = re.sub(r"英文、土语等", "英文等", t)
    t = re.sub(r"非阿语字符的\(英文、土语等\)", "非阿语字符的(英文等)", t)
    return t


def filter_body(body: str) -> str:
    lines = body.splitlines()
    out: List[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if STEP_RE.match(line):
            st = _step_text(line)
            if STEP_DROP_RE.search(st):
                i += 1
                while i < len(lines) and not STEP_RE.match(lines[i]):
                    i += 1
                continue
            cleaned_st = sanitize_step_text(st)
            if cleaned_st != st:
                out.append(f"- **步骤**：{cleaned_st}")
            else:
                out.append(line)
            i += 1
            continue
        if EXPECT_RE.match(line):
            et = _expect_text(line)
            cleaned = sanitize_expect_text(et)
            if not cleaned or EXPECT_DROP_RE.search(et):
                i += 1
                continue
            if cleaned != et:
                out.append(f"  - **预期**：{cleaned}")
            else:
                out.append(line)
            i += 1
            continue
        out.append(line)
        i += 1
    return normalize_lines("\n".join(out))


def filter_block(b: CaseBlock) -> CaseBlock | None:
    if should_drop_block(b):
        return None
    new_body = filter_body(b.body)
    if not new_body or not re.search(r"\*\*步骤\*\*", new_body):
        return None
    return CaseBlock(
        sheet=b.sheet,
        module=b.module,
        version_label=b.version_label,
        version_tuple=b.version_tuple,
        source_file=b.source_file,
        body=new_body,
        parent_module=b.parent_module,
    )


def load_filtered(root: Path) -> Tuple[List[CaseBlock], int]:
    removed = 0
    kept: List[CaseBlock] = []
    for p in sorted(root.glob("*.md")):
        if p.name.startswith("_") or p.name.lower() == "readme.md":
            continue
        for b in extract_blocks(p.read_text(encoding="utf-8")):
            nb = filter_block(b)
            if nb is None:
                removed += 1
            else:
                kept.append(nb)
    return kept, removed


def main() -> None:
    ap = argparse.ArgumentParser(description="移除知识库中土语/俄语相关用例")
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    root: Path = args.root

    blocks, removed = load_filtered(root)
    if not blocks and removed == 0:
        raise SystemExit("未解析到用例块")

    latest: Dict[Tuple[str, str, str], CaseBlock] = {}
    for b in blocks:
        t = csm.classify_target(b)
        key = (t, b.sheet or "未归类需求", b.module)
        if key not in latest or b.version_tuple > latest[key].version_tuple:
            latest[key] = b

    tree = csm.group_for_output(latest)

    remaining = sum(len(c) for s in tree.values() for c in s.values())
    print(f"过滤: 删除 {removed} 块, 保留 {len(latest)} 模块键 / {remaining} cluster")

    if args.dry_run:
        return

    for target, fname in csm.KB_FILE_NAMES.items():
        sheets_map = tree.get(target, {})
        title = fname.replace(".md", "")
        if not sheets_map:
            md = f"# {title}\n\n- **说明**：当前无归类用例块。\n"
        else:
            md = csm.build_from_tree(title, sheets_map)
        if target == "room_pk" and sheets_map:
            intro = (
                "# 房间PK\n\n"
                "> **范围**：房间内 PK、跨房 PK、乱斗/团战/团队 PK。\n"
                "> **说明**：已移除土语/俄语专项用例。\n\n"
                "---\n\n"
            )
            if md.startswith(f"# {title}"):
                rest = md.split("\n---\n\n", 1)
                body = rest[-1] if len(rest) > 1 else md
                if body.lstrip().startswith(f"# {title}"):
                    body = body.split("\n", 1)[1]
                md = intro + body.lstrip("\n")
        (root / fname).write_text(md, encoding="utf-8")

    opt = SCRIPTS / "optimize_kb_docs.py"
    if opt.exists():
        subprocess.run(
            [sys.executable, str(opt), "--root", str(root)],
            check=False,
        )

    # 校验残留
    left = 0
    for p in root.glob("*.md"):
        if p.name.startswith("_"):
            continue
        txt = p.read_text(encoding="utf-8")
        for pat in (r"土语", r"俄语", r"土耳其语", r"土耳其政策", r"土语区"):
            left += len(re.findall(pat, txt))
    print(f"locale_filter done -> {root} (残留关键词约 {left} 处，多为国家名「土耳其」)")


if __name__ == "__main__":
    main()
