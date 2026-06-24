"""批量操作最终结果：Agent/脚本写入，任务结束时网关推送到钉钉群。"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from env_loader import GATEWAY_DIR

logger = logging.getLogger("dingtalk-gateway")

RESULT_DIR = GATEWAY_DIR / "data" / "batch_progress"
MAX_RESULT_CHARS = 120_000


def _safe_filename(user_key: str) -> str:
    digest = hashlib.sha256(user_key.encode("utf-8")).hexdigest()[:24]
    return f"{digest}_result.md"


def _result_path(user_key: str) -> Path:
    return RESULT_DIR / _safe_filename(user_key)


def save_batch_result(user_key: str, text: str) -> None:
    key = (user_key or "").strip()
    body = (text or "").strip()
    if not key or not body:
        return
    if len(body) > MAX_RESULT_CHARS:
        body = body[:MAX_RESULT_CHARS] + "\n\n…（结果过长已截断）"
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    _result_path(key).write_text(body, encoding="utf-8")
    logger.info("批量结果已落盘 user=%s chars=%d", key, len(body))


def read_batch_result(user_key: str) -> str | None:
    key = (user_key or "").strip()
    if not key:
        return None
    path = _result_path(key)
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        logger.warning("读取批量结果失败 user=%s: %s", key, exc)
        return None
    return text or None


def pop_batch_result(user_key: str) -> str | None:
    text = read_batch_result(user_key)
    clear_batch_result(user_key)
    return text


def choose_final_reply_source(*, agent_formatted: str, batch_result: str | None) -> tuple[str, str]:
    """批量任务结束时择一作为群消息正文，避免 Agent 自然语言与 --result-text Markdown 双发。"""
    batch = (batch_result or "").strip()
    if batch:
        return batch, "batch"
    return (agent_formatted or "").strip(), "agent"


def clear_batch_result(user_key: str) -> None:
    key = (user_key or "").strip()
    if not key:
        return
    try:
        _result_path(key).unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("清理批量结果失败 user=%s: %s", key, exc)
