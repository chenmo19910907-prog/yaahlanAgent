#!/usr/bin/env python3
"""Step 4 验收：钉钉 Stream 机器人 echo（不含 Cursor，支持图文链接解析）。"""

from __future__ import annotations

import argparse
import logging
import sys

import dingtalk_stream
from dingtalk_stream import AckMessage

from env_loader import load_env_local, require_env
from inbound_message import parse_inbound_message
from quoted_reply import quote_text_from_inbound, reply_quoted

logger = logging.getLogger("dingtalk-echo")


class EchoBotHandler(dingtalk_stream.ChatbotHandler):
    async def process(self, callback: dingtalk_stream.CallbackMessage):
        incoming = dingtalk_stream.ChatbotMessage.from_dict(callback.data)
        inbound = parse_inbound_message(incoming)
        logger.info(
            "收到消息: type=%s text=%r images=%s links=%s",
            incoming.message_type,
            inbound.text[:200] if inbound.text else "",
            len(inbound.image_download_codes),
            inbound.links,
        )
        if inbound.is_empty:
            reply_quoted(self, "收到空消息或非支持类型（仅 text / picture / richText）", incoming)
            return AckMessage.STATUS_OK, "OK"

        parts = [f"类型：{incoming.message_type}", f"摘要：{inbound.summary_label()}"]
        if inbound.text:
            parts.append(f"文字：{inbound.text[:500]}")
        if inbound.image_download_codes:
            parts.append(f"附图：{len(inbound.image_download_codes)} 张")
        if inbound.links:
            parts.append("链接：\n" + "\n".join(inbound.links))
        reply_quoted(self, "\n".join(parts), incoming, quote_text=quote_text_from_inbound(inbound))
        return AckMessage.STATUS_OK, "OK"


def main() -> int:
    load_env_local()
    parser = argparse.ArgumentParser(description="钉钉 Stream echo 机器人")
    parser.parse_args()

    try:
        client_id = require_env("DINGTALK_CLIENT_ID")
        client_secret = require_env("DINGTALK_CLIENT_SECRET")
    except RuntimeError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        print("Step 3：在钉钉开放平台创建应用并填入 .env.local", file=sys.stderr)
        return 1

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    credential = dingtalk_stream.Credential(client_id, client_secret)
    client = dingtalk_stream.DingTalkStreamClient(credential)
    client.register_callback_handler(
        dingtalk_stream.chatbot.ChatbotMessage.TOPIC,
        EchoBotHandler(),
    )
    logger.info("echo 机器人已启动（Stream，支持图文链接），在群里 @机器人 测试…")
    client.start_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
