"""Web Agent：线上环境权限 — 全员 Admin/手机号只读；已入库 MOA 仅管理员；未入库 MOA 全员禁止。"""

from __future__ import annotations

import re

from online_moa_registry_match import match_registered_online_moa

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
ONLINE_CAPABILITY_CATALOG_RE = re.compile(
    r"(?:有哪些|有什么|清单|列表|一览|列举|"
    r"支持(?:哪些|什么)|能(?:做|用)什么|包含哪些|多少项|几项|"
    r"(?:哪些|什么).{0,8}(?:能力|功能|命令|接口))",
    re.I,
)
ONLINE_CAPABILITY_SCOPE_RE = re.compile(
    r"线上|online(?:/|_|\s|$)|MOA|Admin|Tunnel|registry|线上环境|能力(?:台|目录)?",
    re.I,
)

_DENY_MESSAGE = (
    "你没有线上环境 / 线上账号操作权限（仅限管理员），请在用户头像信息中打开「管理员列表」申请管理员。"
)
_ONLINE_MOA_ADMIN_DENY_MESSAGE = (
    "你没有线上 MOA 操作权限。除全员可用的「Admin-查询用户详情」「MOA-按手机号查 userId」外，"
    "其余已入库线上 MOA 仅管理员/超管可用；请在用户头像信息中打开「管理员列表」申请管理员。"
)
_ONLINE_MOA_NOT_REGISTERED_MESSAGE = (
    "该线上 MOA 能力未登记到 online/config/registry.json，禁止执行（含管理员/超管）。"
    "如需开放：先将 MOA 入库到 online 模块后再操作。"
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
    """非管理员访问已入库线上 MOA。"""
    return _ONLINE_MOA_ADMIN_DENY_MESSAGE.strip()


def online_moa_not_registered_message() -> str:
    """未入库线上 MOA（全员禁止）。"""
    return _ONLINE_MOA_NOT_REGISTERED_MESSAGE.strip()


def looks_like_online_capability_catalog_query(text: str) -> bool:
    """询问线上能力清单/登记项（只读，不执行 online_execute）。"""
    t = (text or "").strip()
    if not t or not ONLINE_CAPABILITY_CATALOG_RE.search(t):
        return False
    if not ONLINE_CAPABILITY_SCOPE_RE.search(t):
        return False
    if re.search(r"\d{5,}", t) and re.search(
        r"(?:查|查询|升级|添加|加|清除|解除|下发|修改|送礼)", t, re.I
    ):
        return False
    return True


def looks_like_online_public_query_request(text: str) -> bool:
    """线上环境全员允许的只读查询：Admin 查用户详情、MOA 按手机号查 userId。"""
    t = (text or "").strip()
    if not t or not looks_like_online_env_request(t):
        return False
    if match_registered_online_moa(t):
        return False
    if ONLINE_ADMIN_QUERY_RE.search(t):
        return True
    return bool(ONLINE_MOA_PHONE_QUERY_RE.search(t))


def looks_like_online_moa_operation_request(text: str) -> bool:
    """除全员公开查询外的线上 MOA 操作（含已入库纯查询）。"""
    t = (text or "").strip()
    if not t or not looks_like_online_env_request(t):
        return False
    if looks_like_online_capability_catalog_query(t):
        return False
    if ONLINE_MOA_PHONE_QUERY_RE.search(t):
        return False
    if match_registered_online_moa(t):
        return True
    if ONLINE_MOA_SCRIPT_RE.search(t):
        return True
    if ONLINE_MOA_MUTATION_NL_RE.search(t):
        return True
    if re.search(r"线上.{0,16}MOA", t, re.I):
        return True
    return False


def looks_like_online_moa_forbidden_request(text: str) -> bool:
    """兼容旧名：线上 MOA 操作（权限在 resolve 中细分）。"""
    return looks_like_online_moa_operation_request(text)


def resolve_online_env_denial(
    text: str,
    *,
    online_admin_allowed: bool,
) -> str | None:
    """返回拦截文案；None 表示允许继续。"""
    if not looks_like_online_env_request(text):
        return None
    if looks_like_online_capability_catalog_query(text):
        return None
    if looks_like_online_public_query_request(text):
        return None
    if looks_like_online_moa_operation_request(text):
        reg_id = match_registered_online_moa(text)
        if reg_id is None:
            return online_moa_not_registered_message()
        if not online_admin_allowed:
            return online_moa_denial_message()
        return None
    if not online_admin_allowed:
        return online_env_denial_message()
    return None


def is_online_env_operation_allowed(*, staff_id: str | None = None) -> bool:
    """与 Web Agent 共用 admin_grants 的 online 权限。"""
    from admin_permission import has_admin_permission

    uid = (staff_id or "").strip()
    if not uid:
        from source_file_permission import resolve_staff_id_from_env

        uid = resolve_staff_id_from_env()
    return has_admin_permission(staff_id=uid, permission="online")
