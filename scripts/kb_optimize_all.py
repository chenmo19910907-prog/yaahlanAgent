#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
全量优化 testcase-kb 知识库（保留现有文件划分，不跨文件重分类）：

1. 移除无效块：无步骤、空正文、默认 Sheet、土语/俄语/老版本兼容专项等
2. 同文件 + 同 Sheet + 归一化模块名：仅保留最新版本
3. 正文指纹去重：完全相同用例合并（cluster 内 + 同 Sheet 跨模块）
4. 矛盾检测（较新版本优先，仅控制台摘要）
5. 清理目录标题、格式化 Markdown、重建房间切片
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from project_paths import testcase_kb_root  # noqa: E402

ROOT = testcase_kb_root()
from typing import Dict, List, Optional, Set, Tuple


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
body_fingerprint = content_opt.body_fingerprint
SAME_AS_SUFFIX_RE = content_opt.SAME_AS_SUFFIX_RE

STEP_RE = re.compile(r"^- \*\*步骤\*\*：(.+)$", re.M)
EXPECT_RE = re.compile(r"^  - \*\*预期\*\*：(.+)$", re.M)
KB_SCENARIO_RE = re.compile(r"^\*\*(.+?)\*\*\s*$", re.M)
KB_VERSION_RE = re.compile(r"^> \*\*版本\*\*")

# 无效 / 应丢弃的块（整块）
DROP_SHEET_RE = re.compile(
    r"土耳其政策整改|土语区分区策略|Android回退|回退\s*SDK|新老版本兼容|版本兼容|系统兼容测试",
    re.I,
)
DROP_MODULE_RE = re.compile(
    r"土耳其协议|多语言\s*[|｜]\s*(俄语|土语)|翻译\s*[|｜]\s*(俄语|土语)|"
    r"老版本|旧版本|低版本|新老版本|新旧版本|系统兼容|版本兼容|兼容性|"
    r"Android回退|回退\s*SDK|历史功能回测|功能回测|及之前旧版本",
    re.I,
)

FILE_DISPLAY_TITLE = {
    "特权VIP.md": "特权VIP",
    "房间PK.md": "房间PK",
}

GENERIC_SHEET_LEAF_RE = re.compile(
    r"^(优化需求|未归类需求|优化$|小需求$|技术优化)$",
    re.I,
)
SOURCE_TOPIC_RE = re.compile(r"版本用例[（(]([^）)]+)")
LEGACY_SHEET_PREFIX_RE = re.compile(r"客服与超管·")
COMPOSITE_PRIOR_RE = re.compile(
    r"展馆|红包|麦位|VIP|心愿|PK|充值|提现|家族|IM|私聊",
    re.I,
)
MIN_GLOBAL_FP_LEN = 80


@dataclass
class IndexedBlock:
    block: CaseBlock
    index: int
    origin: str


@dataclass
class ConflictItem:
    target: str
    sheet: str
    module: str
    kind: str
    older_version: str
    newer_version: str
    detail: str
    step: str = ""
    older_expect: str = ""
    newer_expect: str = ""


def norm_module_key(module: str) -> str:
    s = SAME_AS_SUFFIX_RE.sub("", module or "").strip()
    s = re.sub(r"^\d+[、.．\s]*", "", s)
    return re.sub(r"\s+", "", s).lower()


def norm_step_text(step: str) -> str:
    return re.sub(r"\s+", "", (step or "").strip()).lower()


def file_display_title(fname: str) -> str:
    return FILE_DISPLAY_TITLE.get(fname, fname.replace(".md", ""))


def should_drop_block(b: CaseBlock) -> bool:
    sheet = (b.sheet or "").strip()
    if csm.is_default_sheet_name(sheet):
        return True
    if DROP_SHEET_RE.search(sheet):
        return True
    if DROP_MODULE_RE.search(b.source_file or ""):
        return True
    for name in (b.module, b.parent_module):
        if name and DROP_MODULE_RE.search(name):
            return True
    body = b.body or ""
    if re.search(r"\*\*步骤\*\*", body):
        pass
    elif KB_VERSION_RE.search(body) or KB_SCENARIO_RE.search(body):
        pass
    elif re.search(r"^- ", body, re.M):
        pass
    else:
        return True
    if len(body_fingerprint(body)) < 8:
        return True
    return False


