# -*- coding: utf-8 -*-
"""公会进步奖政策开关。

新政策自结算周期 20260816（2026年8月下）起生效；此前周期仍按 202512 口径。
取值：202512（旧，默认）/ 202608（新）/ auto（按周期自动：>=20260816 用新）。
也接受 old / new。
优先级：pytest --guild-progress-policy > 环境变量 GUILD_PROGRESS_AWARD_POLICY > 默认 202512。
"""
from __future__ import annotations

import os

POLICY_OLD = "202512"
POLICY_NEW = "202608"
DEFAULT_POLICY = POLICY_OLD
ENV_KEY = "GUILD_PROGRESS_AWARD_POLICY"
NEW_POLICY_FIRST_PERIOD = "20260816"

_ALIASES = {
    "202512": POLICY_OLD,
    "202512下": POLICY_OLD,
    "old": POLICY_OLD,
    "legacy": POLICY_OLD,
    "prev": POLICY_OLD,
    "202608": POLICY_NEW,
    "202608上": POLICY_NEW,
    "new": POLICY_NEW,
    "auto": "auto",
}

_LABELS = {
    POLICY_OLD: "202512下（旧：上周期薪资）",
    POLICY_NEW: "202608上（新：近6周期最高薪资；自20260816起）",
    "auto": "按周期自动（<20260816 旧，>=20260816 新）",
}


class UnknownGuildProgressPolicy(ValueError):
    pass


def normalize_policy(raw: str | None) -> str:
    text = (raw or "").strip()
    if not text:
        return DEFAULT_POLICY
    policy = _ALIASES.get(text) or _ALIASES.get(text.lower())
    if policy is None:
        raise UnknownGuildProgressPolicy(
            f"未知公会进步奖政策 {raw!r}，允许：202512 / 202608 / old / new / auto"
        )
    return policy


def policy_for_period(salary_period: str | int) -> str:
    """按结算周期判断应使用的政策。salary_period 如 20260816、20260801。"""
    period = str(salary_period).strip()
    if period >= NEW_POLICY_FIRST_PERIOD:
        return POLICY_NEW
    return POLICY_OLD


def get_guild_progress_award_policy(salary_period: str | int | None = None) -> str:
    selected = normalize_policy(os.environ.get(ENV_KEY))
    if selected == "auto":
        if salary_period is None:
            return DEFAULT_POLICY
        return policy_for_period(salary_period)
    return selected


def is_new_guild_progress_policy(salary_period: str | int | None = None) -> bool:
    return get_guild_progress_award_policy(salary_period) == POLICY_NEW


def policy_label(policy: str | None = None, salary_period: str | int | None = None) -> str:
    selected = normalize_policy(policy) if policy is not None else normalize_policy(os.environ.get(ENV_KEY))
    if selected == "auto":
        if salary_period is not None:
            code = policy_for_period(salary_period)
            return f"{code} {_LABELS[code]}（auto）"
        return f"auto {_LABELS['auto']}"
    return f"{selected} {_LABELS[selected]}"
