#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
testcase-kb 知识库「内容级」优化：

1. 解析用例块（支持 xlsx 导出的 ##### 格式，以及 ## Sheet / ### 模块 格式）
2. 同 Sheet + 同功能模块：仅保留最新版本
3. 「(同上)」「（同上）」「(同…」并入父模块的 #### 变体
4. 按 Excel Sheet 聚合为 ##，功能模块为 ###
5. 生成目录；禁止将「功能模块：…」误作 Sheet 标题
"""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from project_paths import testcase_kb_root  # noqa: E402

ROOT_DEFAULT = testcase_kb_root()

HASH5_RE = re.compile(r"^#####\s+(.+?)\s+·\s+(.+?)\s*$")
from kb_version import (  # noqa: E402
    VERSION_TABLE_BLURB,
    effective_version_label,
    merge_personnel,
    parse_personnel_meta_line,
    parse_version_meta_line,
    parse_version_tuple,
    peel_version_prefix_from_body,
    render_meta_header,
)
GONGNENG_PREFIX_RE = re.compile(r"^功能模块\s*[:：]\s*(.+?)\s*$", re.UNICODE)

SAME_AS_SUFFIX_RE = re.compile(
    r"(?:[\(（]\s*同上\s*[）)]|[\(（]\s*同[^）)]+[）)])\s*$",
    re.UNICODE,
)

SKIP_H2 = frozenset({"目录", "---"})


@dataclass
class CaseBlock:
    sheet: str
    module: str
    version_label: str
    version_tuple: Tuple[int, int, int]
    source_file: str
    body: str
    parent_module: str = ""  # ## 功能模块：父模块 下的子模块时使用
    personnel: Dict[str, str] = field(default_factory=dict)

    @property
    def is_variant(self) -> bool:
        return bool(SAME_AS_SUFFIX_RE.search(self.module))

    @property
    def base_module(self) -> str:
        if self.parent_module:
            return self.parent_module
        m = SAME_AS_SUFFIX_RE.sub("", self.module).strip()
        return m or self.module

    @property
    def variant_label(self) -> str:
        if not self.is_variant:
            return self.module if self.parent_module else ""
        return self.module


def normalize_lines(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [ln.rstrip() for ln in text.split("\n")]
    text = "\n".join(lines)
    return re.sub(r"\n{4,}", "\n\n\n", text).strip()


def body_fingerprint(body: str) -> str:
    lines = []
    for ln in body.splitlines():
        if (
            "来源版本" in ln
            or "来源文件" in ln
            or ln.startswith("> **版本**")
            or ln.startswith("> **人员**")
            or (ln.startswith("> ") and "**摘录自**" in ln)
        ):
            continue
        lines.append(ln.strip())
    return "\n".join(lines).strip()


def is_gongneng_heading(title: str) -> bool:
    return bool(GONGNENG_PREFIX_RE.match(title.strip()))


def gongneng_name(title: str) -> str:
    m = GONGNENG_PREFIX_RE.match(title.strip())
    return m.group(1).strip() if m else title.strip()


def normalize_sheet_name(name: str, current_sheet: str) -> Tuple[str, str]:
    """
    若标题为「功能模块：xxx」，返回 (真实sheet, 父模块名)。
    否则返回 (sheet名, "")。
    """
    if is_gongneng_heading(name):
        return current_sheet or "未归类需求", gongneng_name(name)
    return name.strip(), ""


def extract_blocks(md: str) -> List[CaseBlock]:
    """线性扫描，兼容 ##### 与 ## / ### 结构。"""
    blocks: List[CaseBlock] = []
    current_sheet = ""
    pending_parent = ""
    current_module = ""
    is_variant_line = False
    version_label = ""
    source_file = ""
    personnel: Dict[str, str] = {}
    body_lines: List[str] = []

    def flush() -> None:
        nonlocal body_lines, version_label, source_file, personnel, current_module, pending_parent, is_variant_line
        if not current_module and not body_lines:
            return
        sheet = current_sheet or "未归类需求"
        body = normalize_lines("\n".join(body_lines))
        ver_from_body, file_from_body, pers_from_body, body = peel_version_prefix_from_body(body)
        if ver_from_body and not version_label:
            version_label = ver_from_body
        if file_from_body and not source_file:
            source_file = file_from_body
        personnel = merge_personnel(personnel, pers_from_body)
        if not body and not version_label:
            return
        resolved_ver = effective_version_label(version_label, source_file)
        blocks.append(
            CaseBlock(
                sheet=sheet,
                module=current_module,
                version_label=version_label or resolved_ver,
                version_tuple=parse_version_tuple(resolved_ver),
                source_file=source_file,
                body=body,
                parent_module=pending_parent if pending_parent and pending_parent != current_module else "",
                personnel=dict(personnel),
            )
        )
        body_lines = []
        version_label = ""
        source_file = ""
        personnel = {}
        is_variant_line = False

    for raw_line in md.splitlines():
        line = raw_line.rstrip()
        if not line:
            if body_lines or current_module:
                body_lines.append("")
            continue

        hm = HASH5_RE.match(line)
        if hm:
            flush()
            pending_parent = ""
            raw_sheet, raw_mod = hm.group(1).strip(), hm.group(2).strip()
            sheet, parent = normalize_sheet_name(raw_sheet, current_sheet)
            if parent:
                pending_parent = parent
                current_sheet = sheet
                current_module = raw_mod if raw_mod != parent else parent
            else:
                current_sheet = sheet
                current_module = raw_mod
            continue

        if line.startswith("## ") and not line.startswith("###"):
            flush()
            title = line[2:].strip()
            if title in SKIP_H2 or title == "---":
                pending_parent = ""
                continue
            sheet, parent = normalize_sheet_name(title, current_sheet)
            if parent:
                pending_parent = parent
                current_sheet = sheet
                current_module = ""
            else:
                current_sheet = sheet
                pending_parent = ""
                current_module = ""
            continue

        if line.startswith("#### 变体："):
            flush()
            current_module = line.split("：", 1)[-1].strip()
            is_variant_line = True
            continue

        if line.startswith("### "):
            flush()
            current_module = line[4:].strip()
            continue

        ver_upd, file_upd = parse_version_meta_line(line)
        pers_upd = parse_personnel_meta_line(line)
        if ver_upd is not None or file_upd is not None or pers_upd is not None:
            if ver_upd:
                version_label = ver_upd
            if file_upd:
                source_file = file_upd
            if pers_upd:
                personnel = merge_personnel(personnel, pers_upd)
            continue

        if line.startswith("- **步骤**") or line.startswith("  - **预期**") or line.startswith("- "):
            body_lines.append(line)

    flush()
    return blocks


def pick_latest_blocks(blocks: List[CaseBlock]) -> Dict[Tuple[str, str, str], CaseBlock]:
    """key = (sheet, base_module, module) -> 最新版本。"""
    best: Dict[Tuple[str, str, str], CaseBlock] = {}
    for b in blocks:
        key = (b.sheet, b.base_module, b.module)
        if key not in best or b.version_tuple > best[key].version_tuple:
            best[key] = b
    return best


def group_blocks(latest: Dict[Tuple[str, str, str], CaseBlock]) -> Dict[str, Dict[str, List[CaseBlock]]]:
    sheets: Dict[str, Dict[str, List[CaseBlock]]] = {}

    for b in sorted(
        latest.values(),
        key=lambda x: (x.sheet, x.base_module, x.is_variant, x.module),
    ):
        base = b.base_module
        bucket = sheets.setdefault(b.sheet, {}).setdefault(base, [])
        if any(x.module == b.module and x.parent_module == b.parent_module for x in bucket):
            continue
        if b.is_variant or (b.parent_module and b.module != b.parent_module):
            bucket.append(b)
        else:
            bucket.insert(0, b)

    for sheet_name, mods in sheets.items():
        for base, blist in list(mods.items()):
            seen_fp: Dict[str, CaseBlock] = {}
            deduped: List[CaseBlock] = []
            for blk in blist:
                fp = body_fingerprint(blk.body)
                if fp in seen_fp:
                    if blk.version_tuple > seen_fp[fp].version_tuple:
                        seen_fp[fp] = blk
                    continue
                seen_fp[fp] = blk
                deduped.append(blk)
            prim = [x for x in deduped if not x.is_variant and not (x.parent_module and x.module != x.parent_module)]
            var = [x for x in deduped if x not in prim]
            mods[base] = prim + sorted(var, key=lambda x: x.module)

    return sheets


def render_block_header(b: CaseBlock) -> str:
    return render_meta_header(b.version_label, b.source_file, b.personnel) + "\n"


def render_body_kb(body: str) -> str:
    try:
        from kb_knowledge_style import transform_body

        return transform_body(body)
    except ImportError:
        return body


def render_module_section(blocks: List[CaseBlock]) -> str:
    out: List[str] = []
    for i, b in enumerate(blocks):
        has_parent_child = b.parent_module and b.module != b.parent_module
        if i == 0 and not b.is_variant and not has_parent_child:
            out.append(f"### {b.module}\n")
            out.append(render_block_header(b))
            out.append(render_body_kb(b.body))
        else:
            label = b.variant_label or (b.module if has_parent_child else b.module)
            if has_parent_child and i == 0:
                out.append(f"### {b.parent_module}\n")
            out.append(f"\n#### 补充场景：{label}\n")
            out.append(render_block_header(b))
            out.append(render_body_kb(b.body))
        out.append("")
    return "\n".join(out).strip()


def sheet_anchor(sheet: str) -> str:
    s = unicodedata.normalize("NFKC", sheet).strip().lower()
    s = re.sub(r"[^\w\u4e00-\u9fff]+", "-", s, flags=re.UNICODE)
    s = re.sub(r"-+", "-", s).strip("-")
    return s[:80] or "sheet"


def build_document(title: str, sheets: Dict[str, Dict[str, List[CaseBlock]]]) -> str:
    sheet_names = sorted(sheets.keys(), key=lambda s: (s == "未归类需求", s))

    toc_lines = ["## 目录", ""]
    for sn in sheet_names:
        if is_gongneng_heading(sn):
            continue
        toc_lines.append(f"- [{sn}](#{sheet_anchor(sn)})")
    toc_lines.append("")

    parts: List[str] = [
        f"# {title}",
        "",
        "> **文档类型**：产品规则与验收要点知识库（由版本需求整理，非测试执行清单）",
        "",
        "| 项 | 说明 |",
        "|---|---|",
        "| 组织方式 | `## 业务主题` → `### 功能点` → 场景小节与规则列表 |",
        f"| 版本口径 | {VERSION_TABLE_BLURB} |",
        "| 人员口径 | 各场景可选标注设计/测试/产品/开发（来自 xlsx 表头上方） |",
        "",
        "---",
        "",
        "\n".join(toc_lines),
        "---",
        "",
    ]

    for sn in sheet_names:
        if is_gongneng_heading(sn):
            continue
        mods = sheets[sn]
        parts.append(f"## {sn}")
        parts.append("")
        for base in sorted(mods.keys(), key=lambda x: (not x or not x[0].isdigit(), x)):
            sec = render_module_section(mods[base])
            if sec:
                parts.append(sec)
                parts.append("")

    text = "\n".join(parts)
    return re.sub(r"\n{4,}", "\n\n\n", text).strip() + "\n"


def optimize_file(path: Path) -> str:
    old = path.read_text(encoding="utf-8")
    title = path.stem
    if old.startswith("# "):
        title = old.split("\n", 1)[0][2:].strip() or title

    blocks = extract_blocks(old)
    if not blocks:
        return old

    latest = pick_latest_blocks(blocks)
    grouped = group_blocks(latest)
    return build_document(title, grouped)


def main() -> None:
    ap = argparse.ArgumentParser(description="知识库内容级优化（按 Sheet 重组）")
    ap.add_argument("--root", type=Path, default=ROOT_DEFAULT)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    root: Path = args.root
    files = sorted(p for p in root.glob("*.md") if p.name.lower() != "readme.md")

    changed = 0
    for p in files:
        old = p.read_text(encoding="utf-8")
        new = optimize_file(p)
        if new != old:
            changed += 1
            if not args.dry_run:
                p.write_text(new, encoding="utf-8")
        print(f"{'[dry] ' if args.dry_run else ''}{p.name}: ok")

    print(f"content-optimized {changed}/{len(files)} files")


if __name__ == "__main__":
    main()
