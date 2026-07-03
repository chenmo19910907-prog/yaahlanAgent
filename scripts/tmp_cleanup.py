#!/usr/bin/env python3
"""清理仓库 .tmp 目录中的过期/一次性临时文件。"""

from __future__ import annotations

import argparse
import fnmatch
import json
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TMP_DIR = ROOT / ".tmp"

# 一次性 MOA payload / 探针：执行完即可删，默认保留 1 小时兜底
EPHEMERAL_GLOBS = (
    "incr_pk_*.json",
    "modify_rank_*.json",
    "family_pk_clear_pk_*.json",
    "family_pk_clear_settle_*.json",
    "family_pk_settle_*.json",
    "family_pk_remove_user_*.json",
    "*_payload.json",
    "tunnel_*.json",
    "_area_probe.json",
    "package_gift_*.json",
)

# 执行报告 / 汇总：默认保留 7 天
REPORT_GLOBS = (
    "family_pk_member_pk_seed_*.json",
    "family_pk_member_reward_*.json",
    "family_pk_reward_calc_*.json",
    "family_pk_match_verify_*.json",
    "family_pk_dispatch_verify_*.json",
    "family_pk_receive_rank_set_*.json",
    "family_receive_rank_set_*.json",
    "family_pk_admin_families_*.json",
    "family_pk_rematch_*.json",
    "family_pk_member_incr_*.json",
    "family_pk_reward_verify_*.json",
    "family_pk_settle_run.json",
)

DEFAULT_EPHEMERAL_MAX_AGE_S = 3600
DEFAULT_REPORT_MAX_AGE_S = 7 * 24 * 3600
DEFAULT_LOG_MAX_AGE_S = 3 * 24 * 3600
DEFAULT_WORKFLOW_RUN_MAX_AGE_S = 7 * 24 * 3600
DEFAULT_MISC_MAX_AGE_S = 3 * 24 * 3600
DEFAULT_WORKFLOW_RUN_KEEP = 20


@dataclass
class CleanupStats:
    removed_files: int = 0
    removed_dirs: int = 0
    kept_files: int = 0
    bytes_freed: int = 0
    by_reason: dict[str, int] | None = None

    def __post_init__(self) -> None:
        if self.by_reason is None:
            self.by_reason = {}


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _matches_any(name: str, patterns: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatch(name, pat) for pat in patterns)


def _classify(path: Path) -> str:
    name = path.name
    if path.parent.name == "workflow_runs" and name.endswith("_payload.json"):
        return "ephemeral"
    if _matches_any(name, EPHEMERAL_GLOBS):
        return "ephemeral"
    if path.suffix == ".log":
        return "log"
    if path.parent.name == "workflow_runs" and path.suffix == ".json":
        return "workflow_run"
    if _matches_any(name, REPORT_GLOBS):
        return "report"
    return "misc"


def _max_age_for(kind: str, *, ephemeral_max_age_s: float, report_max_age_s: float) -> float:
    if kind == "ephemeral":
        return ephemeral_max_age_s
    if kind == "report":
        return report_max_age_s
    if kind == "log":
        return DEFAULT_LOG_MAX_AGE_S
    if kind == "workflow_run":
        return DEFAULT_WORKFLOW_RUN_MAX_AGE_S
    return DEFAULT_MISC_MAX_AGE_S


def _remove_path(path: Path, stats: CleanupStats, reason: str, *, dry_run: bool) -> None:
    size = _size(path)
    if dry_run:
        stats.removed_files += 1
        stats.bytes_freed += size
        stats.by_reason[reason] = stats.by_reason.get(reason, 0) + 1
        return
    try:
        if path.is_dir():
            shutil.rmtree(path)
            stats.removed_dirs += 1
        else:
            path.unlink()
            stats.removed_files += 1
        stats.bytes_freed += size
        stats.by_reason[reason] = stats.by_reason.get(reason, 0) + 1
    except OSError as exc:
        print(f"WARN 删除失败 {path}: {exc}", file=sys.stderr)


def _prune_workflow_runs(
    runs_dir: Path,
    *,
    now: float,
    max_age_s: float,
    keep_latest: int,
    stats: CleanupStats,
    dry_run: bool,
) -> None:
    if not runs_dir.is_dir():
        return
    reports = sorted(
        (p for p in runs_dir.iterdir() if p.is_file() and p.suffix == ".json" and not p.name.endswith("_payload.json")),
        key=_mtime,
        reverse=True,
    )
    for idx, path in enumerate(reports):
        age = now - _mtime(path)
        if idx >= keep_latest or age > max_age_s:
            _remove_path(path, stats, "workflow_run_prune", dry_run=dry_run)
        else:
            stats.kept_files += 1


