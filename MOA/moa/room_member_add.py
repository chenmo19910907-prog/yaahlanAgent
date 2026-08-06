"""房间成员快速添加（joinMember backdoor）。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .client import MoaClient, extract_ec_em_result, extract_inner_result, outer_success
from .config import build_room_member_is_member_expr, build_room_member_join_expr
from .params import set_backdoor_execute_expr
from .payload import load_payload

_TEMPLATE = moa_template("房间成员-快速添加.json")

from .project_paths import (
    admin_execute_path,
    get_repo_root,
    gift_module_dir,
    moa_execute_path,
    moa_template,
)



def needs_room_member_add(args: argparse.Namespace) -> bool:
    return bool(
        getattr(args, "room_member_room_id", None) or getattr(args, "room_member_user_id", None)
    )


def _backdoor_payload(expr: str) -> dict[str, Any]:
    with open(_TEMPLATE, "r", encoding="utf-8") as f:
        payload = json.load(f)
    payload.pop("_registry", None)
    payload["url"] = "/service/voga-mts-room-backdoor"
    payload["method"] = "execute"
    set_backdoor_execute_expr(payload, expr)
    return payload


def _query_is_member(client: MoaClient, room_id: str, user_id: str) -> bool:
    payload = _backdoor_payload(build_room_member_is_member_expr(room_id, user_id))
    inner = client.post_expect_inner_ok(payload, action="查询是否房间成员")
    if isinstance(inner, bool):
        return inner
    if isinstance(inner, str):
        return inner.strip().lower() in ("true", "1", "yes")
    return bool(inner)


def run_room_member_add(args: argparse.Namespace, client: MoaClient) -> int:
    room_id = str(getattr(args, "room_member_room_id", None) or "").strip()
    user_id = str(getattr(args, "room_member_user_id", None) or "").strip()
    area = str(getattr(args, "room_member_area", None) or "MENA").strip().upper()
    if not room_id:
        print("执行失败: 须提供 --room-member-room-id", file=sys.stderr)
        return 2
    if not user_id:
        print("执行失败: 须提供 --room-member-user-id", file=sys.stderr)
        return 2

    try:
        before = _query_is_member(client, room_id, user_id)
        if not args.payload_file and not args.payload:
            args.payload_file = str(_TEMPLATE)
        payload = load_payload(args)
        print(
            f"快速添加房间成员 roomId={room_id} userId={user_id} area={area} beforeMember={before}",
            file=sys.stderr,
        )
        if getattr(args, "dump_payload", False):
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

        joined_api = False
        if isinstance(inner_result, bool):
            joined_api = inner_result
        elif isinstance(inner_result, str):
            joined_api = inner_result.strip().lower() in ("true", "1", "yes")

        after = _query_is_member(client, room_id, user_id)
        summary: dict[str, Any] = {
            "roomId": room_id,
            "userId": user_id,
            "area": area,
            "api": "RoomMemberService.joinMember",
            "tunnelAlign": {
                "apply": "/yaahlan/room/member/apply",
                "agree": "/yaahlan/room/member/agree",
                "sample": {
                    "applicant": "100379555",
                    "owner": "100486375",
                    "roomId": "31668628",
                },
            },
            "beforeMember": before,
            "joinResult": joined_api,
            "afterMember": after,
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        if not after:
            print("警告: joinMember 后 isRoomMember=false", file=sys.stderr)
            return 5
        return 0
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"执行失败: {exc}", file=sys.stderr)
        return 1
