#!/usr/bin/env python3
"""查看礼物面板背包：优先 MOA（getGiftTabListV3 + propPackageList），失败则 Tunnel 解析。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO))

from adb.adb.gift_panel_analyze import (  # noqa: E402
    analyze_gift_panel_from_tunnel,
    parse_backpack_gifts_from_tabs,
)
from adb.adb.popup_analyze import fetch_recent_tunnel_items  # noqa: E402
from MOA.moa.gift_panel_backpack import fetch_gift_panel_backpack_via_moa  # noqa: E402


def _latest_prop_package_list(items: list[dict[str, object]]) -> list[dict[str, object]]:
    for item in sorted(items, key=lambda x: str(x.get("time") or ""), reverse=True):
        if "propPackageList" not in str(item.get("url") or ""):
            continue
        resp = item.get("response")
        if isinstance(resp, str):
            try:
                resp = json.loads(resp)
            except json.JSONDecodeError:
                continue
        if not isinstance(resp, dict):
            continue
        data = resp.get("data")
        if not isinstance(data, dict):
            continue
        props = data.get("list") or data.get("propList") or []
        if isinstance(props, list):
            return [p for p in props if isinstance(p, dict)]
    return []


def _tunnel_fallback(
    *,
    user_id: str,
    since_seconds: int,
    g_appid: str,
    g_env: str,
) -> dict[str, object]:
    analysis = analyze_gift_panel_from_tunnel(
        momoid=user_id,
        since_seconds=since_seconds,
        g_appid=g_appid,
        g_env=g_env,
    )
    items, _meta = fetch_recent_tunnel_items(
        momoid=user_id,
        since_seconds=since_seconds,
        g_appid=g_appid,
        g_env=g_env,
    )
    tab_item = analysis.get("apis", {}).get("getGiftTabListV3") or {}
    backpacks = parse_backpack_gifts_from_tabs(analysis.get("tabsDetail") or [])
    prop_list = _latest_prop_package_list(items)

    return {
        "mode": "tunnel",
        "userId": user_id,
        "sinceSeconds": since_seconds,
        "tunnelFoundGift": bool(tab_item.get("found")),
        "tunnelFoundProp": bool(prop_list),
        "backpackGiftCount": len(backpacks),
        "backpackGifts": backpacks,
        "backpackPropCount": len(prop_list),
        "backpackProps": prop_list,
        "agentHint": analysis.get("uiHint"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="查看礼物面板背包（MOA 优先，Tunnel 兜底）")
    parser.add_argument("--user-id", "--momoid", dest="user_id", required=True)
    parser.add_argument("--room-id", default="", help="房间 ID（getGiftTabListV3 房间内场景必填）")
    parser.add_argument("--area", default="MENA")
    parser.add_argument("--service-url", default="", help="指定 MOA ServiceUrl（默认自动探测候选）")
    parser.add_argument("--since", type=int, default=7200, help="Tunnel 兜底查询秒数")
    parser.add_argument("--g-appid", default="All")
    parser.add_argument("--g-env", default="alpha")
    parser.add_argument("--tunnel-only", action="store_true", help="仅 Tunnel 解析，不调用 MOA")
    parser.add_argument("--moa-only", action="store_true", help="仅 MOA 查询，不 Tunnel 兜底")
    parser.add_argument("--skip-props", action="store_true", help="不查 propPackageList")
    parser.add_argument("--timeout-s", type=int, default=30)
    args = parser.parse_args()

    user_id = str(args.user_id).strip()
    room_id = str(args.room_id or "").strip() or None
    service_url = str(args.service_url or "").strip() or None

    if args.tunnel_only:
        out = _tunnel_fallback(
            user_id=user_id,
            since_seconds=max(1, int(args.since)),
            g_appid=str(args.g_appid),
            g_env=str(args.g_env),
        )
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0 if out.get("tunnelFoundGift") else 3

    try:
        out = fetch_gift_panel_backpack_via_moa(
            user_id=user_id,
            room_id=room_id,
            area=str(args.area or "MENA"),
            include_props=not args.skip_props,
            service_url=service_url,
            timeout_s=max(5, int(args.timeout_s)),
        )
        out["mode"] = "moa"
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    except RuntimeError as exc:
        if args.moa_only:
            print(json.dumps({"mode": "moa", "error": str(exc)}, ensure_ascii=False, indent=2))
            print(str(exc), file=sys.stderr)
            return 3
        tunnel_out = _tunnel_fallback(
            user_id=user_id,
            since_seconds=max(1, int(args.since)),
            g_appid=str(args.g_appid),
            g_env=str(args.g_env),
        )
        tunnel_out["moaError"] = str(exc)
        print(json.dumps(tunnel_out, ensure_ascii=False, indent=2))
        if tunnel_out.get("tunnelFoundGift"):
            print("MOA 未调通，已改用 Tunnel 解析背包。", file=sys.stderr)
            return 0
        print(str(exc), file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