def cleanup_tmp(
    *,
    dry_run: bool = False,
    aggressive: bool = False,
    ephemeral_max_age_s: float = DEFAULT_EPHEMERAL_MAX_AGE_S,
    report_max_age_s: float = DEFAULT_REPORT_MAX_AGE_S,
    workflow_run_keep: int = DEFAULT_WORKFLOW_RUN_KEEP,
) -> CleanupStats:
    """按规则清理 .tmp；aggressive=True 时立即删除所有 ephemeral 类文件。"""
    stats = CleanupStats()
    if not TMP_DIR.is_dir():
        return stats

    now = time.time()
    if aggressive:
        ephemeral_max_age_s = 0

    # 先删 workflow_runs 内 payload
    runs_dir = TMP_DIR / "workflow_runs"
    if runs_dir.is_dir():
        for path in runs_dir.iterdir():
            if not path.is_file():
                continue
            if path.name.endswith("_payload.json"):
                age = now - _mtime(path)
                if aggressive or age >= ephemeral_max_age_s:
                    _remove_path(path, stats, "ephemeral", dry_run=dry_run)
                else:
                    stats.kept_files += 1

    # 根目录与其它子目录（workflow_runs 报告单独 prune）
    for path in sorted(TMP_DIR.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if path == TMP_DIR:
            continue
        if not path.exists():
            continue
        if path.is_dir():
            if path.name == "workflow_runs":
                continue
            try:
                if not any(path.iterdir()):
                    _remove_path(path, stats, "empty_dir", dry_run=dry_run)
                else:
                    stats.kept_files += 1
            except OSError:
                pass
            continue

        rel_parent = path.parent.relative_to(TMP_DIR)
        if rel_parent.parts and rel_parent.parts[0] == "workflow_runs":
            continue

        kind = _classify(path)
        age = now - _mtime(path)
        limit = _max_age_for(kind, ephemeral_max_age_s=ephemeral_max_age_s, report_max_age_s=report_max_age_s)
        if aggressive and kind == "ephemeral":
            _remove_path(path, stats, kind, dry_run=dry_run)
        elif age >= limit:
            _remove_path(path, stats, kind, dry_run=dry_run)
        else:
            stats.kept_files += 1

    _prune_workflow_runs(
        runs_dir,
        now=now,
        max_age_s=DEFAULT_WORKFLOW_RUN_MAX_AGE_S,
        keep_latest=workflow_run_keep,
        stats=stats,
        dry_run=dry_run,
    )

    # 再次清理空目录
    for path in sorted(TMP_DIR.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if path.is_dir() and path != TMP_DIR and path.name != "workflow_runs":
            try:
                if not any(path.iterdir()):
                    _remove_path(path, stats, "empty_dir", dry_run=dry_run)
            except OSError:
                pass

    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="清理 .tmp 过期临时文件")
    parser.add_argument("--dry-run", action="store_true", help="仅统计，不实际删除")
    parser.add_argument(
        "--aggressive",
        action="store_true",
        help="立即删除所有 ephemeral 类文件（incr_pk/modify_rank 等 payload）",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="以 JSON 输出统计",
    )
    args = parser.parse_args(argv)

    stats = cleanup_tmp(dry_run=args.dry_run, aggressive=args.aggressive)
    payload = {
        "tmpDir": str(TMP_DIR),
        "dryRun": args.dry_run,
        "aggressive": args.aggressive,
        "removedFiles": stats.removed_files,
        "removedDirs": stats.removed_dirs,
        "keptFiles": stats.kept_files,
        "bytesFreed": stats.bytes_freed,
        "byReason": stats.by_reason,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        mode = "（dry-run）" if args.dry_run else ""
        print(
            f".tmp 清理完成{mode}: "
            f"删除 {stats.removed_files} 文件 / {stats.removed_dirs} 目录, "
            f"释放 {stats.bytes_freed / 1024:.1f} KB, 保留 {stats.kept_files} 项"
        )
        if stats.by_reason:
            for reason, count in sorted(stats.by_reason.items()):
                print(f"  - {reason}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