def parse_steps(body: str) -> Dict[str, frozenset[str]]:
    """解析步骤/预期或知识库场景要点，用于跨 Sheet 矛盾检测。"""
    if STEP_RE.search(body):
        steps: Dict[str, List[str]] = {}
        current: Optional[str] = None
        for ln in body.splitlines():
            sm = STEP_RE.match(ln.strip())
            if sm:
                current = sm.group(1).strip()
                steps.setdefault(current, [])
                continue
            if current:
                em = EXPECT_RE.match(ln)
                if em:
                    steps[current].append(em.group(1).strip())
        return {k: frozenset(v) for k, v in steps.items()}

    scenarios: Dict[str, List[str]] = {}
    current_kb: Optional[str] = None
    for ln in body.splitlines():
        km = KB_SCENARIO_RE.match(ln.strip())
        if km:
            current_kb = km.group(1).strip()
            scenarios.setdefault(current_kb, [])
            continue
        if current_kb and ln.strip().startswith("- "):
            scenarios[current_kb].append(ln.strip()[2:].strip())
    return {k: frozenset(v) for k, v in scenarios.items()}


def block_sort_key(ib: IndexedBlock) -> Tuple[Tuple[int, int, int], int]:
    return (ib.block.version_tuple, ib.index)


def _topic_from_source_file(source_file: str) -> str:
    m = SOURCE_TOPIC_RE.search(source_file or "")
    if not m:
        return ""
    first = re.split(r"[、,，]", m.group(1))[0].strip()
    if 2 <= len(first) <= 32:
        return first
    return ""


def _primary_composite_part(sheet: str) -> str:
    if "&" not in sheet:
        return sheet
    parts = [p for p in sheet.split("·") if p]
    if not parts:
        return sheet
    leaf = parts[-1]
    if "&" not in leaf:
        return sheet
    segs = [s.strip() for s in leaf.split("&") if s.strip()]
    chosen = segs[0]
    for seg in segs:
        if COMPOSITE_PRIOR_RE.search(seg):
            chosen = seg
            break
    parts[-1] = chosen
    return "·".join(parts)


def normalize_sheet_name(block: CaseBlock, origin_fname: str) -> str:
    """清理历史前缀、合订 Sheet 名，泛化 Sheet 用来源版本主题或模块名细化。"""
    sheet = (block.sheet or "未归类需求").strip()
    sheet = LEGACY_SHEET_PREFIX_RE.sub("", sheet)
    sheet = re.sub(r"^·+|·+$", "", sheet)
    sheet = _primary_composite_part(sheet)
    parts = [p for p in sheet.split("·") if p]
    leaf = parts[-1] if parts else sheet
    if GENERIC_SHEET_LEAF_RE.search(leaf):
        topic = _topic_from_source_file(block.source_file)
        mod = (block.module or "").strip()
        if topic:
            prefix = "·".join(parts[:-1]) if len(parts) > 1 else ""
            sheet = f"{prefix}·{topic}" if prefix else topic
        elif mod and len(mod) < 40 and not GENERIC_SHEET_LEAF_RE.search(mod):
            prefix = "·".join(parts[:-1]) if len(parts) > 1 else ""
            sheet = f"{prefix}·{mod}" if prefix else mod
    return sheet.strip() or "未归类需求"


def normalize_indexed_block(ib: IndexedBlock) -> IndexedBlock:
    new_sheet = normalize_sheet_name(ib.block, ib.origin)
    if new_sheet == (ib.block.sheet or ""):
        return ib
    b = ib.block
    nb = CaseBlock(
        sheet=new_sheet,
        module=b.module,
        version_label=b.version_label,
        version_tuple=b.version_tuple,
        source_file=b.source_file,
        body=b.body,
        parent_module=b.parent_module,
    )
    return IndexedBlock(block=nb, index=ib.index, origin=ib.origin)


