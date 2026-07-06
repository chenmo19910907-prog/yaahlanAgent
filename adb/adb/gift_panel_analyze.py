"""结合 Tunnel 抓包解析礼物面板数据（getGiftTabListV3 等）。"""

from __future__ import annotations

import json
import time
from typing import Any

from .popup_analyze import fetch_recent_tunnel_items


GIFT_PANEL_URL_MARKERS = (
    "component/giftPanel/getGiftTabListV3",
    "component/giftPanel/getGiftPanel",
    "component/giftPanel/sendCheckInfo",
    "component/giftPanel/propPackageList",
    "v2/gift/send",
)


def _all_by_url(items: list[dict[str, Any]], marker: str) -> list[dict[str, Any]]:
    matched = [x for x in items if marker in str(x.get("url", ""))]
    return sorted(matched, key=lambda x: str(x.get("time", "")), reverse=True)


def _latest_by_url(items: list[dict[str, Any]], marker: str) -> dict[str, Any] | None:
    matched = _all_by_url(items, marker)
    return matched[0] if matched else None


def _latest_gift_tab_list_with_data(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    """取最近一条含 gift_list 的 getGiftTabListV3（跳过 hash 缓存命中空体）。"""
    for item in _all_by_url(items, "getGiftTabListV3"):
        resp = item.get("response")
        if not isinstance(resp, dict):
            continue
        data = resp.get("data")
        if isinstance(data, dict) and data.get("gift_list"):
            return item
    return _latest_by_url(items, "getGiftTabListV3")


def _normalize_gift(raw: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "name": raw.get("name"),
        "id": raw.get("id"),
        "bid": raw.get("bid"),
        "price": int(raw["price"]) if str(raw.get("price", "")).isdigit() else raw.get("price"),
        "giftType": raw.get("gift_type"),
        "validDays": raw.get("validDays"),
        "extra": raw.get("extra"),
        "isPackage": raw.get("is_package"),
    }
    pkg = raw.get("package")
    if isinstance(pkg, dict):
        out["package"] = {
            "remain": pkg.get("remain"),
            "expire": pkg.get("expire"),
            "label": pkg.get("label"),
        }
    return out


def parse_gift_tab_list_v3(data: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(data, dict):
        return []
    tabs_out: list[dict[str, Any]] = []
    for tab in data.get("gift_list") or []:
        if not isinstance(tab, dict):
            continue
        gifts = [_normalize_gift(g) for g in tab.get("list") or [] if isinstance(g, dict)]
        tabs_out.append(
            {
                "tabId": tab.get("tab_id"),
                "tabName": tab.get("tab_name"),
                "isPackage": tab.get("is_package"),
                "giftCount": len(gifts),
                "gifts": gifts,
            }
        )
    return tabs_out


def gift_grid_navigation_hint(*, index: int, cols: int = 4, visible_rows: int = 3) -> dict[str, Any]:
    """根据列表下标估算 UI：左右滑切 Tab，上下滑浏览礼物格（4 列网格）。"""
    row = index // cols
    col = index % cols
    swipe_up_times = max(0, (row - (visible_rows - 1) + 1) // 2)
    return {
        "index": index,
        "row": row,
        "col": col,
        "swipeUpTimes": swipe_up_times,
        "tapPctHint": [round((col + 0.5) / cols, 3), 0.78],
        "agentHint": (
            f"礼物在 Tab 列表第 {index} 项（约第 {row + 1} 行第 {col + 1} 列）；"
            f"先左右滑切到对应 Tab，再上下滑约 {swipe_up_times} 次浏览礼物格。"
        ),
    }


def find_gifts(
    tabs: list[dict[str, Any]],
    *,
    price: int | None = None,
    tab_name: str | None = None,
    name_contains: str | None = None,
) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for tab in tabs:
        tname = str(tab.get("tabName", ""))
        if tab_name and tab_name.lower() not in tname.lower():
            continue
        for index, gift in enumerate(tab.get("gifts") or []):
            if price is not None and gift.get("price") != price:
                continue
            if name_contains and name_contains.lower() not in str(gift.get("name", "")).lower():
                continue
            hits.append(
                {
                    "tabId": tab.get("tabId"),
                    "tabName": tname,
                    "index": index,
                    "gift": gift,
                    "navigation": gift_grid_navigation_hint(index=index),
                }
            )
    return hits


def analyze_gift_panel_from_tunnel(
    *,
    momoid: str,
    since_seconds: int = 300,
    g_appid: str = "All",
    g_env: str = "alpha",
) -> dict[str, Any]:
    items, meta = fetch_recent_tunnel_items(
        momoid=momoid,
        since_seconds=since_seconds,
        g_appid=g_appid,
        g_env=g_env,
    )
    tab_item = _latest_gift_tab_list_with_data(items)
    panel_item = _latest_by_url(items, "getGiftPanel")

    tabs: list[dict[str, Any]] = []
    if tab_item and isinstance(tab_item.get("response"), dict):
        resp_data = tab_item["response"].get("data")
        if isinstance(resp_data, dict):
            tabs = parse_gift_tab_list_v3(resp_data)

    tab_summary = [
        {
            "tabId": t["tabId"],
            "tabName": t["tabName"],
            "giftCount": t["giftCount"],
            "priceRange": _price_range(t.get("gifts") or []),
        }
        for t in tabs
    ]

    return {
        "momoid": momoid,
        "sinceSeconds": since_seconds,
        "tunnelMeta": meta,
        "apis": {
            "getGiftTabListV3": {
                "found": tab_item is not None,
                "time": tab_item.get("time") if tab_item else None,
                "url": tab_item.get("url") if tab_item else None,
            },
            "getGiftPanel": {
                "found": panel_item is not None,
                "time": panel_item.get("time") if panel_item else None,
            },
        },
        "tabs": tab_summary,
        "tabsDetail": tabs,
        "uiHint": (
            "礼物面板：Tab 栏左右滑切换；礼物格区域上下滑查看更多。"
            "打开面板后应出现 getGiftTabListV3；未出现则先点橙色礼物盒（非快捷礼物）。"
        ),
        "agentHint": (
            "用 tabs 看各 Tab 名称与礼物数；find --price 查目标价礼物及 index；"
            "再按 navigation.swipeUpTimes 上下滑、tapPctHint 点击。"
        ),
    }


def _price_range(gifts: list[dict[str, Any]]) -> dict[str, Any]:
    prices = [g["price"] for g in gifts if isinstance(g.get("price"), int)]
    if not prices:
        return {"min": None, "max": None, "distinct": []}
    distinct = sorted(set(prices))
    return {"min": min(prices), "max": max(prices), "distinctCount": len(distinct)}


def parse_backpack_gifts_from_tabs(tabs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """从 getGiftTabListV3 解析结果中提取背包 Tab（is_package=1）礼物及 package.remain。"""
    hits: list[dict[str, Any]] = []
    for tab in tabs:
        tname = str(tab.get("tabName") or tab.get("tab_name") or "")
        is_pkg = tab.get("isPackage") if tab.get("isPackage") is not None else tab.get("is_package")
        if not is_pkg and "背包" not in tname and "backpack" not in tname.lower():
            continue
        for gift in tab.get("gifts") or []:
            if not isinstance(gift, dict):
                continue
            hits.append(
                {
                    "tabName": tname,
                    "name": gift.get("name"),
                    "id": gift.get("id"),
                    "bid": gift.get("bid"),
                    "price": gift.get("price"),
                    "remain": (gift.get("package") or {}).get("remain"),
                    "expire": (gift.get("package") or {}).get("expire"),
                    "expireLabel": (gift.get("package") or {}).get("label"),
                }
            )
    return hits


def verify_backpack_gift_from_tunnel(
    *,
    momoid: str,
    base_product_id: str | None = None,
    gift_name: str | None = None,
    expected_remain: int | None = None,
    since_seconds: int = 600,
    g_appid: str = "All",
    g_env: str = "alpha",
) -> dict[str, Any]:
    """Tunnel 抓 getGiftTabListV3 → 背包 Tab → 按 bid/名称查 remain 并可选验收数量。"""
    analysis = analyze_gift_panel_from_tunnel(
        momoid=momoid,
        since_seconds=since_seconds,
        g_appid=g_appid,
        g_env=g_env,
    )
    tab_item = analysis.get("apis", {}).get("getGiftTabListV3") or {}
    backpacks = parse_backpack_gifts_from_tabs(analysis.get("tabsDetail") or [])

    cache_only = bool(tab_item) and not backpacks and not (analysis.get("tabsDetail") or [])

    bid_key = str(base_product_id).strip() if base_product_id else ""
    name_key = str(gift_name or "").strip().lower()

    matched: list[dict[str, Any]] = []
    for item in backpacks:
        bid_match = bid_key and str(item.get("bid") or "") == bid_key
        name_match = name_key and name_key in str(item.get("name") or "").lower()
        if bid_key or name_key:
            if not (bid_match or name_match):
                continue
        matched.append(item)

    verify_ok: bool | None = None
    if expected_remain is not None and len(matched) == 1:
        try:
            verify_ok = int(matched[0].get("remain")) == int(expected_remain)
        except (TypeError, ValueError):
            verify_ok = False
    elif expected_remain is not None and len(matched) != 1:
        verify_ok = False

    return {
        "momoid": momoid,
        "sinceSeconds": since_seconds,
        "api": "component/giftPanel/getGiftTabListV3",
        "tunnelFound": bool(tab_item.get("found")),
        "tunnelTime": tab_item.get("time"),
        "tunnelRequestIdHint": "Tunnel 列表 _id 可用于 tunnel.wemomo.com/request/<_id>",
        "filter": {
            "baseProductId": base_product_id,
            "giftName": gift_name,
            "expectedRemain": expected_remain,
        },
        "backpackGiftCount": len(backpacks),
        "backpackGifts": backpacks,
        "matchedCount": len(matched),
        "matches": matched,
        "verifyOk": verify_ok,
        "cacheHitOnly": cache_only,
        "agentHint": (
            "须先在 App 打开礼物面板（橙色礼物盒）；数据源为 getGiftTabListV3 的「背包」Tab，"
            "读 package.remain。propPackageList 仅背包道具，不含礼物。"
            + (" 最近抓包均为 hash 缓存命中（无 gift_list），请关闭并重新打开礼物面板后再查。" if cache_only else "")
        ),
        "uiHint": analysis.get("uiHint"),
    }


def find_gifts_from_tunnel(
    *,
    momoid: str,
    since_seconds: int = 300,
    price: int | None = None,
    tab_name: str | None = None,
    name_contains: str | None = None,
    g_appid: str = "All",
    g_env: str = "alpha",
) -> dict[str, Any]:
    analysis = analyze_gift_panel_from_tunnel(
        momoid=momoid,
        since_seconds=since_seconds,
        g_appid=g_appid,
        g_env=g_env,
    )
    hits = find_gifts(
        analysis.get("tabsDetail") or [],
        price=price,
        tab_name=tab_name,
        name_contains=name_contains,
    )
    return {
        **{k: v for k, v in analysis.items() if k != "tabsDetail"},
        "filter": {"price": price, "tabName": tab_name, "nameContains": name_contains},
        "matchedCount": len(hits),
        "matches": hits,
    }
