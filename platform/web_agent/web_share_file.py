#!/usr/bin/env python3
"""Agent 向 Web 会话回传可下载文件。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

WEB_AGENT_DIR = Path(__file__).resolve().parent
if str(WEB_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_AGENT_DIR))

from web_file_store import FileUploadError, parse_web_user_key, register_output_file  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="向 Web Agent 会话回传可下载文件")
    parser.add_argument("--user-key", required=True, help="Web 会话 batch_key，形如 web:<session_id>")
    parser.add_argument("--path", required=True, help="本地文件路径")
    parser.add_argument("--name", default="", help="下载时展示的文件名")
    args = parser.parse_args()

    session_id = parse_web_user_key(args.user_key)
    if not session_id:
        print("错误：--user-key 须为 web:<session_id>", file=sys.stderr)
        return 2

    try:
        attachment = register_output_file(
            session_id,
            args.path,
            display_name=args.name or None,
        )
    except FileUploadError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1

    print(json.dumps(attachment.to_message_dict(), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
