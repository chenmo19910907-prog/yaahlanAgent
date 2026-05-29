"""风控 CLI 入口。"""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from typing import Any

from .client import http_post_json
from .config import (
    chunk_elements,
    defaults,
    max_elements_for_request,
    max_elements_per_request,
    resolve_menu_operate_body,
)
from .env import load_local_env
from .test_devices import (
    default_test_device_xlsx_path,
    find_devices,
    group_release_elements,
    load_test_devices,
    menu_key_for_dimension,
)


def _parse_elements(
    raw: str | None,
    element_file: str | None,
    mmuid: str | None,
    phone: str | None,
    user_id: str | None,
) -> list[str]:
    items: list[str] = []
    for source in (raw, mmuid, phone, user_id):
        if source:
            items.extend(part.strip() for part in source.split(",") if part.strip())
    if element_file:
        with open(element_file, "r", encoding="utf-8") as f:
            for line in f:
                value = line.strip()
                if value and not value.startswith("#"):
                    items.append(value)
    deduped: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item not in seen:
            seen.add(item)
            deduped.append(item)
    return deduped


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="海外风控开放接口本地调用")
    parser.add_argument("--base-url", default=os.environ.get("SEC_RISK_BASE_URL"), help="接口域名，默认 SEC_RISK_BASE_URL")
    parser.add_argument("--cookie", default=os.environ.get("SEC_RISK_COOKIE"), help="Cookie（可选；开放接口通常仅需 token）")
    parser.add_argument("--timeout-ms", type=int, default=10000, help="HTTP 超时（毫秒）")
    parser.add_argument("--dump-body", action="store_true", help="输出最终请求 body 到 stderr")

    src = parser.add_mutually_exclusive_group(required=False)
    src.add_argument("--payload-file", help="完整请求 JSON 文件")
    src.add_argument("--payload", help="完整请求 JSON 字符串")

    scenario = parser.add_mutually_exclusive_group()
    scenario.add_argument(
        "--release-device",
        action="store_true",
        help="解除设备风控（--menu-key device_risk_release，dimension=mmuid）",
    )
    scenario.add_argument(
        "--release-phone",
        action="store_true",
        help="解除手机号风控（--menu-key phone_risk_release，dimension=phone）",
    )
    scenario.add_argument(
        "--add-recharge-risk",
        action="store_true",
        help="添加充值风控（black/user_id，action=add）",
    )
    scenario.add_argument(
        "--release-recharge-risk",
        action="store_true",
        help="解除充值风控（black/user_id，action=delete）",
    )
    scenario.add_argument(
        "--add-activity-risk",
        action="store_true",
        help="添加活动风控（black/user_id，action=add）",
    )
    scenario.add_argument(
        "--release-activity-risk",
        action="store_true",
        help="解除活动风控（black/user_id，action=delete）",
    )
    scenario.add_argument(
        "--release-test-device",
        action="store_true",
        help="从团队测试机统计表按平台解除设备风控（Android/鸿蒙=mmuidv3，iOS=mmuid）",
    )
    parser.add_argument(
        "--list-test-devices",
        action="store_true",
        help="列出测试机统计表中的设备及其解除风控维度",
    )
    parser.add_argument(
        "--device-xlsx",
        help=f"测试机统计表 xlsx 路径（默认 RISK_TEST_DEVICE_XLSX 或 {default_test_device_xlsx_path()}）",
    )
    parser.add_argument("--device-asset", help="测试机资产编号，逗号分隔（与 --release-test-device 配合）")
    parser.add_argument("--device-name", help="测试机名称/品牌模糊匹配（与 --release-test-device 配合）")
    parser.add_argument("--menu-event", help="名单 event UUID（menu_event）")
    parser.add_argument("--menu-key", help="config.json menu_events 中的别名")
    parser.add_argument("--menu-type", choices=["white", "black"], help="名单类型：white/black")
    parser.add_argument("--dimension", help="维度，如 mmuid、userId")
    parser.add_argument("--elements", help="元素列表，逗号分隔")
    parser.add_argument("--mmuid", help="设备 mmuid 列表，逗号分隔（解除设备风控时使用）")
    parser.add_argument("--phone", help="手机号列表，逗号分隔（解除手机号风控时使用）")
    parser.add_argument("--user-id", help="用户 ID 列表，逗号分隔（充值/活动风控时使用）")
    parser.add_argument("--element-file", help="元素文件，每行一个（mmuid / 手机号 / user_id）")
    parser.add_argument("--action", choices=["add", "delete", "remove", "del"], default="add", help="操作：add/delete")
    parser.add_argument("--reason", default="测试", help="操作原因")
    parser.add_argument("--token", help="开放接口 token，默认 SEC_RISK_TOKEN 或 config.defaults.token")
    parser.add_argument(
        "--strict-limit",
        action="store_true",
        help=f"严格限制单次 elements 上限（超出则报错，不自动分批；默认 {max_elements_per_request()}）",
    )
    parser.add_argument(
        "--max-per-request",
        type=int,
        help=f"单次请求最大 elements 数（默认 {max_elements_per_request()}）",
    )
    return parser


