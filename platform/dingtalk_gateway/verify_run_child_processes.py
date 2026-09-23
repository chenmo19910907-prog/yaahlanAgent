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
    _command_pattern_fragment,
    _extract_shell_command,
    collect_process_tree_pids,
    is_pid_alive,
    kill_run_child_processes,
    list_run_child_pids,
    list_run_commands,
    register_run_child,
    register_run_command,
    register_shell_tool_update,
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

    parent = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import subprocess,sys,time; "
            "subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); "
            "time.sleep(60)",
        ],
        start_new_session=True,
    )
    time.sleep(0.2)
    tree = collect_process_tree_pids(parent.pid)
    assert parent.pid in tree, tree
    assert len(tree) >= 2, tree
    parent.kill()
    parent.wait(timeout=5)

    register_run_command(user_key, "python3 DingTalk/kb_sync_execute.py")
    assert "DingTalk/kb_sync_execute.py" in list_run_commands(user_key), list_run_commands(user_key)
    kill_run_child_processes(user_key)
    assert list_run_commands(user_key) == [], list_run_commands(user_key)

    register_shell_tool_update(
        user_key,
        {
            "type": "tool-call-started",
            "toolCall": {
                "name": "Shell",
                "args": {"command": "python3 DingTalk/kb_sync_execute.py"},
            },
        },
    )
    assert "DingTalk/kb_sync_execute.py" in list_run_commands(user_key), list_run_commands(user_key)
    kill_run_child_processes(user_key)

    assert _command_pattern_fragment("python3 DingTalk/kb_sync_execute.py") == "DingTalk/kb_sync_execute.py"
    assert _extract_shell_command({"name": "Shell", "args": {"command": "echo hi"}}) == "echo hi"

    leftover = REGISTRY_DIR / "nonexistent.json"
    assert not leftover.exists() or leftover.is_file()

    print("verify_run_child_processes: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
