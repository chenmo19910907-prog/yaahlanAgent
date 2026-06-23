"""代码更新后自动重启网关，并在启停时主动推送钉钉群通知。"""

from __future__ import annotations

import json
import logging
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from env_loader import GATEWAY_DIR
from gateway_status_notify import notify_gateway_stopping

logger = logging.getLogger("dingtalk-gateway")

REPO_ROOT = GATEWAY_DIR.parent.parent
RESTART_CONTEXT = GATEWAY_DIR / "data" / "restart_context.json"
GATEWAY_CTL = GATEWAY_DIR / "gateway_ctl.sh"
RESTART_DELAY_S = 3

_SKIP_DIR_NAMES = frozenset({"data", "logs", "exports", ".venv", "__pycache__"})
_SKIP_FILE_NAMES = frozenset({".env.local", "restart_context.json"})


def _is_trackable_gateway_file(path: Path) -> bool:
    if not path.is_file():
        return False
    if path.name in _SKIP_FILE_NAMES or path.suffix in {".pyc", ".log"}:
        return False
    try:
        rel = path.relative_to(GATEWAY_DIR)
    except ValueError:
        return False
    return not any(part in _SKIP_DIR_NAMES for part in rel.parts)


def list_gateway_files_changed_since(since_ts: float) -> list[str]:
    """返回自任务开始以来有改动的网关源码路径（相对仓库根）。"""
    threshold = since_ts - 1.0
    changed: list[str] = []
    for path in GATEWAY_DIR.rglob("*"):
        if not _is_trackable_gateway_file(path):
            continue
        try:
            if path.stat().st_mtime >= threshold:
                changed.append(str(path.relative_to(REPO_ROOT)))
        except OSError as exc:
            logger.debug("跳过文件 mtime 读取失败 %s: %s", path, exc)
    return sorted(set(changed))


def write_restart_context(*, operator: str, changed_files: list[str]) -> None:
    payload = {
        "trigger": "code_update",
        "operator": (operator or "未知").strip() or "未知",
        "changedFiles": changed_files,
        "createdAt": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
    }
    RESTART_CONTEXT.parent.mkdir(parents=True, exist_ok=True)
    RESTART_CONTEXT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def read_and_clear_restart_context() -> dict | None:
    if not RESTART_CONTEXT.is_file():
        return None
    try:
        raw = json.loads(RESTART_CONTEXT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("读取 restart_context.json 失败: %s", exc)
        RESTART_CONTEXT.unlink(missing_ok=True)
        return None
    RESTART_CONTEXT.unlink(missing_ok=True)
    return raw if isinstance(raw, dict) else None


def format_code_update_restart_note(changed_files: list[str]) -> str:
    return (
        "\n\n🔄 检测到网关代码已更新，约 "
        f"{RESTART_DELAY_S} 秒后自动重启；重启前后均会在本群推送通知。"
    )


def schedule_gateway_restart_after_code_change(
    *,
    operator: str,
    changed_files: list[str],
) -> None:
    """任务回复发出后延迟重启：先推送关闭通知，再 launchd restart。"""
    if not changed_files:
        return
    write_restart_context(operator=operator, changed_files=changed_files)
    operator_name = (operator or "未知").strip() or "未知"

    def _worker() -> None:
        time.sleep(RESTART_DELAY_S)
        try:
            notify_gateway_stopping(reason=f"代码更新（{operator_name}），正在重启")
        except Exception as exc:  # noqa: BLE001
            logger.warning("代码更新重启前通知失败: %s", exc)
        time.sleep(0.8)
        if not GATEWAY_CTL.is_file():
            logger.error("未找到 gateway_ctl.sh，无法自动重启")
            return
        try:
            subprocess.Popen(
                ["/bin/bash", str(GATEWAY_CTL), "restart"],
                cwd=str(GATEWAY_DIR),
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            logger.info(
                "已触发代码更新重启 operator=%s files=%d",
                operator_name,
                len(changed_files),
            )
        except OSError as exc:
            logger.error("触发 gateway_ctl restart 失败: %s", exc)

    threading.Thread(
        target=_worker,
        daemon=True,
        name="gateway-code-restart",
    ).start()
