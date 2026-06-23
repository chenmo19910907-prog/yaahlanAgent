"""钉钉网关：禁止经 ADB / 真机 UI 执行任务。"""

from __future__ import annotations

import re

ADB_SCRIPT_RE = re.compile(
    r"(adb/adb_execute|adb_execute\.py|python3\s+adb/)",
    re.I,
)
ADB_CLI_RE = re.compile(
    r"\b(macro|flow\s+run|flow\s+bootstrap|autotest)\b",
    re.I,
)
ADB_OBSERVE_RE = re.compile(
    r"\b(observe|capture|locate|tap|swipe)\s+(--|\d)",
    re.I,
)
ADB_MCP_RE = re.compile(r"adb[_-]?(screen|observe)", re.I)
DEVICE_UI_RE = re.compile(
    r"(真机|USB\s*连接|读屏|点按|滑动).{0,12}(操作|送礼|执行|自动化|点击)|"
    r"(macro|片段|礼物面板|macroRef).{0,16}(送|点|执行|跑)|"
    r"(打开|进入).{0,8}(礼物面板|App内).{0,8}送|"
    r"UI.{0,6}送礼|adb.{0,6}送礼",
    re.I,
)

_PATTERNS = (
    ADB_SCRIPT_RE,
    ADB_CLI_RE,
    ADB_OBSERVE_RE,
    ADB_MCP_RE,
    DEVICE_UI_RE,
)

_DENY_MESSAGE = """\
钉钉机器人**不支持真机 ADB / UI 自动化**（macro、observe、capture、flow 等）。

请改用脚本能力，例如：
• **送礼（默认）** → `Gift/gift_execute.py` Stage HTTP；仅明确「背包送礼」时才走 MOA 背包
• **查数 / MOA / Admin** → 各模块 `*_execute.py`
• **抓包验收** → `Tunnel/tunnel_execute.py`（只读查包，不操作手机）

需要在真机上点按、截图验收时，请在 **Cursor 本机对话** 中操作。"""


def looks_like_adb_execution_request(text: str) -> bool:
    """用户消息是否明确要求走 ADB / 真机 UI 执行。"""
    t = (text or "").strip()
    if not t:
        return False
    return any(pattern.search(t) for pattern in _PATTERNS)


def adb_execution_denial_message() -> str:
    return _DENY_MESSAGE.strip()
