#!/usr/bin/env python3
"""3周年砸金蛋测试记录追加写入钉钉 Sheet。"""

from __future__ import annotations

import asyncio
import json
import re
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any

from family_pk_tab_to_workbook import _ensure_sheet, _string_rows, _write_sheet_replace
from mse_sync_to_workbook import _sheet_cell
from mse_workbook_utils import fetch_workbook_sheets_async, node_id

DEFAULT_SHEET = "砸金蛋测试记录"

# 默认与最新 MSE activityConfig.Year3Anniversary 对齐（拉取失败时兜底）
EGG_LEVEL_LV1_TO_LV2_THRESHOLD = 30
EGG_LEVEL_LV2_TO_LV3_THRESHOLD = 50
EGG_LEVEL_LV1_EXPIRE_SECONDS = 600
EGG_LEVEL_LV2_EXPIRE_SECONDS = 300
EGG_LEVEL_LV3_EXPIRE_SECONDS = 120
MYSTERY_USER_GUARANTEE_MOD = 50
MYSTERY_ROOM_GUARANTEE_MOD = 100
MYSTERY_PLATFORM_GUARANTEE_MOD = 150

_ACTIVITY_RULES_CACHE: dict[str, Any] | None = None


def load_activity_rules(*, force_refresh: bool = False) -> dict[str, Any]:
    """读取砸蛋等级门槛 + 神秘保底模数（优先 MSE，失败用内置默认）。"""
    global _ACTIVITY_RULES_CACHE
    if _ACTIVITY_RULES_CACHE is not None and not force_refresh:
        return _ACTIVITY_RULES_CACHE

    rules: dict[str, Any] = {
        "lv1_to_lv2": EGG_LEVEL_LV1_TO_LV2_THRESHOLD,
        "lv2_to_lv3": EGG_LEVEL_LV2_TO_LV3_THRESHOLD,
        "lv1_expire": EGG_LEVEL_LV1_EXPIRE_SECONDS,
        "lv2_expire": EGG_LEVEL_LV2_EXPIRE_SECONDS,
        "lv3_expire": EGG_LEVEL_LV3_EXPIRE_SECONDS,
        "user_guarantee_mod": MYSTERY_USER_GUARANTEE_MOD,
        "room_guarantee_mod": MYSTERY_ROOM_GUARANTEE_MOD,
        "platform_guarantee_mod": MYSTERY_PLATFORM_GUARANTEE_MOD,
        "source": "default",
    }
    try:
        from anniversary_egg_mse_to_workbook import fetch_year3_mse_config

        cfg, _meta = fetch_year3_mse_config()
        egg_icon = cfg.get("eggIconConfig") or {}
        if isinstance(egg_icon, dict):
            lv1 = egg_icon.get("1") or egg_icon.get(1) or {}
            lv2 = egg_icon.get("2") or egg_icon.get(2) or {}
            lv3 = egg_icon.get("3") or egg_icon.get(3) or {}
            if isinstance(lv1, dict):
                if lv1.get("upgradeThreshold") is not None:
                    rules["lv1_to_lv2"] = int(lv1["upgradeThreshold"])
                # LV1 无过期：忽略 eggIconConfig.1.expireSeconds
            if isinstance(lv2, dict):
                if lv2.get("upgradeThreshold") is not None:
                    rules["lv2_to_lv3"] = int(lv2["upgradeThreshold"])
                if lv2.get("expireSeconds") is not None:
                    rules["lv2_expire"] = int(lv2["expireSeconds"])
            if isinstance(lv3, dict) and lv3.get("expireSeconds") is not None:
                rules["lv3_expire"] = int(lv3["expireSeconds"])
        mystery = cfg.get("mysteryConfig") or {}
        if isinstance(mystery, dict):
            if mystery.get("userGuaranteeMod") is not None:
                rules["user_guarantee_mod"] = int(mystery["userGuaranteeMod"])
            if mystery.get("roomGuaranteeMod") is not None:
                rules["room_guarantee_mod"] = int(mystery["roomGuaranteeMod"])
            if mystery.get("platformGuaranteeMod") is not None:
                rules["platform_guarantee_mod"] = int(mystery["platformGuaranteeMod"])
        rules["source"] = "mse"
    except Exception:
        pass

    _ACTIVITY_RULES_CACHE = rules
    return rules


def egg_level_from_room_smash_count(
    room_smash_count: int,
    *,
    rules: dict[str, Any] | None = None,
) -> str:
    """按房间终身累计砸蛋次数推算金蛋等级（不计 expire；仅作无时间戳时的兜底）。"""
    r = rules or load_activity_rules()
    t1 = max(0, int(r.get("lv1_to_lv2") or EGG_LEVEL_LV1_TO_LV2_THRESHOLD))
    t2 = max(0, int(r.get("lv2_to_lv3") or EGG_LEVEL_LV2_TO_LV3_THRESHOLD))
    n = max(0, int(room_smash_count))
    if n < t1:
        return "LV1"
    if n < t1 + t2:
        return "LV2"
    return "LV3"


def format_egg_level(egg_level: Any) -> str:
    """接口 eggLevel（1/2/3 或 LV1）→ 表内 LV1/LV2/LV3；无法识别则空串。"""
    if egg_level is None or egg_level == "":
        return ""
    raw = str(egg_level).strip().upper()
    if raw.startswith("LV"):
        raw = raw[2:]
    try:
        n = int(float(raw))
    except (TypeError, ValueError):
        return ""
    if n in (1, 2, 3):
        return f"LV{n}"
    return ""


def parse_record_time(value: Any) -> datetime | None:
    """解析「记录写入时间」；支持 `YYYY-MM-DD HH:MM:SS UTC` / ISO。"""
    text = str(value or "").strip()
    if not text:
        return None
    raw = text
    if raw.endswith(" UTC"):
        raw = raw[: -len(" UTC")].strip() + "+00:00"
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
            try:
                dt = datetime.strptime(text.replace(" UTC", "").strip(), fmt)
                return dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def expire_seconds_for_level(level: int, rules: dict[str, Any] | None = None) -> int:
    """本等级过期秒数。LV1 无过期（恒为 0，忽略配置）。"""
    lv = int(level)
    if lv <= 1:
        return 0
    r = rules or load_activity_rules()
    mapping = {
        2: int(r.get("lv2_expire") or EGG_LEVEL_LV2_EXPIRE_SECONDS),
        3: int(r.get("lv3_expire") or EGG_LEVEL_LV3_EXPIRE_SECONDS),
    }
    return max(0, mapping.get(lv, 0))


def apply_egg_level_expire(
    level: int,
    gap_seconds: float,
    *,
    rules: dict[str, Any] | None = None,
) -> tuple[int, bool]:
    """按空闲时长逐级掉级（仅 LV2/LV3；LV1 无过期、不清进度）。

    LV2/LV3：空闲 ≥ 本级 expireSeconds → 降 1 级。
    返回 (新等级, 是否应清零当前等级进度)。
    """
    lv = max(1, min(3, int(level or 1)))
    gap = max(0.0, float(gap_seconds))
    cleared = False
    while lv > 1:
        exp = expire_seconds_for_level(lv, rules)
        if exp <= 0 or gap < exp:
            break
        gap -= exp
        lv -= 1
        cleared = True
    return lv, cleared


def advance_egg_level_by_smash(
    level: int,
    progress: int,
    batch: int,
    *,
    rules: dict[str, Any] | None = None,
) -> tuple[int, int]:
    """本段砸蛋后的等级与当前等级内进度（升级后进度清零）。"""
    r = rules or load_activity_rules()
    t1 = max(0, int(r.get("lv1_to_lv2") or EGG_LEVEL_LV1_TO_LV2_THRESHOLD))
    t2 = max(0, int(r.get("lv2_to_lv3") or EGG_LEVEL_LV2_TO_LV3_THRESHOLD))
    lv = max(1, min(3, int(level or 1)))
    prog = max(0, int(progress or 0)) + max(0, int(batch or 0))
    if lv == 1 and t1 > 0 and prog >= t1:
        return 2, 0
    if lv == 2 and t2 > 0 and prog >= t2:
        return 3, 0
    return lv, prog


