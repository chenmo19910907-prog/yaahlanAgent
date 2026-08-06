"""家族 PK 成员贡献列表（getFamilyPkUserList），支持自动翻页拉全量。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .client import MoaClient, extract_ec_em_result, extract_inner_result, outer_success
from .params import set_family_pk_member_list_params
from .payload import load_payload

_TEMPLATE = moa_template("家族PK-成员贡献列表.json")
_MAX_PAGES = 100

from .project_paths import (
    admin_execute_path,
    get_repo_root,
    gift_module_dir,
    moa_execute_path,
    moa_template,
)



def needs_family_pk_member_list(args: argparse.Namespace) -> bool:
    return bool(
        getattr(args, "family_pk_member_list_user_id", None)
        and getattr(args, "family_pk_member_list_family_id", None)
    )


def _extract_page_data(resp: dict[str, Any]) -> dict[str, Any]:
    ec, em, _ = extract_ec_em_result(resp)
    if not outer_success(ec):
        raise RuntimeError(f"MOA 返回失败: ec={ec}, em={em or 'ec!=0'}")
    inner_ec, inner_em, inner_result = extract_inner_result(resp)
    if inner_ec != 0:
        raise RuntimeError(f"业务失败: ec={inner_ec}, em={inner_em}")
    if isinstance(inner_result, dict) and isinstance(inner_result.get("data"), dict):
        return inner_result["data"]
    if isinstance(inner_result, dict):
        return inner_result
    raise RuntimeError("成员贡献列表返回缺少 data")


def _clone_args(args: argparse.Namespace, **overrides: Any) -> argparse.Namespace:
    data = vars(args).copy()
    data.update(overrides)
    return argparse.Namespace(**data)


def run_family_pk_member_list(args: argparse.Namespace, client: MoaClient) -> int:
    user_id = str(getattr(args, "family_pk_member_list_user_id", None) or "").strip()
    family_id = str(getattr(args, "family_pk_member_list_family_id", None) or "").strip()
    date = str(getattr(args, "family_pk_member_list_date", None) or "").strip()
    area = str(getattr(args, "family_pk_member_list_area", None) or "MENA").strip().upper()
    limit = int(getattr(args, "family_pk_member_list_limit", None) or 20)
    offset = int(getattr(args, "family_pk_member_list_offset", None) or 0)
    fetch_all = not bool(getattr(args, "family_pk_member_list_single_page", False))

    if not user_id or not family_id:
        print("执行失败: 须提供 --family-pk-member-list-user-id 与 --family-pk-member-list-family-id", file=sys.stderr)
        return 2

    if not args.payload_file and not args.payload:
        args.payload_file = str(_TEMPLATE)
    base_payload = load_payload(_clone_args(args, payload_file=str(_TEMPLATE)))

    if not date:
        first = (base_payload.get("params") or [{}])[0]
        if isinstance(first, dict) and isinstance(first.get("value"), dict):
            date = str(first["value"].get("date") or "").strip()
    if not date:
        print("执行失败: 须提供 --family-pk-member-list-date", file=sys.stderr)
        return 2

    all_members: list[dict[str, Any]] = []
    first_page: dict[str, Any] | None = None
    page = 0
    cur_offset = offset

    print(
        f"家族PK成员贡献列表 userId={user_id} familyId={family_id} date={date} "
        f"mode={'all' if fetch_all else 'single-page'} limit={limit}",
        file=sys.stderr,
    )

    while page < _MAX_PAGES:
        payload = json.loads(json.dumps(base_payload))
        set_family_pk_member_list_params(
            payload,
            user_id=user_id,
            family_id=family_id,
            date=date,
            offset=cur_offset,
            limit=limit,
            area=area,
        )
        resp = client.post(payload)
        data = _extract_page_data(resp)
        if first_page is None:
            first_page = data
        batch = data.get("memberList") or []
        if not isinstance(batch, list):
            raise RuntimeError("memberList 不是数组")
        all_members.extend(batch)
        page += 1
        has_next = bool(data.get("hasNext"))
        next_offset = data.get("nextOffset")
        print(
            f"page={page} offset={cur_offset} batch={len(batch)} total={len(all_members)} hasNext={has_next}",
            file=sys.stderr,
        )
        if not fetch_all or not has_next:
            break
        if next_offset is None:
            cur_offset += limit
        else:
            cur_offset = int(next_offset)

    if fetch_all and page >= _MAX_PAGES:
        print(f"WARN: 已达最大翻页次数 {_MAX_PAGES}，可能未拉全", file=sys.stderr)

    summary = {
        "userId": user_id,
        "familyId": family_id,
        "date": date,
        "fetchAll": fetch_all,
        "pageCount": page,
        "memberCount": len(all_members),
        "hasNext": False if fetch_all else bool((first_page or {}).get("hasNext")),
        "pkStatus": (first_page or {}).get("pkStatus"),
        "pkResult": (first_page or {}).get("pkResult"),
        "myFamily": (first_page or {}).get("myFamily"),
        "userInfo": (first_page or {}).get("userInfo"),
        "minRewardPk": (first_page or {}).get("minRewardPk"),
        "titleIcon": (first_page or {}).get("titleIcon"),
        "memberList": all_members,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0
