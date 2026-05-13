#!/usr/bin/env python3
"""对 documents/家族改版.md 做去冗：合并步骤换行、删除各 Sheet 末尾重复占位小节。

另：「创建家族」章内部分表化（名称/介绍字数、头像拍照相册）为文档二轮手工优化，
重新全量导出 Excel 后若丢失，可对照 Git 历史或按表头结构恢复。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


def remove_tail_template(s: str) -> str:
    """删除从 ##### 翻译 到 ##### 兼容性 的整块（各章 Excel 尾部占位，与全局口径重复）。"""
    pat = re.compile(
        r"(?ms)^##### 翻译\n.*?(?=^## |\Z)",
    )
    return pat.sub("", s)


def normalize_step_newlines(s: str) -> str:
    """将 **步骤** 内「1.…\\n2.…」合并为「1.…；2.…」（首条 **预期** 之前的正文）。"""

    def one_block(m: re.Match[str]) -> str:
        prefix, body, suffix = m.group(1), m.group(2), m.group(3)
        body = body.strip()
        body = re.sub(r"\n+\s*(\d+\.)", r"；\1", body)
        return prefix + body + suffix

    pat = re.compile(
        r"(- \*\*步骤\*\*：)(.*?)(\n  - \*\*预期\*\*：)",
        re.DOTALL,
    )
    return pat.sub(one_block, s)


def collapse_extra_blank_lines(s: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", s)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    path = root / "documents" / "家族改版.md"
    if len(sys.argv) >= 2:
        path = Path(sys.argv[1])

    text = path.read_text(encoding="utf-8")

    global_row = (
        "| 全局（翻译 / 镜像 / 占位） | 各 Sheet 末尾原表「##### 翻译」至「##### 兼容性」模板与空占位已删；"
        "业务内多语言用例保留。**阿语 RTL、镜像布局** 与 `documents/主题房.md` 目录下全局口径对齐。 |\n"
    )
    optimize_row = (
        "| 本次优化 | 合并步骤内编号换行；删除章末重复翻译/镜像/占位小节。"
        "重新导出 Excel 后可再运行 `scripts/optimize_family_kb_md.py`。 |\n"
    )

    marker = "| 阅读建议 | 各章 `#####` 对应原表「功能模块」列，可折叠查阅。 |\n"
    if marker in text:
        if "| 本次优化 |" not in text:
            text = text.replace(marker, marker + optimize_row, 1)
        if "| 全局（翻译 / 镜像 / 占位） |" not in text:
            # insert after 本次优化 row if present, else after 阅读建议
            m2 = "| 本次优化 |"
            if m2 in text:
                idx = text.find(m2)
                line_end = text.find("\n", idx) + 1
                text = text[:line_end] + global_row + text[line_end:]
            else:
                text = text.replace(marker, marker + global_row, 1)

    text = remove_tail_template(text)
    text = normalize_step_newlines(text)
    text = collapse_extra_blank_lines(text)

    path.write_text(text, encoding="utf-8")
    print(f"Optimized {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
