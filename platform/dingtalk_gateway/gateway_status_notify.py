"""钉钉群同步网关 Agent 启停状态（主动推送，不依赖 sessionWebhook）。"""

from __future__ import annotations

import sys
import atexit
import json
import logging
import os
import signal
import socket
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

import requests
from dingtalk_stream.utils import DINGTALK_OPENAPI_ENDPOINT

from env_loader import GATEWAY_DIR, load_env_local, require_env

if TYPE_CHECKING:
    import dingtalk_stream
    from dingtalk_stream import ChatbotMessage

logger = logging.getLogger("dingtalk-gateway")

NOTIFY_DATA = GATEWAY_DIR / "data" / "notify_group.json"
SILENT_RESTART_FLAG = GATEWAY_DIR / "data" / "silent_restart.flag"
EXECUTOR_CONFIG = GATEWAY_DIR / "config" / "executor.local.json"

_client: Any | None = None
_stop_notified = False
_lock = threading.Lock()


def _executor_hostname() -> str:
    if EXECUTOR_CONFIG.is_file():
        try:
            data = json.loads(EXECUTOR_CONFIG.read_text(encoding="utf-8"))
            hostname = str(data.get("hostname") or "").strip()
            if hostname:
                return hostname
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("读取 executor.local.json 失败: %s", exc)
    return socket.gethostname()


