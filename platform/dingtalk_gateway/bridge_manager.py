"""Cursor SDK Bridge 生命周期：固定仓库 workspace，断线可恢复。"""

from __future__ import annotations

import logging
import os
import threading

from cursor_sdk._client import _default_client, close_default_client

logger = logging.getLogger("dingtalk-gateway")

_lock = threading.Lock()
_workspace: str | None = None


def init_sdk_bridge(workspace: str) -> None:
    """网关启动时初始化 Bridge（使用仓库根目录，而非 dingtalk_gateway 子目录）。"""
    global _workspace
    with _lock:
        _workspace = workspace
        os.chdir(workspace)
        close_default_client()
        _default_client()
        logger.info("Cursor SDK Bridge 已初始化，workspace=%s", workspace)


def reset_sdk_bridge() -> None:
    """Bridge 断线后重建（中断任务后或 Connection refused 时）。"""
    with _lock:
        workspace = _workspace or os.getcwd()
        logger.warning("重建 Cursor SDK Bridge，workspace=%s", workspace)
        close_default_client()
        os.chdir(workspace)
        _default_client()


def is_bridge_connection_error(exc: BaseException) -> bool:
    message = str(exc).lower()
    needles = (
        "connection refused",
        "server disconnected",
        "connecterror",
        "bridge request failed",
    )
    return any(needle in message for needle in needles)
