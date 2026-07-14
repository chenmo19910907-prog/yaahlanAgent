"""3周年砸金蛋：自己的房间解析 + 次数判定 + smashEgg。"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BACKDOOR_TPL = _REPO_ROOT / "MOA" / "templates" / "3周年-砸金蛋测试.json"
ANNIVERSARY_EGG_DEFAULT_BATCH = 10


def _parse_json_blob(text: str) -> dict[str, Any]:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError(f"未解析到 JSON: {text[-300:]}")
    return json.loads(text[start : end + 1])


def _moa_python() -> str:
    return shutil.which("python3") or sys.executable


def resolve_own_room_id(user_id: str) -> str:
    """Admin queryUserDetail → ownedRoomInfo.roomId（摘要字段 roomId）。"""
    user_id = str(user_id).strip()
    if not user_id:
        raise ValueError("user_id 不能为空")
    proc = subprocess.run(
        [
            _moa_python(),
            str(_REPO_ROOT / "Admin" / "admin_execute.py"),
            "--query-user-id",
            user_id,
        ],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    text = (proc.stdout or "").strip() or (proc.stderr or "").strip()
    if proc.returncode != 0:
        raise RuntimeError(text[-500:] if text else f"Admin 查询用户失败 exit={proc.returncode}")
    body = _parse_json_blob(text)
    room_id = str(body.get("roomId") or "").strip()
    if not room_id:
        user = body.get("user") if isinstance(body.get("user"), dict) else {}
        room_id = str(user.get("roomId") or "").strip()
    if not room_id:
        raise RuntimeError(f"用户 {user_id} 无自己的房间（ownedRoomInfo.roomId 为空）")
    return room_id


def _run_backdoor_expr(expr: str, *, timeout_ms: int = 60000) -> Any:
    """执行 voga-mts-vas-backdoor execute，返回内层 result。"""
    if not _BACKDOOR_TPL.is_file():
        raise FileNotFoundError(f"缺少模板: {_BACKDOOR_TPL}")
    payload = json.loads(_BACKDOOR_TPL.read_text(encoding="utf-8"))
    payload.pop("_registry", None)
    payload["url"] = "/service/voga-mts-vas-backdoor"
    payload["method"] = "execute"
    payload["params"] = [
        {
            "title": "参数1",
            "name": "1",
            "txt": expr,
            "json": "",
            "type": "string",
            "value": expr,
        }
    ]
    tmp = _REPO_ROOT / ".tmp" / "anniversary_egg_backdoor.json"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    proc = subprocess.run(
        [
            _moa_python(),
            str(_REPO_ROOT / "MOA" / "moa_execute.py"),
            "--payload-file",
            str(tmp),
            "--timeout-ms",
            str(timeout_ms),
        ],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=max(timeout_ms // 1000 + 90, 120),
        check=False,
    )
    text = (proc.stdout or "").strip() or (proc.stderr or "").strip()
    if proc.returncode != 0:
        raise RuntimeError(text[-800:] if text else f"MOA 退出码 {proc.returncode}")
    body = _parse_json_blob(text)
    inner = body.get("result")
    if isinstance(inner, dict) and "result" in inner:
        return inner.get("result")
    return inner


def _as_json_object(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        text = raw.strip()
        if text.startswith("{"):
            return json.loads(text)
    raise RuntimeError(f"期望 JSON object，实际: {raw!r}"[:300])


def get_mystery_count(
    user_id: str,
    room_id: str,
    *,
    type_flag: str = "1",
    timeout_ms: int = 60000,
) -> dict[str, int]:
    """year3Dao.testGetMysteryCount(type, userId, roomId)。

    返回用户 / 房间 / 平台砸蛋次数（神秘保底计数），例如::
        {"user": 35, "room": 52, "platform": 71363}

    type 默认 ``"1"``（与质量平台后门试调一致）。
    """
    user_id = str(user_id).strip()
    room_id = str(room_id).strip()
    type_flag = str(type_flag or "1").strip() or "1"
    if not user_id or not room_id:
        raise ValueError("user_id / room_id 不能为空")
    expr = (
        "return new com.fasterxml.jackson.databind.ObjectMapper()"
        ".writeValueAsString(context.getBean(\"year3Dao\")"
        f'.testGetMysteryCount("{type_flag}","{user_id}","{room_id}"));'
    )
    raw = _run_backdoor_expr(expr, timeout_ms=timeout_ms)
    data = _as_json_object(raw if not isinstance(raw, str) else raw)

    def _to_int(val: Any) -> int:
        if val is None or val == "":
            return 0
        try:
            return int(val)
        except (TypeError, ValueError):
            return 0

    return {
        "user": _to_int(data.get("user")),
        "room": _to_int(data.get("room")),
        "platform": _to_int(data.get("platform")),
        "type": type_flag,
        "userId": user_id,
        "roomId": room_id,
    }


def mystery_guarantee_expected(
    *,
    user_before: int,
    user_after: int,
    room_before: int,
    room_after: int,
    platform_before: int,
    platform_after: int,
    user_mod: int = 50,
    room_mod: int = 100,
    platform_mod: int = 150,
) -> list[str]:
    """根据砸蛋前后神秘计数，按「用户>房间>平台」优先级与顺延规则给出理论触发标签。"""
    # 与落表验收同一算法（避免 workbook 循环依赖，此处内联同等逻辑）
    batch = max(0, int(user_after) - int(user_before))
    if batch <= 0:
        batch = max(0, int(room_after) - int(room_before))
    if batch <= 0:
        return []
    u_mod = int(user_mod or 0)
    r_mod = int(room_mod or 0)
    p_mod = int(platform_mod or 0)
    labels = {
        "user": f"用户保底每{u_mod}次",
        "room": f"房间保底每{r_mod}次",
        "platform": f"平台保底每{p_mod}次",
    }
    priority = ("user", "room", "platform")
    pending: set[str] = set()
    tags: list[str] = []
    ub, rb, pb = int(user_before), int(room_before), int(platform_before)
    for i in range(1, batch + 1):
        newly: set[str] = set()
        if u_mod > 0 and (ub + i) % u_mod == 0:
            newly.add("user")
        if r_mod > 0 and (rb + i) % r_mod == 0:
            newly.add("room")
        if p_mod > 0 and (pb + i) % p_mod == 0:
            newly.add("platform")
        candidates = newly | pending
        if not candidates:
            continue
        winner = next(d for d in priority if d in candidates)
        tags.append(labels[winner])
        pending = candidates - {winner}
    return tags


def get_egg_home(user_id: str, room_id: str, *, timeout_ms: int = 60000) -> dict[str, Any]:
    """year3GiftService.getEggHome(userId, roomId, flag)。

    第三参为数字字符串（如 \"0\"），传 en 会 NumberFormatException。
    关键字段含 remainChances / usedSmashChances。
    """
    user_id = str(user_id).strip()
    room_id = str(room_id).strip()
    expr = (
        "return new com.fasterxml.jackson.databind.ObjectMapper()"
        ".writeValueAsString(context.getBean(\"year3GiftService\")"
        f'.getEggHome("{user_id}","{room_id}","0"));'
    )
    return _as_json_object(_run_backdoor_expr(expr, timeout_ms=timeout_ms))


def get_room_egg_entry(user_id: str, room_id: str, *, timeout_ms: int = 60000) -> dict[str, Any]:
    """year3GiftService.getRoomEggEntry(userId, roomId, true)。

    含 smashCount（房间当前等级内被砸次数，升级后会清零）、eggLevel、userRemainChances 等。
    落表「房间内/用户/平台砸蛋次数」改用 year3Dao.testGetMysteryCount；本接口 smashCount 仅作等级内辅助。
    """
    user_id = str(user_id).strip()
    room_id = str(room_id).strip()
    expr = (
        "return new com.fasterxml.jackson.databind.ObjectMapper()"
        ".writeValueAsString(context.getBean(\"year3GiftService\")"
        f'.getRoomEggEntry("{user_id}","{room_id}",true));'
    )
    return _as_json_object(_run_backdoor_expr(expr, timeout_ms=timeout_ms))


def get_remain_chance(user_id: str, room_id: str, *, timeout_ms: int = 60000) -> int:
    """用户剩余砸蛋次数：优先 getEggHome.remainChances / roomEntry.userRemainChances。"""
    home = get_egg_home(user_id, room_id, timeout_ms=timeout_ms)
    if home.get("remainChances") is not None:
        return int(home["remainChances"])
    entry = get_room_egg_entry(user_id, room_id, timeout_ms=timeout_ms)
    if entry.get("userRemainChances") is not None:
        return int(entry["userRemainChances"])
    return 0


def expected_batch_from_remain(remaining: int) -> int:
    """产品默认：剩余>10 → 10；剩余≤10 → 剩余；剩余≤0 → 0。"""
    left = int(remaining)
    if left <= 0:
        return 0
    return min(ANNIVERSARY_EGG_DEFAULT_BATCH, left)


# 无次数时 smashEgg 常返回的 LV 奖池预览礼物（中/英名）
_PRIZE_POOL_NAMES = frozenset(
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


def _is_prize_pool_preview(smash_result: dict[str, Any]) -> bool:
    """无砸蛋次数时的奖池预览：不应记为真实砸蛋。

    特征：type=0 且奖品为 PACKAGE_GIFT 配置池（Celestial Twins / ak47 / lipstick 等）。
    """
    prizes = smash_result.get("prizes")
    if not isinstance(prizes, list) or not prizes:
        return int(smash_result.get("type") or 0) == 0

    names = {
        str(p.get("prizeName") or p.get("name") or "").strip()
        for p in prizes
        if isinstance(p, dict)
    }
    if names and names <= _PRIZE_POOL_NAMES:
        return True

    if int(smash_result.get("type") or 0) != 0:
        return False
    types = {str(p.get("prizeType") or "") for p in prizes if isinstance(p, dict)}
    return types == {"PACKAGE_GIFT"}


def is_real_smash_result(smash_result: dict[str, Any]) -> bool:
    """是否为应写入表格的真实砸蛋结果。"""
    if not isinstance(smash_result, dict):
        return False
    if smash_result.get("prizePoolPreview") or _is_prize_pool_preview(smash_result):
        return False
    try:
        count = int(smash_result.get("smashCount") or 0)
    except (TypeError, ValueError):
        count = 0
    return count > 0


def smash_count_from_result(
    smash_result: dict[str, Any],
    *,
    used_before: int | None = None,
    used_after: int | None = None,
    room_smash_before: int | None = None,
    room_smash_after: int | None = None,
) -> int:
    """本次砸蛋次数：优先响应字段，再用 usedSmashChances / 房间 smashCount 差值。"""
    for key in ("smashCount", "count", "smashTimes", "times"):
        # smashEgg 响应本身通常无该字段；若有则信任
        val = smash_result.get(key)
        if val is None:
            continue
        try:
            n = int(val)
        except (TypeError, ValueError):
            continue
        if n > 0:
            return n

    if used_before is not None and used_after is not None:
        delta = int(used_after) - int(used_before)
        if delta > 0:
            return delta

    if room_smash_before is not None and room_smash_after is not None:
        delta = int(room_smash_after) - int(room_smash_before)
        if delta > 0:
            return delta

    if _is_prize_pool_preview(smash_result):
        return 0

    # 兜底：真实奖励列表里，一蛋常对应多条 prize；用非奖池条数无法稳定还原。
    # 若只有差值都为 0，返回 0，避免再误写成 1。
    return 0


def smash_egg_once(
    *,
    user_id: str,
    room_id: str,
    lang: str = "en",
    timeout_ms: int = 60000,
) -> dict[str, Any]:
    """砸一次：返回归一化结果，含 smashCount（由返回值相关快照差值判定）。

    剩余次数为 0 时不调用 smashEgg，直接标记为奖池/无次数，避免落表脏数据。
    """
    user_id = str(user_id).strip()
    room_id = str(room_id).strip()
    lang = str(lang or "en").strip() or "en"

    home_before = get_egg_home(user_id, room_id, timeout_ms=timeout_ms)
    entry_before = get_room_egg_entry(user_id, room_id, timeout_ms=timeout_ms)
    remain_before = int(home_before.get("remainChances") or entry_before.get("userRemainChances") or 0)
    used_before = int(home_before.get("usedSmashChances") or 0)
    room_smash_before = int(entry_before.get("smashCount") or 0)
    try:
        myst_before = get_mystery_count(user_id, room_id, timeout_ms=timeout_ms)
    except Exception:
        myst_before = None

    if remain_before <= 0:
        myst_room = myst_before["room"] if myst_before else room_smash_before
        myst_user = myst_before["user"] if myst_before else used_before
        myst_plat = myst_before["platform"] if myst_before else None
        return {
            "userId": user_id,
            "roomId": room_id,
            "type": 0,
            "prizes": [],
            "mysteryPrizes": [],
            "remainBefore": remain_before,
            "remainAfter": remain_before,
            "usedSmashBefore": used_before,
            "usedSmashAfter": used_before,
            # 金蛋当前等级内计数（getRoomEggEntry）
            "roomEggSmashBefore": room_smash_before,
            "roomEggSmashAfter": room_smash_before,
            # 落表三列：year3Dao.testGetMysteryCount
            "roomSmashBefore": myst_room,
            "roomSmashAfter": myst_room,
            "roomSmashCount": myst_room,
            "userSmashBefore": myst_user,
            "userSmashCount": myst_user,
            "platformSmashBefore": myst_plat,
            "platformSmashCount": myst_plat,
            "eggLevel": entry_before.get("eggLevel"),
            "mysteryCountBefore": myst_before,
            "mysteryCountAfter": myst_before,
            "smashCount": 0,
            "expectedBatch": 0,
            "prizePoolPreview": True,
            "skipReason": "remainChances=0",
        }

    expr = (
        f'return context.getBean("year3GiftService")'
        f'.smashEgg("{user_id}","{room_id}","{lang}");'
    )
    raw = _run_backdoor_expr(expr, timeout_ms=timeout_ms)
    if not isinstance(raw, dict):
        raise RuntimeError(f"smashEgg 返回非 object: {raw!r}")

    home_after = get_egg_home(user_id, room_id, timeout_ms=timeout_ms)
    entry_after = get_room_egg_entry(user_id, room_id, timeout_ms=timeout_ms)
    remain_after = int(home_after.get("remainChances") or entry_after.get("userRemainChances") or 0)
    used_after = int(home_after.get("usedSmashChances") or 0)
    room_smash_after = int(entry_after.get("smashCount") or 0)
    try:
        myst_after = get_mystery_count(user_id, room_id, timeout_ms=timeout_ms)
    except Exception:
        myst_after = None

    out = dict(raw)
    out.setdefault("userId", user_id)
    out.setdefault("roomId", room_id)
    out["remainBefore"] = remain_before
    out["remainAfter"] = remain_after
    out["usedSmashBefore"] = used_before
    out["usedSmashAfter"] = used_after
    # 保留金蛋等级内计数，供 smashCount 差值与等级状态机
    out["roomEggSmashBefore"] = room_smash_before
    out["roomEggSmashAfter"] = room_smash_after
    out["eggLevel"] = entry_after.get("eggLevel")
    out["prizePoolPreview"] = _is_prize_pool_preview(out)
    out["smashCount"] = smash_count_from_result(
        out,
        used_before=used_before,
        used_after=used_after,
        room_smash_before=room_smash_before,
        room_smash_after=room_smash_after,
    )
    out["expectedBatch"] = expected_batch_from_remain(remain_before)

    # 落表：房间内/用户/平台砸蛋次数一律 year3Dao.testGetMysteryCount
    if myst_before and myst_after:
        out["mysteryCountBefore"] = myst_before
        out["mysteryCountAfter"] = myst_after
        out["roomSmashBefore"] = myst_before["room"]
        out["roomSmashAfter"] = myst_after["room"]
        out["roomSmashCount"] = myst_after["room"]
        out["mysteryRoomBefore"] = myst_before["room"]
        out["mysteryRoomAfter"] = myst_after["room"]
        out["userSmashBefore"] = myst_before["user"]
        out["userSmashCount"] = myst_after["user"]
        out["platformSmashBefore"] = myst_before["platform"]
        out["platformSmashCount"] = myst_after["platform"]
    else:
        out["mysteryCountBefore"] = myst_before
        out["mysteryCountAfter"] = myst_after
        out["roomSmashBefore"] = room_smash_before
        out["roomSmashAfter"] = room_smash_after
        out["roomSmashCount"] = room_smash_after
        out["userSmashCount"] = used_after

    if out["prizePoolPreview"]:
        out["smashCount"] = 0
        out["skipReason"] = "prize_pool_preview"
    return out
