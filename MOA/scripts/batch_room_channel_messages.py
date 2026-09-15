#!/usr/bin/env python3
"""批量向房间公屏随机发送文字/表情/图片，内置 Web Agent 批量进度上报。"""

from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from moa_script_paths import (
    batch_progress_script,
    ensure_moa_gift_paths,
    moa_execute_path,
    moa_template,
    repo_root,
)

ensure_moa_gift_paths()

from moa.anniversary_egg import resolve_own_room_id  # noqa: E402

REPO = repo_root()

MSG_TYPES = ("text", "emote", "image")

DEFAULT_IMAGE_URL = (
    "https://yaahlan.momocdn.com/roomimg/6F/13/"
    "6F13812E-D33F-22EC-70B5-0D07C8B0933520260915_L.webp"
)
IMAGE_SAMPLES = [
    DEFAULT_IMAGE_URL,
    "https://img.momocdn.com/album/76/D1/76D178EC-E3C8-C2FA-6618-45AA85FD3FFE20210901.webp",
    "https://oversea.hellogroupcdn.com/s1/u/baihafdhga/voga-mts-room/task-invite-seat.png",
    "https://img.momocdn.com/album/D4/E3/D4E3A5F2-5BA8-C2B9-8876-FC81D1E82F8520230101.webp",
]
EMOTE_NAMES = ("chaoxiao",)

TEXT_SAMPLES_ZH = [
    "大家好，欢迎来房间！",
    "今天天气不错呀～",
    "哈哈哈笑死我了",
    "有人在吗？",
    "测试公屏消息",
    "晚上好，一起聊天吧",
    "这个房间氛围真不错",
    "送个小心心 ❤️",
]
TEXT_SAMPLES_EN = [
    "Hello everyone!",
    "Good morning, nice to meet you!",
    "How's your day going?",
    "Let's chat together!",
    "This room is awesome!",
    "Anyone here?",
    "Test channel message",
    "Have a great evening!",
]
TEXT_SAMPLES_AR = [
    "مرحبا بالجميع!",
    "صباح الخير",
    "كيف حالكم اليوم؟",
    "هذه الغرفة رائعة",
    "هل من أحد هنا؟",
    "مساء الخير",
    "رسالة اختبار",
    "نتمنى لكم يوماً سعيداً",
]


@dataclass
class SendStats:
    total: int = 0
    success: int = 0
    failed: int = 0
    by_type: dict[str, int] = field(default_factory=lambda: {k: 0 for k in MSG_TYPES})
    errors: list[str] = field(default_factory=list)


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
        "房间公屏消息",
    ]
    cmd.extend(["--user-key", user_key])
    if detail:
        cmd.extend(["--detail", detail])
    if result_text:
        cmd.extend(["--result-text", result_text])
    subprocess.run(cmd, cwd=str(REPO), check=False)


