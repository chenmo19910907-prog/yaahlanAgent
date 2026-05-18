#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
将 documents/documents 下 Markdown 从「用例步骤/预期」体例改写为知识库体例：

- 文档头：说明表 + 知识库定位（非执行用例清单）
- 来源：合并为单行「版本 · 摘录自」
- 正文：「步骤/预期」→ 场景标题 + 规则要点列表
- 子标题：「变体」→「补充场景」
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import List, Optional, Tuple

ROOT_DEFAULT = Path(__file__).resolve().parent.parent / "documents" / "documents"

STEP_RE = re.compile(r"^- \*\*步骤\*\*：(.+)$", re.M)
EXPECT_RE = re.compile(r"^  - \*\*预期\*\*：(.+)$", re.M)
VER_LINE_RE = re.compile(r"^> \*\*来源版本\*\*：`([^`]*)`")
VER_LINE_KB_RE = re.compile(r"^> \*\*版本\*\*：")
FILE_LINE_RE = re.compile(r"^> \*\*来源文件\*\*：`([^`]*)`")
VARIANT_H_RE = re.compile(r"^#### 变体：")

EMPTY_EXPECT = frozenset(
    {
        "_（表中未单列预期）_",
        "（表中未单列预期）",
        "_（表中未单列预期）",
    }
)

LEGACY_META_RE = re.compile(
    r"(?ms)^- \*\*说明\*\*：按版本.*?\n"
    r"- \*\*结构\*\*：.*?\n"
    r"- \*\*冲突\*\*：.*?\n"
)

SCOPE_LINE_RE = re.compile(r"^> \*\*范围\*\*：.+$", re.M)


