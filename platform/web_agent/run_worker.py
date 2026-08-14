#!/usr/bin/env python3
"""Web Agent 独立 worker：与 HTTP 服务解耦，服务重启不中断 Agent 执行。"""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
from pathlib import Path

WEB_AGENT_DIR = Path(__file__).resolve().parent
PLATFORM_DIR = WEB_AGENT_DIR.parent
REPO_ROOT = PLATFORM_DIR.parent
GATEWAY_DIR = PLATFORM_DIR / "dingtalk_gateway"

if str(GATEWAY_DIR) not in sys.path:
    sys.path.insert(0, str(GATEWAY_DIR))
if str(WEB_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_AGENT_DIR))

from web_run_executor import execute_web_run  # noqa: E402


def _spawn_one_shot_from_daemon(run_id: str) -> None:
    """daemon 仅负责转发：每 run 独立子进程，支持多会话并行。"""
    log_path = WEB_AGENT_DIR / "data" / "runs" / run_id / "worker.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_fp = open(log_path, "a", encoding="utf-8")
    env = dict(os.environ)
    if str(PLATFORM_DIR) not in sys.path:
        sys.path.insert(0, str(PLATFORM_DIR))
    try:
        from project.runtime_env import merge_worker_env  # noqa: WPS433

        env = merge_worker_env()
    except (ImportError, OSError, ValueError):
        pass
    subprocess.Popen(
        [sys.executable, str(WEB_AGENT_DIR / "run_worker.py"), "--run-id", run_id],
        cwd=str(REPO_ROOT),
        env=env,
        stdout=log_fp,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )


def _run_daemon() -> int:
    """常驻 worker：从 stdin 读取 run_id，为每个 run 启动独立子进程（并行）。"""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logger = logging.getLogger("web-agent.worker")
    logger.info("worker daemon 就绪，等待 run_id…")
    for line in sys.stdin:
        run_id = line.strip()
        if not run_id:
            continue
        try:
            _spawn_one_shot_from_daemon(run_id)
            logger.info("daemon 已派发 run=%s", run_id)
        except Exception:  # noqa: BLE001
            logger.exception("daemon 派发 run %s 失败", run_id)
    return 0


def _warm_imports() -> int:
    """预加载 worker 执行链常用模块，供 HTTP 启动时预热子进程。"""
    from chat_runner import ensure_bridge  # noqa: WPS433

    ensure_bridge()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Web Agent run worker")
    parser.add_argument("--run-id", default="", help="单次执行（与 --daemon 互斥）")
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="常驻模式：从 stdin 读取 run_id 并并行派发 one-shot worker",
    )
    parser.add_argument(
        "--warm",
        action="store_true",
        help="仅预 import 依赖后退出（HTTP 启动预热）",
    )
    args = parser.parse_args()
    if args.warm:
        return _warm_imports()
    if args.daemon:
        return _run_daemon()
    run_id = (args.run_id or "").strip()
    if not run_id:
        parser.error("须指定 --run-id、--daemon 或 --warm")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    return execute_web_run(run_id)


if __name__ == "__main__":
    raise SystemExit(main())
