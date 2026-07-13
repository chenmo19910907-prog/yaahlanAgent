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
    落表「房间内砸蛋次数」须按终身累计归一（见 normalize_room_smash_lifetime），勿直接当终身次数推等级。
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

    if remain_before <= 0:
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
            "roomSmashBefore": room_smash_before,
            "roomSmashAfter": room_smash_before,
            "eggLevel": entry_before.get("eggLevel"),
            "roomSmashCount": room_smash_before,
            "userSmashCount": used_before,
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

    out = dict(raw)
    out.setdefault("userId", user_id)
    out.setdefault("roomId", room_id)
    out["remainBefore"] = remain_before
    out["remainAfter"] = remain_after
    out["usedSmashBefore"] = used_before
    out["usedSmashAfter"] = used_after
    out["roomSmashBefore"] = room_smash_before
    out["roomSmashAfter"] = room_smash_after
    out["eggLevel"] = entry_after.get("eggLevel")
    out["roomSmashCount"] = room_smash_after
    out["userSmashCount"] = used_after
    out["prizePoolPreview"] = _is_prize_pool_preview(out)
    out["smashCount"] = smash_count_from_result(
        out,
        used_before=used_before,
        used_after=used_after,
        room_smash_before=room_smash_before,
        room_smash_after=room_smash_after,
    )
    out["expectedBatch"] = expected_batch_from_remain(remain_before)
    if out["prizePoolPreview"]:
        out["smashCount"] = 0
        out["skipReason"] = "prize_pool_preview"
    return out
