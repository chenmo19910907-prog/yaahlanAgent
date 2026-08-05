"""Cursor SDK Bridge 生命周期：固定仓库 workspace，断线可恢复。"""

from __future__ import annotations

import logging
import os
import secrets
import threading

from cursor_sdk import _store_callback, _tool_callback
from cursor_sdk._client import _default_client, close_default_client

from user_agent_pool import reset_user_agent_pool

logger = logging.getLogger("dingtalk-gateway")

AGENT_RUN_MAX_RETRIES = 3

_lock = threading.Lock()
_workspace: str | None = None
_auth_token_patch_applied = False


def cli_safe_callback_auth_token() -> str:
    """生成不会以 '-' 开头的 callback token。

    cursor-sdk-bridge 的 CLI 解析器会把以 '-' 开头的值误判为下一参数，
    导致 ``Missing value for --tool-callback-auth-token``（约 1/64 概率）。
    """
    for _ in range(64):
        token = secrets.token_urlsafe(32)
        if token and not token.startswith("-"):
            return token
    raise RuntimeError("无法生成 CLI 安全的 callback auth token")


def _ensure_cursor_sdk_auth_token_patch() -> None:
    global _auth_token_patch_applied
    if _auth_token_patch_applied:
        return
    _tool_callback._new_auth_token = cli_safe_callback_auth_token
    _store_callback._new_auth_token = cli_safe_callback_auth_token
    _auth_token_patch_applied = True


_ensure_cursor_sdk_auth_token_patch()


def init_sdk_bridge(workspace: str) -> None:
    """网关启动时初始化 Bridge（使用仓库根目录，而非 dingtalk_gateway 子目录）。"""
    global _workspace
    ws = (workspace or "").strip()
    with _lock:
        if _workspace == ws:
            return
        _workspace = ws
        os.chdir(ws)
        close_default_client()
        _default_client()
        logger.info("Cursor SDK Bridge 已初始化，workspace=%s", ws)


def bridge_initialized() -> bool:
    with _lock:
        return bool(_workspace)


def reset_sdk_bridge() -> None:
    """Bridge 断线后重建（中断任务后或 Connection refused 时）。"""
    with _lock:
        workspace = _workspace or os.getcwd()
        logger.warning("重建 Cursor SDK Bridge，workspace=%s", workspace)
        close_default_client()
        os.chdir(workspace)
        _default_client()
    reset_user_agent_pool()


def is_bridge_connection_error(exc: BaseException) -> bool:
    message = str(exc).lower()
    needles = (
        "connection refused",
        "server disconnected",
        "connecterror",
        "bridge request failed",
    )
    return any(needle in message for needle in needles)


def is_transient_sdk_error(exc: BaseException) -> bool:
    """Bridge 断连或 SDK 内部瞬态错误，可 invalidate + 重建后重试。"""
    if is_bridge_connection_error(exc):
        return True
    name = type(exc).__name__
    if name in {"InternalServerError", "APITimeoutError", "NetworkError"}:
        return True
    message = str(exc).lower()
    if "missing value for --tool-callback-auth-token" in message:
        return True
    if "missing value for --store-callback-auth-token" in message:
        return True
    return "internal error" in message or "internal:" in message


def is_retryable_agent_error(exc: BaseException) -> bool:
    """Agent 启动/执行瞬态失败，可自动重试（不含参数错误）。"""
    if isinstance(exc, (ValueError, FileNotFoundError)):
        return False
    if is_transient_sdk_error(exc):
        return True
    exc_name = type(exc).__name__
    if exc_name in {"CursorAgentError", "NetworkError"}:
        return True
    message = str(exc).lower()
    if "unknown agent" in message:
        return True
    if "cannot use this model" in message:
        return False
    if message.startswith("agent 执行失败"):
        return True
    if "agent 未返回" in message:
        return True
    if "agent 启动失败" in message:
        return True
    return False
