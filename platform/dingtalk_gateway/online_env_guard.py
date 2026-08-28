"""Web Agent：线上环境权限 — 全员可查用户/手机号；其余线上 MOA 全员禁止（含管理员/超管）；其他线上操作仅管理员。"""

from __future__ import annotations

import re

ONLINE_ADMIN_QUERY_RE = re.compile(
    r"online/online_execute\.py\s+admin\s+--query-user-id\b|"
    r"online_execute\.py\s+admin\s+--query-user-id\b|"
    r"线上(?:环境|账号)?\s*(?:查|查询)\s*(?:用户|userId|userid)\s*\d+|"
    r"线上(?:环境|账号)?\s*(?:用户|userId|userid)\s*\d+\s*(?:详情|资料|是否在线)|"
    r"线上(?:环境|账号)?\s*\d{5,}\s*(?:详情|资料|用户|是否在线)",
    re.I,
)
ONLINE_MOA_PHONE_QUERY_RE = re.compile(
    r"online/online_execute\.py\s+moa\s+--query-user-by-phone\b|"
    r"online_execute\.py\s+moa\s+--query-user-by-phone\b|"
    r"线上(?:环境|账号)?\s*(?:查|查询)\s*(?:手机号|手机)\s*\d+|"
    r"线上(?:环境|账号)?\s*(?:手机号|手机)\s*\d+\s*(?:查|查询|userId|userid|是否注册)|"
    r"线上(?:环境|账号)?\s*(?:查|查询)\s*\d{11}\s*(?:的\s*)?(?:userId|userid|对应)",
    re.I,
)
ONLINE_MOA_SCRIPT_RE = re.compile(
    r"moa_execute\.py[^\n]*(?:--线上环境|--online-env|--target-environment\s+prod)|"
    r"(?:--线上环境|--online-env|--target-environment\s+prod)[^\n]*moa_execute\.py|"
    r"online/online_execute\.py\s+moa\b(?!.*--query-user-by-phone)|"
    r"online_execute\.py\s+moa\b(?!.*--query-user-by-phone)",
    re.I,
)
ONLINE_MOA_MUTATION_NL_RE = re.compile(
    r"线上(?:环境|账号).{0,16}(?:MOA|moa_execute|升级|VIP|vip|增加|添加|清除|下发|送礼|互关|PK|修改)|"
    r"线上(?:环境|账号).{0,8}\d{11}.{0,12}(?:升级|添加|加|VIP|vip|增加|清除)",
    re.I,
)

ONLINE_EXPLICIT_RE = re.compile(
    r"线上环境|线上账号|线上用户|线上号|"
    r"online/online_execute|online_execute\.py|"
    r"--线上环境|--online-env|\bonline_env\b|"
    r"--target-environment\s+prod|"
    r"release-online-login-device",
    re.I,
)
ONLINE_OPERATION_RE = re.compile(
    r"线上.{0,12}(账号|用户|VIP|升级|解除|风控|登录|送礼|查|操作|MOA|Admin|Tunnel)|"
    r"(查|升级|解除|操作|修改|解除|送礼|风控).{0,16}线上|"
    r"线上(?!状态|Offline|offline)\d",
    re.I,
)
PROD_ENV_OPERATION_RE = re.compile(
    r"(在|用|走|切到|切换到).{0,8}(正式环境|生产环境|prod环境)|"
    r"(正式环境|生产环境|prod环境).{0,16}(查|升级|操作|解除|送礼|修改|风控|登录)",
    re.I,
)
POLICY_EXCLUDE_RE = re.compile(
    r"(增加|添加|修改|设置|制定).{0,16}规则|"
    r"只有管理员.{0,24}(权限|操作|可以)|"
    r"(正式环境|测试环境|线上环境).{0,8}还是|"
    r"是.{0,6}(正式环境|测试环境|线上环境).{0,6}还是|"
    r"(应该|需要|希望|要求|限制|开通|授权).{0,24}(管理员|权限)|"
    r"(管理员|权限).{0,24}(应该|需要|希望|要求|限制|开通|授权)",
    re.I,
)

_DENY_MESSAGE = (
    "你没有线上环境 / 线上账号操作权限（仅限管理员），请在用户头像信息中打开「管理员列表」申请管理员。"
)
_ONLINE_MOA_DENY_MESSAGE = (
    "线上环境除「Admin-查询用户详情」「MOA-按手机号查 userId」外，其他 MOA 操作一律不允许（含管理员/超管）。"
    "如需线上造数/改数，请在 Cursor 本机对话中操作。"
)


def looks_like_online_env_request(text: str) -> bool:
    """用户消息是否涉及线上环境 / 线上账号 / 正式环境操作。"""
    t = (text or "").strip()
    if not t:
        return False
    if POLICY_EXCLUDE_RE.search(t):
        return False
    if ONLINE_EXPLICIT_RE.search(t):
        return True
    if ONLINE_OPERATION_RE.search(t):
        return True
    if PROD_ENV_OPERATION_RE.search(t):
        return True
    return False


def online_env_denial_message() -> str:
    return _DENY_MESSAGE.strip()


def online_moa_denial_message() -> str:
    return _ONLINE_MOA_DENY_MESSAGE.strip()


def looks_like_online_public_query_request(text: str) -> bool:
    """线上环境全员允许的只读查询：Admin 查用户详情、MOA 按手机号查 userId。"""
    t = (text or "").strip()
    if not t or not looks_like_online_env_request(t):
        return False
    if ONLINE_ADMIN_QUERY_RE.search(t):
        return True
    return bool(ONLINE_MOA_PHONE_QUERY_RE.search(t))


def looks_like_online_moa_forbidden_request(text: str) -> bool:
    """线上环境禁止的 MOA（除按手机号查 userId 外的所有线上 MOA）。"""
    t = (text or "").strip()
    if not t or looks_like_online_public_query_request(t):
        return False
    if ONLINE_MOA_SCRIPT_RE.search(t):
        return True
    if not looks_like_online_env_request(t):
        return False
    if ONLINE_MOA_MUTATION_NL_RE.search(t):
        return True
    if re.search(r"线上.{0,16}MOA", t, re.I) and not ONLINE_MOA_PHONE_QUERY_RE.search(t):
        return True
    return False


def resolve_online_env_denial(
    text: str,
    *,
    online_admin_allowed: bool,
) -> str | None:
    """返回拦截文案；None 表示允许继续。"""
    if not looks_like_online_env_request(text):
        return None
    if looks_like_online_public_query_request(text):
        return None
    if looks_like_online_moa_forbidden_request(text):
        return online_moa_denial_message()
    if not online_admin_allowed:
        return online_env_denial_message()
    return None


def is_online_env_operation_allowed(*, staff_id: str | None = None) -> bool:
    """Web Agent：与代码修改白名单共用，仅管理员可操作线上环境。"""
    from source_file_permission import is_source_file_allowed

    return is_source_file_allowed(staff_id=staff_id)
