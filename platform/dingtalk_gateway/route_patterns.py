"""快捷指令路由正则（command_router / reply_formatter / dispatcher 共用）。"""

from __future__ import annotations

import re

from export_delivery import is_view_all_follow_up

EXPORT_FILE_RE = re.compile(
    r"^(?:导出|export)\s+(.+\.(?:csv|json|md))\s*$",
    re.I,
)
ENV_CHECK_RE = re.compile(
    r"^(?:环境检查|检查环境(?:配置)?|doctor)\s*$",
    re.I,
)
MOA_CHECK_RE = re.compile(
    r"^(?:MOA检查|检查\s*MOA(?:环境)?|MOA探活|moa探活|moa检查|moa\s*check|MOA\s*check)\s*$",
    re.I,
)
HELP_RE = re.compile(
    r"^(?:帮助|使用说明|使用帮助|能力说明|help|\?|？|说明书|新手引导)\s*$",
    re.I,
)
VIP_UPGRADE_RE = re.compile(
    r"^(?:用户\s*)?(\d{5,})\s*(?:升级|升到|升级到)\s*VIP?\s*(\d+)\s*$",
    re.I,
)
REPORT_VERSION_RE = re.compile(
    r"^(?:生成\s*)?(?:v)?(\d+\.\d+\.\d+)\s*版本\s*(?:生成\s*)?测试报告\s*$",
    re.I,
)
REPORT_NL_RE = re.compile(
    r"^(?:帮(?:我|忙)?(?:生)?成?|做?出?)?\s*(?:v)?(\d+\.\d+\.\d+)\s*(?:版本)?(?:的)?\s*测试报告\s*$",
    re.I,
)
REPORT_URL_RE = re.compile(
    r"^(?:生成\s*)?测试报告\s+(https://alidocs\.dingtalk\.com/\S+)\s*$",
    re.I,
)
CATALOG_OPEN_RE = re.compile(
    r"^(?:打开|刷新|生成)?\s*"
    r"(?:工具平台|工具工作台|工具台|输入工作台|智能工具平台|平台目录|能力目录|工作台|"
    r"工具平台清单|平台说明书|工具说明书|catalog)"
    r"\s*(?:html|HTML)?\s*$",
    re.I,
)

# 含这些特征视为自然语言任务，不做模糊口令归一
_NL_TASK_RE = re.compile(
    r"(https?://|alidocs\.dingtalk|\d{5,}|查|查询|生成|介绍|分析|"
    r"user\s*id|userid|用例|报告|升级\s*VIP?\s*\d|导出\s+\S+\.(csv|json|md))",
    re.I,
)

_FAST_ROUTE_RES = (
    HELP_RE,
    MOA_CHECK_RE,
    ENV_CHECK_RE,
    CATALOG_OPEN_RE,
    EXPORT_FILE_RE,
    VIP_UPGRADE_RE,
    REPORT_VERSION_RE,
    REPORT_NL_RE,
    REPORT_URL_RE,
)


def normalize_report_prompt(text: str) -> str | None:
    """自然语言测试报告口令 → 标准「x.x.x版本生成测试报告」。"""
    t = (text or "").strip()
    m = REPORT_NL_RE.match(t)
    if m:
        return f"{m.group(1)}版本生成测试报告"
    return None


def normalize_fuzzy_fast_command(text: str) -> str | None:
    """模糊快捷口令 → 标准 fast 路由口令（如「帮我 MOA 探活」→「MOA检查」）。"""
    t = (text or "").strip()
    if not t or len(t) > 48:
        return None
    if any(pattern.match(t) for pattern in _FAST_ROUTE_RES):
        return None
    if _NL_TASK_RE.search(t):
        return None
    if re.search(r"moa|探活", t, re.I):
        return "MOA检查"
    if re.search(r"环境|doctor|配置检查", t, re.I):
        return "环境检查"
    if re.search(r"工具|工作台|catalog|平台清单|说明书", t, re.I):
        return "工具平台"
    if re.search(r"帮助|说明|help|怎么用|用法", t, re.I):
        return "帮助"
    return None


def is_likely_fast_route(text: str) -> bool:
    """入队时判断是否走 fast 队列（不与 Agent 任务互斥）。"""
    t = (text or "").strip()
    if not t:
        return False
    if is_view_all_follow_up(t):
        return True
    if normalize_report_prompt(t):
        return True
    if normalize_fuzzy_fast_command(t):
        return True
    return any(pattern.match(t) for pattern in _FAST_ROUTE_RES)