def _load_notify_data() -> dict[str, str]:
    if not NOTIFY_DATA.is_file():
        return {}
    try:
        raw = json.loads(NOTIFY_DATA.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("读取 notify_group.json 失败: %s", exc)
        return {}
    if not isinstance(raw, dict):
        return {}
    return {str(k): str(v) for k, v in raw.items() if v}


def _save_notify_data(payload: dict[str, str]) -> None:
    NOTIFY_DATA.parent.mkdir(parents=True, exist_ok=True)
    NOTIFY_DATA.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _skip_lifecycle_notify() -> bool:
    return SILENT_RESTART_FLAG.is_file()


def _clear_silent_restart_flag() -> None:
    SILENT_RESTART_FLAG.unlink(missing_ok=True)


def resolve_notify_conversation_id() -> str | None:
    load_env_local()
    env_id = (os.environ.get("DINGTALK_NOTIFY_CONVERSATION_ID") or "").strip()
    if env_id:
        return env_id
    data = _load_notify_data()
    conv_id = (data.get("openConversationId") or "").strip()
    return conv_id or None


def touch_notify_group(incoming: ChatbotMessage) -> None:
    """收到群消息时记住 openConversationId，供启停通知使用。"""
    if incoming.conversation_type != "2":
        return
    conv_id = (incoming.conversation_id or "").strip()
    if not conv_id:
        return
    payload = {
        "openConversationId": conv_id,
        "conversationTitle": (incoming.conversation_title or "").strip(),
        "updatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
    }
    _save_notify_data(payload)
    logger.debug("已更新通知群 openConversationId=%s", conv_id[:16])


def _get_access_token(client: Any | None) -> str | None:
    if client is not None:
        token = client.get_access_token()
        if token:
            return token
    try:
        from dingtalk_stream import Credential, DingTalkStreamClient

        credential = Credential(
            require_env("DINGTALK_CLIENT_ID"),
            require_env("DINGTALK_CLIENT_SECRET"),
        )
        temp_client = DingTalkStreamClient(credential)
        return temp_client.get_access_token()
    except RuntimeError as exc:
        logger.warning("获取 access_token 失败: %s", exc)
        return None


def send_proactive_group_text(text: str, *, client: Any | None = None) -> bool:
    """向配置的群主动发送文本（OpenAPI groupMessages/send）。"""
    conv_id = resolve_notify_conversation_id()
    if not conv_id:
        logger.info("未配置通知群，跳过主动推送")
        return False

    access_token = _get_access_token(client or _client)
    if not access_token:
        logger.warning("主动推送失败：无法获取 access_token")
        return False

    load_env_local()
    robot_code = require_env("DINGTALK_CLIENT_ID")
    body = {
        "msgKey": "sampleText",
        "msgParam": json.dumps({"content": text}, ensure_ascii=False),
        "openConversationId": conv_id,
        "robotCode": robot_code,
    }
    url = f"{DINGTALK_OPENAPI_ENDPOINT}/v1.0/robot/groupMessages/send"
    headers = {
        "Content-Type": "application/json",
        "x-acs-dingtalk-access-token": access_token,
    }
    try:
        response = requests.post(url, headers=headers, json=body, timeout=15)
        response.raise_for_status()
        data = response.json()
        if isinstance(data, dict):
            errcode = data.get("errcode")
            if errcode is not None and int(errcode) != 0:
                logger.warning("主动推送返回 errcode=%s errmsg=%s", errcode, data.get("errmsg"))
                return False
        logger.info("已主动推送群通知 openConversationId=%s…", conv_id[:16])
        return True
    except requests.RequestException as exc:
        logger.warning("主动推送群通知失败: %s", exc)
        return False


def _format_changed_files_summary(changed_files: object) -> str:
    if not isinstance(changed_files, list) or not changed_files:
        return "（未记录具体文件）"
    names = [Path(str(item)).name for item in changed_files if str(item).strip()]
    if not names:
        return "（未记录具体文件）"
    if len(names) <= 5:
        return "、".join(names)
    head = "、".join(names[:5])
    return f"{head} 等 {len(names)} 个文件"


def notify_gateway_started(*, client: Any | None = None) -> None:
    if _skip_lifecycle_notify():
        _clear_silent_restart_flag()
        logger.info("静默重启，跳过启动通知")
        return

    from gateway_restart import read_and_clear_restart_context

    host = _executor_hostname()
    ctx = read_and_clear_restart_context()
    if ctx and ctx.get("trigger") == "code_update":
        operator = str(ctx.get("operator") or "未知").strip() or "未知"
        summary = _format_changed_files_summary(ctx.get("changedFiles"))
        text = (
            f"✅ Yaahlan 智能工具网关已启动\n"
            f"原因：代码更新后重启（{operator}）\n"
            f"变更：{summary}\n"
            f"执行机：{host}\n"
            f"@机器人 发消息即可使用"
        )
    else:
        text = (
            f"✅ Yaahlan 智能工具网关已启动\n"
            f"执行机：{host}\n"
            f"@机器人 发消息即可使用"
        )
    send_proactive_group_text(text, client=client)


def notify_gateway_stopping(*, reason: str = "服务停止", client: Any | None = None) -> None:
    if _skip_lifecycle_notify():
        logger.info("静默重启，跳过关闭通知")
        return

    global _stop_notified
    with _lock:
        if _stop_notified:
            return
        _stop_notified = True

    host = _executor_hostname()
    text = (
        f"⏹ Yaahlan 智能工具网关已关闭\n"
        f"执行机：{host}\n"
        f"原因：{reason}\n"
        f"暂停期间 @ 不会响应"
    )
    send_proactive_group_text(text, client=client)


def _shutdown_handler(signum: int, _frame: Any) -> None:
    reason = "收到停止信号" if signum else "进程退出"
    notify_gateway_stopping(reason=reason, client=_client)
    sys.exit(0)


def _atexit_notify() -> None:
    notify_gateway_stopping(reason="进程退出", client=_client)


def register_lifecycle_hooks(client: dingtalk_stream.DingTalkStreamClient) -> None:
    """注册启停通知：启动后发群消息，停止前同步关闭状态。"""
    global _client
    _client = client

    def delayed_start() -> None:
        time.sleep(2)
        try:
            notify_gateway_started(client=client)
        except Exception as exc:  # noqa: BLE001
            logger.warning("启动通知失败: %s", exc)

    threading.Thread(target=delayed_start, daemon=True, name="gateway-start-notify").start()

    atexit.register(_atexit_notify)
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, _shutdown_handler)
        except (ValueError, OSError) as exc:
            logger.debug("无法注册信号 %s: %s", sig, exc)