def _run_moa(cmd: list[str], *, timeout: int = 60) -> tuple[bool, str]:
    proc = subprocess.run(
        cmd,
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    text = (proc.stdout or "").strip() or (proc.stderr or "").strip()
    if proc.returncode != 0:
        return False, text[-400:]
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(text[start : end + 1])
            ec = data.get("ec")
            if ec is not None and str(ec) not in ("0", "200"):
                return False, text[-400:]
            if data.get("ok") is False:
                return False, text[-400:]
        except json.JSONDecodeError:
            pass
    return True, text[-200:]


def random_text_content(*, seq: int, random_lang: bool) -> str:
    if not random_lang:
        return f"#{seq}"
    lang = random.choice(("zh", "en", "ar"))
    pool = {
        "zh": TEXT_SAMPLES_ZH,
        "en": TEXT_SAMPLES_EN,
        "ar": TEXT_SAMPLES_AR,
    }[lang]
    return f"{random.choice(pool)} #{seq}"


def send_text(user_id: str, room_id: str, text: str) -> tuple[bool, str]:
    cmd = [
        "python3",
        str(moa_execute_path()),
        "--payload-file",
        str(moa_template("房间-发送公屏消息.json")),
        "--room-chat-user-id",
        user_id,
        "--room-chat-room-id",
        room_id,
        "--room-chat-text",
        text,
    ]
    return _run_moa(cmd)


def send_emote(user_id: str, room_id: str, emote_name: str) -> tuple[bool, str]:
    cmd = [
        "python3",
        str(moa_execute_path()),
        "--payload-file",
        str(moa_template("房间-发送公屏表情.json")),
        "--room-chat-user-id",
        user_id,
        "--room-chat-room-id",
        room_id,
        "--room-chat-emote-name",
        emote_name,
    ]
    return _run_moa(cmd)


def send_image(user_id: str, room_id: str, image_url: str) -> tuple[bool, str]:
    cmd = [
        "python3",
        str(moa_execute_path()),
        "--payload-file",
        str(moa_template("房间-发送公屏图片.json")),
        "--room-chat-user-id",
        user_id,
        "--room-chat-room-id",
        room_id,
        "--room-chat-image-url",
        image_url,
    ]
    return _run_moa(cmd)


def pick_msg_type() -> str:
    return random.choice(MSG_TYPES)


def send_one(
    user_id: str,
    room_id: str,
    *,
    seq: int,
    image_url: str | None = None,
    emote_name: str | None = None,
    text_only: bool = False,
    random_lang: bool = False,
) -> tuple[str, bool, str]:
    msg_type = "text" if text_only else pick_msg_type()
    if msg_type == "text":
        text = random_text_content(seq=seq, random_lang=random_lang)
        ok, detail = send_text(user_id, room_id, text)
        label = f"#{seq} 文字"
    elif msg_type == "emote":
        name = emote_name or random.choice(EMOTE_NAMES)
        ok, detail = send_emote(user_id, room_id, name)
        label = f"#{seq} 表情({name})"
    else:
        url = image_url or random.choice(IMAGE_SAMPLES)
        ok, detail = send_image(user_id, room_id, url)
        label = f"#{seq} 图片"
    return msg_type, ok, label if ok else detail


def build_result_markdown(
    *,
    user_ids: list[str],
    room_id: str,
    stats: SendStats,
    random_lang: bool = False,
    per_user: dict[str, int] | None = None,
) -> str:
    user_label = ", ".join(user_ids) if len(user_ids) > 1 else user_ids[0]
    lines = [
        f"**已完成。** 用户 `{user_label}` 在房间 `{room_id}` 公屏共发送 **{stats.success}/{stats.total}** 条。",
        "",
        "| 项 | 值 |",
        "|---|---|",
        f"| userId | {user_label} |",
        f"| roomId | {room_id} |",
        f"| 成功 | **{stats.success} / {stats.total}** |",
        f"| 失败 | {stats.failed} |",
        f"| 文字 | {stats.by_type.get('text', 0)} |",
        f"| 表情 | {stats.by_type.get('emote', 0)} |",
        f"| 图片 | {stats.by_type.get('image', 0)} |",
    ]
    if per_user:
        lines.append(f"| 各账号 | {', '.join(f'{uid}:{n}' for uid, n in per_user.items())} |")
    if random_lang:
        lines.extend(["", "文字消息为中/英/阿拉伯语随机；类型在 text/emote/image 间随机。"])
    else:
        lines.extend(["", "文字消息内容为序号编号；类型在 text/emote/image 间随机。"])
    if stats.errors:
        lines.extend(["", "**失败样例（最多 5 条）：**", ""])
        for err in stats.errors[:5]:
            lines.append(f"- {err}")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="批量随机发送房间公屏文字/表情/图片，内置 batch_progress 上报",
    )
    parser.add_argument("--user-id", default="", help="发送方 userId（单账号）")
    parser.add_argument(
        "--user-ids",
        default="",
        help="多账号 userId（逗号分隔，与 --user-id 二选一）",
    )
    parser.add_argument(
        "--room-id",
        default="",
        help="房间 roomId（不传则 Admin 查 userId 自己的房间）",
    )
    parser.add_argument("--count", type=int, default=1000, help="发送条数（默认 1000）")
    parser.add_argument("--start-seq", type=int, default=1, help="文字编号起始值（默认 1，续发时用 1001 等）")
    parser.add_argument("--sleep", type=float, default=0.05, help="每条间隔秒数（默认 0.05）")
    parser.add_argument("--image-url", default=DEFAULT_IMAGE_URL, help="公屏图片 URL")
    parser.add_argument("--emote-name", default="chaoxiao", help="公屏表情 preset（默认 chaoxiao）")
    parser.add_argument("--user-key", default="", help="Web Agent batch_key（默认 WEB_AGENT_BATCH_KEY）")
    parser.add_argument(
        "--progress-every",
        type=int,
        default=1,
        help="每完成 N 条上报一次进度（默认 1）",
    )
    parser.add_argument("--dry-run", action="store_true", help="只输出计划，不发送")
    parser.add_argument(
        "--text-only",
        action="store_true",
        help="仅发送编号文字公屏（不随机表情/图片）",
    )
    parser.add_argument(
        "--random-lang",
        action="store_true",
        help="文字消息随机中/英/阿拉伯语（仍带 #序号）",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="并行线程数（多账号时推荐与账号数相同，默认 1）",
    )
    return parser


