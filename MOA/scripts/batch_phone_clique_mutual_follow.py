#!/usr/bin/env python3
"""手机号段 / userId 列表两两互关，内置 Web Agent 批量进度上报。"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

from moa_script_paths import (
    batch_progress_script,
    ensure_moa_gift_paths,
    moa_execute_path,
    moa_template,
    repo_root,
)

ensure_moa_gift_paths()

from moa.follow_relation import CliqueMutualFollowResult, clique_mutual_follow  # noqa: E402

REPO = repo_root()


def _run_json(cmd: list[str], *, timeout: int = 120) -> dict:
    proc = subprocess.run(
        cmd,
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    text = (proc.stdout or "").strip() or (proc.stderr or "").strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise RuntimeError(f"命令无 JSON: {' '.join(cmd[-4:])} :: {text[-400:]}")
    data = json.loads(text[start : end + 1])
    if proc.returncode != 0 and not data.get("ok") and "userId" not in data:
        raise RuntimeError(f"命令失败 exit={proc.returncode}: {text[-400:]}")
    return data


def resolve_user_key(explicit: str | None) -> str:
    import os

    if explicit and explicit.strip():
        return explicit.strip()
    return (os.environ.get("WEB_AGENT_BATCH_KEY") or "").strip()


def report_progress(
    user_key: str,
    *,
    current: int,
    total: int,
    detail: str = "",
    result_text: str = "",
) -> None:
    if not user_key or total < 3:
        return
    cmd = [
        sys.executable,
        str(batch_progress_script()),
        "--current",
        str(current),
        "--total",
        str(total),
        "--label",
        "两两互关",
    ]
    if user_key:
        cmd.extend(["--user-key", user_key])
    if detail:
        cmd.extend(["--detail", detail])
    if result_text:
        cmd.extend(["--result-text", result_text])
    subprocess.run(cmd, cwd=str(REPO), check=False)


def parse_phones(raw: str | None) -> list[str]:
    if not raw or not str(raw).strip():
        return []
    tokens = str(raw).replace(",", " ").split()
    return [t.strip() for t in tokens if t.strip()]


def phone_range(start: str, end: str) -> list[str]:
    start_n = int(str(start).strip())
    end_n = int(str(end).strip())
    if end_n < start_n:
        start_n, end_n = end_n, start_n
    return [str(n) for n in range(start_n, end_n + 1)]


def resolve_phone_user_id(phone: str, *, area_code: str) -> str:
    cmd = [
        "python3",
        str(moa_execute_path()),
        "--payload-file",
        str(moa_template("用户-按手机号查userId.json")),
        "--query-user-by-phone",
        phone,
        "--phone-area-code",
        area_code,
    ]
    data = _run_json(cmd)
    uid = str(data.get("userId") or data.get("data") or "").strip()
    if not uid:
        raise RuntimeError(f"手机号 {phone} 未解析到 userId: {data}")
    return uid


def resolve_accounts(
    *,
    phones: list[str],
    user_ids: list[str],
    area_code: str,
) -> list[dict[str, str]]:
    accounts: list[dict[str, str]] = []
    for phone in phones:
        uid = resolve_phone_user_id(phone, area_code=area_code)
        accounts.append({"phone": phone, "userId": uid})
    seen: set[str] = set()
    for uid in user_ids:
        key = str(uid).strip()
        if not key or key in seen:
            continue
        seen.add(key)
        accounts.append({"phone": "", "userId": key})
    return accounts


def build_result_markdown(
    accounts: list[dict[str, str]],
    batch: CliqueMutualFollowResult,
) -> str:
    phone_part = ""
    if accounts and accounts[0].get("phone"):
        phones = [a["phone"] for a in accounts if a.get("phone")]
        if phones:
            phone_part = f"{phones[0]} ~ {phones[-1]}（{len(phones)} 个）"
    lines = [
        f"**已完成。** {phone_part or '指定账号'} 已全部两两互相关注（成为好友）。",
        "",
        "| 项 | 值 |",
        "|---|---|",
        f"| 账号数 | {len(batch.user_ids)} |",
        f"| 互关对数 | {batch.pair_total} 对（C({len(batch.user_ids)},2)） |",
        f"| 成功 | **{batch.success} / {batch.pair_total}** |",
        f"| 失败 | {batch.failed} |",
        "",
        "执行方式：MOA `addUserRelation` 双向互关；Web Agent 批量进度按对数 N/M 上报。",
    ]
    if batch.failed:
        lines.extend(["", "**失败对：**", ""])
        for item in batch.results:
            if not item.ok:
                lines.append(
                    f"- `{item.target_user_id}` ↔ `{item.friend_user_id}` "
                    f"（{item.forward_em or '-'} / {item.reverse_em or '-'}）"
                )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="手机号段或 userId 列表内账号两两互关，内置 batch_progress 上报",
    )
    parser.add_argument("--phone-start", help="手机号段起始（含）")
    parser.add_argument("--phone-end", help="手机号段结束（含）")
    parser.add_argument("--phones", help="手机号列表（逗号/空格分隔）")
    parser.add_argument("--user-ids", help="直接指定 userId 列表（逗号/空格分隔）")
    parser.add_argument("--phone-area-code", default="86", help="查 userId 区号（测试默认 86）")
    parser.add_argument("--user-key", default="", help="Web Agent batch_key（默认 WEB_AGENT_BATCH_KEY）")
    parser.add_argument("--sleep-seconds", type=float, default=1.2, help="每次 addUserRelation 间隔")
    parser.add_argument("--retry-sleep-seconds", type=float, default=2.0, help="限流重试等待秒数")
    parser.add_argument("--dry-run", action="store_true", help="只解析账号与对数，不调用 MOA")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    user_key = resolve_user_key(args.user_key or None)

    phones = parse_phones(args.phones)
    if args.phone_start and args.phone_end:
        phones.extend(phone_range(args.phone_start, args.phone_end))
    user_ids = parse_phones(args.user_ids)

    if not phones and not user_ids:
        print("须指定 --phone-start/--phone-end、--phones 或 --user-ids", file=sys.stderr)
        return 2

    accounts = resolve_accounts(
        phones=phones,
        user_ids=user_ids,
        area_code=str(args.phone_area_code or "86").strip(),
    )
    uid_list = [a["userId"] for a in accounts]
    pair_total = len(uid_list) * (len(uid_list) - 1) // 2
    if pair_total < 1:
        print("至少需要 2 个账号", file=sys.stderr)
        return 2

    plan = {
        "accounts": accounts,
        "userIds": uid_list,
        "pairTotal": pair_total,
        "dryRun": args.dry_run,
    }
    print(json.dumps(plan, ensure_ascii=False, indent=2))

    if args.dry_run:
        return 0

    report_progress(user_key, current=0, total=pair_total)

    def on_pair_done(current: int, total: int, item) -> None:
        detail = f"{item.target_user_id}↔{item.friend_user_id}"
        report_progress(user_key, current=current, total=total, detail=detail)

    batch = clique_mutual_follow(
        uid_list,
        sleep_seconds=args.sleep_seconds,
        retry_sleep_seconds=args.retry_sleep_seconds,
        log=lambda msg: print(msg, file=sys.stderr),
        on_pair_done=on_pair_done,
    )
    result_md = build_result_markdown(accounts, batch)
    report_progress(
        user_key,
        current=batch.pair_total,
        total=batch.pair_total,
        result_text=result_md,
    )
    print(result_md)
    summary = {
        "userIds": batch.user_ids,
        "pairTotal": batch.pair_total,
        "success": batch.success,
        "failed": batch.failed,
        "results": [asdict(item) for item in batch.results],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if batch.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
