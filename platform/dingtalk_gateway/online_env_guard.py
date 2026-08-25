"""Web Agent：线上环境 / 线上账号操作仅管理员可执行。"""

from __future__ import annotations

import re

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
    "你没有线上环境 / 线上账号操作权限（仅限管理员），请在右上角头像菜单申请管理员权限。"
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


def is_online_env_operation_allowed(*, staff_id: str | None = None) -> bool:
    """Web Agent：与代码修改白名单共用，仅管理员可操作线上环境。"""
    from source_file_permission import is_source_file_allowed

    return is_source_file_allowed(staff_id=staff_id)
