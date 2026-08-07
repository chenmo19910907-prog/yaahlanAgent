#!/usr/bin/env python3
"""验证 run_child_processes 登记与中断清理。"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

GATEWAY_DIR = Path(__file__).resolve().parents[1] / "dingtalk_gateway"
if str(GATEWAY_DIR) not in sys.path:
    sys.path.insert(0, str(GATEWAY_DIR))

from run_child_processes import (  # noqa: E402
    REGISTRY_DIR,
    is_pid_alive,
    kill_run_child_processes,
    list_run_child_pids,
    register_run_child,
    run_child_guard,
    unregister_run_child,
)


def main() -> int:
    user_key = "web:verify-run-child"
    register_run_child(user_key, 999999)
    assert 999999 in list_run_child_pids(user_key), list_run_child_pids(user_key)
    unregister_run_child(user_key, 999999)
    assert list_run_child_pids(user_key) == [], list_run_child_pids(user_key)

    child = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        start_new_session=True,
    )
    register_run_child(user_key, child.pid)
    assert is_pid_alive(child.pid), child.pid
    killed = kill_run_child_processes(user_key)
    assert killed == 1, killed
    try:
        child.wait(timeout=5)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait(timeout=3)
    assert child.poll() is not None, child.poll()
    assert list_run_child_pids(user_key) == [], list_run_child_pids(user_key)

    with run_child_guard(user_key):
        assert os.getpid() in list_run_child_pids(user_key), list_run_child_pids(user_key)
    assert list_run_child_pids(user_key) == [], list_run_child_pids(user_key)

    leftover = REGISTRY_DIR / "nonexistent.json"
    assert not leftover.exists() or leftover.is_file()

    print("verify_run_child_processes: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
