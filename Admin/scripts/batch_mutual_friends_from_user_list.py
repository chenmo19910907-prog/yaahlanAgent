#!/usr/bin/env python3
"""从 ops-admin 用户列表选取 userId，并通过 MOA 互关结好友。"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "Admin" / "scripts"))

from admin_project_paths import admin_module_dir, moa_module_dir  # noqa: E402

sys.path.insert(0, str(admin_module_dir()))
sys.path.insert(0, str(moa_module_dir()))

from admin.env import load_local_env as load_admin_env  # noqa: E402
from admin.user_list import (  # noqa: E402
    parse_exclude_user_ids,
    pick_friend_candidates_from_user_list,
)
from moa.follow_relation import batch_mutual_follow  # noqa: E402


def _load_exclude_file(path: str | None) -> set[str]:
    if not path:
        return set()
    text = Path(path).read_text(encoding="utf-8")
    ids: set[str] = set()
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        ids.add(line)
    return ids


def _parse_friend_user_ids(raw: str | None) -> list[str]:
    if raw is None or not str(raw).strip():
        return []
    seen: set[str] = set()
    ordered: list[str] = []
    for token in parse_exclude_user_ids(raw):
        if token not in seen:
            seen.add(token)
            ordered.append(token)
    return ordered


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "从 MDP Nova 用户列表（userAdmin/queryUserProfileList）选取 userId，"
            "并通过 addUserRelation 双向互关结好友"
        )
    )
    parser.add_argument("--target-user-id", required=True, help="目标用户 userId（为其增加好友）")
    parser.add_argument("--count", type=int, default=30, help="需要新增互关好友数量（默认 30）")
    parser.add_argument(
        "--friend-user-ids",
        help="直接指定好友 userId 列表（逗号/空格分隔）；指定时跳过用户列表拉取",
    )
    parser.add_argument(
        "--exclude-user-ids",
        help="排除的 userId（逗号/空格分隔；如已是好友的账号）",
    )
    parser.add_argument("--exclude-file", help="每行一个 userId 的排除列表文件")
    parser.add_argument("--page-start", type=int, default=1, help="用户列表起始页 pageNo（默认 1）")
    parser.add_argument("--page-size", type=int, default=50, help="用户列表每页条数 pageSize（默认 50）")
    parser.add_argument("--max-pages", type=int, default=50, help="最多翻页数（默认 50）")
    parser.add_argument("--user-list-app-id", type=int, default=2005, help="用户列表 appId（默认 2005）")
    parser.add_argument("--user-list-nickname", help="用户列表昵称筛选")
    parser.add_argument("--user-list-phone", help="用户列表电话筛选")
    parser.add_argument("--user-list-area-code", help="用户列表电话区号")
    parser.add_argument("--user-list-device-id", help="用户列表 deviceId 筛选")
    parser.add_argument("--user-list-mmuidv3", help="用户列表 mmuidv3 筛选")
    parser.add_argument("--user-list-email", help="用户列表邮箱筛选")
    parser.add_argument("--user-list-area", help="用户列表大区 area")
    parser.add_argument("--user-list-ban-status", help="用户列表 banStatus")
    parser.add_argument("--user-list-gender", help="用户列表 gender")
    parser.add_argument("--user-list-country-code", help="用户列表 countryCode")
    parser.add_argument("--user-list-register-type", help="用户列表 registerType")
    parser.add_argument("--sleep-seconds", type=float, default=1.2, help="每次 addUserRelation 间隔秒数（默认 1.2）")
    parser.add_argument("--retry-sleep-seconds", type=float, default=2.0, help="触发限流后的重试等待秒数（默认 2.0）")
    parser.add_argument("--dry-run", action="store_true", help="只输出将互关的 userId，不调用 MOA")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    load_admin_env(str(admin_module_dir()))

    target_user_id = str(args.target_user_id).strip()
    if not target_user_id:
        print("target-user-id 不能为空", file=sys.stderr)
        return 2
    if args.count <= 0:
        print("count 必须为正整数", file=sys.stderr)
        return 2

    exclude = _load_exclude_file(args.exclude_file)
    exclude |= parse_exclude_user_ids(args.exclude_user_ids)

    if args.friend_user_ids:
        friends = _parse_friend_user_ids(args.friend_user_ids)
        friends = [uid for uid in friends if uid != target_user_id and uid not in exclude]
        if len(friends) > args.count:
            friends = friends[: args.count]
    else:
        friends = pick_friend_candidates_from_user_list(
            target_user_id=target_user_id,
            count=args.count,
            exclude=exclude,
            page_start=args.page_start,
            page_size=args.page_size,
            max_pages=args.max_pages,
            app_id=args.user_list_app_id,
            nickname=args.user_list_nickname,
            phone=args.user_list_phone,
            area_code=args.user_list_area_code,
            device_id=args.user_list_device_id,
            mmuidv3=args.user_list_mmuidv3,
            email=args.user_list_email,
            area=args.user_list_area,
            ban_status=args.user_list_ban_status,
            gender=args.user_list_gender,
            country_code=args.user_list_country_code,
            register_type=args.user_list_register_type,
        )

    plan = {
        "targetUserId": target_user_id,
        "requested": args.count,
        "selectedCount": len(friends),
        "excludeCount": len(exclude),
        "friendUserIds": friends,
        "dryRun": args.dry_run,
    }
    print(json.dumps(plan, ensure_ascii=False, indent=2))

    if len(friends) < args.count:
        print(
            f"仅找到 {len(friends)} 个可用 userId，少于目标 {args.count}",
            file=sys.stderr,
        )
        return 2
    if args.dry_run:
        return 0

    batch = batch_mutual_follow(
        target_user_id,
        friends,
        sleep_seconds=args.sleep_seconds,
        retry_sleep_seconds=args.retry_sleep_seconds,
        log=lambda msg: print(msg, file=sys.stderr),
    )
    summary = {
        "targetUserId": batch.target_user_id,
        "requested": batch.requested,
        "success": batch.success,
        "failed": batch.failed,
        "results": [asdict(item) for item in batch.results],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if batch.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
