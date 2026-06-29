"""用户关系 MOA（addUserRelation 关注 / 互关成为好友）。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from .client import MoaClient, extract_ec_em_result, extract_inner_result, outer_success
from .params import set_user_follow_params
from .payload import apply_top_level_overrides
from .paths import templates_dir


def _follow_pair(args: argparse.Namespace) -> tuple[str, str]:
    uid = str(args.follow_uid or "").strip()
    remote_uid = str(args.follow_remote_uid or "").strip()
    if not uid or not remote_uid:
        raise ValueError("关注好友须同时提供 --follow-uid 与 --follow-remote-uid")
    if uid == remote_uid:
        raise ValueError("uid 与 remoteUid 不能相同")
    return uid, remote_uid


def _load_follow_payload(args: argparse.Namespace, uid: str, remote_uid: str) -> dict[str, Any]:
    template_path = os.path.join(templates_dir(), "用户-关注好友.json")
    with open(template_path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, dict):
        raise ValueError("用户-关注好友.json 必须是 JSON object")
    payload.pop("_registry", None)
    apply_top_level_overrides(payload, args)
    set_user_follow_params(payload, uid, remote_uid)
    return payload


def _post_follow(client: MoaClient, payload: dict[str, Any], *, label: str) -> dict[str, Any]:
    print(label, file=sys.stderr)
    resp = client.post(payload)
    ec, em, _ = extract_ec_em_result(resp)
    if not outer_success(ec):
        print(f"MOA 返回失败: ec={ec}, em={em or 'ec!=0'}", file=sys.stderr)
        raise RuntimeError(f"MOA 外层失败 ec={ec}")
    inner_ec, inner_em, _ = extract_inner_result(resp)
    if inner_ec != 0:
        print(f"业务返回失败: ec={inner_ec}, em={inner_em}", file=sys.stderr)
        raise RuntimeError(f"业务失败 ec={inner_ec}, em={inner_em}")
    return resp


def run_mutual_follow(args: argparse.Namespace, client: MoaClient) -> int:
    uid, remote_uid = _follow_pair(args)
    first = _load_follow_payload(args, uid, remote_uid)
    second = _load_follow_payload(args, remote_uid, uid)
    results: list[dict[str, Any]] = []
    results.append(_post_follow(client, first, label=f"互关 1/2: {uid} -> {remote_uid}"))
    results.append(_post_follow(client, second, label=f"互关 2/2: {remote_uid} -> {uid}"))
    print(
        json.dumps(
            {"mutualFollow": True, "uid": uid, "remoteUid": remote_uid, "responses": results},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0
