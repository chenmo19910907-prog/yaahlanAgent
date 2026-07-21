"""活动奖池（cms/activity）后台接口响应解析。"""

from __future__ import annotations

from typing import Any

from .client import http_post_json
from .config import defaults
from .guild import anchor_success

_LOTTERY_POOLS_BY_ID: dict[int, dict[str, Any]] | None = None

# getLotteryList.lotteryList[].type 约定（结合砸金蛋/商城奖池样例）
LOTTERY_PRIZE_TYPE_LABELS: dict[int, str] = {
    1: "钻石区间",
    2: "装扮/道具",
    3: "VIP经验",
    5: "背包礼物",
    7: "兑换券/代币",
}


def _normalize_lottery_prize(row: dict[str, Any]) -> dict[str, Any]:
    prize_type = row.get("type")
    try:
        prize_type_int = int(prize_type)
    except (TypeError, ValueError):
        prize_type_int = None

    return {
        "numStart": row.get("numStart"),
        "numEnd": row.get("numEnd"),
        "type": prize_type_int,
        "typeLabel": LOTTERY_PRIZE_TYPE_LABELS.get(prize_type_int)
        if prize_type_int is not None
        else None,
        "id": row.get("id"),
        "rate": row.get("rate"),
        "limit": row.get("limit"),
        "isReplace": row.get("isReplace"),
    }


def _normalize_lottery_pool(row: dict[str, Any]) -> dict[str, Any]:
    raw_prizes = row.get("lotteryList")
    prizes: list[dict[str, Any]] = []
    if isinstance(raw_prizes, list):
        prizes = [_normalize_lottery_prize(prize) for prize in raw_prizes if isinstance(prize, dict)]

    pool_id = row.get("id")
    try:
        pool_id_int = int(pool_id)
    except (TypeError, ValueError):
        pool_id_int = pool_id

    return {
        "id": pool_id_int,
        "name": row.get("name"),
        "ruleId": row.get("ruleId"),
        "prizeCount": len(prizes),
        "lotteryList": prizes,
    }


def _match_lottery_pool(
    pool: dict[str, Any],
    *,
    lottery_id: str | None,
    lottery_name: str | None,
) -> bool:
    if lottery_id:
        pool_id = str(pool.get("id") or "").strip()
        if pool_id != str(lottery_id).strip():
            return False
    if lottery_name:
        name = str(pool.get("name") or "").strip().lower()
        needle = str(lottery_name).strip().lower()
        if needle and needle not in name:
            return False
    return True


def parse_query_lottery_list_summary(
    data: Any,
    *,
    lottery_id: str | None = None,
    lottery_name: str | None = None,
) -> dict[str, Any]:
    if not isinstance(data, list):
        raise RuntimeError("无法解析奖池配置 data（不是 array）")

    pools = [_normalize_lottery_pool(row) for row in data if isinstance(row, dict)]
    filtered = [
        pool
        for pool in pools
        if _match_lottery_pool(pool, lottery_id=lottery_id, lottery_name=lottery_name)
    ]

    return {
        "totalPools": len(pools),
        "returnedCount": len(filtered),
        "lotteryIdFilter": str(lottery_id).strip() if lottery_id else None,
        "lotteryNameFilter": str(lottery_name).strip() if lottery_name else None,
        "pools": filtered,
    }


def fetch_lottery_pools_by_id(*, force_refresh: bool = False) -> dict[int, dict[str, Any]]:
    """拉取 CMS getLotteryList 全量奖池，按 lotteryId 索引。"""
    global _LOTTERY_POOLS_BY_ID
    if _LOTTERY_POOLS_BY_ID is not None and not force_refresh:
        return _LOTTERY_POOLS_BY_ID

    cfg = defaults("query_activity_lottery_list")
    base_url = str(cfg.get("baseUrl") or "https://melon-gateway-alpha-stage.immomo.com").rstrip("/")
    path = str(cfg.get("path") or "/yaahlan/cms/activity/getLotteryList")
    resp = http_post_json(f"{base_url}{path}", {}, timeout_s=30.0)
    if not anchor_success(resp):
        raise RuntimeError(
            f"getLotteryList 失败: ec={resp.get('ec')}, em={resp.get('em')}"
        )
    summary = parse_query_lottery_list_summary(resp.get("data"))
    pools = summary.get("pools")
    if not isinstance(pools, list):
        raise RuntimeError("getLotteryList pools 不是 array")

    by_id: dict[int, dict[str, Any]] = {}
    for pool in pools:
        if not isinstance(pool, dict):
            continue
        pool_id = pool.get("id")
        try:
            by_id[int(pool_id)] = pool
        except (TypeError, ValueError):
            continue
    _LOTTERY_POOLS_BY_ID = by_id
    return by_id
