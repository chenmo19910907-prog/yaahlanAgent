#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""知识库一键优化：重分类 → 去重/矛盾合并 → 标题清理 → 房间切片 → 索引。"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent / "documents" / "documents"


def run(script: str, root: Path, extra: list[str] | None = None) -> None:
    cmd = [sys.executable, str(SCRIPTS / script), "--root", str(root)]
    if extra:
        cmd.extend(extra)
    print(f"\n>>> {script}")
    subprocess.run(cmd, check=False)


def main() -> None:
    ap = argparse.ArgumentParser(description="知识库一键优化流水线")
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument("--skip-reclassify", action="store_true")
    args = ap.parse_args()
    root: Path = args.root

    if not args.skip_reclassify:
        run("kb_reclassify.py", root)
    else:
        run("kb_optimize_all.py", root)
        run("kb_knowledge_style.py", root)
        run("kb_clean_toc_titles.py", root)
        run("kb_final_polish.py", root)
        run("optimize_kb_docs.py", root)
        run("kb_extract_room_modules.py", root)
        return

    run("kb_optimize_all.py", root)
    run("kb_knowledge_style.py", root)
    run("kb_clean_toc_titles.py", root)
    run("kb_final_polish.py", root)
    run("optimize_kb_docs.py", root)
    print(f"\npipeline done -> {root}")


if __name__ == "__main__":
    main()