def dedupe_global_fingerprint(
    indexed: List[IndexedBlock],
) -> Tuple[List[IndexedBlock], int]:
    """跨文件正文完全相同：全局仅保留最新版本一条。"""
    winners: Dict[str, IndexedBlock] = {}
    fp_candidates = 0
    for ib in indexed:
        if should_drop_block(ib.block):
            continue
        fp = body_fingerprint(ib.block.body)
        if len(fp) < MIN_GLOBAL_FP_LEN:
            continue
        fp_candidates += 1
        prev = winners.get(fp)
        if prev is None or block_sort_key(ib) > block_sort_key(prev):
            winners[fp] = ib
    kept: List[IndexedBlock] = []
    for ib in indexed:
        if should_drop_block(ib.block):
            continue
        fp = body_fingerprint(ib.block.body)
        if len(fp) < MIN_GLOBAL_FP_LEN:
            kept.append(normalize_indexed_block(ib))
            continue
        if winners.get(fp) is ib:
            kept.append(normalize_indexed_block(ib))
    removed = fp_candidates - len(winners)
    return kept, removed


def load_indexed_blocks(root: Path) -> List[IndexedBlock]:
    out: List[IndexedBlock] = []
    idx = 0
    for p in sorted(root.glob("*.md")):
        if p.name.startswith("_") or p.name.lower() == "readme.md":
            continue
        for b in extract_blocks(p.read_text(encoding="utf-8")):
            out.append(IndexedBlock(block=b, index=idx, origin=p.name))
            idx += 1
    return out


def detect_module_body_conflicts(
    groups: Dict[Tuple[str, str, str], List[IndexedBlock]],
) -> List[ConflictItem]:
    conflicts: List[ConflictItem] = []
    for (fname, sheet, mod_key), items in groups.items():
        if len(items) < 2 or not (mod_key or "").strip():
            continue
        by_fp: Dict[str, IndexedBlock] = {}
        for ib in items:
            fp = body_fingerprint(ib.block.body)
            if len(fp) < 16:
                continue
            if fp not in by_fp:
                by_fp[fp] = ib
        if len(by_fp) < 2:
            continue
        ordered = sorted(by_fp.values(), key=block_sort_key)
        o, n = ordered[0].block, ordered[-1].block
        conflicts.append(
            ConflictItem(
                target=fname,
                sheet=sheet,
                module=mod_key,
                kind="module",
                older_version=o.version_label or str(o.version_tuple),
                newer_version=n.version_label or str(n.version_tuple),
                detail=f"模块名「{o.module}」→「{n.module}」；保留 `{n.source_file}`",
            )
        )
    return conflicts


def detect_step_conflicts(
    groups: Dict[Tuple[str, str, str], List[IndexedBlock]],
) -> List[ConflictItem]:
    conflicts: List[ConflictItem] = []
    for (fname, sheet, mod_key), items in groups.items():
        if len(items) < 2:
            continue
        sorted_items = sorted(items, key=block_sort_key)
        timeline: Dict[str, Tuple[str, frozenset[str]]] = {}
        for ib in sorted_items:
            b = ib.block
            ver = b.version_label or str(b.version_tuple)
            for step, expects in parse_steps(b.body).items():
                if not step:
                    continue
                if step not in timeline:
                    timeline[step] = (ver, expects)
                    continue
                prev_ver, prev_exp = timeline[step]
                if prev_exp != expects:
                    conflicts.append(
                        ConflictItem(
                            target=fname,
                            sheet=sheet,
                            module=mod_key,
                            kind="step",
                            step=step,
                            older_version=prev_ver,
                            newer_version=ver,
                            older_expect=(next(iter(prev_exp)) if prev_exp else "")[:120],
                            newer_expect=(next(iter(expects)) if expects else "")[:120],
                            detail=f"步骤「{step[:60]}」预期不一致",
                        )
                    )
                timeline[step] = (ver, expects)
    return conflicts


