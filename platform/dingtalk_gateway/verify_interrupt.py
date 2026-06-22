#!/usr/bin/env python3
"""离线验证中断指令识别。"""

from __future__ import annotations

import sys

from interrupt import is_interrupt_command


def main() -> int:
    cases = [
        ("中断操作", True),
        ("@机器人 中断操作", True),
        ("取消", True),
        ("stop", True),
        ("100465989升级 VIP3", False),
    ]
    for text, expected in cases:
        got = is_interrupt_command(text)
        if got != expected:
            print(f"[FAIL] {text!r} => {got}, want {expected}", file=sys.stderr)
            return 1
        print(f"[OK] {text!r}")
    print("[PASS] interrupt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
