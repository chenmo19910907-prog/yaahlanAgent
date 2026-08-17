#!/usr/bin/env python3
"""从指定好友列表中随机选取用户，向目标 userId 发送随机类型私聊消息。"""

from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GIFT_DIR = REPO_ROOT / "Gift"
sys.path.insert(0, str(GIFT_DIR))

from gift.send_stage import call_moa

IM_SERVICE = "/service/voga-base-service-im-stage"
IM_METHOD = "sendP2PMessageWithNoGreet"

TEXT_SAMPLES = [
    "Hey! How's your day going?",
    "What are you up to today?",
    "Just wanted to say hi! 👋",
    "Long time no chat! Miss you!",
    "Have you seen anything fun lately?",
    "Let's catch up soon!",
    "Good morning! Hope you have a great day!",
    "Just thinking about you, sending love ❤️",
    "Wanna hang out in a room later?",
    "Check out my new profile pic!",
    "Did you get the gift I sent?",
    "Are you free tonight?",
    "I found something interesting, let me share!",
    "Happy to be friends with you!",
    "What do you think about the new update?",
]

IMG_SAMPLES = [
    "https://img.momocdn.com/album/76/D1/76D178EC-E3C8-C2FA-6618-45AA85FD3FFE20210901.webp",
    "https://oversea.hellogroupcdn.com/s1/u/baihafdhga/voga-mts-room/task-invite-seat.png",
    "https://img.momocdn.com/album/D4/E3/D4E3A5F2-5BA8-C2B9-8876-FC81D1E82F8520230101.webp",
    "https://img.momocdn.com/album/AB/12/AB12CD34-EF56-7890-1234-567890ABCDEF20240101.webp",
    "https://img.momocdn.com/album/11/22/11223344-5566-7788-99AA-BBCCDDEEFF0020240601.webp",
]

VIDEO_SAMPLES = [
    "https://img.momocdn.com/album/76/D1/76D178EC-E3C8-C2FA-6618-45AA85FD3FFE20210901.mp4",
    "https://img.momocdn.com/album/D4/E3/D4E3A5F2-5BA8-C2B9-8876-FC81D1E82F8520230101.mp4",
    "https://img.momocdn.com/album/AB/12/AB12CD34-EF56-7890-1234-567890ABCDEF20240101.mp4",
]

MSG_TYPES = ["TEXT", "IMG", "VIDEO"]


def build_message_body(from_uid: str, to_uid: str, msg_type: str) -> dict:
    if msg_type == "TEXT":
        text = random.choice(TEXT_SAMPLES)
    elif msg_type == "IMG":
        text = random.choice(IMG_SAMPLES)
    else:
        text = random.choice(VIDEO_SAMPLES)

    return {
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


def send_message(from_uid: str, to_uid: str, msg_type: str) -> tuple[bool, str]:
    body = build_message_body(from_uid, to_uid, msg_type)
    try:
        result = call_moa(IM_SERVICE, IM_METHOD, [body])
        if isinstance(result, dict) and result.get("success"):
            return True, result.get("messageId", "")
        return False, str(result)
    except Exception as e:
        return False, str(e)


def main() -> int:
    import argparse

    MOA_DIR = REPO_ROOT / "MOA"
    if str(MOA_DIR) not in sys.path:
        sys.path.insert(0, str(MOA_DIR))

    from moa.parallel_runner import BatchTask, TaskResult, run_parallel_batch, default_progress_printer

    parser = argparse.ArgumentParser(description="批量从好友发随机类型私聊消息到目标用户")
    parser.add_argument("--target-uid", required=True, help="接收消息的目标 userId")
    parser.add_argument("--friend-ids", help="好友 userId（逗号分隔）")
    parser.add_argument("--friend-ids-file", help="好友 userId 文件（逗号分隔）")
    parser.add_argument("--count", type=int, default=100, help="选取好友数量（默认 100）")
    parser.add_argument("--messages-per-friend", type=int, default=2, help="每人发送消息数（默认 2）")
    parser.add_argument("--sleep", type=float, default=0.3, help="同一线程内每条消息间隔秒数（默认 0.3）")
    parser.add_argument("--workers", type=int, default=1, help="并行线程数（默认 1，推荐 3~5）")
    parser.add_argument("--dry-run", action="store_true", help="只输出计划，不发送")
    args = parser.parse_args()

    friends: list[str] = []
    if args.friend_ids:
        friends = [uid.strip() for uid in args.friend_ids.split(",") if uid.strip()]
    elif args.friend_ids_file:
        text = Path(args.friend_ids_file).read_text(encoding="utf-8")
        friends = [uid.strip() for uid in text.split(",") if uid.strip()]

    if not friends:
        print("未提供好友列表", file=sys.stderr)
        return 2

    if len(friends) > args.count:
        friends = random.sample(friends, args.count)

    total_messages = len(friends) * args.messages_per_friend
    workers = max(1, min(args.workers, total_messages))
    print(
        f"计划: {len(friends)} 个好友 × {args.messages_per_friend} 条消息 = {total_messages} 条 | {workers} 路并行",
        file=sys.stderr,
    )

    if args.dry_run:
        print(json.dumps({"friends": friends, "total": total_messages, "workers": workers}, ensure_ascii=False, indent=2))
        return 0

    target_uid = args.target_uid
    tasks: list[BatchTask] = []
    for friend_uid in friends:
        for _ in range(args.messages_per_friend):
            msg_type = random.choice(MSG_TYPES)
            tasks.append(BatchTask(
                id=f"{friend_uid}->{target_uid}({msg_type})",
                payload={"from_uid": friend_uid, "to_uid": target_uid, "msg_type": msg_type},
            ))

    def _worker(task: BatchTask) -> TaskResult:
        p = task.payload
        ok, detail = send_message(p["from_uid"], p["to_uid"], p["msg_type"])
        return TaskResult(task_id=task.id, ok=ok, detail=detail, error=None if ok else detail)

    summary = run_parallel_batch(
        tasks=tasks,
        worker_fn=_worker,
        workers=workers,
        sleep_between=args.sleep,
        progress_fn=default_progress_printer,
    )

    result = {
        "targetUid": target_uid,
        "friendCount": len(friends),
        "messagesPerFriend": args.messages_per_friend,
        "totalMessages": total_messages,
        "workers": workers,
        "success": summary.success,
        "failed": summary.failed,
        "elapsedSeconds": summary.elapsed_seconds,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if summary.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
