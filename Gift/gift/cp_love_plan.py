"""CP 爱意值送礼规划：最少 HTTP 次数达成目标增量（1 钻 = 1 爱意值）。"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from gift.send_stage import StageGiftError, query_gift

_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "cp_love_gift.json"

# 单次 /v2/gift/send 允许的最大 num（爱意值造数场景实测可至 50 万）
DEFAULT_MAX_NUM_PER_SEND = 500_000

# 兼容旧引用
DEFAULT_CANDIDATE_GIFT_IDS: tuple[str, ...] = ("2005000233",)


@dataclass(frozen=True)
class CpLoveGiftConfig:
    default_gift_id: str
    default_gift_name: str
    display_name: str
    candidate_gift_ids: tuple[str, ...]
    forbidden_gift_ids: frozenset[str]


@dataclass(frozen=True)
class CpLoveSendBatch:
    gift_id: str
    num: int
    price: int
    diamond_cost: int


@dataclass(frozen=True)
class CpLoveGiftPlan:
    delta: int
    gift_id: str
    product_name: str
    price: int
    send_count: int
    total_diamond_cost: int
    batches: tuple[CpLoveSendBatch, ...]
    note: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "delta": self.delta,
            "giftId": self.gift_id,
            "productName": self.product_name,
            "price": self.price,
            "sendCount": self.send_count,
            "totalDiamondCost": self.total_diamond_cost,
            "batches": [
                {
                    "giftId": b.gift_id,
                    "num": b.num,
                    "price": b.price,
                    "diamondCost": b.diamond_cost,
                }
                for b in self.batches
            ],
            "note": self.note,
        }


@lru_cache(maxsize=1)
def load_cp_love_gift_config() -> CpLoveGiftConfig:
    if _CONFIG_PATH.is_file():
        raw = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            candidates = raw.get("candidateGiftIds") or list(DEFAULT_CANDIDATE_GIFT_IDS)
            forbidden = raw.get("forbiddenGiftIds") or ["2005004730"]
            return CpLoveGiftConfig(
                default_gift_id=str(raw.get("defaultGiftId") or "2005000233"),
                default_gift_name=str(raw.get("defaultGiftName") or "Rose"),
                display_name=str(raw.get("displayName") or "Rose"),
                candidate_gift_ids=tuple(str(x) for x in candidates if str(x).strip()),
                forbidden_gift_ids=frozenset(str(x) for x in forbidden if str(x).strip()),
            )
    return CpLoveGiftConfig(
        default_gift_id="2005000233",
        default_gift_name="Rose",
        display_name="Rose",
        candidate_gift_ids=DEFAULT_CANDIDATE_GIFT_IDS,
        forbidden_gift_ids=frozenset({"2005004730", "2005001776", "2005001778", "2005001774"}),
    )


def _price_int(meta: dict[str, Any]) -> int | None:
    price = meta.get("price")
    if price is None:
        return None
    try:
        p = int(float(price))
    except (TypeError, ValueError):
        return None
    return p if p > 0 else None


def _build_batches(
    gift_id: str,
    price: int,
    delta: int,
    *,
    max_num_per_send: int,
) -> tuple[CpLoveSendBatch, ...]:
    if delta <= 0:
        return ()
    per_send_cap = max(1, max_num_per_send)
    max_love_per_send = price * per_send_cap
    batches: list[CpLoveSendBatch] = []
    remaining = delta
    while remaining > 0:
        if remaining <= max_love_per_send:
            num = math.ceil(remaining / price)
            batches.append(
                CpLoveSendBatch(
                    gift_id=gift_id,
                    num=num,
                    price=price,
                    diamond_cost=num * price,
                )
            )
            break
        batches.append(
            CpLoveSendBatch(
                gift_id=gift_id,
                num=per_send_cap,
                price=price,
                diamond_cost=per_send_cap * price,
            )
        )
        remaining -= per_send_cap * price
    return tuple(batches)


def _plan_rank(plan: CpLoveGiftPlan, *, default_gift_id: str) -> tuple[int, int, int, int]:
    overshoot = plan.total_diamond_cost - plan.delta
    first_num = plan.batches[0].num if plan.batches else 0
    default_bias = 0 if plan.gift_id == default_gift_id else 1
    return (plan.send_count, first_num, overshoot, default_bias)


def plan_cp_love_gift(
    delta: int,
    *,
    candidate_gift_ids: tuple[str, ...] | None = None,
    max_num_per_send: int = DEFAULT_MAX_NUM_PER_SEND,
    gift_id: str | None = None,
) -> CpLoveGiftPlan:
    """规划最少送礼次数；在 Rose 面板礼物中选单价合适者，使 num 尽量小。"""
    if delta <= 0:
        raise ValueError("delta 须 > 0")
    if max_num_per_send <= 0:
        raise ValueError("max_num_per_send 须 > 0")

    cfg = load_cp_love_gift_config()
    if gift_id:
        ids = (str(gift_id).strip(),)
    else:
        ids = candidate_gift_ids or cfg.candidate_gift_ids
    ids = tuple(gid for gid in ids if gid and gid not in cfg.forbidden_gift_ids)
    if not ids:
        raise StageGiftError("cp_love_plan", "无可用 Rose 候选礼物")

    best: CpLoveGiftPlan | None = None
    errors: list[str] = []

    for gid in ids:
        try:
            meta = query_gift(gid)
        except StageGiftError as exc:
            errors.append(f"{gid}: {exc.message}")
            continue
        price = _price_int(meta)
        if price is None:
            errors.append(f"{gid}: 无有效 price")
            continue
        batches = _build_batches(gid, price, delta, max_num_per_send=max_num_per_send)
        if not batches:
            continue
        total_cost = sum(b.diamond_cost for b in batches)
        plan = CpLoveGiftPlan(
            delta=delta,
            gift_id=gid,
            product_name=str(meta.get("productName") or ""),
            price=price,
            send_count=len(batches),
            total_diamond_cost=total_cost,
            batches=batches,
            note=(
                f"面板礼 Rose（{meta.get('productName')}）：单次 num={batches[0].num}，共 {len(batches)} 次 HTTP"
                if len(batches) == 1
                else f"Rose 分 {len(batches)} 次，每批最多 num={max_num_per_send}"
            ),
        )
        if best is None or _plan_rank(plan, default_gift_id=cfg.default_gift_id) < _plan_rank(
            best, default_gift_id=cfg.default_gift_id
        ):
            best = plan

    if best is None:
        detail = "; ".join(errors) if errors else "无候选礼物"
        raise StageGiftError("cp_love_plan", f"无法规划 CP 爱意值送礼: {detail}")
    return best