def _normalize_newlines(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return text


def _short_filename(path: str) -> str:
    p = path.strip()
    if not p:
        return "—"
    return Path(p).name if ("/" in p or "\\" in p) else p


def _step_to_heading(step: str) -> str:
    s = step.strip()
    s = re.sub(r"\s+", " ", s)
    if len(s) <= 48:
        return f"**{s}**"
    if re.match(r"^\d+[.．、]", s):
        return "**场景要点**"
    return f"**{s[:45]}…**"


def _clean_expect(text: str) -> Optional[str]:
    t = text.strip()
    if not t or t in EMPTY_EXPECT:
        return None
    return t


def transform_body(body: str) -> str:
    """将步骤/预期列表转为知识库规则列表。"""
    if not body or not STEP_RE.search(body):
        return body.strip()

    lines = body.splitlines()
    out: List[str] = []
    i = 0
    pending_source: Optional[str] = None

    while i < len(lines):
        line = lines[i]
        vm = VER_LINE_RE.match(line)
        if vm:
            ver = vm.group(1).strip()
            sf = ""
            if i + 1 < len(lines):
                fm = FILE_LINE_RE.match(lines[i + 1])
                if fm:
                    sf = _short_filename(fm.group(1))
                    i += 1
            pending_source = f"> **版本**：`{ver}`" + (
                f" · **摘录自**：`{sf}`" if sf else ""
            )
            i += 1
            continue

        if VER_LINE_KB_RE.match(line):
            pending_source = line.rstrip()
            if i + 1 < len(lines) and FILE_LINE_RE.match(lines[i + 1]):
                i += 1
            i += 1
            continue

        if FILE_LINE_RE.match(line):
            i += 1
            continue

        sm = STEP_RE.match(line)
        if sm:
            if pending_source:
                out.append(pending_source)
                out.append("")
                pending_source = None
            step = sm.group(1).strip()
            i += 1
            expects: List[str] = []
            while i < len(lines):
                em = EXPECT_RE.match(lines[i])
                if not em:
                    break
                cleaned = _clean_expect(em.group(1))
                if cleaned:
                    expects.append(cleaned)
                i += 1
            out.append(_step_to_heading(step))
            if expects:
                out.extend(f"- {e}" for e in expects)
            else:
                out.append("- （无额外规则说明）")
            out.append("")
            continue

        if line.strip():
            if pending_source:
                out.append(pending_source)
                out.append("")
                pending_source = None
            out.append(line.rstrip())
        i += 1

    if pending_source:
        out.append(pending_source)

    return "\n".join(out).strip()


def build_kb_doc_meta(title: str, scope_line: Optional[str] = None) -> str:
    parts = [f"# {title}", ""]
    if scope_line:
        parts.append(scope_line.strip())
        parts.append("")
    parts.extend(
        [
            "> **文档类型**：产品规则与验收要点知识库（由版本需求整理，非测试执行清单）",
            "",
            "| 项 | 说明 |",
            "|---|---|",
            "| 组织方式 | `## 业务主题` → `### 功能点` → 场景小节与规则列表 |",
            "| 版本口径 | 同一功能点多版本时保留最新；「同上」类补充已并入父条目 |",
            "| 索引 | 下方目录为文内业务主题，便于跳转 |",
            "",
        ]
    )
    return "\n".join(parts)


def transform_toc(lines: List[str]) -> List[str]:
    out: List[str] = []
    in_toc = False
    toc_intro_done = False
    for line in lines:
        if line.strip() == "以下为文内业务主题索引。":
            if not toc_intro_done:
                out.append(line)
                toc_intro_done = True
            continue
        if line.strip() == "## 目录":
            in_toc = True
            out.append(line)
            out.append("")
            if not toc_intro_done:
                out.append("以下为文内业务主题索引。")
                toc_intro_done = True
            continue
        if in_toc and line.strip() == "---":
            in_toc = False
        if in_toc and line.startswith("- [") and "](" in line:
            m = re.match(r"^- \[(.+?)\]\(#", line)
            out.append(f"- {m.group(1)}" if m else line)
            continue
        out.append(line)
    return out


def transform_main_content(main_body: str) -> str:
    """对正文全文做体例转换（保留 ## / ### 标题结构）。"""
    body = transform_body(main_body)
    body = VARIANT_H_RE.sub("#### 补充场景：", body)
    return body


def transform_document(text: str) -> str:
    text = _normalize_newlines(text)
    if not text.startswith("# "):
        return text

    title = text.split("\n", 1)[0][2:].strip()
    scope_m = SCOPE_LINE_RE.search(text)
    scope_line = scope_m.group(0) if scope_m else None

    # 拆分：文首 / 目录区 / 正文
    first_sep = text.find("\n---\n")
    if first_sep == -1:
        return text

    body_rest = text[first_sep + 5 :]
    second_sep = body_rest.find("\n---\n")
    if second_sep == -1:
        prefix = build_kb_doc_meta(title, scope_line)
        main = transform_main_content(body_rest)
        return _normalize_newlines(prefix + "---\n\n" + main) + "\n"

    toc_block = body_rest[:second_sep]
    main_body = body_rest[second_sep + 5 :]

    toc_lines = transform_toc(toc_block.splitlines())
    toc_text = "\n".join(toc_lines).strip()

    prefix = build_kb_doc_meta(title, scope_line)
    main = transform_main_content(main_body)

    merged = f"{prefix}---\n\n{toc_text}\n\n---\n\n{main}"
    merged = re.sub(r"^(## .+)\n(### )", r"\1\n\n\2", merged, flags=re.M)
    merged = re.sub(r"^(### .+)\n(> \*\*版本\*\*)", r"\1\n\n\2", merged, flags=re.M)
    merged = re.sub(r"\n{4,}", "\n\n\n", merged)
    return merged.strip() + "\n"


def transform_file(path: Path) -> Tuple[str, bool]:
    old = path.read_text(encoding="utf-8")
    new = transform_document(old)
    return new, new != old


def main() -> None:
    ap = argparse.ArgumentParser(description="知识库体例改写（步骤/预期 → 规则要点）")
    ap.add_argument("--root", type=Path, default=ROOT_DEFAULT)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    root: Path = args.root
    files = sorted(p for p in root.glob("*.md") if p.name.lower() != "readme.md")
    changed = 0
    for p in files:
        new, diff = transform_file(p)
        if diff:
            changed += 1
            if not args.dry_run:
                p.write_text(new, encoding="utf-8")
        print(f"{'[dry] ' if args.dry_run else ''}{p.name}: {'updated' if diff else 'ok'}")

    print(f"kb-knowledge-style: {changed}/{len(files)} files updated")


if __name__ == "__main__":
    main()
