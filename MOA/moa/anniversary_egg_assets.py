"""砸蛋前后资产快照：礼物背包（个数）、个人装扮（天数）、活动积分。"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Callable

from .project_paths import (
    admin_execute_path,
    get_repo_root,
    gift_module_dir,
    moa_execute_path,
    moa_template,
)


from moa.gift_panel_backpack import fetch_gift_panel_backpack_via_moa

_PERMANENT_END_MS = 7258089599000
_MS_PER_DAY = 86_400_000
# 砸金蛋常见装扮类型（queryOwnPropList；propPackageList 不含已拥有装扮）
_EGG_OWNED_PROP_TYPE_CODES: tuple[str, ...] = (
    "10043",  # 头框（如 السلطان $）
    "10045",  # 座驾
    "10047",  # 进房特效
    "10072",  # 房间列表背景图
)
_USER_PROP_SERVICE = "/service/mdp-prop/user-prop-api-service-test"


def backpack_gift_counts(backpack_gifts: list[dict[str, Any]]) -> dict[str, int]:
    """礼物背包：giftId → package.remain（个数）。"""
    counts: dict[str, int] = {}
    for item in backpack_gifts:
        if not isinstance(item, dict):
            continue
        gift_id = str(item.get("id") or item.get("bid") or "").strip()
        if not gift_id:
            continue
        try:
            remain = int(item.get("remain") or 0)
        except (TypeError, ValueError):
            remain = 0
        counts[gift_id] = counts.get(gift_id, 0) + remain
    return counts


def _to_epoch_ms(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        ms = int(value)
    except (TypeError, ValueError):
        return None
    if ms <= 0:
        return None
    if ms < 1_000_000_000_000:
        ms *= 1000
    return ms


def _prop_end_time_ms(item: dict[str, Any]) -> int | None:
    for key in ("propUseEndTime", "expireTime", "expireAt", "expire", "endTime"):
        ms = _to_epoch_ms(item.get(key))
        if ms is not None:
            return ms
    return None


def prop_state_from_list(backpack_props: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """个人装扮：propId → 到期时间与 validityPeriod（用于算下发天数）。"""
    state: dict[str, dict[str, Any]] = {}
    for item in backpack_props:
        if not isinstance(item, dict):
            continue
        prop_id = str(
            item.get("propId") or item.get("productId") or item.get("id") or ""
        ).strip()
        if not prop_id:
            continue
        validity = item.get("validityPeriod")
        try:
            validity_i = int(validity) if validity not in (None, "") else None
        except (TypeError, ValueError):
            validity_i = None
        end_ms = _prop_end_time_ms(item)
        prev = state.get(prop_id) or {}
        prev_end = prev.get("endTimeMs")
        if end_ms is not None and (prev_end is None or end_ms > int(prev_end)):
            prev_end = end_ms
        state[prop_id] = {
            "endTimeMs": prev_end,
            "validityPeriod": validity_i if validity_i is not None else prev.get("validityPeriod"),
        }
    return state


def sum_inventory_counts(counts: dict[str, int], prize_ids: set[str]) -> int:
    if not prize_ids:
        return sum(int(v) for v in counts.values())
    return sum(int(counts.get(str(pid), 0)) for pid in prize_ids)


def prop_days_added(
    before_state: dict[str, dict[str, Any]] | None,
    after_state: dict[str, dict[str, Any]] | None,
    prop_id: str,
    *,
    now_ms: int | None = None,
) -> int | None:
    """单个 propId 本次新增有效天数（对比砸蛋前后到期时间）。"""
    pid = str(prop_id or "").strip()
    if not pid:
        return None
    before = (before_state or {}).get(pid) or {}
    after = (after_state or {}).get(pid) or {}
    before_end = before.get("endTimeMs")
    after_end = after.get("endTimeMs")
    validity = after.get("validityPeriod")

    if after_end is not None and int(after_end) >= _PERMANENT_END_MS:
        return None

    if after_end is None:
        if validity not in (None, -1):
            try:
                return max(0, int(validity))
            except (TypeError, ValueError):
                return None
        return None

    after_end_i = int(after_end)
    if before_end is None:
        now = int(now_ms if now_ms is not None else time.time() * 1000)
        days_from_now = round((after_end_i - now) / _MS_PER_DAY)
        if days_from_now >= 0:
            return days_from_now
        if validity not in (None, -1):
            try:
                return max(0, int(validity))
            except (TypeError, ValueError):
                return None
        return None

    before_end_i = int(before_end)
    if before_end_i >= _PERMANENT_END_MS:
        return None
    delta_ms = after_end_i - before_end_i
    if delta_ms <= 0:
        return 0
    return max(0, round(delta_ms / _MS_PER_DAY))


def sum_prop_days_added(
    before_state: dict[str, dict[str, Any]] | None,
    after_state: dict[str, dict[str, Any]] | None,
    prop_ids: set[str],
    *,
    now_ms: int | None = None,
) -> int | None:
    if not prop_ids:
        return None
    total = 0
    any_known = False
    for pid in prop_ids:
        days = prop_days_added(
            before_state, after_state, pid, now_ms=now_ms
        )
        if days is None:
            continue
        any_known = True
        total += int(days)
    return total if any_known else None


def _call_query_own_prop_list(user_id: str, prop_type_code: str) -> list[dict[str, Any]]:
    """MOA queryOwnPropList：查用户已拥有装扮（非背包 propPackageList）。"""
    gift_dir = gift_module_dir()
    if str(gift_dir) not in sys.path:
        sys.path.insert(0, str(gift_dir))
    from gift.send_stage import StageGiftError, call_moa

    body = {
        "appId": 2005,
        "userId": str(user_id).strip(),
        "propTypeCode": str(prop_type_code).strip(),
        "lang": "en",
    }
    header_s = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
    try:
        result = call_moa(
            _USER_PROP_SERVICE,
            "queryOwnPropList",
            [body],
            headers=header_s,
        )
    except StageGiftError as exc:
        raise RuntimeError(str(exc.message)) from exc
    if not isinstance(result, dict):
        return []
    data = result.get("data")
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        items = data.get("items") or data.get("propList") or []
        return [x for x in items if isinstance(x, dict)]
    items = result.get("items") or []
    return [x for x in items if isinstance(x, dict)]


def fetch_owned_props_for_egg(
    user_id: str,
    *,
    prop_type_codes: tuple[str, ...] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """拉取砸金蛋相关已拥有装扮列表。"""
    codes = prop_type_codes or _EGG_OWNED_PROP_TYPE_CODES
    merged: list[dict[str, Any]] = []
    errors: list[str] = []
    for code in codes:
        try:
            merged.extend(_call_query_own_prop_list(user_id, code))
        except RuntimeError as exc:
            errors.append(f"{code}: {exc}")
    return merged, errors


def _merge_prop_states(*states: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for state in states:
        for pid, row in (state or {}).items():
            if not pid:
                continue
            prev = out.get(pid)
            if not prev:
                out[pid] = dict(row)
                continue
            prev_end = prev.get("endTimeMs")
            new_end = row.get("endTimeMs")
            if new_end is not None and (prev_end is None or int(new_end) > int(prev_end)):
                out[pid] = dict(row)
    return out


def _finalize_credit_check(
    check: dict[str, Any],
    *,
    expected: int,
    unverified_label: str,
) -> dict[str, Any]:
    """有预期奖励但未能比对到账 → 验收失败。"""
    exp = max(0, int(expected or 0))
    if exp <= 0:
        return check
    if check.get("ok") is not None:
        return check
    out = dict(check)
    out["ok"] = False
    out["verdictCell"] = "未核验"
    out["unverified"] = True
    out["unverifiedLabel"] = unverified_label
    return out


def snapshot_user_assets(
    user_id: str,
    room_id: str | None = None,
    *,
    include_voucher: bool = True,
) -> dict[str, Any]:
    """砸蛋前后查背包礼物个数、已拥有装扮到期、活动积分余额。"""
    user_id = str(user_id).strip()
    room_id = str(room_id or "").strip() or None
    backpack: dict[str, int] = {}
    props: dict[str, dict[str, Any]] = {}
    backpack_error = ""
    owned_prop_errors: list[str] = []
    try:
        bp = fetch_gift_panel_backpack_via_moa(
            user_id=user_id,
            room_id=room_id,
            include_props=True,
        )
        backpack = backpack_gift_counts(bp.get("backpackGifts") or [])
        package_props = prop_state_from_list(bp.get("backpackProps") or [])
        owned_items, owned_prop_errors = fetch_owned_props_for_egg(user_id)
        owned_props = prop_state_from_list(owned_items)
        props = _merge_prop_states(owned_props, package_props)
    except Exception as exc:  # noqa: BLE001
        backpack_error = str(exc)

    voucher_balance: int | None = None
    voucher_error = ""
    if include_voucher:
        try:
            from moa.anniversary_egg import query_voucher_balance

            voucher_balance = query_voucher_balance(user_id, room_id or "")
        except Exception as exc:  # noqa: BLE001
            voucher_error = str(exc)

    return {
        "userId": user_id,
        "roomId": room_id,
        "backpackGifts": backpack,
        "props": props,
        "voucherBalance": voucher_balance,
        "backpackError": backpack_error,
        "ownedPropErrors": owned_prop_errors,
        "voucherError": voucher_error,
    }


def query_balance_after_credit(
    *,
    before: int,
    expected_delta: int,
    query_fn: Callable[[], int],
    timeout_s: float = 8.0,
) -> int:
    if expected_delta <= 0:
        return query_fn()
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        bal = query_fn()
        if bal - before >= expected_delta:
            return bal
        time.sleep(0.35)
    return query_fn()


def query_inventory_after_credit(
    *,
    before_counts: dict[str, int],
    prize_ids: set[str],
    expected_delta: int,
    query_fn: Callable[[], dict[str, int]],
    timeout_s: float = 8.0,
) -> dict[str, int]:
    """背包礼物：轮询直到指定 giftId 的 remain 增量达到预期个数。"""
    if expected_delta <= 0:
        return query_fn()
    before_sum = sum_inventory_counts(before_counts, prize_ids)
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        after_counts = query_fn()
        after_sum = sum_inventory_counts(after_counts, prize_ids)
        if after_sum - before_sum >= expected_delta:
            return after_counts
        time.sleep(0.35)
    return query_fn()


def query_prop_days_after_credit(
    *,
    before_state: dict[str, dict[str, Any]],
    prop_ids: set[str],
    expected_days: int,
    query_fn: Callable[[], dict[str, dict[str, Any]]],
    timeout_s: float = 8.0,
) -> dict[str, dict[str, Any]]:
    """个人装扮：轮询直到 propId 到期时间延长达到预期天数。"""
    if expected_days <= 0:
        return query_fn()
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        after_state = query_fn()
        actual_days = sum_prop_days_added(before_state, after_state, prop_ids)
        if actual_days is not None and actual_days >= expected_days:
            return after_state
        time.sleep(0.35)
    return query_fn()


def build_smash_asset_verify_payload(
    *,
    user_id: str,
    room_id: str,
    smash: dict[str, Any],
    diamond_before: int,
    vip_before: int,
    assets_before: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """砸蛋后核验五类到账，返回可 merge 进 verify 载荷的字段。"""
    from anniversary_egg_smash_to_workbook import (
        evaluate_diamond_credit,
        expected_diamond_delta_from_smash,
        expected_package_gift_delta_from_smash,
        expected_tool_days_from_smash,
        expected_vip_exp_delta_from_smash,
        expected_voucher_delta_from_smash,
        is_package_gift_reward_item,
        is_tool_reward_item,
        prize_ids_from_smash_rewards,
    )
    from gift.send_stage import query_diamond_balance, query_vip_exp
    from moa.anniversary_egg import query_voucher_balance

    before = assets_before or snapshot_user_assets(user_id, room_id)
    backpack_before = before.get("backpackGifts") or {}
    prop_before = before.get("props") or {}
    voucher_before = before.get("voucherBalance")

    expected_backpack = expected_package_gift_delta_from_smash(smash)
    expected_prop_days = expected_tool_days_from_smash(smash)
    expected_voucher = expected_voucher_delta_from_smash(smash)
    expected_diamond = expected_diamond_delta_from_smash(smash)
    expected_vip = expected_vip_exp_delta_from_smash(smash)
    backpack_ids = prize_ids_from_smash_rewards(
        smash, matcher=is_package_gift_reward_item
    )
    prop_ids = prize_ids_from_smash_rewards(smash, matcher=is_tool_reward_item)

    def _backpack_counts() -> dict[str, int]:
        snap = snapshot_user_assets(user_id, room_id, include_voucher=False)
        return snap.get("backpackGifts") or {}

    def _prop_state() -> dict[str, dict[str, Any]]:
        snap = snapshot_user_assets(user_id, room_id, include_voucher=False)
        return snap.get("props") or {}

    if expected_backpack > 0:
        backpack_after_counts = query_inventory_after_credit(
            before_counts=backpack_before,
            prize_ids=backpack_ids,
            expected_delta=expected_backpack,
            query_fn=_backpack_counts,
        )
    else:
        backpack_after_counts = backpack_before

    if expected_prop_days > 0:
        prop_after_state = query_prop_days_after_credit(
            before_state=prop_before,
            prop_ids=prop_ids,
            expected_days=expected_prop_days,
            query_fn=_prop_state,
        )
    else:
        prop_after_state = prop_before

    diamond_after = query_balance_after_credit(
        before=diamond_before,
        expected_delta=expected_diamond,
        query_fn=lambda: query_diamond_balance(user_id),
    )
    vip_after = query_balance_after_credit(
        before=vip_before,
        expected_delta=expected_vip,
        query_fn=lambda: query_vip_exp(user_id),
    )

    if expected_voucher > 0 and voucher_before is not None:
        voucher_after = query_balance_after_credit(
            before=int(voucher_before),
            expected_delta=expected_voucher,
            query_fn=lambda: query_voucher_balance(user_id, room_id),
        )
    elif voucher_before is not None:
        voucher_after = int(voucher_before)
    else:
        voucher_after = None

    backpack_before_sum = sum_inventory_counts(backpack_before, backpack_ids)
    backpack_after_sum = sum_inventory_counts(backpack_after_counts, backpack_ids)
    backpack_check = evaluate_diamond_credit(
        before=backpack_before_sum if expected_backpack > 0 else None,
        after=backpack_after_sum if expected_backpack > 0 else None,
        expected=expected_backpack,
    )
    actual_prop_days = sum_prop_days_added(prop_before, prop_after_state, prop_ids)
    prop_check = evaluate_diamond_credit(
        before=0 if expected_prop_days > 0 else None,
        after=actual_prop_days if expected_prop_days > 0 else None,
        expected=expected_prop_days,
    )
    prop_check = _finalize_credit_check(
        prop_check, expected=expected_prop_days, unverified_label="个人装扮"
    )
    diamond_check = evaluate_diamond_credit(
        before=diamond_before,
        after=diamond_after,
        expected=expected_diamond,
    )
    vip_check = evaluate_diamond_credit(
        before=vip_before,
        after=vip_after,
        expected=expected_vip,
    )
    voucher_check = evaluate_diamond_credit(
        before=int(voucher_before)
        if voucher_before is not None and expected_voucher > 0
        else None,
        after=int(voucher_after)
        if voucher_after is not None and expected_voucher > 0
        else None,
        expected=expected_voucher,
    )
    if expected_voucher > 0 and voucher_before is None:
        voucher_check = {
            **voucher_check,
            "ok": False,
            "verdictCell": "未核验",
            "unverified": True,
            "unverifiedLabel": "积分",
            "expectedDelta": expected_voucher,
            "actualDelta": None,
            "balanceBefore": None,
            "balanceAfter": voucher_after,
        }
    else:
        voucher_check = _finalize_credit_check(
            voucher_check, expected=expected_voucher, unverified_label="积分"
        )

    payload = {
        "expectedBackpack": expected_backpack,
        "backpackBeforeSum": backpack_before_sum if expected_backpack > 0 else None,
        "backpackAfterSum": backpack_after_sum if expected_backpack > 0 else None,
        "actualBackpackDelta": backpack_check.get("actualDelta"),
        "expectedProp": expected_prop_days,
        "expectedPropDays": expected_prop_days,
        "propBeforeDays": 0 if expected_prop_days > 0 else None,
        "propAfterDays": actual_prop_days if expected_prop_days > 0 else None,
        "actualPropDaysDelta": prop_check.get("actualDelta"),
        "actualPropDelta": prop_check.get("actualDelta"),
        "expectedVoucher": expected_voucher,
        "voucherBefore": voucher_before if expected_voucher > 0 else None,
        "voucherAfter": voucher_after if expected_voucher > 0 else None,
        "actualVoucherDelta": voucher_check.get("actualDelta"),
        "diamondBefore": diamond_check.get("balanceBefore"),
        "diamondAfter": diamond_check.get("balanceAfter"),
        "expectedDiamond": diamond_check.get("expectedDelta"),
        "actualDiamondDelta": diamond_check.get("actualDelta"),
        "vipExpBefore": vip_check.get("balanceBefore"),
        "vipExpAfter": vip_check.get("balanceAfter"),
        "expectedVipExp": vip_check.get("expectedDelta"),
        "actualVipExpDelta": vip_check.get("actualDelta"),
    }
    return {
        "payload": payload,
        "backpack": backpack_check,
        "prop": prop_check,
        "diamond": diamond_check,
        "vipExp": vip_check,
        "voucher": voucher_check,
        "assetsBefore": before,
    }
