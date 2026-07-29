"""Web Agent 代码更新后自动重启（带源码监视，不推送钉钉群通知）。"""

from __future__ import annotations

import logging
import subprocess
import threading
import time
from pathlib import Path

from env_loader import GATEWAY_DIR

logger = logging.getLogger("dingtalk-gateway")

REPO_ROOT = GATEWAY_DIR.parent.parent
WEB_AGENT_DIR = REPO_ROOT / "platform" / "web_agent"
SERVER_PY = WEB_AGENT_DIR / "server.py"
RESTART_LOG = WEB_AGENT_DIR / "data" / "restart.log"
RESTART_DELAY_S = 3

_SKIP_DIR_NAMES = frozenset(
    {
        "data",
        "__pycache__",
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "bookmarks_backups",
        "messages",
        "exports",
    }
)
_SKIP_SUFFIXES = frozenset({".pyc", ".log"})
_SKIP_FILE_PREFIXES = ("verify_",)


def _is_trackable_web_agent_file(path: Path) -> bool:
    if not path.is_file():
        return False
    if path.suffix in _SKIP_SUFFIXES:
        return False
    if path.name.startswith(_SKIP_FILE_PREFIXES):
        return False
    try:
        rel = path.relative_to(WEB_AGENT_DIR)
    except ValueError:
        return False
    if any(part in _SKIP_DIR_NAMES for part in rel.parts[:-1]):
        return False
    if rel.parts and rel.parts[0] == "data":
        return False
    return path.suffix in {".py", ".html", ".js", ".json"}


def list_web_agent_files_changed_since(since_ts: float) -> list[str]:
    """返回自任务开始以来有改动的 Web Agent 源码路径（相对仓库根）。"""
    threshold = since_ts - 1.0
    changed: list[str] = []
    if not WEB_AGENT_DIR.is_dir():
        return changed
    for path in WEB_AGENT_DIR.rglob("*"):
        if not _is_trackable_web_agent_file(path):
            continue
        try:
            if path.stat().st_mtime >= threshold:
                changed.append(str(path.relative_to(REPO_ROOT)))
        except OSError as exc:
            logger.debug("跳过文件 mtime 读取失败 %s: %s", path, exc)
    return sorted(set(changed))


def format_web_agent_restart_note(changed_files: list[str]) -> str:
    return (
        "\n\n🔄 检测到 Web Agent 代码已更新，约 "
        f"{RESTART_DELAY_S} 秒后自动重启（带源码监视，不向本群推送通知）。"
    )


def _resolve_python() -> str:
    candidates = (
        GATEWAY_DIR / ".venv" / "bin" / "python3",
        REPO_ROOT / ".venv" / "bin" / "python3",
    )
    for path in candidates:
        if path.is_file():
            return str(path)
    return "python3"


def _run_web_agent_ensure_restart() -> None:
    if not SERVER_PY.is_file():
        logger.error("未找到 server.py，无法自动重启 Web Agent")
        return
    RESTART_LOG.parent.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    with RESTART_LOG.open("a", encoding="utf-8") as log_f:
        log_f.write(f"\n--- {stamp} ensure-restart ---\n")
        log_f.flush()
        proc = subprocess.run(
            [_resolve_python(), str(SERVER_PY), "--ensure"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.stdout:
            log_f.write(proc.stdout)
        if proc.stderr:
            log_f.write(proc.stderr)
        log_f.write(f"\nexit={proc.returncode}\n")
    if proc.returncode != 0:
        logger.error("Web Agent --ensure 失败 exit=%s stderr=%s", proc.returncode, proc.stderr)
    else:
        logger.info("Web Agent 已自动重启（--ensure + server_watch）")


def schedule_web_agent_restart_after_code_change(
    *,
    operator: str,
    changed_files: list[str],
) -> None:
    """任务回复发出后延迟重启 Web Agent。"""
    if not changed_files:
        return
    operator_name = (operator or "未知").strip() or "未知"

    def _worker() -> None:
        time.sleep(RESTART_DELAY_S)
        try:
            _run_web_agent_ensure_restart()
            logger.info(
                "已触发 Web Agent 代码更新重启 operator=%s files=%d",
                operator_name,
                len(changed_files),
            )
        except OSError as exc:
            logger.error("触发 Web Agent 重启失败: %s", exc)

    threading.Thread(
        target=_worker,
        daemon=True,
        name="web-agent-code-restart",
    ).start()
