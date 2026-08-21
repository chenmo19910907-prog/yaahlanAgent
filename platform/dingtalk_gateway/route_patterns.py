"""快捷指令路由正则（command_router / reply_formatter / dispatcher 共用）。"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_PLATFORM_DIR = Path(__file__).resolve().parents[1]
if str(_PLATFORM_DIR) not in sys.path:
    sys.path.insert(0, str(_PLATFORM_DIR))

from project.loader import web_login_pattern  # noqa: E402

WEB_LOGIN_RE = web_login_pattern()

_MOA_REGISTRY_INTENT_RE = re.compile(
    r"(?:"
    r"(?:入库|登记|注册|同步).{0,24}(?:MOA|moa|模板|registry|能力清单)|"
    r"(?:MOA|moa).{0,32}(?:入库|登记|注册|sync_registry)|"
    r"sync_registry|generate_index\.py"
    r")",
    re.I,
)

EXPORT_FILE_RE = re.compile(
    r"^(?:导出|export)\s+(.+\.(?:csv|json|md))\s*$",
    re.I,
)
MOA_CHECK_RE = re.compile(
    r"^(?:MOA检查|检查\s*MOA(?:环境)?|MOA探活|moa探活|moa检查|moa\s*check|MOA\s*check)\s*$",
    re.I,
)
WEB_AGENT_RESTART_RE = re.compile(
    r"^(?:重启|restart)\s*(?:web\s*agent|webagent|网页版\s*agent|网页\s*agent)\s*$",
    re.I,
)
REPLY_MODE_SET_RE = re.compile(
    r"^(?:切换(?:为)?)?(精简回复|标准回复|详细回复)\s*$",
    re.I,
)
REPLY_MODE_QUERY_RE = re.compile(
    r"^(?:当前)?回复(?:详略|模式)\s*$",
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
ADMIN_APPLY_APPROVE_RE = re.compile(
    r"^同意管理员申请\s+([a-f0-9]{8})\s*$",
    re.I,
)
ADMIN_APPLY_REJECT_RE = re.compile(
    r"^拒绝管理员申请\s+([a-f0-9]{8})\s*$",
    re.I,
)

# 含这些特征视为自然语言任务，不做模糊口令归一
_NL_TASK_RE = re.compile(
    r"(https?://|alidocs\.dingtalk|\d{5,}|查|查询|生成|介绍|分析|"
    r"user\s*id|userid|用例|报告|升级\s*VIP?\s*\d|导出\s+\S+\.(csv|json|md)|"
    r"入库|登记|sync_registry|registry\.json)",
    re.I,
)

_FAST_ROUTE_RES = (WEB_AGENT_RESTART_RE, REPLY_MODE_SET_RE, REPLY_MODE_QUERY_RE)

_REPLY_MODE_TOKEN = {
    "精简回复": "concise",
    "标准回复": "standard",
    "详细回复": "detailed",
}


def is_web_agent_restart_request(text: str) -> bool:
    return bool(WEB_AGENT_RESTART_RE.match((text or "").strip()))


def parse_reply_mode_request(text: str) -> str | None:
    """命中回复详略口令 → concise/standard/detailed；查询 → query；否则 None。"""
    t = (text or "").strip()
    if REPLY_MODE_QUERY_RE.match(t):
        return "query"
    m = REPLY_MODE_SET_RE.match(t)
    if not m:
        return None
    token = m.group(1).strip()
    return _REPLY_MODE_TOKEN.get(token)


def normalize_report_prompt(text: str) -> str | None:
    """自然语言测试报告口令 → 标准「x.x.x版本生成测试报告」。"""
    t = (text or "").strip()
    m = REPORT_NL_RE.match(t)
    if m:
        return f"{m.group(1)}版本生成测试报告"
    return None


def normalize_fuzzy_fast_command(text: str) -> str | None:
    """模糊快捷口令 → 标准 fast 路由口令（当前仅 Web Agent 重启，无模糊归一）。"""
    t = (text or "").strip()
    if not t or len(t) > 48:
        return None
    if any(pattern.match(t) for pattern in _FAST_ROUTE_RES):
        return None
    if _NL_TASK_RE.search(t):
        return None
    if _MOA_REGISTRY_INTENT_RE.search(t):
        return None
    return None


def is_web_login_request(text: str) -> bool:
    return bool(WEB_LOGIN_RE.match((text or "").strip()))


def parse_admin_apply_decision(text: str) -> tuple[str, bool] | None:
    """解析管理员申请审批口令 → (token, approve)。"""
    t = (text or "").strip()
    m = ADMIN_APPLY_APPROVE_RE.match(t)
    if m:
        return m.group(1).lower(), True
    m = ADMIN_APPLY_REJECT_RE.match(t)
    if m:
        return m.group(1).lower(), False
    return None


def is_admin_apply_decision_request(text: str) -> bool:
    return parse_admin_apply_decision(text) is not None


def is_likely_fast_route(text: str) -> bool:
    """入队时判断是否走 fast 队列（不与 Agent 任务互斥）。含网页验证码、Web Agent 重启与回复详略切换。"""
    t = (text or "").strip()
    if not t:
        return False
    if is_web_login_request(t):
        return True
    return any(pattern.match(t) for pattern in _FAST_ROUTE_RES)


def should_send_text_task_ack(text: str) -> bool:
    """入队时是否发送「已收到，执行中」文本确认；快捷指令秒回，跳过。"""
    return not is_likely_fast_route(text)
