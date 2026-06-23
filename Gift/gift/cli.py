"""Stage 送礼 CLI。"""

from __future__ import annotations

import sys

from .env import load_local_env
from .send_stage import StageGiftError, build_parser, emit_error, run


def main(argv: list[str] | None = None) -> int:
    load_local_env()
    parser = build_parser()
    ns = parser.parse_args(argv)
    if ns.send_room_all:
        if ns.scene != "chatroom":
            emit_error("args", "全房间送礼仅支持 chatroom 场景")
            return 1
        if not ns.scene_id:
            emit_error("args", "全房间送礼需要 --scene-id (roomId)")
            return 1
    elif not ns.receivers:
        emit_error("args", "非全房间送礼必须提供 --receivers")
        return 1
    try:
        run(ns)
    except StageGiftError as exc:
        emit_error(exc.step, exc.message)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
