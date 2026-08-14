"""Web Agent 代码更新后自动重启（带源码监视，不推送钉钉群通知）。"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from env_loader import GATEWAY_DIR

logger = logging.getLogger("dingtalk-gateway")

REPO_ROOT = GATEWAY_DIR.parent.parent
WEB_AGENT_DIR = REPO_ROOT / "platform" / "web_agent"
SERVER_PY = WEB_AGENT_DIR / "server.py"
CONFIG_JSON = WEB_AGENT_DIR / "config.json"
RESTART_LOG = WEB_AGENT_DIR / "data" / "restart.log"
RESTART_DELAY_S = 3
FORCE_RESTART_WAIT_S = 10.0
FORCE_RESTART_TASK_WAIT_S = 15.0

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


@dataclass(frozen=True)
class WebAgentRestartOutcome:
    ok: bool
    message: str


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


def _python_can_import_cursor_sdk(python: Path | str) -> bool:
    try:
        proc = subprocess.run(
            [str(python), "-c", "import cursor_sdk"],
            capture_output=True,
            timeout=5,
            check=False,
        )
        return proc.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _resolve_python() -> str:
    candidates = (
        GATEWAY_DIR / ".venv" / "bin" / "python3",
        REPO_ROOT / ".venv" / "bin" / "python3",
    )
    fallback: str | None = None
    for path in candidates:
        if not path.is_file():
            continue
        resolved = str(path)
        if _python_can_import_cursor_sdk(path):
            return resolved
        fallback = fallback or resolved
    return fallback or "python3"


def _load_web_agent_bind() -> tuple[str, int]:
    host = "0.0.0.0"
    port = 18766
    if not CONFIG_JSON.is_file():
        return host, port
    try:
        cfg = json.loads(CONFIG_JSON.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.debug("读取 Web Agent config.json 失败: %s", exc)
        return host, port
    host = str(cfg.get("host") or host)
    try:
        port = int(cfg.get("port") or port)
    except (TypeError, ValueError):
        port = 18766
    return host, port


def _health_check(port: int) -> bool:
    url = f"http://127.0.0.1:{port}/api/meta"
    try:
        with urllib.request.urlopen(url, timeout=1.5) as resp:
            return int(getattr(resp, "status", 0) or 0) == 200
    except (OSError, urllib.error.URLError, ValueError):
        return False


def _import_server_watch():
    web_agent_str = str(WEB_AGENT_DIR)
    if web_agent_str not in sys.path:
        sys.path.insert(0, web_agent_str)
    from server_watch import (  # noqa: WPS433
        kill_all_watch_processes,
        kill_process_on_port,
        read_watch_pid,
        start_watch_background,
    )

    return kill_all_watch_processes, kill_process_on_port, read_watch_pid, start_watch_background


def _count_active_worker_runs() -> int:
    try:
        from server_watch import _active_worker_run_count

        return int(_active_worker_run_count())
    except Exception as exc:
        logger.debug("统计活跃 worker 失败: %s", exc)
        return 0


def force_restart_web_agent(*, wait_s: float = FORCE_RESTART_WAIT_S) -> WebAgentRestartOutcome:
    """强制重启 Web Agent（杀旧进程 + 拉起监视），供快捷路由与代码更新后重启。"""
    if not SERVER_PY.is_file():
        return WebAgentRestartOutcome(False, "未找到 Web Agent 服务程序。")

    task_deadline = time.monotonic() + FORCE_RESTART_TASK_WAIT_S
    while time.monotonic() < task_deadline:
        active = _count_active_worker_runs()
        if active == 0:
            break
        time.sleep(0.5)
    else:
        active = _count_active_worker_runs()
        if active > 0:
            return WebAgentRestartOutcome(
                False,
                f"仍有 {active} 个 Agent 任务执行中，请待任务结束后再重启。",
            )

    host, port = _load_web_agent_bind()
    try:
        kill_all_watch_processes, kill_process_on_port, read_watch_pid, start_watch_background = (
            _import_server_watch()
        )
    except ImportError as exc:
        logger.error("导入 server_watch 失败: %s", exc)
        return WebAgentRestartOutcome(False, "无法加载 Web Agent 监视模块。")

    kill_all_watch_processes()
    kill_process_on_port(port)
    proc = start_watch_background(host=host, port=port)

    deadline = time.monotonic() + max(wait_s, 5.0)
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return WebAgentRestartOutcome(False, "监视进程启动后立即退出，请查看 server_watch.log。")
        if _health_check(port):
            watch_pid = read_watch_pid()
            detail = f"监视进程 PID {watch_pid}，端口 {port} 健康检查通过。" if watch_pid else f"端口 {port} 健康检查通过。"
            return WebAgentRestartOutcome(True, detail)
        time.sleep(0.15)

    return WebAgentRestartOutcome(False, f"启动超时（{int(wait_s)} 秒内未通过健康检查）。")


def format_force_restart_reply(outcome: WebAgentRestartOutcome) -> str:
    if not outcome.ok:
        return f"❌ Web Agent 重启失败：{outcome.message}"
    _, port = _load_web_agent_bind()
    return (
        "Web Agent 已重启完成，服务运行正常。\n"
        f"{outcome.message}\n"
        f"本机访问：http://127.0.0.1:{port}/\n"
        "刷新浏览器页面即可继续使用。"
    )


def _append_restart_log(label: str, *, stdout: str = "", stderr: str = "", exit_code: int = 0) -> None:
    RESTART_LOG.parent.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    with RESTART_LOG.open("a", encoding="utf-8") as log_f:
        log_f.write(f"\n--- {stamp} {label} ---\n")
        if stdout:
            log_f.write(stdout)
        if stderr:
            log_f.write(stderr)
        log_f.write(f"\nexit={exit_code}\n")


def _run_web_agent_ensure_restart() -> None:
    outcome = force_restart_web_agent()
    _append_restart_log(
        "force-restart",
        stdout=outcome.message + "\n",
        exit_code=0 if outcome.ok else 1,
    )
    if not outcome.ok:
        logger.error("Web Agent 强制重启失败: %s", outcome.message)
    else:
        logger.info("Web Agent 已强制重启: %s", outcome.message)


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