def detect_all_conflicts(
    groups: Dict[Tuple[str, str, str], List[IndexedBlock]],
) -> List[ConflictItem]:
    seen: Set[Tuple[str, str, str, str, str]] = set()
    out: List[ConflictItem] = []
    for item in detect_module_body_conflicts(groups) + detect_step_conflicts(groups):
        key = (item.target, item.sheet, item.module, item.kind, item.step or item.detail[:40])
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def resolve_duplicate_steps_in_body(body: str) -> Tuple[str, int]:
    """正文内同一步骤/场景重复出现：保留最后一次（视为较新）。"""
    if not STEP_RE.search(body):
        return body, 0
    lines = body.splitlines()
    meta_end = 0
    for j, ln in enumerate(lines):
        if STEP_RE.match(ln.strip()):
            meta_end = j
            break
    header = lines[:meta_end]
    rest = lines[meta_end:]

    ordered_steps: List[str] = []
    expects_map: Dict[str, List[str]] = {}
    dup_count = 0
    i = 0
    while i < len(rest):
        sm = STEP_RE.match(rest[i].strip())
        if not sm:
            i += 1
            continue
        step = sm.group(1).strip()
        i += 1
        exps: List[str] = []
        while i < len(rest):
            if STEP_RE.match(rest[i].strip()):
                break
            em = EXPECT_RE.match(rest[i])
            if em:
                exps.append(em.group(1).strip())
            i += 1
        if step in expects_map:
            dup_count += 1
        else:
            ordered_steps.append(step)
        expects_map[step] = exps

    out_lines = list(header)
    if out_lines and out_lines[-1].strip():
        out_lines.append("")
    for step in ordered_steps:
        out_lines.append(f"- **步骤**：{step}")
        for e in expects_map[step]:
            out_lines.append(f"  - **预期**：{e}")
        out_lines.append("")
    return content_opt.normalize_lines("\n".join(out_lines)), dup_count


def collapse_cross_sheet_modules(
    best: Dict[Tuple[str, str, str], IndexedBlock],
) -> Tuple[Dict[Tuple[str, str, str], IndexedBlock], List[ConflictItem], int]:
    """同文件 + 同归一化模块跨 Sheet 重复：仅保留最新版本块。"""
    by_mod: Dict[Tuple[str, str], List[Tuple[Tuple[str, str, str], IndexedBlock]]] = (
        defaultdict(list)
    )
    for key, ib in best.items():
        by_mod[(key[0], key[2])].append((key, ib))

    out: Dict[Tuple[str, str, str], IndexedBlock] = {}
    conflicts: List[ConflictItem] = []
    collapsed = 0
    for (fname, mod_key), entries in by_mod.items():
        if len(entries) == 1:
            out[entries[0][0]] = entries[0][1]
            continue
        items = [ib for _, ib in entries]
        step_seen: Dict[str, Tuple[str, frozenset[str]]] = {}
        for ib in sorted(items, key=block_sort_key):
            b = ib.block
            ver = b.version_label or str(b.version_tuple)
            for step, expects in parse_steps(b.body).items():
                if not step:
                    continue
                ns = norm_step_text(step)
                if ns in step_seen:
                    prev_ver, prev_exp = step_seen[ns]
                    if prev_exp != expects:
                        conflicts.append(
                            ConflictItem(
                                target=fname,
                                sheet=b.sheet or "",
                                module=mod_key,
                                kind="step",
                                step=step[:80],
                                older_version=prev_ver,
                                newer_version=ver,
                                older_expect=(next(iter(prev_exp)) if prev_exp else "")[
                                    :120
                                ],
                                newer_expect=(
                                    next(iter(expects)) if expects else ""
                                )[:120],
                                detail="同模块跨 Sheet 步骤预期不一致，已保留较新版本",
                            )
                        )
                step_seen[ns] = (ver, expects)
        winner = max(items, key=block_sort_key)
        collapsed += len(entries) - 1
        sheet = winner.block.sheet or "未归类需求"
        out[(fname, sheet, mod_key)] = winner
    return out, conflicts, collapsed


def dedupe_cluster_keep_newest(
    tree: Dict[str, Dict[str, Dict[str, List[CaseBlock]]]],
) -> Tuple[Dict[str, Dict[str, Dict[str, List[CaseBlock]]]], int, int]:
    """同 Sheet 同 cluster 多模块块：仅保留最新版本；并清理正文内重复步骤。"""
    removed = 0
    intra_dups = 0
    for sheets in tree.values():
        for sheet_clusters in sheets.values():
            for cluster, blist in list(sheet_clusters.items()):
                if len(blist) > 1:
                    winner = max(
                        blist,
                        key=lambda b: (b.version_tuple, b.module),
                    )
                    removed += len(blist) - 1
                    blist = [winner]
                for b in blist:
                    new_body, n = resolve_duplicate_steps_in_body(b.body)
                    intra_dups += n
                    b.body = new_body
                sheet_clusters[cluster] = blist
    return tree, removed, intra_dups


