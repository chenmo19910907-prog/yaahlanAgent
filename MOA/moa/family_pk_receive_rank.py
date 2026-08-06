"""家族 PK 收礼日榜：查询并排除已解散家族、顺延名次。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .client import MoaClient
from .family import parse_family_create_time_summary
from .params import json_param, set_family_create_time_query_params
from .payload import load_payload

_CREATE_TIME_TEMPLATE = moa_template("家族-查询创建时间.json")
_RANK_TEMPLATE = moa_template("家族PK-查询收礼日榜.json")

from .project_paths import (
    admin_execute_path,
    get_repo_root,
    gift_module_dir,
    moa_execute_path,
    moa_template,
)



def _clone_args(args: argparse.Namespace, **overrides: Any) -> argparse.Namespace:
    data = vars(args).copy()
    data.update(overrides)
    return argparse.Namespace(**data)


def _normalize_rank_item(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    family_id = item.get("familyId")
    if family_id is None:
        return None
    return {
        "rank": item.get("rank"),
        "familyId": str(family_id).strip(),
        "receiveScore": item.get("receiveScore"),
    }


def _parse_raw_rank_list(inner_result: Any) -> list[dict[str, Any]]:
    raw_list: Any = None
    if isinstance(inner_result, dict):
        data = inner_result.get("data")
        if isinstance(data, dict):
            raw_list = data.get("rankList")
        if raw_list is None and isinstance(inner_result.get("result"), dict):
            nested_data = inner_result["result"].get("data")
            if isinstance(nested_data, dict):
                raw_list = nested_data.get("rankList")
        if raw_list is None:
            raw_list = inner_result.get("rankList")
    elif isinstance(inner_result, list):
        raw_list = inner_result

    if not isinstance(raw_list, list):
        raise RuntimeError("收礼日榜返回缺少 rankList")

    items: list[dict[str, Any]] = []
    for item in raw_list:
        normalized = _normalize_rank_item(item)
        if normalized and normalized["familyId"]:
            items.append(normalized)
    items.sort(key=lambda x: (x.get("rank") is None, x.get("rank") or 0))
    return items


def adjust_receive_rank_excluding_dissolved(
    rank_list: list[dict[str, Any]],
    dissolved_family_ids: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    excluded: list[dict[str, Any]] = []
    effective: list[dict[str, Any]] = []
    for item in rank_list:
        family_id = str(item["familyId"])
        if family_id in dissolved_family_ids:
            excluded.append(
                {
                    "familyId": family_id,
                    "rawRank": item.get("rank"),
                    "receiveScore": item.get("receiveScore"),
                    "reason": "dissolved",
                }
            )
            continue
        effective.append(
            {
                "rank": len(effective) + 1,
                "familyId": family_id,
                "receiveScore": item.get("receiveScore"),
                "rawRank": item.get("rank"),
            }
        )
    return effective, excluded


def _is_family_dissolved(client: MoaClient, args: argparse.Namespace, family_id: str) -> bool:
    payload = load_payload(
        _clone_args(
            args,
            payload_file=str(_CREATE_TIME_TEMPLATE),
            family_id=family_id,
            family_query_create_time=True,
        )
    )
    set_family_create_time_query_params(payload, family_id)
    inner_result = client.post_expect_inner_ok(payload, action=f"查询家族创建时间 {family_id}")
    summary = parse_family_create_time_summary(family_id, inner_result)
    return bool(summary.get("dissolved"))


def _query_raw_receive_rank(
    client: MoaClient,
    args: argparse.Namespace,
    date: str,
    limit: int,
) -> list[dict[str, Any]]:
    body = {"lang": "zh", "date": date, "limit": limit}
    payload = load_payload(_clone_args(args, payload_file=str(_RANK_TEMPLATE)))
    payload["method"] = "queryReceiveDailyRankForTest"
    payload["params"] = [json_param(body)]
    inner_result = client.post_expect_inner_ok(payload, action="查询家族收礼日榜")
    return _parse_raw_rank_list(inner_result)


def build_receive_rank_summary(
    client: MoaClient,
    args: argparse.Namespace,
    date: str,
    limit: int,
    *,
    exclude_dissolved: bool = True,
) -> dict[str, Any]:
    raw_rank_list = _query_raw_receive_rank(client, args, date, limit)
    summary: dict[str, Any] = {
        "date": date,
        "limit": limit,
        "rawCount": len(raw_rank_list),
        "excludeDissolved": exclude_dissolved,
        "rawRankList": raw_rank_list,
    }
    if not exclude_dissolved:
        summary["rankList"] = [
            {
                "rank": item.get("rank"),
                "familyId": item["familyId"],
                "receiveScore": item.get("receiveScore"),
                "rawRank": item.get("rank"),
            }
            for item in raw_rank_list
        ]
        summary["effectiveCount"] = len(raw_rank_list)
        summary["excludedDissolved"] = []
        return summary

    dissolved_ids: set[str] = set()
    for item in raw_rank_list:
        family_id = item["familyId"]
        if _is_family_dissolved(client, args, family_id):
            dissolved_ids.add(family_id)

    effective, excluded = adjust_receive_rank_excluding_dissolved(raw_rank_list, dissolved_ids)
    summary["effectiveCount"] = len(effective)
    summary["excludedDissolved"] = excluded
    summary["rankList"] = effective
    return summary


def needs_family_pk_query_receive_rank(args: argparse.Namespace) -> bool:
    return bool(getattr(args, "family_pk_query_receive_rank", False))


def run_family_pk_query_receive_rank(args: argparse.Namespace, client: MoaClient) -> int:
    date = str(getattr(args, "family_pk_date", "") or "").strip()
    if not date:
        print("查询收礼日榜时，必须提供 --family-pk-date", file=sys.stderr)
        return 2
    limit = getattr(args, "family_pk_limit", None)
    if limit is None:
        limit = 500
    if limit <= 0 or limit > 500:
        print("--family-pk-limit 须在 1~500 之间", file=sys.stderr)
        return 2

    exclude_dissolved = not bool(getattr(args, "family_pk_include_dissolved", False))
    try:
        summary = build_receive_rank_summary(
            client,
            args,
            date,
            limit,
            exclude_dissolved=exclude_dissolved,
        )
    except (ValueError, RuntimeError) as exc:
        print(f"执行失败: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0
