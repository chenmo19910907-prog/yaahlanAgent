"""代码更新后自动静默重启网关（不推送钉钉群启停通知）。"""

from __future__ import annotations

import json
import logging
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from env_loader import GATEWAY_DIR

logger = logging.getLogger("dingtalk-gateway")

REPO_ROOT = GATEWAY_DIR.parent.parent
RESTART_CONTEXT = GATEWAY_DIR / "data" / "restart_context.json"
GATEWAY_CTL = GATEWAY_DIR / "gateway_ctl.sh"
RESTART_LOG = GATEWAY_DIR / "logs" / "restart.log"
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
        f"{RESTART_DELAY_S} 秒后自动静默重启（不向本群推送启停通知）。"
    )


def _run_gateway_silent_restart() -> None:
    if not GATEWAY_CTL.is_file():
        logger.error("未找到 gateway_ctl.sh，无法自动重启")
        return
    RESTART_LOG.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    with RESTART_LOG.open("a", encoding="utf-8") as log_f:
        log_f.write(f"\n--- {stamp} silent-restart ---\n")
        log_f.flush()
        subprocess.Popen(
            ["/bin/bash", str(GATEWAY_CTL), "silent-restart"],
            cwd=str(GATEWAY_DIR),
            start_new_session=True,
            stdout=log_f,
            stderr=subprocess.STDOUT,
        )


def schedule_gateway_restart_after_code_change(
    *,
    operator: str,
    changed_files: list[str],
) -> None:
    """任务回复发出后延迟静默重启（gateway_ctl.sh silent-restart）。"""
    if not changed_files:
        return
    operator_name = (operator or "未知").strip() or "未知"
    write_restart_context(operator=operator_name, changed_files=changed_files)

    def _worker() -> None:
        time.sleep(RESTART_DELAY_S)
        try:
            _run_gateway_silent_restart()
            logger.info(
                "已触发代码更新静默重启 operator=%s files=%d",
                operator_name,
                len(changed_files),
            )
        except OSError as exc:
            logger.error("触发 gateway_ctl silent-restart 失败: %s", exc)

    threading.Thread(
        target=_worker,
        daemon=True,
        name="gateway-code-restart",
    ).start()
