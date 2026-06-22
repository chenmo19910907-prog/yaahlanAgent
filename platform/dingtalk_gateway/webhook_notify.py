"""钉钉自定义 Webhook 机器人：单向推送消息到群（不能收 @）。"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import urllib.parse
import urllib.request

from env_loader import load_env_local, require_env


def send_webhook_text(text: str, *, title: str = "Yaahlan Agent") -> None:
    """向群推送 markdown 消息。"""
    load_env_local()
    url = require_env("DINGTALK_WEBHOOK_URL")
    secret = require_env("DINGTALK_WEBHOOK_SECRET")

    timestamp = str(round(time.time() * 1000))
    string_to_sign = f"{timestamp}\n{secret}"
    sign = urllib.parse.quote_plus(
        base64.b64encode(
            hmac.new(
                secret.encode("utf-8"),
                string_to_sign.encode("utf-8"),
                digestmod=hashlib.sha256,
            ).digest()
        ).decode("utf-8")
    )
    sep = "&" if "?" in url else "?"
    post_url = f"{url}{sep}timestamp={timestamp}&sign={sign}"

    body = {
        "msgtype": "markdown",
        "markdown": {
            "title": title,
            "text": text,
        },
    }
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        post_url,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    if result.get("errcode") != 0:
        raise RuntimeError(f"Webhook 发送失败: {result}")
