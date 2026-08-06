"""礼物面板背包：getGiftTabListV3 / propPackageList MOA 调用与响应解析。"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from .project_paths import (
    admin_execute_path,
    get_repo_root,
    gift_module_dir,
    moa_execute_path,
    moa_template,
)


GIFT_TEMPLATE = moa_template("礼物面板-查看背包礼物.json")
PROP_TEMPLATE = moa_template("礼物面板-查看背包道具.json")

# MSE 调用链 / components-backdoor: moa.serviceUri.gateway.gift-panel
GIFT_PANEL_SERVICE_URL = "/service/yh-components/gift-panel"

GIFT_SERVICE_URL_CANDIDATES = (
    GIFT_PANEL_SERVICE_URL,
    "/service/voga-components/gateway/gift-panel-api-stage",
    "/service/voga-components/gateway/gift-panel-stage",
    "/service/voga-components/gateway/gift-stage",
)

PROP_SERVICE_URL_CANDIDATES = GIFT_SERVICE_URL_CANDIDATES


def _call_moa_direct(service_uri: str, method: str, body: dict[str, Any]) -> dict[str, Any]:
    gift_dir = gift_module_dir()
    if str(gift_dir) not in sys.path:
        sys.path.insert(0, str(gift_dir))
    from gift.send_stage import StageGiftError, call_moa

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
    if isinstance(data, dict):
        return data
    if data is None:
        return {}
    raise RuntimeError(f"MOA 返回 data 非 object: {data!r}")


def _build_gift_tab_body(
    *,
    user_id: str,
    room_id: str | None,
    area: str,
    clear_hash: bool,
    template: Path,
) -> dict[str, Any]:
    body: dict[str, Any] = {}
    params = json.loads(template.read_text(encoding="utf-8")).get("params")
    if isinstance(params, list) and params:
        first = params[0]
        if isinstance(first, dict) and isinstance(first.get("value"), dict):
            body = dict(first["value"])

    body["userId"] = user_id
    body["uid"] = user_id
    body["area"] = str(area or "MENA").strip().upper() or "MENA"
    if room_id:
        body["roomId"] = str(room_id).strip()
    if clear_hash:
        body.pop("giftListHash", None)
    return body


def _parse_moa_stdout(text: str) -> dict[str, Any]:
    start = text.find("{")
    if start < 0:
        raise RuntimeError("MOA 输出不含 JSON")
    decoder = json.JSONDecoder()
    obj, _ = decoder.raw_decode(text[start:])
    if not isinstance(obj, dict):
        raise RuntimeError("MOA 返回不是 object")
    return obj


def _unwrap_httpproxy_business(resp: dict[str, Any]) -> dict[str, Any]:
    outer_ec = resp.get("ec")
    if outer_ec not in (0, 200, "0", "200"):
        raise RuntimeError(f"MOA 外层失败: ec={outer_ec}, em={resp.get('em')}")
    inner = resp.get("result")
    if not isinstance(inner, dict):
        raise RuntimeError("MOA 缺少 result")
    inner_ec = inner.get("ec")
    if inner_ec not in (0, 200, "0", "200"):
        raise RuntimeError(f"MOA 业务失败: ec={inner_ec}, em={inner.get('em')}")
    payload = inner.get("result")
    if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
        return payload["data"]
    if isinstance(payload, dict):
        return payload
    raise RuntimeError("MOA 返回缺少 data")


def _run_moa_httpproxy(
    *,
    template: Path,
    user_id: str,
    room_id: str | None,
    area: str,
    clear_hash: bool,
    service_url: str | None,
    timeout_s: int,
) -> dict[str, Any]:
    cmd = [
        sys.executable,
        str(moa_execute_path()),
        "--payload-file",
        str(template),
        "--gift-panel-backpack-user-id",
        user_id,
        "--gift-panel-backpack-area",
        area,
        "--timeout-ms",
        str(max(timeout_s, 5) * 1000),
    ]
    if room_id:
        cmd.extend(["--gift-panel-backpack-room-id", room_id])
    if clear_hash:
        cmd.append("--gift-panel-backpack-clear-hash")
    if service_url:
        cmd.extend(["--gift-panel-backpack-service-url", service_url])

    proc = subprocess.run(
        cmd,
        cwd=str(get_repo_root()),
        capture_output=True,
        text=True,
        timeout=max(timeout_s + 10, 30),
        check=False,
    )
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "MOA 调用失败")[-800:]
        raise RuntimeError(tail)
    resp = _parse_moa_stdout(proc.stdout)
    return _unwrap_httpproxy_business(resp)


def _fetch_via_direct_moa(
    *,
    user_id: str,
    room_id: str | None,
    area: str,
    clear_hash: bool,
    include_props: bool,
    service_url: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, list[str], list[str]]:
    gift_body = _build_gift_tab_body(
        user_id=user_id,
        room_id=room_id,
        area=area,
        clear_hash=clear_hash,
        template=GIFT_TEMPLATE,
    )
    prop_body = _build_gift_tab_body(
        user_id=user_id,
        room_id=room_id,
        area=area,
        clear_hash=False,
        template=PROP_TEMPLATE,
    )

    gift_errors: list[str] = []
    prop_errors: list[str] = []
    gift_data: dict[str, Any] | None = None
    prop_data: dict[str, Any] | None = None

    try:
        gift_data = _call_moa_direct(service_url, "getGiftTabListV3", gift_body)
    except RuntimeError as exc:
        gift_errors.append(f"{service_url}: {exc}")

    if include_props:
        try:
            prop_data = _call_moa_direct(service_url, "propPackageList", prop_body)
        except RuntimeError as exc:
            prop_errors.append(f"{service_url}: {exc}")

    return gift_data, prop_data, gift_errors, prop_errors


def parse_backpack_gifts_from_moa_data(data: dict[str, Any]) -> list[dict[str, Any]]:
    gifts: list[dict[str, Any]] = []
    for tab in data.get("gift_list") or []:
        if not isinstance(tab, dict):
            continue
        tab_name = str(tab.get("tab_name") or "")
        is_package = tab.get("is_package")
        if not is_package and tab_name not in ("背包", "Backpack"):
            continue
        for item in tab.get("list") or []:
            if not isinstance(item, dict):
                continue
            pkg = item.get("package") if isinstance(item.get("package"), dict) else {}
            gifts.append(
                {
                    "tabName": tab_name,
                    "name": item.get("name"),
                    "id": item.get("id"),
                    "bid": item.get("bid"),
                    "price": item.get("price"),
                    "remain": pkg.get("remain"),
                    "expire": pkg.get("expire"),
                    "expireLabel": pkg.get("label"),
                }
            )
    return gifts


def parse_backpack_props_from_moa_data(data: dict[str, Any]) -> list[dict[str, Any]]:
    props = data.get("list") or data.get("propList") or []
    if not isinstance(props, list):
        return []
    return [item for item in props if isinstance(item, dict)]


def fetch_gift_panel_backpack_via_moa(
    *,
    user_id: str,
    room_id: str | None = None,
    area: str = "MENA",
    clear_hash: bool = True,
    include_props: bool = True,
    service_url: str | None = None,
    timeout_s: int = 30,
    prefer_direct: bool = True,
) -> dict[str, Any]:
    """MOA 拉取礼物面板背包。默认走 Stage Redis 直连（/service/yh-components/gift-panel）。"""
    user_id = str(user_id).strip()
    if not user_id:
        raise ValueError("user_id 不能为空")

    gift_urls = (service_url,) if service_url else GIFT_SERVICE_URL_CANDIDATES
    gift_data: dict[str, Any] | None = None
    prop_data: dict[str, Any] | None = None
    gift_url_used: str | None = None
    prop_url_used: str | None = None
    gift_errors: list[str] = []
    prop_errors: list[str] = []
    transport = "moa-direct"

    if prefer_direct:
        for url in gift_urls:
            gift_data, prop_data, gift_errors, prop_errors = _fetch_via_direct_moa(
                user_id=user_id,
                room_id=room_id,
                area=area,
                clear_hash=clear_hash,
                include_props=include_props,
                service_url=url,
            )
            if gift_data is not None or (include_props and prop_data is not None):
                gift_url_used = url
                prop_url_used = url
                break

    if gift_data is None and (not include_props or prop_data is None):
        transport = "moa-httpproxy"
        gift_data = None
        prop_data = None
        gift_errors = []
        prop_errors = []
        for url in gift_urls:
            try:
                gift_data = _run_moa_httpproxy(
                    template=GIFT_TEMPLATE,
                    user_id=user_id,
                    room_id=room_id,
                    area=area,
                    clear_hash=clear_hash,
                    service_url=url,
                    timeout_s=timeout_s,
                )
                gift_url_used = url
                break
            except RuntimeError as exc:
                gift_errors.append(f"{url}: {exc}")

        if include_props:
            for url in gift_urls:
                try:
                    prop_data = _run_moa_httpproxy(
                        template=PROP_TEMPLATE,
                        user_id=user_id,
                        room_id=room_id,
                        area=area,
                        clear_hash=False,
                        service_url=url,
                        timeout_s=timeout_s,
                    )
                    prop_url_used = url
                    break
                except RuntimeError as exc:
                    prop_errors.append(f"{url}: {exc}")

    if gift_data is None and (not include_props or prop_data is None):
        raise RuntimeError(
            "MOA 查看背包失败；"
            f"giftErrors={gift_errors[-3:]}; propErrors={prop_errors[-3:]}"
        )

    backpack_gifts = parse_backpack_gifts_from_moa_data(gift_data or {})
    backpack_props = parse_backpack_props_from_moa_data(prop_data or {}) if include_props else []

    return {
        "userId": user_id,
        "roomId": room_id,
        "area": area,
        "transport": transport,
        "serviceUrlGift": gift_url_used,
        "serviceUrlProp": prop_url_used,
        "backpackGiftCount": len(backpack_gifts),
        "backpackGifts": backpack_gifts,
        "backpackPropCount": len(backpack_props),
        "backpackProps": backpack_props,
        "giftErrors": gift_errors,
        "propErrors": prop_errors,
        "httpPathGift": "/yaahlan/component/giftPanel/getGiftTabListV3",
        "httpPathProp": "/yaahlan/component/giftPanel/propPackageList",
        "methodGift": "getGiftTabListV3",
        "methodProp": "propPackageList",
    }