def _resolve_operate_url(base_url: str | None) -> str:
    cfg = defaults()
    root = (base_url or cfg.get("base_url") or "https://sec-risk-admin-oversea.wemomo.com").rstrip("/")
    path = cfg.get("menu_operate_path") or "/open/menu/operate"
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{root}{path}"


def _apply_scenario_defaults(args: argparse.Namespace) -> None:
    if args.release_device:
        if not args.menu_key:
            args.menu_key = "device_risk_release"
        if not args.dimension:
            args.dimension = "mmuid"
        if not args.menu_type:
            args.menu_type = "white"
        return
    if args.release_phone:
        if not args.menu_key:
            args.menu_key = "phone_risk_release"
        if not args.dimension:
            args.dimension = "phone"
        if not args.menu_type:
            args.menu_type = "white"
        return
    if args.add_recharge_risk:
        args.menu_key = args.menu_key or "recharge_risk_control"
        args.menu_type = args.menu_type or "black"
        args.dimension = args.dimension or "user_id"
        args.action = "add"
        return
    if args.release_recharge_risk:
        args.menu_key = args.menu_key or "recharge_risk_control"
        args.menu_type = args.menu_type or "black"
        args.dimension = args.dimension or "user_id"
        args.action = "delete"
        return
    if args.add_activity_risk:
        args.menu_key = args.menu_key or "activity_risk_control"
        args.menu_type = args.menu_type or "black"
        args.dimension = args.dimension or "user_id"
        args.action = "add"
        return
    if args.release_activity_risk:
        args.menu_key = args.menu_key or "activity_risk_control"
        args.menu_type = args.menu_type or "black"
        args.dimension = args.dimension or "user_id"
        args.action = "delete"


def _resolve_batch_limit(args: argparse.Namespace) -> int:
    if args.max_per_request:
        return args.max_per_request
    return max_elements_for_request(args.menu_key)


def _split_elements(
    elements: list[str],
    *,
    strict_limit: bool,
    limit: int,
    label: str = "elements",
) -> list[list[str]]:
    if strict_limit and len(elements) > limit:
        raise ValueError(
            f"单次最多 {limit} 个 {label}，当前 {len(elements)} 个；"
            "请减少数量或去掉 --strict-limit 以自动分批"
        )
    if len(elements) <= limit:
        return [elements]
    return chunk_elements(elements, limit)


def _build_request_bodies(args: argparse.Namespace) -> list[dict[str, Any]]:
    _apply_scenario_defaults(args)
    limit = _resolve_batch_limit(args)
    dimension = (args.dimension or "").strip()
    label = {
        "mmuid": "mmuid",
        "mmuidv3": "mmuidv3",
        "phone": "phone",
        "user_id": "user_id",
    }.get(dimension, "elements")

    if args.payload_file:
        with open(args.payload_file, "r", encoding="utf-8") as f:
            template = json.load(f)
    elif args.payload:
        template = json.loads(args.payload)
    else:
        elements = _parse_elements(args.elements, args.element_file, args.mmuid, args.phone, args.user_id)
        chunks = _split_elements(elements, strict_limit=args.strict_limit, limit=limit, label=label)
        return [
            resolve_menu_operate_body(
                menu_event=args.menu_event,
                menu_key=args.menu_key,
                menu_type=args.menu_type,
                dimension=args.dimension,
                elements=chunk,
                action=args.action,
                reason=args.reason,
                token=args.token,
            )
            for chunk in chunks
        ]

    if not isinstance(template, dict):
        raise ValueError("请求 body 必须是 JSON object")

    elements_raw = template.get("elements")
    if not isinstance(elements_raw, list):
        return [template]

    elements = [str(item).strip() for item in elements_raw if str(item).strip()]
    chunks = _split_elements(elements, strict_limit=args.strict_limit, limit=limit)
    bodies: list[dict[str, Any]] = []
    for chunk in chunks:
        body = copy.deepcopy(template)
        body["elements"] = chunk
        bodies.append(body)
    return bodies


