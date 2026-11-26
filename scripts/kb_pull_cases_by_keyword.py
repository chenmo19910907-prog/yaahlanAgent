#!/usr/bin/env python3
"""从 testcase-kb / documents 按关键词原样捞出步骤·预期用例行（不写新用例）。"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from project_paths import repo_root  # noqa: E402

ROOT = repo_root()
KB = ROOT / "testcase-kb"
DOCS = ROOT / "documents"
OUT = ROOT / "temporary_testcase"

STEP_RE = re.compile(r"^\s*-\s+\*\*步骤\*\*[：:]\s*(.*)")
EXP_RE = re.compile(r"^\s*-\s+\*\*预期\*\*[：:]\s*(.*)")
H2_RE = re.compile(r"^##\s+(.+)")
H3_RE = re.compile(r"^###\s+(.+)")
H5_RE = re.compile(r"^#####\s+(.+)")
TABLE_ROW_RE = re.compile(r"^\|\s*([^|]+)\|\s*([^|]*)\|\s*([^|]*)\|\s*$")


def flush_step(rows: list, mod: str, src: str, step: str, exps: list[str], seq: list[int]) -> None:
    if not step and not exps:
        return
    seq[0] += 1
    exp_text = "\n".join(exps) if exps else "（表中未单列预期）"
    rows.append(
        {
            "编号": f"KB_{seq[0]:04d}",
            "功能模块": mod,
            "测试步骤": step or "—",
            "预期结果": exp_text,
            "来源": src,
        }
    )


def parse_step_expected_md(text: str, src: str, mod_filter: str, include_fn) -> list[dict]:
    rows: list[dict] = []
    seq = [0]
    lines = text.splitlines()
    i = 0
    cur_mod = ""
    cur_sub = ""
    in_section = False

    while i < len(lines):
        line = lines[i]
        m2 = H2_RE.match(line)
        m3 = H3_RE.match(line)
        m5 = H5_RE.match(line)

        if m2:
            title = m2.group(1).strip()
            in_section = include_fn("##", title, cur_sub)
            if in_section:
                cur_mod = mod_filter if mod_filter else title
            i += 1
            continue
        if m3 and in_section:
            cur_sub = m3.group(1).strip()
            i += 1
            continue
        if m5:
            sub = m5.group(1).strip()
            if include_fn("#####", sub, cur_sub):
                in_section = True
                cur_mod = mod_filter if mod_filter else sub
            i += 1
            continue

        if not in_section:
            i += 1
            continue

        sm = STEP_RE.match(line)
        if sm:
            step = sm.group(1).strip()
            exps: list[str] = []
            j = i + 1
            while j < len(lines):
                em = EXP_RE.match(lines[j])
                if em:
                    exps.append(em.group(1).strip())
                    j += 1
                    continue
                if STEP_RE.match(lines[j]) or H2_RE.match(lines[j]) or H5_RE.match(lines[j]):
                    break
                if lines[j].startswith("## "):
                    break
                j += 1
            flush_step(rows, cur_mod, src, step, exps, seq)
            i = j
            continue
        i += 1
    return rows


ANCHOR_H2_EXACT = {
    "主播任务",
    "主播任务优化",
    "主播任务奖励货币替换",
    "平台/主播任务流程优化",
}

ANCHOR_FM_PREFIX = (
    "功能模块：主播任务",
    "功能模块：任务面板",
    "功能模块：任务组件-邀请首充",
    "功能模块：对话聊天组件-邀请上麦",
    "功能模块：任务用户聊天外显",
    "功能模块：任务用户的通知",
    "功能模块：主播任务的推荐列表副标题",
    "功能模块：取尾号为2的主播,聊天任务要求",
)


def anchor_include(level: str, title: str, _parent: str) -> bool:
    t = title.strip()
    if level == "##":
        if t in ANCHOR_H2_EXACT:
            return True
        if any(t.startswith(p) for p in ANCHOR_FM_PREFIX):
            return True
        if t == "功能模块：主播任务":
            return True
        return False
    if level == "#####":
        return (
            "任务帧+任务面板" in t
            or "聊天对话任务组件" in t
            or t.startswith("主播任务优化 ·")
            or t.endswith("· 主播任务")
        )
    return False


def family_include(level: str, title: str, _parent: str) -> bool:
    if level == "##":
        return title.strip() == "家族任务" or title.strip().startswith("五、家族任务")
    if level == "#####":
        return "家族任务" in title
    return False


def parse_family_revamp(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    start = text.find("## 五、家族任务")
    end = text.find("## 六、", start)
    if start < 0:
        return []
    chunk = text[start:end] if end > 0 else text[start:]
    return parse_step_expected_md(chunk, str(path.relative_to(ROOT)), "家族任务", family_include)


def parse_doc_table_anchor(path: Path) -> list[dict]:
    rows: list[dict] = []
    seq = [0]
    in_mod = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## 功能模块："):
            in_mod = "主播任务" in line or "任务Tab" in line
            continue
        if not in_mod or not line.startswith("|"):
            continue
        if "---" in line or "功能模块" in line:
            continue
        m = TABLE_ROW_RE.match(line)
        if not m:
            continue
        mod_col, step_col, exp_col = (x.strip() for x in m.groups())
        if "主播任务" not in mod_col and mod_col and "任务" not in mod_col:
            continue
        module = "主播任务" if "主播任务" in mod_col or "任务Tab" in mod_col else mod_col or "主播任务"
        flush_step(rows, module, str(path.relative_to(ROOT)), step_col, [exp_col] if exp_col else [], seq)
    return rows


def parse_bullet_legacy(
    text: str,
    src: str,
    module: str,
    start_heading: str,
    stop_at_h2: bool,
    only_h3: str | None = None,
) -> list[dict]:
    """知识库早期 bullet 形态：子模块名作步骤分组，每条 bullet 为预期。"""
    rows: list[dict] = []
    seq = [0]
    lines = text.splitlines()
    i = 0
    while i < len(lines) and lines[i].strip() != start_heading.strip():
        i += 1
    if i >= len(lines):
        return rows
    i += 1
    ctx = ""
    in_plat_anchor = only_h3 is not None
    while i < len(lines):
        line = lines[i]
        if stop_at_h2 and line.startswith("## ") and not line.startswith("### "):
            break
        if in_plat_anchor and line.startswith("### "):
            ctx = line.replace("###", "").strip()
            if ctx != only_h3:
                i += 1
                while i < len(lines) and not lines[i].startswith("### ") and not lines[i].startswith("## "):
                    i += 1
                continue
            i += 1
            continue
        if line.startswith("### "):
            ctx = line.replace("###", "").strip()
            i += 1
            continue
        if line.startswith("- ") and not line.startswith("- **"):
            bullet = line[2:].strip()
            if bullet and bullet != "—":
                step = ctx or "—"
                flush_step(rows, module, src, step, [bullet], seq)
        i += 1
    return rows


def dedupe_rows(rows: list[dict]) -> list[dict]:
    seen: set[tuple[str, str, str]] = set()
    out: list[dict] = []
    n = 0
    for r in rows:
        key = (r["测试步骤"], r["预期结果"], r["来源"])
        if key in seen:
            continue
        seen.add(key)
        n += 1
        r = {**r, "编号": f"KB_{n:04d}"}
        out.append(r)
    return out


def main() -> None:
    anchor_rows: list[dict] = []

    for md in sorted(KB.glob("*.md")):
        text = md.read_text(encoding="utf-8")
        anchor_rows.extend(
            parse_step_expected_md(text, f"testcase-kb/{md.name}", "主播任务", anchor_include)
        )

    anchor_rows.extend(parse_doc_table_anchor(DOCS / "消息.md"))
    anchor_rows.extend(
        parse_bullet_legacy(
            (KB / "消息.md").read_text(encoding="utf-8"),
            "testcase-kb/消息.md#主播任务",
            "主播任务",
            "## 主播任务",
            True,
        )
    )
    plat = (KB / "消息.md").read_text(encoding="utf-8")
    anchor_rows.extend(
        parse_bullet_legacy(
            plat,
            "testcase-kb/消息.md#平台/主播任务流程优化·主播任务",
            "主播任务",
            "## 平台/主播任务流程优化",
            True,
            only_h3="主播任务",
        )
    )

    family_rows: list[dict] = []
    family_rows.extend(
        parse_step_expected_md(
            (KB / "家族.md").read_text(encoding="utf-8"),
            "testcase-kb/家族.md",
            "家族任务",
            family_include,
        )
    )
    family_rows.extend(parse_family_revamp(DOCS / "家族改版.md"))
    family_rows.extend(
        parse_bullet_legacy(
            (KB / "家族.md").read_text(encoding="utf-8"),
            "testcase-kb/家族.md#家族任务",
            "家族任务",
            "## 家族任务",
            True,
        )
    )

    anchor_rows = dedupe_rows(anchor_rows)
    family_rows = dedupe_rows(family_rows)

    OUT.mkdir(parents=True, exist_ok=True)
    fields = ["编号", "功能模块", "测试步骤", "预期结果", "来源"]

    def write_csv(path: Path, rows: list[dict]) -> None:
        with path.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)

    def write_md(path: Path, title: str, rows: list[dict]) -> None:
        with path.open("w", encoding="utf-8") as f:
            f.write(f"# {title}\n\n")
            f.write(f"共 **{len(rows)}** 条（testcase-kb / documents 原文捞取，未改写）\n\n")
            f.write("| 编号 | 功能模块 | 测试步骤 | 预期结果 | 来源 |\n")
            f.write("|------|----------|----------|----------|------|\n")
            for r in rows:
                def esc(s: str) -> str:
                    return s.replace("|", "\\|").replace("\n", "<br>")

                f.write(
                    f"| {r['编号']} | {esc(r['功能模块'])} | {esc(r['测试步骤'])} | "
                    f"{esc(r['预期结果'])} | {esc(r['来源'])} |\n"
                )

    a_md = OUT / "主播任务_历史用例_库内原文.md"
    f_md = OUT / "家族任务_历史用例_库内原文.md"
    combo = OUT / "主播与家族任务_历史用例_库内原文.md"
    write_md(a_md, "主播任务 · 历史用例（库内原文）", anchor_rows)
    write_md(f_md, "家族任务 · 历史用例（库内原文）", family_rows)
    write_md(combo, "主播任务 + 家族任务 · 历史用例（库内原文）", anchor_rows + family_rows)
    write_csv(OUT / "主播与家族任务_历史用例_库内原文.csv", anchor_rows + family_rows)

    print(f"anchor_cases={len(anchor_rows)} family_cases={len(family_rows)} total={len(anchor_rows) + len(family_rows)}")
    print(f"written: {combo}")


if __name__ == "__main__":
    main()