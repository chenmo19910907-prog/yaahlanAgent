#!/usr/bin/env python3
"""从 ops-admin 用户列表选取 userId，并通过 MOA 互关结好友。

支持：
- 从创新中台用户列表自动拉取候选人
- 直接指定 userId 列表
- 互关后自动发送随机消息（--send-message）
- 自动去重日志（--processed-log）
- 大批量（1000+）自动采用分阶段策略：A→B 并行 → B→A 串行
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

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

# ── 消息模板 ──────────────────────────────────────────────────────────────────

RANDOM_TEXTS = [
    "Hey! How are you?", "Hello~", "Nice to meet you!", "Hi there 👋",
    "What's up?", "Good morning!", "Long time no see!", "How's it going?",
    "Let's chat!", "Yo!", "Hey buddy!", "Hi friend!",
    "Have a great day!", "Miss you!", "Wanna hang out?",
    "Good vibes only!", "How's everything?", "Nice day!",
]
IMG_URLS = [
    "https://static.momocdn.com/vogazone/test/img_001.jpg",
    "https://static.momocdn.com/vogazone/test/img_002.jpg",
    "https://static.momocdn.com/vogazone/test/img_003.jpg",
]
VIDEO_URLS = [
    "https://static.momocdn.com/vogazone/test/video_001.mp4",
    "https://static.momocdn.com/vogazone/test/video_002.mp4",
]

IM_SERVICE_URI = "/service/voga-base-service-im-stage"
IM_METHOD = "sendP2PMessageWithNoGreet"


# ── 工具函数 ──────────────────────────────────────────────────────────────────

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


def _load_processed_log(path: str | None) -> set[str]:
    """加载已处理过的 userId，自动排除避免重复互关。"""
    if not path:
        return set()
    p = Path(path)
    if not p.exists():
        return set()
    ids: set[str] = set()
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            ids.add(line)
    return ids


def _append_processed_log(path: str | None, user_ids: list[str]) -> None:
    """追加写入已处理的 userId 到日志文件。"""
    if not path or not user_ids:
        return
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        for uid in user_ids:
            f.write(f"{uid}\n")


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


def _call_moa_direct(service_uri: str, method: str, args: list[Any]) -> Any:
    """直接通过 Redis 调用 MOA 服务（复用 Gift 模块的底层能力）。"""
    gift_dir = str(REPO_ROOT / "Gift")
    if gift_dir not in sys.path:
        sys.path.insert(0, gift_dir)
    from gift.send_stage import call_moa
    return call_moa(service_uri, method, args)


def _send_random_message(from_uid: str, to_uid: str) -> tuple[bool, str]:
    """发送随机类型消息（TEXT 60% / IMG 25% / VIDEO 15%）。"""
    roll = random.random()
    if roll < 0.60:
        msg_type = "TEXT"
        text = random.choice(RANDOM_TEXTS)
    elif roll < 0.85:
        msg_type = "IMG"
        text = random.choice(IMG_URLS)
    else:
        msg_type = "VIDEO"
        text = random.choice(VIDEO_URLS)

    body = {
        "fromUid": from_uid,
        "receiverList": [to_uid],
        "imDataTypeEnum": msg_type,
        "text": text,
        "mustReach": True,
        "imCallBackTag": 0,
        "extra": {"is_greet": 0},
        "messageExtraDto": {
            "needPush": True,
            "sendMode": "SEND_SENDER_AND_RECEIVER",
            "needSaveMsg": True,
            "addUnReadCount": True,
        },
    }
    try:
        result = _call_moa_direct(IM_SERVICE_URI, IM_METHOD, [body])
        ok = isinstance(result, dict) and (
            result.get("success") is True or result.get("ec") == 200
        )
        return ok, msg_type
    except Exception:
        return False, msg_type


# ── 大批量并行策略 ──────────────────────────────────────────────────────────────

def _fast_batch_follow_and_message(
    target_user_id: str,
    friends: list[str],
    *,
    send_message: bool = False,
    log: Any = None,
) -> dict[str, Any]:
    """
    大批量互关策略：
    Phase 1: A→B 全部并行（无频控）
    Phase 2: B→A 串行（自然间隔，频控时短暂等待）
    Phase 3: 发消息（可选，并行安全）
    """
    from moa.follow_relation import add_user_relation

    def _log(msg: str) -> None:
        if log:
            log(msg)

    total = len(friends)
    ab_ok = 0
    ba_ok = 0
    msg_ok = 0

    # Phase 1: A→B
    _log(f"Phase 1/3: A→B 关注 ({total} 人)...")
    for i, fid in enumerate(friends):
        ok, _ = add_user_relation(target_user_id, fid)
        if ok:
            ab_ok += 1
        if (i + 1) % 200 == 0:
            _log(f"  A→B [{i+1}/{total}] success={ab_ok}")
    _log(f"  A→B 完成: {ab_ok}/{total}")

    # Phase 2: B→A
    _log(f"Phase 2/3: B→A 回关 ({total} 人)...")
    for i, fid in enumerate(friends):
        ok, em = add_user_relation(fid, target_user_id)
        if ok:
            ba_ok += 1
        elif em and "频繁" in em:
            time.sleep(1.0)
            ok2, _ = add_user_relation(fid, target_user_id)
            if ok2:
                ba_ok += 1
        if (i + 1) % 200 == 0:
            _log(f"  B→A [{i+1}/{total}] success={ba_ok}")
    _log(f"  B→A 完成: {ba_ok}/{total}")

    # Phase 3: 发消息
    if send_message:
        _log(f"Phase 3/3: 发送随机消息 ({total} 人)...")
        for i, fid in enumerate(friends):
            ok, _ = _send_random_message(fid, target_user_id)
            if ok:
                msg_ok += 1
            if (i + 1) % 200 == 0:
                _log(f"  消息 [{i+1}/{total}] success={msg_ok}")
        _log(f"  消息完成: {msg_ok}/{total}")

    return {
        "targetUserId": target_user_id,
        "total": total,
        "ab_follow_success": ab_ok,
        "ba_follow_success": ba_ok,
        "message_sent": msg_ok if send_message else "skipped",
    }


# ── CLI ──────────────────────────────────────────────────────────────────────

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
    parser.add_argument(
        "--processed-log",
        default=str(REPO_ROOT / ".tmp" / "mutual_follow_processed.log"),
        help="已处理 userId 日志文件路径（自动排除+追加；默认 .tmp/mutual_follow_processed.log）",
    )
    parser.add_argument("--no-processed-log", action="store_true", help="禁用去重日志")
    parser.add_argument(
        "--send-message", action="store_true",
        help="互关后向目标用户发送一条随机消息（TEXT/IMG/VIDEO）",
    )
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
    parser.add_argument("--sleep-seconds", type=float, default=1.2, help="同一线程内每次 addUserRelation 间隔秒数（默认 1.2）")
    parser.add_argument("--retry-sleep-seconds", type=float, default=2.0, help="触发限流后的重试等待秒数（默认 2.0）")
    parser.add_argument("--workers", type=int, default=1, help="并行线程数（默认 1，推荐 3~5 加速大批量互关）")
    parser.add_argument(
        "--fast-mode", action="store_true",
        help="大批量快速模式：A→B并行 + B→A串行 + 消息并行（适合 count≥200）",
    )
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

    # 加载排除列表
    exclude = _load_exclude_file(args.exclude_file)
    exclude |= parse_exclude_user_ids(args.exclude_user_ids)

    # 加载去重日志
    processed_log_path = None if args.no_processed_log else args.processed_log
    if processed_log_path:
        processed = _load_processed_log(processed_log_path)
        exclude |= processed
        if processed:
            print(f"去重日志已排除 {len(processed)} 个已处理用户", file=sys.stderr)

    # 获取候选人
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
        "sendMessage": args.send_message,
        "fastMode": args.fast_mode or args.count >= 200,
        "dryRun": args.dry_run,
    }
    print(json.dumps(plan, ensure_ascii=False, indent=2))

    if len(friends) < args.count:
        print(
            f"仅找到 {len(friends)} 个可用 userId，少于目标 {args.count}",
            file=sys.stderr,
        )
        if len(friends) == 0:
            return 2

    if args.dry_run:
        print(json.dumps({"friendUserIds": friends}, ensure_ascii=False, indent=2))
        return 0

    use_fast_mode = args.fast_mode or args.count >= 200

    if use_fast_mode:
        print("使用快速模式（A→B并行 + B→A串行）", file=sys.stderr)
        result = _fast_batch_follow_and_message(
            target_user_id,
            friends,
            send_message=args.send_message,
            log=lambda msg: print(msg, file=sys.stderr),
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        _append_processed_log(processed_log_path, friends)
        return 0 if result["ba_follow_success"] == len(friends) else 1

    # 常规模式（小批量）
    workers = max(1, args.workers)
    if workers > 1:
        print(f"并行模式: {workers} 路同时互关", file=sys.stderr)

    batch = batch_mutual_follow(
        target_user_id,
        friends,
        sleep_seconds=args.sleep_seconds,
        retry_sleep_seconds=args.retry_sleep_seconds,
        workers=workers,
        log=lambda msg: print(msg, file=sys.stderr),
    )

    # 互关后发消息
    msg_results: list[dict[str, Any]] = []
    if args.send_message:
        print("互关完成，开始发送随机消息...", file=sys.stderr)
        success_friends = [r.friend_user_id for r in batch.results if r.ok]
        msg_sent = 0
        for fid in success_friends:
            ok, mtype = _send_random_message(fid, target_user_id)
            msg_results.append({"userId": fid, "ok": ok, "type": mtype})
            if ok:
                msg_sent += 1
        print(f"消息发送: {msg_sent}/{len(success_friends)}", file=sys.stderr)

    # 记录已处理
    processed_ids = [r.friend_user_id for r in batch.results]
    _append_processed_log(processed_log_path, processed_ids)

    summary = {
        "targetUserId": batch.target_user_id,
        "requested": batch.requested,
        "success": batch.success,
        "failed": batch.failed,
        "results": [asdict(item) for item in batch.results],
    }
    if msg_results:
        summary["messageResults"] = msg_results
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if batch.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
