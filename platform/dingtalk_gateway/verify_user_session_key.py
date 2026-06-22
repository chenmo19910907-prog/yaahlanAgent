#!/usr/bin/env python3
"""离线验证：群聊按用户隔离 session key。"""

from __future__ import annotations

import sys

from conversation_store import ConversationStore


def main() -> int:
    cases = [
        (
            {
                "conversation_id": "cidgroup",
                "sender_id": "u1",
                "sender_staff_id": "WB001",
                "conversation_type": "2",
            },
            "cidgroup:user:WB001",
        ),
        (
            {
                "conversation_id": "cidgroup",
                "sender_id": "u2",
                "sender_staff_id": "WB002",
                "conversation_type": "2",
            },
            "cidgroup:user:WB002",
        ),
        (
            {
                "conversation_id": None,
                "sender_id": "u3",
                "sender_staff_id": None,
                "conversation_type": "1",
            },
            "dm:u3",
        ),
    ]
    for kwargs, expected in cases:
        got = ConversationStore.conversation_key(
            kwargs["conversation_id"],
            kwargs["sender_id"],
            sender_staff_id=kwargs["sender_staff_id"],
            conversation_type=kwargs["conversation_type"],
        )
        if got != expected:
            print(f"[FAIL] {kwargs} => {got!r}, want {expected!r}", file=sys.stderr)
            return 1
        print(f"[OK] {expected}")
    print("[PASS] user session key")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
