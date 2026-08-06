"""platform/dingtalk_gateway 侧读取 AGENT_PROJECT 路径。"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_PLATFORM = _REPO / "platform"
if str(_PLATFORM) not in sys.path:
    sys.path.insert(0, str(_PLATFORM))

from project.loader import temporary_testcase_dir, test_devices_path  # noqa: E402

__all__ = ["temporary_testcase_dir", "test_devices_path"]