def pick_latest_resolved(
    indexed: List[IndexedBlock],
) -> Tuple[Dict[Tuple[str, str, str], IndexedBlock], List[ConflictItem], int, int]:
    """key = (origin_file, sheet, norm_module) -> 最新块；再按模块跨 Sheet 折叠。"""
    groups: Dict[Tuple[str, str, str], List[IndexedBlock]] = defaultdict(list)
    dropped = 0
    for ib in indexed:
        if should_drop_block(ib.block):
            dropped += 1
            continue
        key = (ib.origin, ib.block.sheet or "未归类需求", norm_module_key(ib.block.module))
        groups[key].append(ib)

    conflicts = detect_all_conflicts(groups)
    best: Dict[Tuple[str, str, str], IndexedBlock] = {}
    for key, items in groups.items():
        best[key] = max(items, key=block_sort_key)

    best, cross_conflicts, collapsed = collapse_cross_sheet_modules(best)
    conflicts.extend(cross_conflicts)
    return best, conflicts, dropped, collapsed


def _block_newer(a: CaseBlock, b: CaseBlock) -> CaseBlock:
    if a.version_tuple != b.version_tuple:
        return a if a.version_tuple > b.version_tuple else b
    return a if a.module >= b.module else b


def build_trees_by_file(
    best: Dict[Tuple[str, str, str], IndexedBlock],
) -> Dict[str, Dict[str, Dict[str, List[CaseBlock]]]]:
    tree: Dict[str, Dict[str, Dict[str, List[CaseBlock]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(list))
    )
    for (fname, sheet, _mk), ib in best.items():
        b = ib.block
        cluster = csm.merge_cluster_key(sheet, b.module)
        bucket = tree[fname][sheet][cluster]
        if not any(x.module == b.module for x in bucket):
            bucket.append(b)
    return tree


def dedupe_fingerprint_variants(
    tree: Dict[str, Dict[str, Dict[str, List[CaseBlock]]]],
) -> Tuple[Dict[str, Dict[str, Dict[str, List[CaseBlock]]]], int]:
    removed = 0
    for sheets in tree.values():
        for clusters in sheets.values():
            for cluster, blist in list(clusters.items()):
                seen: Dict[str, CaseBlock] = {}
                for b in blist:
                    fp = body_fingerprint(b.body)
                    if not fp:
                        continue
                    if fp not in seen:
                        seen[fp] = b
                        continue
                    removed += 1
                    seen[fp] = _block_newer(seen[fp], b)
                no_fp = [b for b in blist if not body_fingerprint(b.body)]
                clusters[cluster] = no_fp + list(seen.values())
    return tree, removed


def dedupe_sheet_fingerprint(
    tree: Dict[str, Dict[str, Dict[str, List[CaseBlock]]]],
) -> int:
    removed = 0
    for sheets in tree.values():
        for sheet, clusters in sheets.items():
            fp_best: Dict[str, Tuple[str, CaseBlock]] = {}
            for cluster, blist in clusters.items():
                for b in blist:
                    fp = body_fingerprint(b.body)
                    if not fp:
                        continue
                    if fp not in fp_best:
                        fp_best[fp] = (cluster, b)
                    else:
                        prev_c, prev_b = fp_best[fp]
                        winner = _block_newer(prev_b, b)
                        fp_best[fp] = (cluster if winner is b else prev_c, winner)
            for cluster, blist in list(clusters.items()):
                kept = []
                for b in blist:
                    fp = body_fingerprint(b.body)
                    if not fp:
                        kept.append(b)
                        continue
                    best_c, best_b = fp_best[fp]
                    if cluster == best_c and b is best_b:
                        kept.append(b)
                    else:
                        removed += 1
                clusters[cluster] = kept
            sheets[sheet] = {k: v for k, v in clusters.items() if v}
    return removed


def prune_empty_sheets(tree: Dict) -> int:
    removed = 0
    for fname in list(tree.keys()):
        for sheet in list(tree[fname].keys()):
            if csm.is_default_sheet_name(sheet):
                del tree[fname][sheet]
                removed += 1
                continue
            tree[fname][sheet] = {k: v for k, v in tree[fname][sheet].items() if v}
            if not tree[fname][sheet]:
                del tree[fname][sheet]
                removed += 1
        if not tree[fname]:
            del tree[fname]
    return removed


def main() -> None:
    ap = argparse.ArgumentParser(description="知识库全量去重（保留文件划分）")
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-post", action="store_true", help="跳过后续 clean/format/房间切片")
    args = ap.parse_args()
    root: Path = args.root

    raw_indexed = load_indexed_blocks(root)
    if not raw_indexed:
        raise SystemExit("未解析到任何用例块")

    sheet_renamed = sum(
        1
        for ib in raw_indexed
        if normalize_sheet_name(ib.block, ib.origin) != (ib.block.sheet or "")
    )
    indexed, global_dup = dedupe_global_fingerprint(raw_indexed)

    latest_ib, conflicts, dropped, collapsed = pick_latest_resolved(indexed)
    tree = build_trees_by_file(latest_ib)
    tree, n_var = dedupe_fingerprint_variants(tree)
    n_sheet = dedupe_sheet_fingerprint(tree)
    tree, n_cluster, n_intra = dedupe_cluster_keep_newest(tree)
    n_prune = prune_empty_sheets(tree)

    module_count = sum(len(c) for f in tree.values() for c in f.values())

    if args.dry_run:
        print(
            f"dry-run: in={len(indexed)} drop={dropped} keep={len(latest_ib)} "
            f"conflicts={len(conflicts)} dedup={n_var + n_sheet} files={len(tree)}"
        )
        return

    stats = {
        "dropped_invalid": dropped,
        "global_fp_dup": global_dup,
        "sheet_renamed": sheet_renamed,
        "collapsed_cross_sheet": collapsed,
        "cluster_newest": n_cluster,
        "intra_step_dup": n_intra,
        "fp_variant": n_var,
        "fp_sheet": n_sheet,
        "pruned_sheets": n_prune,
        "modules": module_count,
    }

    for fname, sheets_map in sorted(tree.items()):
        title = file_display_title(fname)
        if not sheets_map:
            continue
        md = csm.build_from_tree(title, sheets_map)
        md = md.replace(
            "- **冲突**：同一 Sheet + 原功能模块名仅保留最新版本。",
            "- **冲突**：同 Sheet + 模块仅保留最新版本；完全相同正文已合并。",
            1,
        )
        md = md.replace(
            "- **冲突**：同 Sheet + 模块仅保留最新版本；完全相同正文已合并（见 `_知识库优化报告.md`）。",
            "- **冲突**：同 Sheet + 模块仅保留最新版本；完全相同正文已合并。",
        )
        if fname == "房间PK.md" and md.startswith("# 房间PK"):
            rest = md.split("\n---\n\n", 1)
            body = rest[-1] if len(rest) > 1 else md
            if body.lstrip().startswith("# 房间PK"):
                body = body.split("\n", 1)[1]
            md = (
                "# 房间PK\n\n> **范围**：房间内 PK、跨房 PK。\n\n---\n\n" + body.lstrip("\n")
            )
        (root / fname).write_text(md, encoding="utf-8")

    if not args.skip_post:
        for script in (
            "kb_clean_toc_titles.py",
            "optimize_kb_docs.py",
            "kb_extract_room_modules.py",
        ):
            p = SCRIPTS / script
            if p.exists():
                subprocess.run([sys.executable, str(p), "--root", str(root)], check=False)
    print(
        f"kb_optimize_all: {len(raw_indexed)} 块 -> 全局去重 {global_dup}, "
        f"丢弃无效 {dropped}, 跨Sheet折叠 {collapsed}, "
        f"保留 {module_count} 模块 / {len(tree)} 文件"
    )
    print(
        f"  去重: cluster块 {n_cluster} + 正文重复步骤 {n_intra} + "
        f"指纹 {n_var}+{n_sheet}; 矛盾 {len(conflicts)} 条"
    )
    if conflicts:
        print(f"  矛盾: {len(conflicts)} 条（已按较新版本保留）")


if __name__ == "__main__":
    main()
