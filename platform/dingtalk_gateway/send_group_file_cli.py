#!/usr/bin/env python3
"""通过钉钉 OpenAPI 向群/单聊发送本地 zip 附件（Agent 即时投递用）。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import requests
from dingtalk_stream import Credential, DingTalkStreamClient
from dingtalk_stream.utils import DINGTALK_OPENAPI_ENDPOINT

from dingtalk_group_file import _file_type, _response_succeeded, _upload_file
from env_loader import load_env_local, require_env


def _parse_user_key(user_key: str) -> tuple[str | None, str | None]:
    key = (user_key or "").strip()
    if not key:
        return None, None
    if key.startswith("dm:"):
        return None, key[3:].strip() or None
    if ":user:" in key:
        conv, _, staff = key.partition(":user:")
        return conv.strip() or None, staff.strip() or None
    return key, None


def _build_client() -> DingTalkStreamClient:
    load_env_local()
    credential = Credential(
        require_env("DINGTALK_CLIENT_ID"),
        require_env("DINGTALK_CLIENT_SECRET"),
    )
    return DingTalkStreamClient(credential)


class _ClientHandler:
    def __init__(self, client: DingTalkStreamClient) -> None:
        self.dingtalk_client = client


def send_file_to_conversation(
    *,
    file_path: Path,
    user_key: str,
    display_name: str | None = None,
) -> None:
    path = file_path.expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(path)

    open_conv, staff_id = _parse_user_key(user_key)
    if not open_conv and not staff_id:
        raise ValueError(f"无法从 user_key 解析会话: {user_key}")

    client = _build_client()
    handler = _ClientHandler(client)
    filename = display_name or path.name
    content = path.read_bytes()
    media_id = _upload_file(handler, content, filename)

    access_token = client.get_access_token()
    if not access_token:
        raise RuntimeError("获取钉钉 access_token 失败")

    robot_code = require_env("DINGTALK_CLIENT_ID")
    msg_param = json.dumps(
        {"mediaId": media_id, "fileName": filename, "fileType": _file_type(filename)},
        ensure_ascii=False,
    )
    body: dict[str, str] = {
        "msgKey": "sampleFile",
        "msgParam": msg_param,
        "robotCode": robot_code,
    }
    if open_conv:
        body["openConversationId"] = open_conv
    elif staff_id:
        body["singleChatReceiver"] = json.dumps({"userId": staff_id}, ensure_ascii=False)

    url = f"{DINGTALK_OPENAPI_ENDPOINT}/v1.0/robot/groupMessages/send"
    headers = {
        "Content-Type": "application/json",
        "x-acs-dingtalk-access-token": access_token,
    }
    response = requests.post(url, headers=headers, json=body, timeout=60)
    ok, detail = _response_succeeded(response)
    if not ok:
        raise RuntimeError(f"OpenAPI 发文件失败：{detail}")


def main() -> int:
    parser = argparse.ArgumentParser(description="向钉钉群/单聊发送 zip 附件")
    parser.add_argument("--user-key", required=True, help="网关 user_key（batch_key）")
    parser.add_argument("--file", required=True, help="本地附件路径（建议 .zip）")
    parser.add_argument("--display-name", default="", help="发送显示文件名")
    args = parser.parse_args()

    try:
        send_file_to_conversation(
            file_path=Path(args.file),
            user_key=args.user_key,
            display_name=(args.display_name or "").strip() or None,
        )
    except (OSError, RuntimeError, ValueError, FileNotFoundError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1

    print(f"[OK] 已发送附件: {Path(args.file).name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