def simulate_room_egg_level(
    *,
    prev_level: int,
    prev_progress: int,
    prev_time: datetime | None,
    batch: int,
    record_time: datetime | None,
    rules: dict[str, Any] | None = None,
) -> tuple[str, int, int]:
    """结合记录时间过期 + 本段砸次，模拟砸蛋后的金蛋等级。

    返回 (LVn, new_level_int, new_progress)。
    """
    r = rules or load_activity_rules()
    lv = max(1, min(3, int(prev_level or 1)))
    prog = max(0, int(prev_progress or 0))
    if prev_time is not None and record_time is not None:
        gap = (record_time - prev_time).total_seconds()
        lv, cleared = apply_egg_level_expire(lv, gap, rules=r)
        if cleared:
            prog = 0
    lv, prog = advance_egg_level_by_smash(lv, prog, batch, rules=r)
    return f"LV{lv}", lv, prog


def normalize_room_smash_lifetime(
    room_before: Any,
    room_after: Any,
    batch: Any,
) -> tuple[int, int, bool]:
    """将「当前等级内」smashCount 归一成落表用的房间区间。

    升级时服务端会把当前等级 smashCount 清零（after < before），本段实际跨过门槛，
    落表应用 before+batch 作为房间终身累计，避免等级被误算回 LV1。

    返回 (room_before_i, room_after_i, reset)。
    """
    try:
        before_i = int(room_before or 0)
    except (TypeError, ValueError):
        before_i = 0
    try:
        after_i = int(room_after or 0)
    except (TypeError, ValueError):
        after_i = 0
    try:
        batch_i = max(0, int(batch or 0))
    except (TypeError, ValueError):
        batch_i = 0

    reset = batch_i > 0 and after_i < before_i
    if reset:
        return before_i, before_i + batch_i, True
    if batch_i > 0 and after_i < before_i + batch_i and after_i <= before_i:
        # after 未随 batch 增加（升级清零落在 0..before）
        return before_i, before_i + batch_i, True
    if after_i == 0 and before_i == 0 and batch_i > 0:
        return 0, batch_i, False
    if batch_i > 0 and after_i == before_i + batch_i:
        return before_i, after_i, False
    if batch_i > 0 and after_i > before_i:
        return before_i, after_i, False
    return before_i, max(after_i, before_i + batch_i if batch_i else after_i), False


def resolve_egg_level_label(
    *,
    room_smash_lifetime: int,
    egg_level: Any = None,
    rules: dict[str, Any] | None = None,
) -> str:
    """优先接口 eggLevel；否则按房间终身累计理论推算。"""
    from_api = format_egg_level(egg_level)
    if from_api:
        return from_api
    return egg_level_from_room_smash_count(room_smash_lifetime, rules=rules)


