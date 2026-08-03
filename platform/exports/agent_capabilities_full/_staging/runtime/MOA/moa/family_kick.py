"""家族长踢出成员（removeMember）+ 角色/归属校验。"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .client import MoaClient, extract_ec_em_result, extract_inner_result, outer_success
from .family_detail import _query_admin_family_info, _query_user_joined_family
from .payload import load_payload


def needs_family_kick(args: argparse.Namespace) -> bool:
    return bool(
        getattr(args, "family_kick_operator_id", None)
        or getattr(args, "family_kick_remote_id", None)
    )


def _resolve_family_id(client: MoaClient, args: argparse.Namespace, operator_id: str) -> str:
    explicit = str(getattr(args, "family_id", None) or "").strip()
    if explicit:
        return explicit
    joined = _query_user_joined_family(client, args, operator_id)
    family_id = str(joined.get("familyId") or "").strip()
    if not joined.get("joinedFamily") or not family_id:
        raise ValueError(f"操作人 {operator_id} 未加入任何家族，无法踢人")
    return family_id


def validate_family_kick(
    client: MoaClient,
    args: argparse.Namespace,
    *,
    operator_id: str,
    remote_id: str,
    family_id: str,
) -> dict[str, Any]:
    if operator_id == remote_id:
        raise ValueError("操作人与被踢人不能是同一 userId")

    admin = _query_admin_family_info(family_id)
    items = admin.get("items")
    if not isinstance(items, list) or not items:
        raise RuntimeError(f"Admin 未查到家族 {family_id}")
    family_info = items[0] if isinstance(items[0], dict) else {}
    owner_id = str(family_info.get("familyOwnerId") or "").strip()
    if not owner_id:
        raise RuntimeError(f"家族 {family_id} 缺少 familyOwnerId")
    if operator_id != owner_id:
        raise ValueError(
            f"操作人必须是家族长：operator={operator_id} owner={owner_id} familyId={family_id}"
        )
    if remote_id == owner_id:
        raise ValueError(f"不能踢出家族长：remoteId={remote_id} familyId={family_id}")

    remote_joined = _query_user_joined_family(client, args, remote_id)
    if not remote_joined.get("joinedFamily"):
        raise ValueError(f"被踢人 {remote_id} 当前不在任何家族")
    remote_family = str(remote_joined.get("familyId") or "").strip()
    if remote_family != family_id:
        raise ValueError(
            f"被踢人必须在本家族：remoteId={remote_id} remoteFamily={remote_family} "
            f"expectFamily={family_id}"
        )

    return {
        "familyId": family_id,
        "operatorId": operator_id,
        "remoteId": remote_id,
        "familyOwnerId": owner_id,
        "familyName": family_info.get("familyName"),
        "validated": True,
    }


def run_family_kick_member(args: argparse.Namespace, client: MoaClient) -> int:
    operator_id = str(getattr(args, "family_kick_operator_id", None) or "").strip()
    remote_id = str(getattr(args, "family_kick_remote_id", None) or "").strip()
    if not operator_id:
        print("执行失败: 须提供 --family-kick-operator-id（家族长 userId）", file=sys.stderr)
        return 2
    if not remote_id:
        print("执行失败: 须提供 --family-kick-remote-id（被踢成员 userId）", file=sys.stderr)
        return 2

    try:
        family_id = _resolve_family_id(client, args, operator_id)
        check = validate_family_kick(
            client,
            args,
            operator_id=operator_id,
            remote_id=remote_id,
            family_id=family_id,
        )
        args.family_id = family_id

        payload = load_payload(args)
        print(
            f"踢出家族成员 familyId={family_id} operator={operator_id} remote={remote_id}",
            file=sys.stderr,
        )
        if getattr(args, "dump_payload", False):
            print("最终 payload（不含 cookie）:", file=sys.stderr)
            print(json.dumps(payload, ensure_ascii=False, indent=2), file=sys.stderr)

        from .cli import _print_request_info, _print_response

        _print_request_info(args, payload)
        resp = client.post(payload)
        _print_response(args, resp)

        ec, em, _ = extract_ec_em_result(resp)
        if not outer_success(ec):
            print(f"MOA 返回失败: ec={ec}, em={em or 'ec!=0'}", file=sys.stderr)
            return 3

        inner_ec, inner_em, inner_result = extract_inner_result(resp)
        if inner_ec != 0:
            print(f"业务返回失败: ec={inner_ec}, em={inner_em}", file=sys.stderr)
            return 4

        kicked = False
        if isinstance(inner_result, bool):
            kicked = inner_result
        elif isinstance(inner_result, dict):
            kicked = bool(
                inner_result.get("data") if "data" in inner_result else inner_result.get("success")
            )

        after = _query_user_joined_family(client, args, remote_id)
        summary = {
            **check,
            "api": "removeMember",
            "kicked": kicked,
            "remoteAfter": after,
        }
        if after.get("joinedFamily") and str(after.get("familyId")) == family_id:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            print("警告: 踢出后被踢人仍在本家族", file=sys.stderr)
            return 5
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"执行失败: {exc}", file=sys.stderr)
        return 1
