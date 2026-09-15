"""线上 MOA 纯查询能力白名单（与 online/config/registry.json MOA 节对齐）。"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from pathlib import Path

QueryPredicate = Callable[[argparse.Namespace], bool]


def _payload_name(args: argparse.Namespace) -> str:
    path = getattr(args, "payload_file", None) or ""
    return Path(str(path)).name


def _is_payload(args: argparse.Namespace, filename: str) -> bool:
    return _payload_name(args) == filename


def _online_moa_query_checks() -> list[tuple[str, QueryPredicate]]:
    return [
        ("user_login_query_by_phone", lambda a: a.query_user_by_phone is not None),
        (
            "vip_query_current",
            lambda a: bool(
                a.vip_query_current
                and a.vip_user_id
                and a.vip_exp is None
                and a.vip_level is None
            ),
        ),
        (
            "family_query_members",
            lambda a: bool(a.family_query_members and a.family_id),
        ),
        (
            "family_query_joined_by_user",
            lambda a: a.family_query_joined_user_id is not None,
        ),
        (
            "family_detail_by_id",
            lambda a: bool(a.family_detail and a.family_id),
        ),
        (
            "family_detail_by_user",
            lambda a: a.family_detail_by_user_id is not None,
        ),
        (
            "id_auth_query_real_person_record",
            lambda a: bool(
                a.id_auth_user_id is not None
                and a.id_auth_fix_failure_user_id is None
                and a.id_auth_reset_expire_user_id is None
                and a.id_auth_delete_user_id is None
                and a.id_auth_del_relation_user_id is None
            ),
        ),
        ("ip_find", lambda a: a.find_ip is not None),
        ("user_reg_time_query", lambda a: a.user_reg_time_user_id is not None),
        ("charm_query_current", lambda a: a.charm_query_user_id is not None),
        ("wealth_query_current", lambda a: a.wealth_query_user_id is not None),
        ("diamond_query_account", lambda a: a.diamond_query_user_id is not None),
        (
            "user_active_days_query",
            lambda a: _is_payload(a, "查询用户登录天数.json") and a.expr is not None,
        ),
        (
            "user_app_language_query",
            lambda a: _is_payload(a, "查看用户app语言.json")
            and getattr(a, "user_app_language_user_id", None) is not None,
        ),
        (
            "user_prop_query_own",
            lambda a: a.user_prop_query_user_id is not None and a.user_prop_type_code is not None,
        ),
        (
            "user_query_joined_trade_union",
            lambda a: _is_payload(a, "用户-查所属公会.json") and a.expr is not None,
        ),
    ]


def online_moa_query_requested(args: argparse.Namespace) -> str | None:
    """若 args 属于允许的线上纯查询，返回 registry id；否则 None。"""
    for reg_id, predicate in _online_moa_query_checks():
        if predicate(args):
            return reg_id
    return None


def online_moa_query_registry_ids() -> list[str]:
    return [reg_id for reg_id, _ in _online_moa_query_checks()]