def _parse_user_ids(args: argparse.Namespace) -> list[str]:
    raw = str(args.user_ids or "").strip()
    if raw:
        return [u.strip() for u in raw.split(",") if u.strip()]
    single = str(args.user_id or "").strip()
    if single:
        return [single]
    return []


def main() -> int:
    from moa.parallel_runner import BatchTask, TaskResult, run_parallel_batch

    args = build_parser().parse_args()
    user_key = resolve_user_key(args.user_key or None)
    user_ids = _parse_user_ids(args)
    if not user_ids:
        print("须指定 --user-id 或 --user-ids", file=sys.stderr)
        return 2

    room_id = str(args.room_id or "").strip()
    if not room_id:
        room_id = resolve_own_room_id(user_ids[0])
        print(f"未传 roomId，使用自己的房间 roomId={room_id}", file=sys.stderr)

    total = max(1, int(args.count))
    start_seq = max(1, int(args.start_seq))
    progress_every = max(1, int(args.progress_every))
    workers = max(1, min(int(args.workers), total))

    per_user_count: dict[str, int] = {uid: 0 for uid in user_ids}
    base, rem = divmod(total, len(user_ids))
    quotas = {uid: base + (1 if i < rem else 0) for i, uid in enumerate(user_ids)}

    plan = {
        "userIds": user_ids,
        "roomId": room_id,
        "count": total,
        "quotas": quotas,
        "startSeq": start_seq,
        "sleep": args.sleep,
        "workers": workers,
        "msgTypes": ["text"] if args.text_only else list(MSG_TYPES),
        "randomLang": args.random_lang,
        "textOnly": args.text_only,
        "dryRun": args.dry_run,
    }
    print(json.dumps(plan, ensure_ascii=False, indent=2))

    if args.dry_run:
        return 0

    tasks: list[BatchTask] = []
    seq = start_seq
    for uid in user_ids:
        for _ in range(quotas[uid]):
            tasks.append(BatchTask(id=f"{uid}#{seq}", payload={"user_id": uid, "seq": seq}))
            seq += 1

    stats = SendStats(total=total)
    report_progress(user_key, current=0, total=total)

    def _worker(task: BatchTask) -> TaskResult:
        uid = task.payload["user_id"]
        task_seq = int(task.payload["seq"])
        msg_type, ok, detail = send_one(
            uid,
            room_id,
            seq=task_seq,
            text_only=args.text_only,
            random_lang=args.random_lang,
        )
        return TaskResult(
            task_id=task.id,
            ok=ok,
            detail={"msg_type": msg_type, "label": detail},
            error=None if ok else str(detail),
        )

    def _on_progress(current: int, _total: int, result: TaskResult) -> None:
        detail = result.detail if isinstance(result.detail, dict) else {}
        msg_type = detail.get("msg_type", "?")
        stats.by_type[msg_type] = stats.by_type.get(msg_type, 0) + 1
        uid = result.task_id.split("#", 1)[0]
        per_user_count[uid] = per_user_count.get(uid, 0) + 1
        if result.ok:
            stats.success += 1
        else:
            stats.failed += 1
            if len(stats.errors) < 20:
                stats.errors.append(f"{result.task_id} {msg_type}: {result.error}")
        if current % progress_every == 0 or current == total:
            label = detail.get("label", result.task_id)
            report_progress(
                user_key,
                current=current,
                total=total,
                detail=label if result.ok else f"{result.task_id} 失败",
            )

    summary = run_parallel_batch(
        tasks=tasks,
        worker_fn=_worker,
        workers=workers,
        sleep_between=args.sleep,
        progress_fn=_on_progress,
    )

    result_md = build_result_markdown(
        user_ids=user_ids,
        room_id=room_id,
        stats=stats,
        random_lang=args.random_lang,
        per_user=per_user_count,
    )
    report_progress(
        user_key,
        current=total,
        total=total,
        result_text=result_md,
    )
    print(result_md)
    out = {
        "userIds": user_ids,
        "roomId": room_id,
        "total": stats.total,
        "success": stats.success,
        "failed": stats.failed,
        "byType": stats.by_type,
        "perUser": per_user_count,
        "elapsedSeconds": summary.elapsed_seconds,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if stats.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