def _parse_device_assets(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def _print_test_devices(xlsx_path: str | None) -> None:
    devices = load_test_devices(xlsx_path)
    path = xlsx_path or default_test_device_xlsx_path()
    print(f"测试机统计表: {path}（共 {len(devices)} 台）")
    print(f"{'资产编号':<16} {'设备名称':<24} {'系统':<8} {'字段':<10} {'element'}")
    print("-" * 100)
    for device in devices:
        try:
            dimension, element = device.release_dimension_and_element()
            field = "mmuidv3" if device.os_kind in {"android", "harmony"} else "mmuid"
            status = f"{field}  {element}"
        except ValueError as e:
            status = f"缺失  {e}"
        name = device.name or device.brand or "-"
        print(f"{device.asset_id:<16} {name:<24} {device.os_name:<8} {status}")


def _build_bodies_from_test_devices(args: argparse.Namespace) -> list[dict[str, Any]]:
    asset_ids = _parse_device_assets(args.device_asset)
    if not asset_ids and not args.device_name:
        raise ValueError("解除测试机设备风控需提供 --device-asset 或 --device-name")

    devices = find_devices(
        devices=load_test_devices(args.device_xlsx),
        asset_ids=asset_ids or None,
        name_query=args.device_name,
    )
    grouped = group_release_elements(devices)
    if not grouped:
        raise ValueError("未解析到可解除设备风控的测试机")

    limit = _resolve_batch_limit(args)
    bodies: list[dict[str, Any]] = []
    for dimension, elements in grouped.items():
        menu_key = menu_key_for_dimension(dimension)
        chunks = _split_elements(
            elements,
            strict_limit=args.strict_limit,
            limit=limit,
            label=dimension,
        )
        for chunk in chunks:
            bodies.append(
                resolve_menu_operate_body(
                    menu_event=args.menu_event,
                    menu_key=menu_key,
                    menu_type=args.menu_type or "white",
                    dimension=dimension,
                    elements=chunk,
                    action="add",
                    reason=args.reason,
                    token=args.token,
                )
            )

    for device in devices:
        dimension, element = device.release_dimension_and_element()
        print(
            f"测试机 {device.asset_id} ({device.name or device.brand}, {device.os_name}) "
            f"-> dimension={dimension}, element={element}",
            file=sys.stderr,
        )
    return bodies


def main() -> int:
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_local_env(base_dir)

    args = build_parser().parse_args()

    if args.list_test_devices:
        try:
            _print_test_devices(args.device_xlsx)
        except ValueError as e:
            print(f"参数错误: {e}", file=sys.stderr)
            return 2
        return 0

    try:
        if args.release_test_device:
            bodies = _build_bodies_from_test_devices(args)
        else:
            bodies = _build_request_bodies(args)
    except ValueError as e:
        print(f"参数错误: {e}", file=sys.stderr)
        return 2

    if not bodies:
        print("没有可执行的请求", file=sys.stderr)
        return 2

    url = _resolve_operate_url(args.base_url)
    if args.dump_body:
        for index, body in enumerate(bodies, start=1):
            prefix = f"批次 {index}/{len(bodies)} " if len(bodies) > 1 else ""
            print(f"{prefix}POST {url}", file=sys.stderr)
            print(json.dumps(body, ensure_ascii=False, indent=2), file=sys.stderr)

    results: list[dict[str, Any]] = []

    for index, body in enumerate(bodies, start=1):
        if len(bodies) > 1:
            print(
                f"分批请求 {index}/{len(bodies)}，本批 elements 数量: {len(body.get('elements', []))}",
                file=sys.stderr,
            )

        try:
            resp = http_post_json(
                url,
                body,
                cookie=args.cookie,
                timeout_s=max(args.timeout_ms, 1) / 1000.0,
            )
        except RuntimeError as e:
            print(f"执行失败(第 {index} 批): {e}", file=sys.stderr)
            return 1
        results.append({"batch": index, "elementsCount": len(body.get("elements", [])), "response": resp})

    if len(results) == 1:
        print(json.dumps(results[0]["response"], ensure_ascii=False, indent=2))
    else:
        print(json.dumps({"batchCount": len(results), "results": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
