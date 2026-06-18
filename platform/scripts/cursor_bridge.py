#!/usr/bin/env python3
"""将提示语填入已打开的 Cursor 聊天输入框（macOS）。"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

_ACTIVATE_AND_PASTE = """
tell application "Cursor" to activate
delay 0.2
tell application "System Events" to tell process "Cursor"
  keystroke "v" using command down
end tell
"""

_OPEN_COMPOSER_AND_PASTE = """
tell application "Cursor" to activate
delay 0.3
tell application "System Events" to tell process "Cursor"
  keystroke "i" using command down
  delay 0.35
  keystroke "v" using command down
end tell
"""


def is_cursor_running() -> bool:
    proc = subprocess.run(
        ["pgrep", "-x", "Cursor"],
        capture_output=True,
        check=False,
    )
    return proc.returncode == 0


def _set_clipboard(text: str) -> None:
    proc = subprocess.run(
        ["pbcopy"],
        input=text,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        err = proc.stderr.strip() or "pbcopy failed"
        raise RuntimeError(err)


def _run_osascript(script: str) -> None:
    proc = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        err = proc.stderr.strip() or proc.stdout.strip() or "osascript failed"
        raise RuntimeError(err)


def send_prompt_to_cursor(text: str, repo_root: Path | None = None) -> str:
    """填入 Cursor 输入框。已运行时复用现有窗口；未运行时启动 Cursor。

    Returns:
        ``existing`` — Cursor 已在运行，激活后粘贴到当前焦点
        ``existing_clipboard`` — 已激活 Cursor，粘贴因系统权限失败，文案在剪贴板
        ``launched`` — 新启动 Cursor 并打开 Agent 后粘贴
        ``launched_clipboard`` — 已启动 Cursor，粘贴失败，文案在剪贴板
    """
    if sys.platform != "darwin":
        raise OSError("cursor bridge 仅支持 macOS")

    if not text.strip():
        raise ValueError("提示语不能为空")

    _set_clipboard(text)

    if is_cursor_running():
        try:
            _run_osascript(_ACTIVATE_AND_PASTE)
            return "existing"
        except RuntimeError:
            _run_osascript('tell application "Cursor" to activate')
            return "existing_clipboard"

    launch_target = str(repo_root) if repo_root and repo_root.is_dir() else ""
    if launch_target:
        subprocess.run(["open", "-a", "Cursor", launch_target], check=False)
    else:
        subprocess.run(["open", "-a", "Cursor"], check=False)
    time.sleep(2.5)
    try:
        _run_osascript(_OPEN_COMPOSER_AND_PASTE)
        return "launched"
    except RuntimeError:
        _run_osascript('tell application "Cursor" to activate')
        return "launched_clipboard"
