"""近义口令提示：快捷路由未命中时，避免误进 Agent。"""

from __future__ import annotations

import re

from route_patterns import (
    CATALOG_OPEN_RE,
    ENV_CHECK_RE,
    HELP_RE,
    MOA_CHECK_RE,
)

# 含这些特征视为自然语言任务，不做口令猜测
_NL_TASK_RE = re.compile(
    r"(https?://|alidocs\.dingtalk|\d{5,}|查|查询|生成|介绍|分析|"
    r"user\s*id|userid|用例|报告|升级\s*VIP?\s*\d|导出\s+\S+\.(csv|json|md))",
    re.I,
)


def suggest_command_hint(text: str) -> str | None:
    """短句且像口令打错时，返回提示文案；否则 None。"""
    t = (text or "").strip()
    if not t or len(t) > 48:
        return None
    if _NL_TASK_RE.search(t):
        return None

    hints: list[str] = []
    if re.search(r"moa|探活", t, re.I) and not MOA_CHECK_RE.match(t):
        hints.append("MOA检查")
    if re.search(r"环境|doctor|配置检查", t, re.I) and not ENV_CHECK_RE.match(t):
        hints.append("环境检查")
    if re.search(r"帮助|说明|help|怎么用|用法", t, re.I) and not HELP_RE.match(t):
        hints.append("帮助")
    if re.search(r"工具|工作台|catalog|平台清单|说明书", t, re.I) and not CATALOG_OPEN_RE.match(t):
        hints.append("工具平台")

    if not hints:
        return None

    quoted = " / ".join(f"`{item}`" for item in hints[:3])
    return f"💡 你是不是想说：{quoted}？\n直接发送上述口令即可（更快，不走 Agent）。"