def _crossed_guarantee(before: int, after: int, mod: int) -> bool:
    """区间 (before, after] 是否越过保底模数的整数倍。"""
    try:
        b, a, m = int(before), int(after), int(mod)
    except (TypeError, ValueError):
        return False
    if m <= 0 or a <= b:
        return False
    first = (b // m + 1) * m
    return first <= a


# 同一颗蛋多保底同时满足时：个人 > 房间 > 平台；未消耗的顺延到下一颗蛋 / 下一次砸蛋
_MYSTERY_GUARANTEE_PRIORITY = ("user", "room", "platform")
_MYSTERY_PENDING_LABEL = {
    "user": "用户保底",
    "room": "房间保底",
    "platform": "平台保底",
}


def _normalize_mystery_pending(raw: Any) -> set[str]:
    if not raw:
        return set()
    if isinstance(raw, (set, frozenset)):
        items = raw
    elif isinstance(raw, str):
        items = [p.strip() for p in raw.replace("；", "+").replace(";", "+").split("+") if p.strip()]
    else:
        items = list(raw)
    out: set[str] = set()
    for item in items:
        key = str(item or "").strip().lower()
        if key in {"user", "u", "用户", "用户保底", "个人", "个人保底"}:
            out.add("user")
        elif key in {"room", "r", "房间", "房间保底"}:
            out.add("room")
        elif key in {"platform", "p", "plat", "平台", "平台保底"}:
            out.add("platform")
    return out


def resolve_mystery_guarantee_triggers(
    *,
    user_before: int,
    user_after: int,
    room_before: int,
    room_after: int,
    platform_before: int | None = None,
    platform_after: int | None = None,
    user_mod: int = 0,
    room_mod: int = 0,
    platform_mod: int = 0,
    pending_in: Any = None,
) -> tuple[list[str], set[str]]:
    """按颗模拟神秘保底触发（支持同砸多蛋、优先级与跨次顺延）。

    规则：
    1. 逐颗蛋推进计数；落在模数倍则该维度本颗候选
    2. 同一颗蛋多个候选：只消耗最高优先级（用户>房间>平台）
    3. 未消耗候选顺延到下一颗蛋；若本砸结束仍剩余，作为下一次砸蛋的 pending_in
    4. 一次砸 N 个蛋 → 最多可触发 N 次保底

    返回：(本砸触发标签列表, 顺延到下次的维度集合)
    """
    try:
        ub = int(user_before)
        ua = int(user_after)
        rb = int(room_before)
        ra = int(room_after)
    except (TypeError, ValueError):
        return [], set()
    batch = max(0, ua - ub)
    if batch <= 0:
        batch = max(0, ra - rb)
    if batch <= 0:
        # 无新砸蛋仍保留未消耗顺延
        return [], _normalize_mystery_pending(pending_in)

    u_mod = int(user_mod or 0)
    r_mod = int(room_mod or 0)
    p_mod = int(platform_mod or 0)
    try:
        pb = int(platform_before) if platform_before not in (None, "") else None
    except (TypeError, ValueError):
        pb = None

    labels = {
        "user": f"用户保底每{u_mod}次",
        "room": f"房间保底每{r_mod}次",
        "platform": f"平台保底每{p_mod}次",
    }
    pending = _normalize_mystery_pending(pending_in)
    tags: list[str] = []
    for i in range(1, batch + 1):
        newly: set[str] = set()
        if u_mod > 0 and (ub + i) % u_mod == 0:
            newly.add("user")
        if r_mod > 0 and (rb + i) % r_mod == 0:
            newly.add("room")
        if p_mod > 0 and pb is not None and (pb + i) % p_mod == 0:
            newly.add("platform")
        candidates = newly | pending
        if not candidates:
            continue
        winner = next(d for d in _MYSTERY_GUARANTEE_PRIORITY if d in candidates)
        tags.append(labels[winner])
        pending = candidates - {winner}
    return tags, pending


def theory_mystery_result(
    *,
    user_before: int,
    user_after: int,
    room_before: int,
    room_after: int,
    platform_before: int | None = None,
    platform_after: int | None = None,
    rules: dict[str, Any] | None = None,
    pending_in: Any = None,
) -> tuple[list[str], set[str]]:
    """返回 (本砸理论触发标签, 顺延到下次的维度)。"""
    r = rules or load_activity_rules()
    return resolve_mystery_guarantee_triggers(
        user_before=user_before,
        user_after=user_after,
        room_before=room_before,
        room_after=room_after,
        platform_before=platform_before,
        platform_after=platform_after,
        user_mod=int(r.get("user_guarantee_mod") or 0),
        room_mod=int(r.get("room_guarantee_mod") or 0),
        platform_mod=int(r.get("platform_guarantee_mod") or 0),
        pending_in=pending_in,
    )


def theory_mystery_tags(
    *,
    user_before: int,
    user_after: int,
    room_before: int,
    room_after: int,
    platform_before: int | None = None,
    platform_after: int | None = None,
    rules: dict[str, Any] | None = None,
    pending_in: Any = None,
) -> list[str]:
    """按配置保底模数计算本段砸蛋理论应触发的神秘奖（含优先级/顺延）。"""
    tags, _pending = theory_mystery_result(
        user_before=user_before,
        user_after=user_after,
        room_before=room_before,
        room_after=room_after,
        platform_before=platform_before,
        platform_after=platform_after,
        rules=rules,
        pending_in=pending_in,
    )
    return tags


def pending_mystery_labels(pending: Any, *, rules: dict[str, Any] | None = None) -> list[str]:
    """把顺延维度转成展示标签（带当前模数）。"""
    r = rules or load_activity_rules()
    mods = {
        "user": int(r.get("user_guarantee_mod") or 0),
        "room": int(r.get("room_guarantee_mod") or 0),
        "platform": int(r.get("platform_guarantee_mod") or 0),
    }
    labels: list[str] = []
    for dim in _MYSTERY_GUARANTEE_PRIORITY:
        if dim not in _normalize_mystery_pending(pending):
            continue
        mod = mods[dim]
        if mod > 0:
            labels.append(f"{_MYSTERY_PENDING_LABEL[dim]}每{mod}次")
        else:
            labels.append(_MYSTERY_PENDING_LABEL[dim])
    return labels


def compose_mystery_pending_in(
    *,
    user_id: str,
    room_id: str,
    pending_user: dict[str, bool],
    pending_room: dict[str, bool],
    pending_platform: bool,
) -> set[str]:
    """按账号/房间装配本砸开始前的顺延集合。"""
    out: set[str] = set()
    uid = str(user_id or "").strip()
    rid = str(room_id or "").strip()
    if uid and pending_user.get(uid):
        out.add("user")
    if rid and pending_room.get(rid):
        out.add("room")
    if pending_platform:
        out.add("platform")
    return out


def apply_mystery_pending_out(
    *,
    user_id: str,
    room_id: str,
    pending_out: Any,
    pending_user: dict[str, bool],
    pending_room: dict[str, bool],
) -> bool:
    """写回顺延状态，返回新的平台顺延标记。"""
    pending = _normalize_mystery_pending(pending_out)
    uid = str(user_id or "").strip()
    rid = str(room_id or "").strip()
    if uid:
        pending_user[uid] = "user" in pending
    if rid:
        pending_room[rid] = "room" in pending
    return "platform" in pending


_THEORY_SPLIT = re.compile(
    r"（理论触发：[^）]*）|\(理论触发：[^\)]*\)"
    r"|（顺延下次：[^）]*）|\(顺延下次：[^\)]*\)"
    r"|；理论触发：.*$|^理论触发：.+$"
    r"|；顺延下次：.*$|^顺延下次：.+$"
)


def strip_theory_mystery_note(text: Any) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    if raw in ("无保底触发", "无"):
        return ""
    cleaned = _THEORY_SPLIT.sub("", raw).strip("；; ")
    if cleaned in ("无保底触发", "无"):
        return ""
    return cleaned


def format_mystery_cell(
    actual_summary: str,
    theory_tags: list[str],
    *,
    pending_next: Any = None,
    rules: dict[str, Any] | None = None,
) -> str:
    actual = strip_theory_mystery_note(actual_summary)
    parts: list[str] = []
    if theory_tags:
        parts.append("理论触发：" + "+".join(theory_tags))
    defer = pending_mystery_labels(pending_next, rules=rules)
    if defer:
        parts.append("顺延下次：" + "+".join(defer))
    if not parts:
        return actual
    note = "；".join(parts)
    if actual:
        return f"{actual}（{note}）"
    return note


# 无次数时奖池预览名（不应算作金蛋等级档次奖励）
_TIER_POOL_PREVIEW_NAMES = frozenset(
    {
        "Celestial Twins",
        "天穹双子",
        "ak47",
        "lipstick",
        "口红",
        "instant noodles",
        "方便面",
        "I do",
        "我愿意",
    }
)


def _tier_reward_names(tier_summary: str) -> set[str]:
    names: set[str] = set()
    for part in str(tier_summary or "").replace(";", "；").split("；"):
        part = part.strip()
        if not part:
            continue
        name = part.split("×")[0].strip()
        if name:
            names.add(name)
    return names


def mystery_reward_meets_expectation(
    *,
    theory_tags: list[str],
    mystery_cell: str,
) -> bool:
    """神秘奖励是否符合预期。

    - 理论应触发保底：须有实发神秘奖（多保底钻石会合并成一段，不按段数计次）
    - 理论不应触发：不得有「理论触发」标注，也不得有实发神秘奖
    """
    cell = str(mystery_cell or "").strip()
    actual = strip_theory_mystery_note(cell)
    has_theory_note = "理论触发" in cell
    if theory_tags:
        return bool(actual)
    return (not has_theory_note) and (not actual)


def tier_reward_meets_expectation(
    *,
    tier_cell: str,
    batch: int,
    egg_level: str = "",
) -> bool:
    """金蛋等级档次礼物是否符合预期。

    - 有砸次：档次奖励非空，且不能只是奖池预览礼物名
    - 无砸次：不验收档次
    """
    if int(batch or 0) <= 0:
        return True
    text = str(tier_cell or "").strip()
    if not text:
        return False
    names = _tier_reward_names(text)
    if names and names <= _TIER_POOL_PREVIEW_NAMES:
        return False
    # egg_level 预留：后续可对照 lv1/2/3 奖池奖品白名单
    _ = egg_level
    return True


# 与服务端 maxSmashPerClick / 产品默认一致
DEFAULT_MAX_SMASH_PER_CLICK = 10


def expected_smash_batch(remain_before: int | None) -> int | None:
    """剩余>10 → 10；剩余≤10 → 剩余；剩余≤0 → 0。None 表示无法校验。"""
    if remain_before is None:
        return None
    left = int(remain_before)
    if left <= 0:
        return 0
    return min(DEFAULT_MAX_SMASH_PER_CLICK, left)


def smash_count_meets_expectation(
    *,
    actual_batch: int,
    expected_batch: int | None,
) -> bool:
    """本次砸蛋次数是否符合剩余次数规则。"""
    if expected_batch is None:
        return True
    return int(actual_batch or 0) == int(expected_batch)


def count_accumulation_meets_expectation(
    *,
    batch: int,
    room_before: int | None = None,
    room_after: int | None = None,
    user_before: int | None = None,
    user_after: int | None = None,
    platform_before: int | None = None,
    platform_after: int | None = None,
) -> tuple[bool, list[str]]:
    """房间/用户/平台次数累加：after == before + 本次砸蛋次数。

    缺 before/after 的维度跳过；全部跳过视为通过（无法校验）。
    """
    b = int(batch or 0)
    fails: list[str] = []
    for name, before, after in (
        ("房间内砸蛋次数", room_before, room_after),
        ("用户砸蛋次数", user_before, user_after),
        ("平台砸蛋次数", platform_before, platform_after),
    ):
        if before is None or after is None:
            continue
        try:
            bf = int(before)
            af = int(after)
        except (TypeError, ValueError):
            fails.append(f"{name}无法解析")
            continue
        if af != bf + b:
            fails.append(f"{name}累加不符(期望{bf}+{b}={bf + b}，实际{af})")
    return (not fails), fails


def evaluate_acceptance_verdict(
    *,
    theory_tags: list[str],
    mystery_cell: str,
    tier_cell: str,
    batch: int,
    egg_level: str = "",
    expected_batch: int | None = None,
    room_before: int | None = None,
    room_after: int | None = None,
    user_before: int | None = None,
    user_after: int | None = None,
    platform_before: int | None = None,
    platform_after: int | None = None,
) -> dict[str, Any]:
    """验收结论：①神秘奖励 ②金蛋等级礼物 ③本次砸蛋次数 ④房/用/平累加。"""
    fails: list[str] = []
    myst_ok = mystery_reward_meets_expectation(
        theory_tags=theory_tags, mystery_cell=mystery_cell
    )
    tier_ok = tier_reward_meets_expectation(
        tier_cell=tier_cell, batch=batch, egg_level=egg_level
    )
    smash_ok = smash_count_meets_expectation(
        actual_batch=batch, expected_batch=expected_batch
    )
    accum_ok, accum_fails = count_accumulation_meets_expectation(
        batch=batch,
        room_before=room_before,
        room_after=room_after,
        user_before=user_before,
        user_after=user_after,
        platform_before=platform_before,
        platform_after=platform_after,
    )
    if not myst_ok:
        fails.append("神秘奖励不符合预期")
    if not tier_ok:
        fails.append("金蛋等级礼物不符合预期")
    if not smash_ok:
        fails.append(
            f"本次砸蛋次数不符合预期(期望{expected_batch}，实际{int(batch or 0)})"
        )
    if not accum_ok:
        fails.extend(accum_fails)
    if not fails:
        return {
            "verdict": "通过",
            "failItems": "",
            "mysteryOk": True,
            "tierOk": True,
            "smashCountOk": True,
            "countAccumOk": True,
        }
    return {
        "verdict": "失败：" + "；".join(fails),
        "failItems": "；".join(fails),
        "mysteryOk": myst_ok,
        "tierOk": tier_ok,
        "smashCountOk": smash_ok,
        "countAccumOk": accum_ok,
    }


# 房间内/用户/平台砸蛋次数：year3Dao.testGetMysteryCount 的 room/user/platform（砸后快照）
HEADER = [
    "用例序号",
    "砸蛋账号",
    "砸蛋房间",
    "获次实得",
    "本次砸蛋次数",
    "房间内砸蛋次数",
    "用户砸蛋次数",
    "平台砸蛋次数",
    "砸蛋时金蛋等级",
    "档次奖励",
    "神秘奖励",
    "用户奖励汇总",
    "验收结论",
    "记录写入时间",
]

# 曾含「获次目标」「本次砸蛋次数-预期」
_LEGACY_HEADER_WITH_CHANCE_EXPECT = [
    "用例序号",
    "砸蛋账号",
    "砸蛋房间",
    "获次目标",
    "获次实得",
    "本次砸蛋次数",
    "本次砸蛋次数-预期",
    "房间内砸蛋次数",
    "用户砸蛋次数",
    "平台砸蛋次数",
    "砸蛋时金蛋等级",
    "档次奖励",
    "神秘奖励",
    "用户奖励汇总",
    "验收结论",
    "记录写入时间",
]

# 合并表曾含「手机号」
_LEGACY_HEADER_WITH_PHONE = [
    "用例序号",
    "手机号",
    "砸蛋账号",
    "砸蛋房间",
    "获次目标",
    "获次实得",
    "本次砸蛋次数",
    "本次砸蛋次数-预期",
    "房间内砸蛋次数",
    "用户砸蛋次数",
    "平台砸蛋次数",
    "砸蛋时金蛋等级",
    "档次奖励",
    "神秘奖励",
    "用户奖励汇总",
    "验收结论",
    "记录写入时间",
]

# 合并表曾分列「神秘奖励」+「神秘理论-预期」
_LEGACY_HEADER_WITH_MYSTERY_THEORY = [
    "用例序号",
    "手机号",
    "砸蛋账号",
    "砸蛋房间",
    "获次目标",
    "获次实得",
    "本次砸蛋次数",
    "本次砸蛋次数-预期",
    "房间内砸蛋次数",
    "用户砸蛋次数",
    "平台砸蛋次数",
    "砸蛋时金蛋等级",
    "档次奖励",
    "神秘奖励",
    "神秘理论-预期",
    "用户奖励汇总",
    "验收结论",
    "记录写入时间",
]

# 合并表曾含「失败项」的旧表头
_LEGACY_HEADER_WITH_FAIL_ITEMS = [
    "用例序号",
    "手机号",
    "砸蛋账号",
    "砸蛋房间",
    "获次目标",
    "获次实得",
    "本次砸蛋次数",
    "本次砸蛋次数-预期",
    "房间内砸蛋次数",
    "用户砸蛋次数",
    "平台砸蛋次数",
    "砸蛋时金蛋等级",
    "档次奖励",
    "神秘奖励",
    "神秘理论-预期",
    "用户奖励汇总",
    "验收结论",
    "失败项",
    "记录写入时间",
]

# 合并表曾含「金蛋等级-预期」的旧表头（投影时丢弃）
_LEGACY_HEADER_WITH_EXPECTED_LEVEL = [
    "用例序号",
    "手机号",
    "砸蛋账号",
    "砸蛋房间",
    "获次目标",
    "获次实得",
    "本次砸蛋次数",
    "本次砸蛋次数-预期",
    "房间内砸蛋次数",
    "用户砸蛋次数",
    "平台砸蛋次数",
    "砸蛋时金蛋等级",
    "金蛋等级-预期",
    "档次奖励",
    "神秘奖励",
    "神秘理论-预期",
    "用户奖励汇总",
    "验收结论",
    "失败项",
    "记录写入时间",
]

# 合并表曾含「充钻数量」+「金蛋等级-预期」的旧表头
_LEGACY_HEADER_WITH_TOPUP = [
    "用例序号",
    "手机号",
    "砸蛋账号",
    "砸蛋房间",
    "获次目标",
    "获次实得",
    "充钻数量",
    "本次砸蛋次数",
    "本次砸蛋次数-预期",
    "房间内砸蛋次数",
    "用户砸蛋次数",
    "平台砸蛋次数",
    "砸蛋时金蛋等级",
    "金蛋等级-预期",
    "档次奖励",
    "神秘奖励",
    "神秘理论-预期",
    "用户奖励汇总",
    "验收结论",
    "失败项",
    "记录写入时间",
]

# 合并前仅砸蛋记录的旧表头（投影补验收空列）
_LEGACY_HEADER_SMASH_ONLY = [
    "砸蛋账号",
    "砸蛋房间",
    "本次砸蛋次数",
    "房间内砸蛋次数",
    "用户砸蛋次数",
    "平台砸蛋次数",
    "砸蛋时金蛋等级",
    "档次奖励",
    "神秘奖励",
    "用户奖励汇总",
    "记录写入时间",
]

# 无「神秘奖励」列的旧表头（投影补空列）
_LEGACY_HEADER_NO_MYSTERY = [
    "砸蛋账号",
    "砸蛋房间",
    "本次砸蛋次数",
    "房间内砸蛋次数",
    "用户砸蛋次数",
    "平台砸蛋次数",
    "砸蛋时金蛋等级",
    "档次奖励",
    "用户奖励汇总",
    "记录写入时间",
]

# 兼容旧表头
_LEGACY_HEADER_ALIASES = {
    "列表总奖励": "用户奖励汇总",
}

_REWARD_NAME_ALIASES = {
    "DIAMOND": "钻石",
}

_REWARD_PAIR = re.compile(r"^(.+?)×(\d+)$")


def _canonicalize_reward_name(name: str) -> str:
    raw = str(name or "").strip()
    if not raw:
        return raw
    aliased = _REWARD_NAME_ALIASES.get(raw) or _REWARD_NAME_ALIASES.get(raw.upper())
    return aliased or raw


def reward_display_name(item: dict[str, Any]) -> str:
    """奖品展示名：优先具体名称，占位名「1」按类型归为积分/钻石。"""
    name = str(
        item.get("name") or item.get("prizeName") or item.get("giftName") or ""
    ).strip()
    prize_type = str(item.get("prizeType") or "").upper()
    if prize_type == "DIAMOND" or name.upper() == "DIAMOND":
        return "钻石"
    if name and name not in {"1", "奖励"} and not name.isdigit():
        return _canonicalize_reward_name(name)
    icon = str(item.get("icon") or "").lower()
    if "token" in icon or prize_type in {"UNKNOWN", ""}:
        # smashEgg 里 token 类常把 prizeName 写成 "1"
        return "积分"
    prize_id = str(item.get("prizeId") or "").strip()
    if prize_id:
        return f"奖品{prize_id}"
    return "奖励"


def aggregate_rewards(rewards: Any) -> OrderedDict[str, int]:
    """按具体名字汇总数量。"""
    totals: OrderedDict[str, int] = OrderedDict()
    if not isinstance(rewards, list):
        return totals
    for item in rewards:
        if not isinstance(item, dict):
            continue
        name = reward_display_name(item)
        try:
            num = int(item.get("num") or item.get("count") or item.get("amount") or 1)
        except (TypeError, ValueError):
            num = 1
        totals[name] = int(totals.get(name, 0)) + num
    return totals


def format_reward_totals(totals: OrderedDict[str, int] | dict[str, int]) -> str:
    if not totals:
        return ""
    return "；".join(f"{name}×{count}" for name, count in totals.items())


def parse_reward_summary(text: Any) -> OrderedDict[str, int]:
    """从「A×1；B×2」摘要解析回汇总。"""
    totals: OrderedDict[str, int] = OrderedDict()
    raw = str(text or "").strip()
    if not raw:
        return totals
    for part in raw.replace("\n", "；").split("；"):
        piece = part.strip()
        if not piece:
            continue
        m = _REWARD_PAIR.match(piece)
        if not m:
            continue
        name, num_s = m.group(1).strip(), m.group(2)
        try:
            num = int(num_s)
        except ValueError:
            continue
        name = _canonicalize_reward_name(name)
        if not name:
            continue
        totals[name] = int(totals.get(name, 0)) + num
    return totals


def merge_reward_totals(
    *parts: OrderedDict[str, int] | dict[str, int],
) -> OrderedDict[str, int]:
    merged: OrderedDict[str, int] = OrderedDict()
    for part in parts:
        for name, num in part.items():
            key = _canonicalize_reward_name(str(name))
            merged[key] = int(merged.get(key, 0)) + int(num)
    return merged


def _reward_summary(rewards: Any) -> str:
    """档次奖励 / 神秘奖励：按名字汇总。"""
    return format_reward_totals(aggregate_rewards(rewards))


def record_to_row(
    smash_result: dict[str, Any],
    *,
    fallback_user_id: str = "",
    fallback_room_id: str = "",
    fallback_smash_count: int | None = None,
    user_total_summary: str = "",
    verify: dict[str, Any] | None = None,
) -> list[str]:
    rules = load_activity_rules()
    user_id = str(smash_result.get("userId") or fallback_user_id or "").strip()
    room_id = str(smash_result.get("roomId") or fallback_room_id or "").strip()
    smash_count = smash_result.get("smashCount")
    if smash_count is None:
        smash_count = fallback_smash_count
    try:
        batch = int(smash_count or 0)
    except (TypeError, ValueError):
        batch = 0

    room_after_raw = smash_result.get("roomSmashCount")
    if room_after_raw is None:
        room_after_raw = smash_result.get("roomSmashAfter")
    # 金蛋等级内计数（仅状态机兜底用）
    egg_room_after_raw = smash_result.get("roomEggSmashAfter")
    if egg_room_after_raw is None:
        egg_room_after_raw = room_after_raw
    egg_room_before_raw = smash_result.get("roomEggSmashBefore")
    if egg_room_before_raw is None:
        egg_room_before_raw = smash_result.get("roomSmashBefore")

    user_after = smash_result.get("userSmashCount")
    if user_after is None:
        user_after = smash_result.get("usedSmashAfter")
    platform_after = smash_result.get("platformSmashCount")

    try:
        user_after_i = int(user_after or 0)
    except (TypeError, ValueError):
        user_after_i = 0

    try:
        egg_room_before_raw_i = (
            max(0, int(egg_room_after_raw or 0) - batch)
            if egg_room_before_raw is None
            else int(egg_room_before_raw or 0)
        )
    except (TypeError, ValueError):
        egg_room_before_raw_i = 0
    egg_room_before_i, egg_room_after_i, _ = normalize_room_smash_lifetime(
        egg_room_before_raw_i, egg_room_after_raw, batch
    )

    user_before = smash_result.get("userSmashBefore")
    if user_before is None:
        user_before = smash_result.get("usedSmashBefore")
    if user_before is None:
        user_before = max(0, user_after_i - batch)

    platform_before = smash_result.get("platformSmashBefore")
    platform_after_i: int | None
    platform_before_i: int | None
    try:
        platform_after_i = int(platform_after) if platform_after not in (None, "") else None
    except (TypeError, ValueError):
        platform_after_i = None
    try:
        platform_before_i = (
            int(platform_before)
            if platform_before not in (None, "")
            else (
                max(0, platform_after_i - batch)
                if platform_after_i is not None
                else None
            )
        )
    except (TypeError, ValueError):
        platform_before_i = None

    # 落表三列 + 神秘保底：一律 year3Dao.testGetMysteryCount
    myst_b = smash_result.get("mysteryCountBefore")
    myst_a = smash_result.get("mysteryCountAfter")
    if isinstance(myst_b, dict) and isinstance(myst_a, dict):
        try:
            user_before = int(myst_b.get("user") or 0)
            user_after_i = int(myst_a.get("user") or 0)
            user_after = user_after_i
            myst_room_before = int(myst_b.get("room") or 0)
            myst_room_after = int(myst_a.get("room") or 0)
            platform_before_i = int(myst_b.get("platform") or 0)
            platform_after_i = int(myst_a.get("platform") or 0)
            platform_after = platform_after_i
            sheet_room_after = myst_room_after
        except (TypeError, ValueError):
            myst_room_before, myst_room_after = egg_room_before_i, egg_room_after_i
            sheet_room_after = egg_room_after_i
    else:
        # 兼容旧数据：无 mysteryCount 时尽量用已写入的房间/用户/平台绝对值
        try:
            sheet_room_after = int(room_after_raw if room_after_raw not in (None, "") else egg_room_after_i)
        except (TypeError, ValueError):
            sheet_room_after = egg_room_after_i
        myst_room_before = int(smash_result.get("mysteryRoomBefore") or max(0, sheet_room_after - batch))
        myst_room_after = int(smash_result.get("mysteryRoomAfter") or sheet_room_after)

    # 金蛋等级：优先接口 eggLevel；否则按神秘计数房间累计 / 等级内归一推算
    egg_level = resolve_egg_level_label(
        room_smash_lifetime=myst_room_after if isinstance(myst_a, dict) else egg_room_after_i,
        egg_level=smash_result.get("eggLevel"),
        rules=rules,
    )

    rewards = smash_result.get("rewards")
    mystery = smash_result.get("mysteryPrizes") or smash_result.get("mysteryRewards")
    tier_summary = _reward_summary(rewards)
    actual_mystery = _reward_summary(mystery)
    pending_in = _normalize_mystery_pending(
        smash_result.get("mysteryPendingBefore")
        or (verify or {}).get("mysteryPendingBefore")
    )
    theory_tags, pending_out = theory_mystery_result(
        user_before=int(user_before or 0),
        user_after=user_after_i,
        room_before=myst_room_before,
        room_after=myst_room_after,
        platform_before=platform_before_i,
        platform_after=platform_after_i,
        rules=rules,
        pending_in=pending_in,
    )
    mystery_summary = format_mystery_cell(
        actual_mystery,
        theory_tags,
        pending_next=pending_out,
        rules=rules,
    )
    # 无实发且无理论触发：神秘奖励列留空（不写「无保底触发」）；有顺延仍写顺延标注
    if not mystery_summary and pending_out:
        mystery_summary = format_mystery_cell(
            "",
            [],
            pending_next=pending_out,
            rules=rules,
        )

    # 无显式汇总时：档次 + 实发神秘一并计入本行用户汇总（写入后仍会按用户历史重算）
    if user_total_summary:
        user_summary = user_total_summary
    else:
        user_summary = format_reward_totals(
            merge_reward_totals(
                aggregate_rewards(rewards),
                aggregate_rewards(mystery),
            )
        )
    recorded_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    v = verify or {}
    remain_before_raw = smash_result.get("remainBefore")
    try:
        remain_before_i = (
            int(remain_before_raw) if remain_before_raw not in (None, "") else None
        )
    except (TypeError, ValueError):
        remain_before_i = None
    expected_batch = expected_smash_batch(remain_before_i)
    if v.get("expectedSmashCount") not in (None, ""):
        try:
            expected_batch = int(v["expectedSmashCount"])
        except (TypeError, ValueError):
            pass
    acceptance = evaluate_acceptance_verdict(
        theory_tags=theory_tags,
        mystery_cell=mystery_summary,
        tier_cell=tier_summary,
        batch=batch,
        egg_level=egg_level,
        expected_batch=expected_batch,
        room_before=myst_room_before,
        room_after=myst_room_after,
        user_before=int(user_before or 0) if user_before is not None else None,
        user_after=user_after_i,
        platform_before=platform_before_i,
        platform_after=platform_after_i,
    )
    verdict = acceptance["verdict"]
    return [
        _sheet_cell(v.get("caseNo")),
        _sheet_cell(user_id),
        _sheet_cell(room_id),
        _sheet_cell(v.get("gainedChances")),
        _sheet_cell(smash_count),
        _sheet_cell(sheet_room_after),
        _sheet_cell(user_after),
        _sheet_cell(platform_after),
        _sheet_cell(egg_level),
        _sheet_cell(tier_summary),
        _sheet_cell(mystery_summary),
        _sheet_cell(user_summary),
        _sheet_cell(verdict),
        _sheet_cell(recorded_at),
    ]


def _canonicalize_header_cells(first_row: list[Any]) -> list[str]:
    cells = [str(c or "").strip() for c in first_row]
    # 去掉尾部空列
    while cells and not cells[-1]:
        cells.pop()
    return [_LEGACY_HEADER_ALIASES.get(c, c) for c in cells if c]


def _rows_match_header(first_row: list[Any]) -> bool:
    if not first_row:
        return False
    return _canonicalize_header_cells(first_row) == HEADER


def _header_compatible(first_row: list[Any]) -> bool:
    """当前合并表头、仅砸蛋旧表头、无神秘奖励旧表头，或仅多一列「砸蛋时间」。"""
    cells = _canonicalize_header_cells(first_row)
    if cells in (
        HEADER,
        _LEGACY_HEADER_WITH_CHANCE_EXPECT,
        _LEGACY_HEADER_WITH_PHONE,
        _LEGACY_HEADER_WITH_MYSTERY_THEORY,
        _LEGACY_HEADER_WITH_FAIL_ITEMS,
        _LEGACY_HEADER_WITH_EXPECTED_LEVEL,
        _LEGACY_HEADER_WITH_TOPUP,
        _LEGACY_HEADER_SMASH_ONLY,
        _LEGACY_HEADER_NO_MYSTERY,
    ):
        return True
    if cells and cells[0] == "砸蛋时间" and cells[1:] in (
        HEADER,
        _LEGACY_HEADER_WITH_CHANCE_EXPECT,
        _LEGACY_HEADER_WITH_PHONE,
        _LEGACY_HEADER_WITH_MYSTERY_THEORY,
        _LEGACY_HEADER_WITH_FAIL_ITEMS,
        _LEGACY_HEADER_WITH_EXPECTED_LEVEL,
        _LEGACY_HEADER_WITH_TOPUP,
        _LEGACY_HEADER_SMASH_ONLY,
        _LEGACY_HEADER_NO_MYSTERY,
    ):
        return True
    return False


def _merge_mystery_and_theory(actual: str, theory: str) -> str:
    """把「神秘奖励」与「神秘理论-预期」合成一格；皆无则留空。"""
    a = str(actual or "").strip()
    t = str(theory or "").strip()
    if a in ("无保底触发", "无"):
        a = ""
    if t in ("无保底触发", "无"):
        t = ""
    if not t:
        return a
    if not a:
        return t if t.startswith("理论触发") or "保底" in t else (
            f"理论触发：{t}" if t else ""
        )
    if t in a:
        return a
    if "理论触发" in a:
        return a
    return f"{a}（理论触发：{t}）"


def _project_row_to_header(
    header_cells: list[str],
    row: list[Any],
) -> list[str]:
    """按旧表头列名投影到当前 HEADER（丢掉已删除列；神秘两列合并）。"""
    names = _canonicalize_header_cells(header_cells)
    values = [str(c or "") for c in row]
    by_name = {
        name: values[i] if i < len(values) else ""
        for i, name in enumerate(names)
    }
    if "神秘理论-预期" in by_name:
        by_name["神秘奖励"] = _merge_mystery_and_theory(
            by_name.get("神秘奖励", ""),
            by_name.get("神秘理论-预期", ""),
        )
    return [by_name.get(col, "") for col in HEADER]


def _tier_col_index() -> int:
    return HEADER.index("档次奖励")


def _mystery_col_index() -> int:
    return HEADER.index("神秘奖励")


def _user_total_col_index() -> int:
    return HEADER.index("用户奖励汇总")


def _user_id_col_index() -> int:
    return HEADER.index("砸蛋账号")


def _room_id_col_index() -> int:
    return HEADER.index("砸蛋房间")


def _batch_count_col_index() -> int:
    return HEADER.index("本次砸蛋次数")


def _room_smash_col_index() -> int:
    return HEADER.index("房间内砸蛋次数")


def _user_smash_col_index() -> int:
    return HEADER.index("用户砸蛋次数")


def _platform_smash_col_index() -> int:
    return HEADER.index("平台砸蛋次数")


def _egg_level_col_index() -> int:
    return HEADER.index("砸蛋时金蛋等级")


def _recorded_at_col_index() -> int:
    return HEADER.index("记录写入时间")


def _verdict_col_index() -> int:
    return HEADER.index("验收结论")


def _parse_count(value: Any) -> int:
    text = str(value or "").strip()
    if not text:
        return 0
    try:
        return max(0, int(float(text)))
    except ValueError:
        return 0


def _normalize_data_row(row: list[Any]) -> list[str]:
    cells = [str(c or "") for c in row]
    if len(cells) < len(HEADER):
        cells.extend([""] * (len(HEADER) - len(cells)))
    return cells[: len(HEADER)]


def _is_blank_data_row(row: list[str]) -> bool:
    return not any(str(c or "").strip() for c in row)


def _recompute_derived_columns(data_rows: list[list[str]]) -> list[list[str]]:
    """按行序重算：

    - 房间内/用户/平台砸蛋次数：优先保留本行已有绝对值（来自 year3Dao.testGetMysteryCount）；
      仅当单元格为空时按表内累计补齐（旧行兼容）
    - 砸蛋时金蛋等级：按房间状态机模拟（upgradeThreshold + expireSeconds + 记录时间掉级）
    - 神秘奖励：保留实发奖品文案，并按保底模数补「理论触发」标注
    - 验收结论：①神秘奖励 ②金蛋等级档次礼物 ③本次砸蛋次数 ④房/用/平相对上条同主体累加
    - 用户奖励汇总：该用户截至本行（含本次档次奖励 + 实发神秘）的累计
    """
    rules = load_activity_rules()
    tier_idx = _tier_col_index()
    mystery_idx = _mystery_col_index()
    user_total_idx = _user_total_col_index()
    user_idx = _user_id_col_index()
    room_idx = _room_id_col_index()
    batch_idx = _batch_count_col_index()
    room_smash_idx = _room_smash_col_index()
    user_smash_idx = _user_smash_col_index()
    platform_smash_idx = _platform_smash_col_index()
    egg_level_idx = _egg_level_col_index()
    recorded_at_idx = _recorded_at_col_index()
    verdict_idx = _verdict_col_index()

    rows = [list(r) for r in data_rows if not _is_blank_data_row(r)]

    room_running: dict[str, int] = {}
    room_seen: set[str] = set()
    user_seen: set[str] = set()
    pending_user: dict[str, bool] = {}
    pending_room: dict[str, bool] = {}
    pending_platform = False
    # 每房间：等级、当前等级内进度、上次记录时间
    room_egg_state: dict[str, tuple[int, int, datetime | None]] = {}
    user_running: dict[str, int] = {}
    user_reward_running: dict[str, OrderedDict[str, int]] = {}
    platform_running = 0
    platform_seen = False
    out: list[list[str]] = []
    for row in rows:
        cells = list(row)
        batch = _parse_count(cells[batch_idx])
        uid = str(cells[user_idx] or "").strip()
        rid = str(cells[room_idx] or "").strip()
        tier = parse_reward_summary(cells[tier_idx])
        actual_mystery_text = strip_theory_mystery_note(cells[mystery_idx])
        if actual_mystery_text in ("无保底触发", "无"):
            actual_mystery_text = ""
        mystery_for_total = parse_reward_summary(actual_mystery_text)
        cells[tier_idx] = format_reward_totals(tier)

        room_existing = (
            _parse_count(cells[room_smash_idx])
            if str(cells[room_smash_idx] or "").strip()
            else None
        )
        user_existing = (
            _parse_count(cells[user_smash_idx])
            if str(cells[user_smash_idx] or "").strip()
            else None
        )
        plat_existing = (
            _parse_count(cells[platform_smash_idx])
            if str(cells[platform_smash_idx] or "").strip()
            else None
        )

        room_before_i: int | None = None
        room_after_i: int | None = None
        user_before_i: int | None = None
        user_after_i: int | None = None
        plat_before_i: int | None = None
        plat_after_i: int | None = None

        if rid:
            prev_room = int(room_running.get(rid, 0))
            if rid in room_seen:
                room_before_i = prev_room
            if room_existing is None:
                # 旧行无 mystery 快照：按表内累计补齐
                room_total = prev_room + batch
            else:
                # testGetMysteryCount.room 等服务端绝对值：原样保留，勿按升级清零改写
                room_total = room_existing
            room_after_i = room_total
            room_running[rid] = room_total
            room_seen.add(rid)
            cells[room_smash_idx] = str(room_total)

            prev_lv, prev_prog, prev_ts = room_egg_state.get(rid, (1, 0, None))
            rec_ts = parse_record_time(cells[recorded_at_idx])
            level_label, new_lv, new_prog = simulate_room_egg_level(
                prev_level=prev_lv,
                prev_progress=prev_prog,
                prev_time=prev_ts,
                batch=batch,
                record_time=rec_ts,
                rules=rules,
            )
            cells[egg_level_idx] = level_label
            room_egg_state[rid] = (new_lv, new_prog, rec_ts or prev_ts)
        else:
            room_total = room_existing or 0
            room_after_i = room_existing
            cells[room_smash_idx] = (
                str(room_existing) if room_existing is not None else ""
            )
            cells[egg_level_idx] = (
                egg_level_from_room_smash_count(room_total, rules=rules)
                if room_existing is not None
                else ""
            )

        if uid:
            prev_user = int(user_running.get(uid, 0))
            if uid in user_seen:
                user_before_i = prev_user
            if user_existing is None:
                user_running[uid] = prev_user + batch
                user_total = user_running[uid]
            else:
                user_total = user_existing
                user_running[uid] = user_total
            user_after_i = user_total
            user_seen.add(uid)
            cells[user_smash_idx] = str(user_total)
            user_reward_running[uid] = merge_reward_totals(
                user_reward_running.get(uid, OrderedDict()),
                tier,
                mystery_for_total,
            )
            cells[user_total_idx] = format_reward_totals(user_reward_running[uid])
        else:
            user_total = user_existing or 0
            user_after_i = user_existing
            cells[user_smash_idx] = (
                str(user_existing) if user_existing is not None else ""
            )
            cells[user_total_idx] = format_reward_totals(
                merge_reward_totals(tier, mystery_for_total)
            )

        if platform_seen:
            plat_before_i = platform_running
        if plat_existing is None:
            platform_running = (platform_running if platform_seen else 0) + batch
            plat_total = platform_running
            cells[platform_smash_idx] = str(plat_total)
        else:
            plat_total = plat_existing
            platform_running = plat_total
            cells[platform_smash_idx] = str(plat_total)
        plat_after_i = plat_total
        platform_seen = True

        pending_in = compose_mystery_pending_in(
            user_id=uid,
            room_id=rid,
            pending_user=pending_user,
            pending_room=pending_room,
            pending_platform=pending_platform,
        )
        theory_tags, pending_out = theory_mystery_result(
            user_before=max(0, (user_after_i or 0) - batch)
            if user_after_i is not None
            else max(0, user_total - batch),
            user_after=user_after_i if user_after_i is not None else user_total,
            room_before=max(0, (room_after_i or 0) - batch)
            if room_after_i is not None
            else max(0, room_total - batch),
            room_after=room_after_i if room_after_i is not None else room_total,
            platform_before=max(0, (plat_after_i or 0) - batch)
            if plat_after_i is not None
            else max(0, plat_total - batch),
            platform_after=plat_after_i if plat_after_i is not None else plat_total,
            rules=rules,
            pending_in=pending_in,
        )
        pending_platform = apply_mystery_pending_out(
            user_id=uid,
            room_id=rid,
            pending_out=pending_out,
            pending_user=pending_user,
            pending_room=pending_room,
        )
        cells[mystery_idx] = format_mystery_cell(
            actual_mystery_text,
            theory_tags,
            pending_next=pending_out,
            rules=rules,
        )
        acceptance = evaluate_acceptance_verdict(
            theory_tags=theory_tags,
            mystery_cell=cells[mystery_idx],
            tier_cell=cells[tier_idx],
            batch=batch,
            egg_level=str(cells[egg_level_idx] or ""),
            # 表内重算无 remainBefore，跳过「本次砸蛋次数 vs 剩余」校验
            expected_batch=None,
            room_before=room_before_i,
            room_after=room_after_i,
            user_before=user_before_i,
            user_after=user_after_i,
            platform_before=plat_before_i,
            platform_after=plat_after_i,
        )
        cells[verdict_idx] = acceptance["verdict"]
        out.append(cells)
    return out


# 兼容旧名
def _recompute_user_totals(data_rows: list[list[str]]) -> list[list[str]]:
    return _recompute_derived_columns(data_rows)


async def append_smash_record_async(
    workbook_url_or_id: str,
    row: list[str],
    *,
    sheet_name: str = DEFAULT_SHEET,
) -> str:
    """追加一行砸金蛋记录。

    从表头向下找「第一个空行」写入（保证连续接在已有数据后），
    禁止按 sheet rowCount / 表尾扫描（否则会写到超长空白末尾）。
    """
    from alidocs_excel_export import DOC_API, _col_letter, _excel_env, _get_token_and_operator

    import httpx

    workbook_id = node_id(workbook_url_or_id)
    url = f"https://alidocs.dingtalk.com/i/nodes/{workbook_id}"
    env = _excel_env()
    token, operator = await _get_token_and_operator(env)
    cols = len(HEADER)
    end_col = _col_letter(cols)
    data_row = _normalize_data_row(row)
    str_row = [_sheet_cell(c) for c in data_row]

    async with httpx.AsyncClient(timeout=120) as client:
        await _ensure_sheet(
            token=token,
            operator=operator,
            workbook_id=workbook_id,
            sheet_name=sheet_name,
            client=client,
        )
        sheets_url = f"{DOC_API}/workbooks/{workbook_id}/sheets?operatorId={operator}"
        resp = await client.get(
            sheets_url, headers={"x-acs-dingtalk-access-token": token}
        )
        resp.raise_for_status()
        sheet_id = None
        for item in resp.json().get("value", []):
            if str(item.get("name") or "") == sheet_name:
                sheet_id = str(item.get("id") or "")
                break
        if not sheet_id:
            raise RuntimeError(f"未找到工作表: {sheet_name}")

        info_url = (
            f"{DOC_API}/workbooks/{workbook_id}/sheets/{sheet_id}"
            f"?select=rowCount,columnCount&operatorId={operator}"
        )
        info_resp = await client.get(
            info_url, headers={"x-acs-dingtalk-access-token": token}
        )
        info_resp.raise_for_status()
        info = info_resp.json()
        old_row_count = int(info.get("rowCount") or 0)

        async def _put_range(range_str: str, values: list[list[str]]) -> None:
            write_url = (
                f"{DOC_API}/workbooks/{workbook_id}/sheets/{sheet_id}"
                f"/ranges/{range_str}?operatorId={operator}"
            )
            wr = await client.put(
                write_url,
                headers={
                    "x-acs-dingtalk-access-token": token,
                    "Content-Type": "application/json",
                },
                json={"values": values, "wordWrap": "autoWrap"},
            )
            if wr.status_code >= 400:
                raise RuntimeError(
                    f"写入 {sheet_name} {range_str} 失败 HTTP {wr.status_code}: {wr.text[:300]}"
                )

        async def _find_next_row_from_top() -> int:
            """从表头向下扫描，返回第一个空数据行号（至少为 2）。"""
            if old_row_count <= 0:
                return 2
            # 只扫已有 rowCount，但若全满则落到 rowCount+1；遇空洞立刻停止（优先填洞）
            scan_limit = max(old_row_count, 1)
            chunk = 100
            start = 1
            while start <= scan_limit:
                end = min(start + chunk - 1, scan_limit)
                scan_url = (
                    f"{DOC_API}/workbooks/{workbook_id}/sheets/{sheet_id}"
                    f"/ranges/A{start}:{end_col}{end}?operatorId={operator}"
                )
                sr = await client.get(
                    scan_url, headers={"x-acs-dingtalk-access-token": token}
                )
                if sr.status_code >= 400:
                    # 读失败时退化为「表头下一行」
                    return 2
                vals = sr.json().get("values") or []
                for i, r in enumerate(vals):
                    abs_row = start + i
                    if abs_row == 1:
                        # 表头行：若空则先写表头+本行在外层处理
                        continue
                    if not any(str(c or "").strip() for c in (r or [])):
                        return abs_row
                start = end + 1
            return scan_limit + 1

        if old_row_count <= 0:
            await _put_range(
                f"A1:{end_col}2",
                [[_sheet_cell(c) for c in HEADER], str_row],
            )
        else:
            # 确保表头存在
            header_url = (
                f"{DOC_API}/workbooks/{workbook_id}/sheets/{sheet_id}"
                f"/ranges/A1:{end_col}1?operatorId={operator}"
            )
            hr = await client.get(
                header_url, headers={"x-acs-dingtalk-access-token": token}
            )
            header_empty = True
            if hr.status_code < 400:
                hv = (hr.json().get("values") or [[]])[0]
                header_empty = not any(str(c or "").strip() for c in (hv or []))
            if header_empty:
                await _put_range(
                    f"A1:{end_col}1", [[_sheet_cell(c) for c in HEADER]]
                )
            next_row = await _find_next_row_from_top()
            if next_row < 2:
                next_row = 2
            await _put_range(f"A{next_row}:{end_col}{next_row}", [str_row])

    return url


def append_smash_record(
    workbook_url_or_id: str,
    row: list[str],
    *,
    sheet_name: str = DEFAULT_SHEET,
) -> str:
    return asyncio.run(
        append_smash_record_async(workbook_url_or_id, row, sheet_name=sheet_name)
    )


async def create_workbook_with_records_async(
    *,
    parent_node_id: str,
    workbook_name: str,
    rows: list[list[str]],
    sheet_name: str = DEFAULT_SHEET,
) -> str:
    """在指定目录新建砸金蛋记录表并写入行。"""
    from alidocs_excel_export import (
        ALIDOCS_NODE,
        _create_workbook,
        _excel_env,
        _get_token_and_operator,
        _get_workspace_id,
    )

    import httpx

    env = _excel_env()
    token, operator = await _get_token_and_operator(env)
    workspace_id = _get_workspace_id(parent_node_id, "")
    workbook_id = await _create_workbook(
        token=token,
        operator=operator,
        workspace_id=workspace_id,
        parent_node_id=parent_node_id,
        name=workbook_name,
    )
    data_rows = _recompute_user_totals([_normalize_data_row(r) for r in rows])
    async with httpx.AsyncClient(timeout=120) as client:
        await _ensure_sheet(
            token=token,
            operator=operator,
            workbook_id=workbook_id,
            sheet_name=sheet_name,
            client=client,
        )
    await _write_sheet_replace(
        token=token,
        operator=operator,
        workbook_id=workbook_id,
        sheet_name=sheet_name,
        rows=_string_rows([HEADER] + data_rows),
    )
    return ALIDOCS_NODE.format(node_id=workbook_id)


# ---------- 验收列（已并入 DEFAULT_SHEET，保留常量兼容旧参数） ----------

VERIFY_SHEET = DEFAULT_SHEET  # 不再单独建「砸金蛋验收结果」

# 旧验收表头（仅用于历史数据合并投影）
_LEGACY_VERIFY_HEADER = [
    "用例序号",
    "手机号",
    "砸蛋账号",
    "砸蛋房间",
    "获次目标",
    "获次实得",
    "充钻数量",
    "本次砸蛋次数-预期",
    "本次砸蛋次数-实际",
    "金蛋等级-预期",
    "金蛋等级-实际",
    "神秘理论-预期",
    "神秘奖励-实际",
    "档次奖励",
    "验收结论",
    "失败项",
    "记录写入时间",
]

VERIFY_HEADER = HEADER  # 兼容旧引用

# 旧「砸金蛋验收结果」列名 → 合并表
_VERIFY_COL_ALIASES = {
    "本次砸蛋次数-实际": "本次砸蛋次数",
    "金蛋等级-实际": "砸蛋时金蛋等级",
    "神秘奖励-实际": "神秘奖励",
}


def verify_record_to_row(result: dict[str, Any]) -> list[str]:
    """兼容旧调用：仅有验收字段时拼成合并表一行（砸蛋明细列为空）。"""
    return record_to_row(
        {
            "userId": result.get("userId"),
            "roomId": result.get("roomId"),
            "smashCount": result.get("actualSmashCount"),
            "eggLevel": result.get("actualEggLevel"),
            "rewards": [],
            "mysteryPrizes": [],
        },
        verify=result,
    )


def _project_verify_row_to_header(header_cells: list[str], row: list[Any]) -> list[str]:
    names = [str(c or "").strip() for c in header_cells]
    while names and not names[-1]:
        names.pop()
    values = [str(c or "") for c in row]
    by_name: dict[str, str] = {}
    for i, name in enumerate(names):
        key = _VERIFY_COL_ALIASES.get(name, name)
        by_name[key] = values[i] if i < len(values) else ""
    return [by_name.get(col, "") for col in HEADER]


def merge_smash_and_verify_rows(
    smash_rows: list[list[str]],
    *,
    smash_header: list[str],
    verify_rows: list[list[str]] | None = None,
    verify_header: list[str] | None = None,
) -> list[list[str]]:
    """将历史「测试记录」+「验收结果」合成合并表行（按账号/房间/次数从后往前配对）。"""
    merged = [
        _project_row_to_header(smash_header, r)
        for r in smash_rows
        if any(str(c or "").strip() for c in r)
    ]
    if not verify_rows or not verify_header:
        return _recompute_derived_columns(merged)

    verify_proj = [
        _project_verify_row_to_header(verify_header, r)
        for r in verify_rows
        if any(str(c or "").strip() for c in r)
    ]
    used: set[int] = set()
    case_i = HEADER.index("用例序号")
    uid_i = HEADER.index("砸蛋账号")
    rid_i = HEADER.index("砸蛋房间")
    batch_i = HEADER.index("本次砸蛋次数")
    gain_a_i = HEADER.index("获次实得")
    verdict_i = HEADER.index("验收结论")

    fill_idxs = (
        case_i,
        gain_a_i,
        verdict_i,
    )

    for si in range(len(merged) - 1, -1, -1):
        s = merged[si]
        if str(s[verdict_i] or "").strip():
            continue
        for vi, v in enumerate(verify_proj):
            if vi in used:
                continue
            if (
                str(s[uid_i]).strip() == str(v[uid_i]).strip()
                and str(s[rid_i]).strip() == str(v[rid_i]).strip()
                and str(s[batch_i]).strip() == str(v[batch_i]).strip()
            ):
                for idx in fill_idxs:
                    if not str(s[idx] or "").strip() and str(v[idx] or "").strip():
                        s[idx] = v[idx]
                used.add(vi)
                break

    for vi, v in enumerate(verify_proj):
        if vi not in used:
            merged.append(v)

    return _recompute_derived_columns(merged)


async def append_verify_record_async(
    workbook_url_or_id: str,
    row: list[str],
    *,
    sheet_name: str = DEFAULT_SHEET,
) -> str:
    """兼容旧接口：验收行写入合并后的「砸金蛋测试记录」。"""
    return await append_smash_record_async(
        workbook_url_or_id, row, sheet_name=sheet_name or DEFAULT_SHEET
    )


def append_verify_record(
    workbook_url_or_id: str,
    row: list[str],
    *,
    sheet_name: str = DEFAULT_SHEET,
) -> str:
    return asyncio.run(
        append_verify_record_async(
            workbook_url_or_id, row, sheet_name=sheet_name
        )
    )
