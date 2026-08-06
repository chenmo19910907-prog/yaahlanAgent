"""家族详情：MOA 成员/归属 + Admin 家族管理查询。"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from .client import MoaClient
from .family import parse_family_members_summary, parse_user_joined_family_summary
from .payload import load_payload

_MEMBERS_TEMPLATE = moa_template("家族-查询成员userId.json")
_JOINED_TEMPLATE = moa_template("家族-按userId查家族id.json")

from .project_paths import (
    admin_execute_path,
    get_repo_root,
    gift_module_dir,
    moa_execute_path,
    moa_template,
)



def _clone_args(args: argparse.Namespace, **overrides: Any) -> argparse.Namespace:
    data = vars(args).copy()
    # 清空可能劫持 load_payload 路由的 family kick 参数
    data["family_kick_operator_id"] = None
    data["family_kick_remote_id"] = None
    data["family_leave_user_id"] = None
    data["family_delete"] = False
    data["family_query_members"] = False
    data["family_query_create_time"] = False
    data["family_query_joined_user_id"] = None
    data["family_query_current"] = False
    data.update(overrides)
    return argparse.Namespace(**data)


def _query_admin_family_info(family_id: str) -> dict[str, Any]:
    family_id = str(family_id).strip()
    if not family_id:
        raise ValueError("family_id 不能为空")

    cmd = [
        "python3",
        str(admin_execute_path()),
        "--query-family",
        "--family-id",
        family_id,
    ]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(get_repo_root()),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"Admin 查询家族超时: {exc}") from exc

    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    if proc.returncode != 0:
        tail = stderr[-500:] if stderr else stdout[-500:]
        raise RuntimeError(f"Admin 查询家族失败（exit={proc.returncode}）{': ' + tail if tail else ''}")

    if not stdout:
        raise RuntimeError("Admin 查询家族无 stdout")

    try:
        body = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Admin 返回非 JSON: {stdout[:200]}") from exc

    if not isinstance(body, dict):
        raise RuntimeError("Admin 返回须为 object")

    items = body.get("items")
    if not isinstance(items, list) or not items:
        raise RuntimeError(f"Admin 未查到家族 {family_id}")

    return body


def _query_family_members(client: MoaClient, args: argparse.Namespace, family_id: str) -> dict[str, Any]:
    payload = load_payload(
        _clone_args(
            args,
            payload_file=str(_MEMBERS_TEMPLATE),
            family_id=family_id,
            family_query_members=True,
        )
    )
    inner_result = client.post_expect_inner_ok(payload, action="查询家族成员")
    return parse_family_members_summary(family_id, inner_result)


def _query_user_joined_family(client: MoaClient, args: argparse.Namespace, user_id: str) -> dict[str, Any]:
    payload = load_payload(
        _clone_args(
            args,
            payload_file=str(_JOINED_TEMPLATE),
            family_query_joined_user_id=user_id,
        )
    )
    inner_result = client.post_expect_inner_ok(payload, action="查询用户所属家族")
    return parse_user_joined_family_summary(user_id, inner_result)


def build_family_detail_by_family_id(
    client: MoaClient,
    args: argparse.Namespace,
    family_id: str,
) -> dict[str, Any]:
    admin_summary = _query_admin_family_info(family_id)
    members_summary = _query_family_members(client, args, family_id)
    admin_item = admin_summary["items"][0] if admin_summary.get("items") else {}
    return {
        "familyId": str(family_id),
        "adminFamilyInfo": admin_item,
        "memberCount": members_summary.get("memberCount", 0),
        "memberUserIds": members_summary.get("memberUserIds", []),
    }


def build_family_detail_by_user_id(
    client: MoaClient,
    args: argparse.Namespace,
    user_id: str,
) -> dict[str, Any]:
    joined = _query_user_joined_family(client, args, user_id)
    if not joined.get("joinedFamily") or not joined.get("familyId"):
        return {
            "userId": str(user_id).strip(),
            "joinedFamily": False,
            "familyId": None,
            "adminFamilyInfo": None,
            "memberCount": 0,
            "memberUserIds": [],
        }

    detail = build_family_detail_by_family_id(client, args, str(joined["familyId"]))
    detail["userId"] = str(user_id).strip()
    detail["joinedFamily"] = True
    return detail


def needs_family_detail(args: argparse.Namespace) -> bool:
    return bool(getattr(args, "family_detail", False) and args.family_id)


def needs_family_detail_by_user(args: argparse.Namespace) -> bool:
    return getattr(args, "family_detail_by_user_id", None) is not None


def run_family_detail(args: argparse.Namespace, client: MoaClient) -> int:
    try:
        if needs_family_detail_by_user(args):
            summary = build_family_detail_by_user_id(client, args, args.family_detail_by_user_id)
        elif needs_family_detail(args):
            summary = build_family_detail_by_family_id(client, args, args.family_id)
        else:
            raise ValueError("未指定家族详情查询参数")
    except (ValueError, RuntimeError) as exc:
        print(f"执行失败: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0
