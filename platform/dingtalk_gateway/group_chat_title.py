"""钉钉群聊标题：区分用户自定义群名与系统默认名。"""

from __future__ import annotations

import re

# 占位标题：钉钉未设置群名时的兜底文案
_PLACEHOLDER_GROUP_TITLE_RE = re.compile(r"^钉钉群(?:\s*·.*)?$")
_GENERIC_GROUP_TITLE_RE = re.compile(r"^(?:群聊|group\s*chat)$", re.IGNORECASE)
# 成员名列表后缀：张三,李四等 / 张三,李四等4人
_MEMBER_LIST_SUFFIX_RE = re.compile(r"等\d*人?$")
# 多段人名拼接（逗号/顿号分隔），常见于未自定义群名
_MEMBER_LIST_TITLE_RE = re.compile(
    r"^[\u4e00-\u9fffA-Za-z0-9·．.\s'\-]{1,24}"
    r"(?:[,，、][\u4e00-\u9fffA-Za-z0-9·．.\s'\-]{1,24})+$"
)


def is_custom_group_title(title: str) -> bool:
    """群聊是否有用户自定义名称（排除占位名与成员名拼接默认名）。"""
    name = (title or "").strip()
    if not name:
        return False
    if _PLACEHOLDER_GROUP_TITLE_RE.match(name):
        return False
    if _GENERIC_GROUP_TITLE_RE.match(name):
        return False
    if _MEMBER_LIST_SUFFIX_RE.search(name):
        return False
    if _MEMBER_LIST_TITLE_RE.match(name):
        return False
    return True
