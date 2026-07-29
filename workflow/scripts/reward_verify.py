#!/usr/bin/env python3
"""奖励下发验收：快照用户资产、对比前后增量、验证背包礼物数量/价值/有效期、装扮有效期与钻石记录。"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
_PROP_TYPES_PATH = _REPO / "MOA/config/prop_types.json"
_DIAMOND_HISTORY_BODY = _REPO / "MOA-generative/templates/example-diamondHistory.body.json"
_DIAMOND_HISTORY_SERVICE = "/service/yaahlan/components/wallet-api"
_DIAMOND_HISTORY_METHOD = "diamondHistory"
_DEFAULT_PROP_TYPES = (
    "10043",
    "10045",
    "10069",
    "10177",
    "10180",
    "10182",
    "10183",
    "10140",
    "10144",
)
SNAPSHOT_VERSION = 3
_DEFAULT_DIAMOND_HISTORY_LIMIT = 30


def _run(cmd: list[str], *, timeout: int = 180) -> tuple[int, str, str]:
    proc = subprocess.run(
        cmd,
        cwd=str(_REPO),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def _json_from_stdout(stdout: str) -> dict[str, Any]:
    if "{" not in stdout:
        return {}
    return json.loads(stdout[stdout.find("{") : stdout.rfind("}") + 1])


def _load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"JSON 须为对象: {path}")
    return data


def query_diamond(user_id: str) -> int | None:
    rc, out, _ = _run(
        [
            "python3",
            "MOA/moa_execute.py",
            "--payload-file",
            "MOA/templates/钻石-查询余额.json",
            "--diamond-query-user-id",
            user_id,
        ]
    )
    if rc != 0:
        return None
    data = _json_from_stdout(out)
    if "diamonds" in data:
        return int(data["diamonds"])
    raw = data.get("raw") or data.get("result") or data
    if isinstance(raw, dict):
        inner = raw.get("result") if isinstance(raw.get("result"), dict) else raw
        val = inner.get("data") if isinstance(inner.get("data"), (int, float, str)) else None
        if val is not None:
            return int(float(val))
    return None


def _call_moa_direct(service_uri: str, method: str, body: dict[str, Any]) -> dict[str, Any]:
    gift_dir = _REPO / "Gift"
    if str(gift_dir) not in sys.path:
        sys.path.insert(0, str(gift_dir))
    from gift.send_stage import StageGiftError, call_moa  # noqa: WPS433

    header_s = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
    try:
        result = call_moa(service_uri, method, [body], headers=header_s)
    except StageGiftError as exc:
        raise RuntimeError(str(exc.message)) from exc
    if not isinstance(result, dict):
        raise RuntimeError(f"MOA 返回非 object: {result!r}")
    ec = result.get("ec")
    if ec not in (0, 200, "0", "200"):
        raise RuntimeError(f"MOA 业务失败: ec={ec}, em={result.get('em')}")
    data = result.get("data")
    return data if isinstance(data, dict) else {}


def query_diamond_history(
    user_id: str,
    *,
    page_size: int = 20,
    last_id: str = "0",
    record_type: str = "",
) -> list[dict[str, Any]]:
    template = json.loads(_DIAMOND_HISTORY_BODY.read_text(encoding="utf-8"))
    body = dict(template)
    uid = str(user_id).strip()
    body["userId"] = uid
    body["uid"] = uid
    body["pageSize"] = str(max(1, page_size))
    body["lastId"] = str(last_id)
    body["type"] = record_type
    data = _call_moa_direct(_DIAMOND_HISTORY_SERVICE, _DIAMOND_HISTORY_METHOD, body)
    items = data.get("list")
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _record_source_text(entry: dict[str, Any]) -> str:
    parts = [entry.get("desc"), entry.get("rechargeMethod"), entry.get("type")]
    return " | ".join(str(p) for p in parts if p)


def _find_diamond_record(
    records: list[dict[str, Any]],
    *,
    amount: int,
    source_contains: str | None = None,
    since_ms: int | None = None,
) -> dict[str, Any] | None:
    needle = (source_contains or "").strip().lower()
    for entry in records:
        diff = entry.get("diamondDiff")
        try:
            diff_val = int(diff)
        except (TypeError, ValueError):
            continue
        if diff_val != amount:
            continue
        if since_ms is not None:
            create_ms = _parse_expire_ms(entry.get("createTime"))
            if create_ms is None or create_ms < since_ms:
                continue
        if needle:
            hay = _record_source_text(entry).lower()
            if needle not in hay:
                continue
        return entry
    return None


def query_nameplates(user_id: str, *, since: int = 0) -> dict[str, dict[str, Any]]:
    """铭牌页 nameplatePageData（Tunnel 自动读取，无需人工验收）。"""
    cmd = [
        "python3",
        "MOA-generative/scripts/form_nameplate_page.py",
        "--user-id",
        user_id,
    ]
    if since > 0:
        cmd.extend(["--since", str(since)])
    rc, out, _ = _run(cmd)
    data = _json_from_stdout(out)
    if not data.get("ok"):
        return {}
    plates = data.get("nameplates")
    return plates if isinstance(plates, dict) else {}


def query_cp_medals(
    user_id: str,
    *,
    cp_user_id: str = "",
    intimate_id: str = "",
) -> dict[str, int]:
    cmd = [
        "python3",
        "MOA-generative/scripts/form_cp_space_medals.py",
        "--user-id",
        user_id,
        "--strict",
        "0",
    ]
    if cp_user_id:
        cmd.extend(["--cp-user-id", cp_user_id])
    if intimate_id:
        cmd.extend(["--intimate-id", intimate_id])
    rc, out, _ = _run(cmd)
    if rc != 0:
        return {}
    data = _json_from_stdout(out)
    summary = data.get("cpMedalSummary") or {}
    medals: dict[str, int] = {}
    for item in summary.get("medals") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("medalName") or "").strip()
        if not name:
            continue
        medals[name] = int(item.get("num") or 0)
    return medals


def query_backpack_gifts(user_id: str) -> dict[str, dict[str, Any]]:
    rc, out, _ = _run(
        ["python3", "MOA/scripts/gift_panel_backpack_view.py", "--user-id", user_id, "--moa-only"]
    )
    data = _json_from_stdout(out)
    gifts: dict[str, dict[str, Any]] = {}
    for item in data.get("backpackGifts") or []:
        if not isinstance(item, dict):
            continue
        gid = str(item.get("giftId") or item.get("productId") or item.get("bid") or item.get("id") or "")
        if not gid:
            continue
        pkg = item.get("package") if isinstance(item.get("package"), dict) else {}
        remain = pkg.get("remain") if pkg else item.get("remain")
        expire = pkg.get("expire") if pkg else item.get("expire")
        price = item.get("price") if item.get("price") is not None else item.get("nominalPrice")
        gifts[gid] = {
            "giftId": gid,
            "name": item.get("name"),
            "remain": int(remain) if remain is not None else None,
            "price": float(price) if price is not None else None,
            "expire": expire,
            "expireLabel": pkg.get("label") if pkg else item.get("expireLabel"),
        }
    return gifts


def query_props(user_id: str, prop_type: str) -> dict[str, dict[str, Any]]:
    rc, out, _ = _run(
        [
            "python3",
            "MOA/moa_execute.py",
            "--payload-file",
            "MOA/templates/装扮-查询用户拥有道具.json",
            "--user-prop-query-user-id",
            user_id,
            "--user-prop-type-code",
            prop_type,
        ]
    )
    data = _json_from_stdout(out)
    props: dict[str, dict[str, Any]] = {}
    items = data.get("items") if isinstance(data.get("items"), list) else None
    if items is None:
        raw = data.get("raw") or {}
        result = raw.get("result") if isinstance(raw.get("result"), dict) else raw
        inner = result.get("result") if isinstance(result.get("result"), dict) else result
        payload = inner.get("data") if isinstance(inner.get("data"), dict) else inner.get("data")
        items = payload if isinstance(payload, list) else (payload or {}).get("list") if isinstance(payload, dict) else []
    if isinstance(items, list):
        for it in items:
            if isinstance(it, dict):
                pid = str(it.get("propId") or it.get("id") or "")
                if pid:
                    props[pid] = it
    return props


def _normalize_prop_item(item: dict[str, Any], *, prop_type_code: str) -> dict[str, Any]:
    return {
        "propId": str(item.get("propId") or item.get("id") or ""),
        "propName": item.get("propName") or item.get("name"),
        "propTypeCode": prop_type_code,
        "expireTime": item.get("expireTime") or item.get("expire"),
        "propUseEndTime": item.get("propUseEndTime"),
        "validityPeriod": item.get("validityPeriod"),
        "wearStatus": item.get("wearStatus"),
        "count": item.get("count"),
    }


def snapshot_user(
    user_id: str,
    *,
    prop_types: list[str] | None = None,
    cp_user_id: str = "",
    intimate_id: str = "",
    diamond_history_limit: int = _DEFAULT_DIAMOND_HISTORY_LIMIT,
    include_diamond_history: bool = True,
    include_nameplates: bool = False,
    nameplate_tunnel_since: int = 0,
) -> dict[str, Any]:
    types = prop_types or list(_DEFAULT_PROP_TYPES)
    props_by_type: dict[str, dict[str, dict[str, Any]]] = {}
    props_flat: dict[str, dict[str, Any]] = {}
    for pt in types:
        raw = query_props(user_id, pt)
        normalized = {
            pid: _normalize_prop_item(item, prop_type_code=pt)
            for pid, item in raw.items()
            if isinstance(item, dict)
        }
        props_by_type[pt] = normalized
        for pid, item in normalized.items():
            props_flat[pid] = item

    diamond_history: list[dict[str, Any]] = []
    if include_diamond_history:
        try:
            diamond_history = query_diamond_history(user_id, page_size=max(1, diamond_history_limit))
        except RuntimeError:
            diamond_history = []

    snap: dict[str, Any] = {
        "snapshotVersion": SNAPSHOT_VERSION,
        "userId": user_id,
        "ts": int(time.time()),
        "tsIso": datetime.now(timezone.utc).isoformat(),
        "diamond": query_diamond(user_id),
        "diamondHistory": diamond_history,
        "backpackGifts": query_backpack_gifts(user_id),
        "propsByType": props_by_type,
        "props": props_flat,
    }
    if cp_user_id or intimate_id:
        snap["cpMedals"] = query_cp_medals(
            user_id,
            cp_user_id=cp_user_id,
            intimate_id=intimate_id,
        )
        include_nameplates = True
    if include_nameplates:
        snap["nameplates"] = query_nameplates(user_id, since=nameplate_tunnel_since)
    return snap


def _parse_expire_ms(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        ms = int(value)
        return ms if ms > 1_000_000_000_000 else ms * 1000
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        ms = int(text)
        return ms if ms > 1_000_000_000_000 else ms * 1000
    for fmt in (
        "%Y-%m-%d %H:%M:%S %z",
        "%Y-%m-%d %H:%M:%S",
    ):
        try:
            dt = datetime.strptime(text.replace(" +0800", " +0800"), fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return int(dt.timestamp() * 1000)
        except ValueError:
            continue
    cleaned = text.replace(" +0800", "").strip()
    try:
        dt = datetime.strptime(cleaned, "%Y-%m-%d %H:%M:%S")
        return int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000)
    except ValueError:
        return None


def _gift_is_valid(gift: dict[str, Any], *, now_ms: int) -> bool:
    expire_ms = _parse_expire_ms(gift.get("expire"))
    if expire_ms is None:
        return True
    return expire_ms > now_ms


def _expected_gift_price(reward: dict[str, Any]) -> float | None:
    for key in ("price", "diamondValue", "value", "giftValue"):
        raw = reward.get(key)
        if raw is None or raw == "":
            continue
        return float(raw)
    return None


def _gift_price_matches(actual: Any, expected: float, *, tolerance: float = 0.01) -> bool:
    if actual is None:
        return False
    return abs(float(actual) - expected) <= tolerance


def _prop_days(prop: dict[str, Any], *, reference_ts: int) -> float | None:
    expire_ms = _parse_expire_ms(prop.get("expireTime") or prop.get("expire"))
    if expire_ms is None:
        return None
    return (expire_ms / 1000 - reference_ts) / 86400


def _format_ts_label(ms: int | None) -> str | None:
    if ms is None:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _load_prop_type_labels() -> dict[str, str]:
    if not _PROP_TYPES_PATH.is_file():
        return {}
    try:
        data = json.loads(_PROP_TYPES_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    types = data.get("types")
    return {str(k): str(v) for k, v in types.items()} if isinstance(types, dict) else {}


def _validity_days_between(before_value: Any, after_value: Any) -> float | None:
    before_ms = _parse_expire_ms(before_value)
    after_ms = _parse_expire_ms(after_value)
    if before_ms is None or after_ms is None:
        return None
    return round((after_ms - before_ms) / 86_400_000, 2)


def _format_days_label(days: float | None) -> str:
    if days is None:
        return "—"
    if days >= 365:
        return f"{days:.1f} 天（约 {days / 365:.1f} 年）"
    return f"{days:.2f} 天"


def _enrich_gift_diff_entry(entry: dict[str, Any], *, reference_ts: int) -> dict[str, Any]:
    expire_after = entry.get("expireAfter")
    expire_ms = _parse_expire_ms(expire_after)
    price = entry.get("price")
    remain_delta = int(entry.get("remainDelta") or 0)
    enriched = dict(entry)
    enriched["expireAfterLabel"] = _format_ts_label(expire_ms) or (
        str(expire_after) if expire_after is not None else None
    )
    expire_days = _prop_days({"expire": expire_after}, reference_ts=reference_ts)
    if expire_days is not None:
        enriched["validityDays"] = round(expire_days, 2)
    if price is not None and remain_delta > 0:
        enriched["totalDiamondValue"] = round(float(price) * remain_delta, 2)
    enriched["issued"] = remain_delta > 0
    return enriched


def _enrich_prop_diff_entry(entry: dict[str, Any], *, reference_ts: int) -> dict[str, Any]:
    expire_before = entry.get("expireTimeBefore")
    expire_after = entry.get("expireTimeAfter")
    before_ms = _parse_expire_ms(expire_before)
    after_ms = _parse_expire_ms(expire_after)
    status = str(entry.get("status") or "")
    enriched = dict(entry)
    enriched["expireTimeBeforeLabel"] = _format_ts_label(before_ms) or (
        str(expire_before) if expire_before is not None else None
    )
    enriched["expireTimeAfterLabel"] = _format_ts_label(after_ms) or (
        str(expire_after) if expire_after is not None else None
    )
    if status == "new":
        actual_days = _prop_days({"expireTime": expire_after}, reference_ts=reference_ts)
    elif status == "changed":
        ref_ms = reference_ts * 1000
        if before_ms is not None and before_ms <= ref_ms:
            # 发奖前已过期：按本次新发计剩余有效期，不用旧 expire→新 expire 日历差
            actual_days = _prop_days({"expireTime": expire_after}, reference_ts=reference_ts)
        else:
            actual_days = _validity_days_between(expire_before, expire_after)
    else:
        actual_days = None
    if actual_days is not None:
        enriched["actualIssuedDays"] = round(actual_days, 2)
    enriched["issued"] = status in ("new", "changed") and (
        status == "new" or before_ms != after_ms
    )
    return enriched


def _issued_gifts_from_diff(diff: dict[str, Any]) -> list[dict[str, Any]]:
    reference_ts = int(diff.get("afterTs") or diff.get("beforeTs") or time.time())
    issued: list[dict[str, Any]] = []
    for item in diff.get("backpackGifts") or []:
        if not isinstance(item, dict):
            continue
        enriched = item if item.get("issued") is not None else _enrich_gift_diff_entry(
            item, reference_ts=reference_ts
        )
        if enriched.get("issued") or int(enriched.get("remainDelta") or 0) > 0:
            issued.append(enriched)
    return issued


def _issued_props_from_diff(diff: dict[str, Any]) -> list[dict[str, Any]]:
    reference_ts = int(diff.get("afterTs") or diff.get("beforeTs") or time.time())
    issued: list[dict[str, Any]] = []
    for item in diff.get("props") or []:
        if not isinstance(item, dict):
            continue
        enriched = item if item.get("issued") is not None else _enrich_prop_diff_entry(
            item, reference_ts=reference_ts
        )
        if enriched.get("issued"):
            issued.append(enriched)
        elif str(enriched.get("status") or "") in ("new", "changed"):
            issued.append(enriched)
    return issued


def _enrich_nameplate_diff_entry(entry: dict[str, Any], *, reference_ts: int) -> dict[str, Any]:
    remain_before = entry.get("remainTimeBefore")
    remain_after = entry.get("remainTimeAfter")
    remain_days_before = entry.get("remainDaysBefore")
    remain_days_after = entry.get("remainDaysAfter")
    newly_unlocked = bool(entry.get("newlyUnlocked"))
    unlocked_after = bool(entry.get("unlockedAfter"))

    enriched = dict(entry)
    if entry.get("unlockTimeBeforeLabel"):
        enriched["unlockTimeBeforeLabel"] = entry.get("unlockTimeBeforeLabel")
    elif entry.get("unlockTimeBefore") is not None:
        unlock_before_ms = _parse_expire_ms(entry.get("unlockTimeBefore"))
        enriched["unlockTimeBeforeLabel"] = _format_ts_label(unlock_before_ms)

    if entry.get("unlockTimeAfterLabel"):
        enriched["unlockTimeAfterLabel"] = entry.get("unlockTimeAfterLabel")
    elif entry.get("unlockTimeAfter") is not None:
        unlock_after_ms = _parse_expire_ms(entry.get("unlockTimeAfter"))
        enriched["unlockTimeAfterLabel"] = _format_ts_label(unlock_after_ms)

    actual_days: float | None = None
    if newly_unlocked and remain_days_after is not None:
        actual_days = float(remain_days_after)
    elif (
        isinstance(remain_before, (int, float))
        and isinstance(remain_after, (int, float))
        and remain_after > remain_before
    ):
        actual_days = round((float(remain_after) - float(remain_before)) / 86_400, 2)
    elif (
        remain_days_before is not None
        and remain_days_after is not None
        and float(remain_days_after) > float(remain_days_before)
    ):
        actual_days = round(float(remain_days_after) - float(remain_days_before), 2)

    if actual_days is not None:
        enriched["actualIssuedDays"] = actual_days

    expire_ms: int | None = None
    unlock_after = entry.get("unlockTimeAfter")
    if isinstance(unlock_after, (int, float)) and isinstance(remain_after, (int, float)):
        expire_ms = int(unlock_after) * 1000 + int(remain_after) * 1000
    elif isinstance(remain_after, (int, float)):
        expire_ms = int(reference_ts + float(remain_after)) * 1000
    enriched["expireAfterLabel"] = _format_ts_label(expire_ms)

    remain_increased = (
        isinstance(remain_before, (int, float))
        and isinstance(remain_after, (int, float))
        and remain_after > remain_before
    )
    days_increased = (
        remain_days_before is not None
        and remain_days_after is not None
        and float(remain_days_after) > float(remain_days_before)
    )
    enriched["issued"] = unlocked_after and (newly_unlocked or remain_increased or days_increased)
    return enriched


def _issued_nameplates_from_diff(diff: dict[str, Any]) -> list[dict[str, Any]]:
    reference_ts = int(diff.get("afterTs") or diff.get("beforeTs") or time.time())
    issued: list[dict[str, Any]] = []
    for item in diff.get("nameplates") or []:
        if not isinstance(item, dict):
            continue
        enriched = item if item.get("issued") is not None else _enrich_nameplate_diff_entry(
            item, reference_ts=reference_ts
        )
        if enriched.get("issued"):
            issued.append(enriched)
        elif enriched.get("newlyUnlocked"):
            issued.append(enriched)
    return issued


def format_diff_report(
    diff: dict[str, Any],
    *,
    title: str = "奖励下发验收报告",
    user_label: str = "",
) -> str:
    """将 diff JSON 格式化为 Markdown 测试报告（装扮/铭牌有效期、礼物钻价/有效期）。"""
    prop_labels = _load_prop_type_labels()
    user_id = str(diff.get("userId") or "")
    label = user_label.strip() or user_id
    diamond = diff.get("diamond") if isinstance(diff.get("diamond"), dict) else {}
    issued_gifts = _issued_gifts_from_diff(diff)
    issued_props = _issued_props_from_diff(diff)
    issued_nameplates = _issued_nameplates_from_diff(diff)

    lines = [
        f"# {title}",
        "",
        f"- **用户**：{label}" + (f"（userId `{user_id}`）" if label != user_id else ""),
        f"- **快照区间**：beforeTs={diff.get('beforeTs')} → afterTs={diff.get('afterTs')}",
    ]
    if diamond:
        lines.append(
            f"- **钻石余额**：{diamond.get('before')} → {diamond.get('after')}（Δ{diamond.get('delta')}）"
        )
    lines += ["", "## 个人装扮（实际下发）", ""]
    if issued_props:
        lines += [
            "| 装扮ID | 名称 | 类型 | 下发状态 | 实际下发有效期 | 到期时间 |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for item in issued_props:
            ptc = str(item.get("propTypeCode") or "")
            type_label = prop_labels.get(ptc, ptc or "—")
            actual_days = item.get("actualIssuedDays")
            lines.append(
                "| {propId} | {name} | {type_label} | {status} | {validity} | {expire} |".format(
                    propId=item.get("propId") or "—",
                    name=item.get("propName") or "—",
                    type_label=type_label,
                    status=item.get("status") or "—",
                    validity=_format_days_label(
                        float(actual_days) if actual_days is not None else None
                    ),
                    expire=item.get("expireTimeAfterLabel")
                    or item.get("expireTimeAfter")
                    or "—",
                )
            )
    else:
        lines.append("_无新增/延期的个人装扮变化_")

    lines += ["", "## 礼物背包（实际下发）", ""]
    if issued_gifts:
        lines += [
            "| 礼物ID | 名称 | 数量+ | 单价(钻) | 下发总价值(钻) | 有效期 | 到期时间 |",
            "| --- | --- | ---: | ---: | ---: | --- | --- |",
        ]
        for item in issued_gifts:
            price = item.get("price")
            lines.append(
                "| {giftId} | {name} | +{delta} | {price} | {total} | {validity} | {expire} |".format(
                    giftId=item.get("giftId") or "—",
                    name=item.get("name") or "—",
                    delta=item.get("remainDelta") or 0,
                    price=price if price is not None else "—",
                    total=item.get("totalDiamondValue")
                    if item.get("totalDiamondValue") is not None
                    else "—",
                    validity=_format_days_label(
                        float(item["validityDays"]) if item.get("validityDays") is not None else None
                    ),
                    expire=item.get("expireAfterLabel") or item.get("expireAfter") or "—",
                )
            )
    else:
        lines.append("_无新增背包礼物_")

    lines += ["", "## 铭牌（实际下发）", ""]
    if issued_nameplates:
        lines += [
            "| 铭牌ID | 名称 | 下发状态 | 实际下发有效期 | 剩余有效期 | 解锁时间 | 到期时间 |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        for item in issued_nameplates:
            actual_days = item.get("actualIssuedDays")
            remain_days = item.get("remainDaysAfter")
            status = "新解锁" if item.get("newlyUnlocked") else "续期"
            lines.append(
                "| {nid} | {title} | {status} | {issued} | {remain} | {unlock} | {expire} |".format(
                    nid=item.get("nameplateId") or "—",
                    title=item.get("title") or "—",
                    status=status,
                    issued=_format_days_label(
                        float(actual_days) if actual_days is not None else None
                    ),
                    remain=_format_days_label(
                        float(remain_days) if remain_days is not None else None
                    ),
                    unlock=item.get("unlockTimeAfterLabel")
                    or item.get("unlockTimeAfter")
                    or "—",
                    expire=item.get("expireAfterLabel") or "—",
                )
            )
    else:
        lines.append("_无新增/续期铭牌变化_")

    hist = diff.get("diamondHistoryNew") if isinstance(diff.get("diamondHistoryNew"), list) else []
    if hist:
        lines += ["", "## 钻石记录（新增）", ""]
        lines += ["| 变动(钻) | 描述 | 时间 |", "| ---: | --- | --- |"]
        for row in hist:
            if not isinstance(row, dict):
                continue
            lines.append(
                f"| {row.get('diamondDiff')} | {row.get('desc') or '—'} | {row.get('createTimeLabel') or '—'} |"
            )

    medals = diff.get("cpMedals") if isinstance(diff.get("cpMedals"), list) else []
    medal_issued = [
        m for m in medals if isinstance(m, dict) and int(m.get("countDelta") or 0) > 0
    ]
    if medal_issued:
        lines += ["", "## CP 勋章（实际下发）", ""]
        lines += ["| 勋章 | 数量+ | 变更后 |", "| --- | ---: | ---: |"]
        for item in medal_issued:
            lines.append(
                f"| {item.get('medalName') or '—'} | +{item.get('countDelta')} | {item.get('countAfter')} |"
            )

    lines.append("")
    return "\n".join(lines)


def _diamond_history_since(
    records: list[dict[str, Any]],
    *,
    since_ms: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for entry in records:
        create_ms = _parse_expire_ms(entry.get("createTime"))
        if create_ms is None or create_ms < since_ms:
            continue
        diff = entry.get("diamondDiff")
        try:
            diff_val = float(diff)
        except (TypeError, ValueError):
            continue
        rows.append(
            {
                "diamondDiff": diff_val,
                "desc": entry.get("desc") or entry.get("rechargeMethod"),
                "createTime": create_ms,
                "createTimeLabel": _format_ts_label(create_ms),
            }
        )
    rows.sort(key=lambda x: x.get("createTime") or 0)
    return rows


def diff_snapshots(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """发奖前后快照求差：钻石余额/记录、背包礼物、装扮、CP 勋章。"""
    user_id = str(after.get("userId") or before.get("userId") or "")
    before_ts = int(before.get("ts") or 0)
    after_ts = int(after.get("ts") or before_ts)
    reference_ts = after_ts or before_ts

    bd = before.get("diamond")
    ad = after.get("diamond")
    diamond_delta = (ad - bd) if bd is not None and ad is not None else None

    after_hist = after.get("diamondHistory") if isinstance(after.get("diamondHistory"), list) else []
    if not after_hist:
        try:
            after_hist = query_diamond_history(user_id, page_size=_DEFAULT_DIAMOND_HISTORY_LIMIT)
        except RuntimeError:
            after_hist = []
    since_ms = before_ts * 1000 - 60_000 if before_ts else 0
    diamond_history_new = _diamond_history_since(after_hist, since_ms=since_ms)

    bg = before.get("backpackGifts") or {}
    ag = after.get("backpackGifts") or {}
    gift_ids = sorted(set(bg) | set(ag))
    backpack_changes: list[dict[str, Any]] = []
    for gid in gift_ids:
        b = bg.get(gid) or {}
        a = ag.get(gid) or {}
        before_remain = int(b.get("remain") or 0)
        after_remain = int(a.get("remain") or 0)
        delta = after_remain - before_remain
        if delta == 0 and gid not in ag:
            continue
        entry: dict[str, Any] = {
            "giftId": gid,
            "name": a.get("name") or b.get("name"),
            "remainBefore": before_remain,
            "remainAfter": after_remain,
            "remainDelta": delta,
            "price": a.get("price") if a.get("price") is not None else b.get("price"),
            "expireBefore": b.get("expire"),
            "expireAfter": a.get("expire"),
        }
        expire_days = _prop_days(a, reference_ts=reference_ts) if a else None
        if expire_days is not None:
            entry["expireDaysAfter"] = round(expire_days, 2)
        backpack_changes.append(_enrich_gift_diff_entry(entry, reference_ts=reference_ts))

    bprops = before.get("props") or {}
    if not bprops and before.get("propsByType"):
        for items in (before.get("propsByType") or {}).values():
            if isinstance(items, dict):
                bprops.update(items)
    aprops = after.get("props") or {}
    if not aprops and after.get("propsByType"):
        for items in (after.get("propsByType") or {}).values():
            if isinstance(items, dict):
                aprops.update(items)
    prop_ids = sorted(set(bprops) | set(aprops))
    prop_changes: list[dict[str, Any]] = []
    for pid in prop_ids:
        b = bprops.get(pid) or {}
        a = aprops.get(pid) or {}
        if not a and not b:
            continue
        expire_before = b.get("expireTime")
        expire_after = a.get("expireTime")
        if pid in bprops and pid in aprops and expire_before == expire_after:
            continue
        if not a:
            prop_changes.append(
                {
                    "propId": pid,
                    "propName": b.get("propName"),
                    "propTypeCode": b.get("propTypeCode"),
                    "status": "removed",
                    "expireTimeBefore": expire_before,
                }
            )
            continue
        expire_days = _prop_days(a, reference_ts=reference_ts)
        prop_changes.append(
            _enrich_prop_diff_entry(
                {
                    "propId": pid,
                    "propName": a.get("propName") or b.get("propName"),
                    "propTypeCode": a.get("propTypeCode") or b.get("propTypeCode"),
                    "status": "new" if pid not in bprops else "changed",
                    "expireTimeBefore": expire_before,
                    "expireTimeAfter": expire_after,
                    "expireDaysAfter": round(expire_days, 2) if expire_days is not None else None,
                    "validityPeriod": a.get("validityPeriod"),
                },
                reference_ts=reference_ts,
            )
        )

    bmedals = before.get("cpMedals") if isinstance(before.get("cpMedals"), dict) else {}
    amedals = after.get("cpMedals") if isinstance(after.get("cpMedals"), dict) else {}
    medal_names = sorted(set(bmedals) | set(amedals))
    medal_changes: list[dict[str, Any]] = []
    for name in medal_names:
        before_count = int(bmedals.get(name) or 0)
        after_count = int(amedals.get(name) or 0)
        delta = after_count - before_count
        if delta == 0 and name not in amedals:
            continue
        medal_changes.append(
            {
                "medalName": name,
                "countBefore": before_count,
                "countAfter": after_count,
                "countDelta": delta,
            }
        )

    bnameplates = before.get("nameplates") if isinstance(before.get("nameplates"), dict) else {}
    anameplates = after.get("nameplates") if isinstance(after.get("nameplates"), dict) else {}
    nameplate_ids = sorted(set(bnameplates) | set(anameplates))
    nameplate_changes: list[dict[str, Any]] = []
    for nid in nameplate_ids:
        b = bnameplates.get(nid) or {}
        a = anameplates.get(nid) or {}
        before_unlocked = bool(b.get("unlocked"))
        after_unlocked = bool(a.get("unlocked"))
        if not after_unlocked and not before_unlocked and not a and not b:
            continue
        nameplate_changes.append(
            _enrich_nameplate_diff_entry(
                {
                    "nameplateId": nid,
                    "title": a.get("title") or b.get("title"),
                    "unlockedBefore": before_unlocked,
                    "unlockedAfter": after_unlocked,
                    "newlyUnlocked": after_unlocked and not before_unlocked,
                    "unlockTimeBefore": b.get("unlockTime"),
                    "unlockTimeAfter": a.get("unlockTime"),
                    "unlockTimeBeforeLabel": b.get("unlockTimeLabel"),
                    "unlockTimeAfterLabel": a.get("unlockTimeLabel"),
                    "remainTimeBefore": b.get("remainTime"),
                    "remainTimeAfter": a.get("remainTime"),
                    "remainDaysBefore": b.get("remainDays"),
                    "remainDaysAfter": a.get("remainDays"),
                    "wearStateAfter": a.get("wearState"),
                },
                reference_ts=reference_ts,
            )
        )

    return {
        "ok": True,
        "userId": user_id,
        "beforeTs": before_ts,
        "afterTs": after_ts,
        "diamond": {
            "before": bd,
            "after": ad,
            "delta": diamond_delta,
        },
        "diamondHistoryNew": diamond_history_new,
        "backpackGifts": backpack_changes,
        "props": prop_changes,
        "cpMedals": medal_changes,
        "nameplates": nameplate_changes,
    }


def _find_prop(
    props_by_type: dict[str, dict[str, dict[str, Any]]],
    prop_id: str,
    prop_type_code: str | None,
    *,
    props_flat: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    if props_flat and prop_id in props_flat:
        return props_flat[prop_id]
    if prop_type_code:
        return (props_by_type.get(prop_type_code) or {}).get(prop_id)
    for items in props_by_type.values():
        if prop_id in items:
            return items[prop_id]
    return None


def compare_rewards(
    before: dict[str, Any],
    after: dict[str, Any],
    expected: dict[str, Any],
) -> dict[str, Any]:
    rewards = expected.get("rewards") or expected.get("reward") or []
    if not isinstance(rewards, list):
        raise ValueError("expected.rewards 须为数组")

    cross_gift_cost = int(expected.get("crossGiftCost") or 0)
    before_ts = int(before.get("ts") or 0)
    after_ts = int(after.get("ts") or before_ts)
    reference_ts = after_ts or before_ts
    since_ms = before_ts * 1000 - 60_000 if before_ts else reference_ts * 1000 - 300_000
    verify_diamond_records = expected.get("verifyDiamondRecords")
    if verify_diamond_records is None:
        verify_diamond_records = True
    now_ms = int(time.time() * 1000)
    issues: list[str] = []
    diamond_history_cache: list[dict[str, Any]] | None = None

    bd = before.get("diamond")
    ad = after.get("diamond")
    bg = before.get("backpackGifts") or {}
    ag = after.get("backpackGifts") or {}
    bprops = before.get("propsByType") or {}
    aprops = after.get("propsByType") or {}
    bprops_flat = before.get("props") if isinstance(before.get("props"), dict) else {}
    aprops_flat = after.get("props") if isinstance(after.get("props"), dict) else {}

    for idx, reward in enumerate(rewards):
        if not isinstance(reward, dict):
            continue
        rtype = str(reward.get("rewardType") or reward.get("type") or "").upper()
        rid = str(reward.get("rewardId") or reward.get("giftId") or reward.get("propId") or "")
        count = int(reward.get("count") or 1)

        if rtype == "DIAMOND":
            exp = count - cross_gift_cost
            if bd is None or ad is None:
                issues.append(f"[{idx}] 钻石不可查 before={bd} after={ad}")
            elif ad - bd < exp:
                issues.append(f"[{idx}] 钻石增量不足 期望+{exp} 实际+{ad - bd}")
            if verify_diamond_records and exp > 0:
                source = reward.get("recordSource") or reward.get("source") or reward.get("desc")
                if diamond_history_cache is None:
                    user_id = str(after.get("userId") or before.get("userId") or "")
                    cached = after.get("diamondHistory")
                    if isinstance(cached, list) and cached:
                        diamond_history_cache = cached
                    else:
                        try:
                            diamond_history_cache = query_diamond_history(user_id)
                        except RuntimeError as exc:
                            issues.append(f"[{idx}] 钻石记录查询失败: {exc}")
                            diamond_history_cache = []
                if diamond_history_cache is not None:
                    matched = _find_diamond_record(
                        diamond_history_cache,
                        amount=exp,
                        source_contains=str(source) if source else None,
                        since_ms=since_ms,
                    )
                    if matched is None:
                        hint = f" 来源含「{source}」" if source else ""
                        issues.append(
                            f"[{idx}] 钻石记录未找到 +{exp} 条目{hint}（diamondHistory）"
                        )
        elif rtype == "GIFT" and rid:
            before_g = bg.get(rid) or {}
            after_g = ag.get(rid) or {}
            before_remain = int(before_g.get("remain") or 0)
            after_remain = int(after_g.get("remain") or 0)
            delta = after_remain - before_remain
            if delta < count:
                issues.append(
                    f"[{idx}] 背包礼物 {rid} 数量不足 期望+{count} 实际+{delta} "
                    f"(before={before_remain} after={after_remain})"
                )
            if after_g and not _gift_is_valid(after_g, now_ms=now_ms):
                issues.append(f"[{idx}] 背包礼物 {rid} 已过期 expire={after_g.get('expire')}")
            if rid not in ag:
                issues.append(f"[{idx}] 背包礼物 {rid} 未检出")
                continue
            expected_price = _expected_gift_price(reward)
            if expected_price is not None:
                actual_price = after_g.get("price")
                tol = float(reward.get("priceTolerance") or 0.01)
                if not _gift_price_matches(actual_price, expected_price, tolerance=tol):
                    issues.append(
                        f"[{idx}] 背包礼物 {rid} 价值不符 期望{expected_price}钻 实测{actual_price}"
                    )
                expected_total = reward.get("totalValue")
                if expected_total is not None:
                    issued_value = delta * expected_price
                    if issued_value + tol < float(expected_total):
                        issues.append(
                            f"[{idx}] 背包礼物 {rid} 下发总价值不足 "
                            f"期望{expected_total}钻 实测{issued_value}钻 (数量+{delta}×{expected_price})"
                        )
                elif count > 0 and expected_price is not None:
                    issued_value = delta * float(after_g.get("price") or expected_price)
                    exp_issued = count * expected_price
                    if issued_value + tol < exp_issued:
                        issues.append(
                            f"[{idx}] 背包礼物 {rid} 下发总价值不足 "
                            f"期望{exp_issued}钻 实测{issued_value}钻"
                        )
        elif rtype == "NAMEPLATE" and rid:
            plates = after.get("nameplates") if isinstance(after.get("nameplates"), dict) else {}
            plate = plates.get(rid)
            if plate is None or not plate.get("unlocked"):
                issues.append(
                    f"[{idx}] 铭牌 {rid} 未检出（snapshot 含 nameplates 时自动 Tunnel 读取；"
                    f"无抓包时需 App 打开铭牌页一次）"
                )
                continue
            expire_days = reward.get("expireDays")
            if expire_days is not None:
                tol = float(reward.get("toleranceDays") or 1)
                actual = plate.get("remainDays")
                if actual is None:
                    issues.append(f"[{idx}] 铭牌 {rid} 无 remainTime 字段")
                elif abs(float(actual) - float(expire_days)) > tol:
                    issues.append(
                        f"[{idx}] 铭牌 {rid} 有效期不符 期望{expire_days}天 实测{actual}天"
                    )
        elif rtype == "PROP" and rid:
            ptc = str(reward.get("propTypeCode") or reward.get("propType") or "")
            prop = _find_prop(aprops, rid, ptc or None, props_flat=aprops_flat)
            if prop is None:
                issues.append(f"[{idx}] 装扮 {rid} type={ptc or '?'} 未检出")
                continue
            expire_days = reward.get("expireDays")
            if expire_days is not None:
                tol = float(reward.get("toleranceDays") or 1)
                actual = _prop_days(prop, reference_ts=reference_ts)
                if actual is None:
                    issues.append(f"[{idx}] 装扮 {rid} 无 expireTime 字段")
                elif abs(actual - float(expire_days)) > tol:
                    issues.append(
                        f"[{idx}] 装扮 {rid} 有效期不符 期望{expire_days}天 实测{actual:.1f}天"
                    )

    return {
        "ok": not issues,
        "issues": issues,
        "userId": after.get("userId") or before.get("userId"),
        "referenceTs": reference_ts,
    }


def verify_prop_days(
    user_id: str,
    *,
    prop_id: str,
    prop_type_code: str,
    expected_days: float,
    tolerance_days: float = 1.0,
    reference_ts: int | None = None,
) -> dict[str, Any]:
    props = query_props(user_id, prop_type_code)
    prop = props.get(prop_id)
    ref = reference_ts or int(time.time())
    if prop is None:
        return {
            "ok": False,
            "userId": user_id,
            "propId": prop_id,
            "propTypeCode": prop_type_code,
            "issues": [f"装扮 {prop_id} 未检出"],
        }
    actual = _prop_days(prop, reference_ts=ref)
    if actual is None:
        return {
            "ok": False,
            "userId": user_id,
            "propId": prop_id,
            "propTypeCode": prop_type_code,
            "issues": [f"装扮 {prop_id} 无 expireTime"],
            "prop": prop,
        }
    ok = abs(actual - expected_days) <= tolerance_days
    issues: list[str] = []
    if not ok:
        issues.append(f"有效期不符 期望{expected_days}天 实测{actual:.1f}天")
    return {
        "ok": ok,
        "userId": user_id,
        "propId": prop_id,
        "propTypeCode": prop_type_code,
        "expectedDays": expected_days,
        "actualDays": round(actual, 2),
        "toleranceDays": tolerance_days,
        "issues": issues,
        "prop": prop,
    }


def cmd_snapshot(args: argparse.Namespace) -> int:
    prop_types = [p.strip() for p in args.prop_types.split(",") if p.strip()] if args.prop_types else None
    snap = snapshot_user(
        str(args.user_id).strip(),
        prop_types=prop_types,
        cp_user_id=str(args.cp_user_id or "").strip(),
        intimate_id=str(args.intimate_id or "").strip(),
        diamond_history_limit=int(args.diamond_history_limit),
        include_diamond_history=not args.skip_diamond_history,
        include_nameplates=bool(args.include_nameplates),
        nameplate_tunnel_since=int(args.nameplate_tunnel_since),
    )
    out_path = Path(args.out).expanduser() if args.out else None
    text = json.dumps(snap, ensure_ascii=False, indent=2)
    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding="utf-8")
    print(text)
    return 0


def cmd_diff(args: argparse.Namespace) -> int:
    before = _load_json(Path(args.before))
    after = _load_json(Path(args.after))
    result = diff_snapshots(before, after)
    out_path = Path(args.out).expanduser() if args.out else None
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding="utf-8")
    print(text)
    return 0


def cmd_diamond_history(args: argparse.Namespace) -> int:
    records = query_diamond_history(
        str(args.user_id).strip(),
        page_size=int(args.page_size),
        last_id=str(args.last_id),
        record_type=str(args.record_type or ""),
    )
    result = {"ok": True, "userId": args.user_id, "count": len(records), "records": records[: int(args.limit)]}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    diff_path = str(args.diff or "").strip()
    before_path = str(args.before or "").strip()
    after_path = str(args.after or "").strip()
    if diff_path:
        diff = _load_json(Path(diff_path))
    elif before_path and after_path:
        before = _load_json(Path(before_path))
        after = _load_json(Path(after_path))
        diff = diff_snapshots(before, after)
    else:
        raise ValueError("report 须指定 --diff 或同时指定 --before 与 --after")
    report = format_diff_report(
        diff,
        title=str(args.title).strip() or "奖励下发验收报告",
        user_label=str(args.user_label or "").strip(),
    )
    out_path = Path(args.out).expanduser() if args.out else None
    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report, encoding="utf-8")
    print(report)
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    before = _load_json(Path(args.before))
    after = _load_json(Path(args.after))
    expected = _load_json(Path(args.expected))
    result = compare_rewards(before, after, expected)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 3


def cmd_verify_prop_days(args: argparse.Namespace) -> int:
    result = verify_prop_days(
        str(args.user_id).strip(),
        prop_id=str(args.prop_id).strip(),
        prop_type_code=str(args.prop_type_code).strip(),
        expected_days=float(args.expected_days),
        tolerance_days=float(args.tolerance_days),
        reference_ts=int(args.reference_ts) if args.reference_ts else None,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 3


def main() -> int:
    parser = argparse.ArgumentParser(description="奖励下发验收：快照 / 对比 / 装扮有效期")
    sub = parser.add_subparsers(dest="command", required=True)

    p_snap = sub.add_parser("snapshot", help="快照用户钻石、背包礼物、装扮")
    p_snap.add_argument("--user-id", required=True)
    p_snap.add_argument("--out", default="", help="输出 JSON 路径")
    p_snap.add_argument(
        "--prop-types",
        default="",
        help="逗号分隔 propTypeCode，默认常用装扮类型",
    )
    p_snap.add_argument("--cp-user-id", default="", help="CP 对方 userId（快照 CP 勋章个数）")
    p_snap.add_argument("--intimate-id", default="", help="intimateId（查 CP 勋章）")
    p_snap.add_argument(
        "--diamond-history-limit",
        type=int,
        default=_DEFAULT_DIAMOND_HISTORY_LIMIT,
        help="快照内保留钻石记录条数（发奖前基线）",
    )
    p_snap.add_argument(
        "--skip-diamond-history",
        action="store_true",
        help="跳过快照内 diamondHistory（不推荐）",
    )
    p_snap.add_argument(
        "--include-nameplates",
        action="store_true",
        help="纳入铭牌（Tunnel 自动读取 nameplatePageData；CP 场景传 --cp-user-id 时默认开启）",
    )
    p_snap.add_argument(
        "--nameplate-tunnel-since",
        type=int,
        default=0,
        help="铭牌 Tunnel 回溯秒数；0=自动多级回溯（2h→24h→7d）",
    )
    p_snap.set_defaults(func=cmd_snapshot)

    p_diff = sub.add_parser("diff", help="发奖前后快照求差（钻石/记录/背包/装扮/勋章）")
    p_diff.add_argument("--before", required=True, help="发奖前 snapshot JSON")
    p_diff.add_argument("--after", required=True, help="发奖后 snapshot JSON")
    p_diff.add_argument("--out", default="", help="差值报告 JSON 路径")
    p_diff.set_defaults(func=cmd_diff)

    p_report = sub.add_parser("report", help="生成 Markdown 测试报告（装扮有效期、礼物钻价/有效期）")
    p_report.add_argument("--diff", default="", help="diff JSON（与 before/after 二选一）")
    p_report.add_argument("--before", default="", help="发奖前 snapshot JSON")
    p_report.add_argument("--after", default="", help="发奖后 snapshot JSON")
    p_report.add_argument("--out", default="", help="Markdown 报告输出路径")
    p_report.add_argument("--title", default="奖励下发验收报告", help="报告标题")
    p_report.add_argument("--user-label", default="", help="报告显示的用户标识（如手机号）")
    p_report.set_defaults(func=cmd_report)

    p_cmp = sub.add_parser("compare", help="对比前后快照与期望奖励")
    p_cmp.add_argument("--before", required=True, help="发奖前 snapshot JSON")
    p_cmp.add_argument("--after", required=True, help="发奖后 snapshot JSON")
    p_cmp.add_argument("--expected", required=True, help="期望奖励 JSON（rewards 数组）")
    p_cmp.set_defaults(func=cmd_compare)

    p_days = sub.add_parser("verify-prop-days", help="验证单个装扮有效期天数")
    p_days.add_argument("--user-id", required=True)
    p_days.add_argument("--prop-id", required=True)
    p_days.add_argument("--prop-type-code", required=True)
    p_days.add_argument("--expected-days", type=float, required=True)
    p_days.add_argument("--tolerance-days", type=float, default=1.0)
    p_days.add_argument("--reference-ts", default="", help="发放时刻 Unix 秒，默认当前")
    p_days.set_defaults(func=cmd_verify_prop_days)

    p_hist = sub.add_parser("diamond-history", help="查询钻石记录 diamondHistory")
    p_hist.add_argument("--user-id", required=True)
    p_hist.add_argument("--page-size", type=int, default=20)
    p_hist.add_argument("--last-id", default="0")
    p_hist.add_argument("--type", dest="record_type", default="")
    p_hist.add_argument("--limit", type=int, default=10, help="输出条数上限")
    p_hist.set_defaults(func=cmd_diamond_history)

    args = parser.parse_args()
    try:
        return args.func(args)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
