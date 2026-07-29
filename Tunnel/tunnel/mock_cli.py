"""Tunnel Mock CLI。"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .env import load_local_env
from .mock_api import (
    create_mock_case,
    delete_mock_case,
    delete_param_mock,
    find_latest_capture,
    list_mock_cases,
    list_param_mocks,
    normalize_uri,
    set_param_mock,
    toggle_mock_case,
)
from .paths import tunnel_dir


def _print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _resolve_uri(args: argparse.Namespace) -> str:
    if args.uri:
        return normalize_uri(args.uri)
    if not args.keyword:
        raise ValueError("须指定 --uri 或 --keyword（从最近抓包解析 URL）")
    item = find_latest_capture(
        base_url=args.base_url,
        momoid=args.momoid,
        keyword=args.keyword,
        since_s=args.since,
        url_contains=args.url_contains or "",
    )
    url = str(item.get("url") or "").strip()
    if not url:
        raise RuntimeError("抓包条目缺少 url")
    return normalize_uri(url)


def _resolve_response_json(args: argparse.Namespace, capture: dict[str, Any] | None = None) -> str:
    if args.response_file:
        return open(args.response_file, "r", encoding="utf-8").read()
    if args.response_json:
        json.loads(args.response_json)
        return args.response_json
    item = capture
    if item is None:
        if not args.keyword:
            raise ValueError("创建 mock_case 须 --response-file / --response-json，或配合 --keyword 使用最近抓包 response")
        item = find_latest_capture(
            base_url=args.base_url,
            momoid=args.momoid,
            keyword=args.keyword,
            since_s=args.since,
            url_contains=args.url_contains or "",
        )
    response = item.get("response")
    if not isinstance(response, dict):
        raise RuntimeError("抓包条目缺少 response 对象")
    return json.dumps(response, ensure_ascii=False)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Tunnel Mock：整包 mock_cases / 字段 param_mock")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--base-url",
        default="https://tunnel.wemomo.com",
        help="Tunnel 域名",
    )
    common.add_argument("--momoid", required=True, help="用户 userId")
    common.add_argument("--app-id", default="All", help="mock_cases 的 appId，默认 All")
    common.add_argument("--g-appid", default="All", help="Tunnel 查询参数 g_appid，默认 All")
    common.add_argument("--g-env", default="alpha", help="Tunnel 查询参数 g_env，默认 alpha")
    common.add_argument("--uri", help="接口 URI（可路径或完整 URL）")
    common.add_argument("--keyword", help="从最近抓包按关键字定位 URI")
    common.add_argument("--url-contains", default="", help="与 --keyword 联用，进一步过滤 URL 子串")
    common.add_argument("--since", type=int, default=3600, help="--keyword 查抓包的时间窗（秒）")
    common.add_argument("--output", choices=("summary", "json"), default="summary")

    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", parents=[common], help="列出整包 mock_cases")
    p_list.set_defaults(handler=_cmd_list_cases)

    p_case_create = sub.add_parser("case-create", parents=[common], help="创建整包 mock（可基于最近抓包 response）")
    p_case_create.add_argument("--response-file", help="response JSON 文件路径")
    p_case_create.add_argument("--response-json", help="response JSON 字符串")
    p_case_create.add_argument("--index", type=int, default=0)
    p_case_create.add_argument("--name", default="")
    p_case_create.add_argument("--enable", action="store_true", default=True)
    p_case_create.add_argument("--no-enable", dest="enable", action="store_false")
    p_case_create.set_defaults(handler=_cmd_case_create)

    p_case_on = sub.add_parser("case-start", parents=[common], help="启用 mock_case（action=start）")
    p_case_on.add_argument("--index", type=int, help="mock index；省略则启用该 URI 全部")
    p_case_on.set_defaults(handler=_cmd_case_start)

    p_case_off = sub.add_parser("case-stop", parents=[common], help="停用 mock_case（action=stop）")
    p_case_off.add_argument("--index", type=int, help="mock index；省略则停用该 URI 全部")
    p_case_off.set_defaults(handler=_cmd_case_stop)

    p_case_del = sub.add_parser("case-delete", parents=[common], help="删除指定 index 的 mock_case")
    p_case_del.add_argument("--index", type=int, required=True)
    p_case_del.set_defaults(handler=_cmd_case_delete)

    p_param_list = sub.add_parser("param-list", parents=[common], help="列出 param_mock 字段覆盖")
    p_param_list.set_defaults(handler=_cmd_param_list)

    p_param_set = sub.add_parser("param-set", parents=[common], help="设置 response 字段 mock（推荐改单个字段）")
    p_param_set.add_argument("--key", required=True, help="字段路径，如 data.countdownSec")
    p_param_set.add_argument("--value", required=True, help="mock 值（字符串；数字直接写）")
    p_param_set.set_defaults(handler=_cmd_param_set)

    p_param_del = sub.add_parser("param-delete", parents=[common], help="删除 param_mock 字段")
    p_param_del.add_argument("--key", required=True)
    p_param_del.set_defaults(handler=_cmd_param_delete)

    p_field = sub.add_parser(
        "field",
        parents=[common],
        help="便捷：按 keyword 找 URI + param-set（如 CP 宝箱倒计时）",
    )
    p_field.add_argument("--key", required=True, help="字段路径，如 data.countdownSec")
    p_field.add_argument("--value", required=True)
    p_field.set_defaults(handler=_cmd_field)

    return parser


def _cmd_list_cases(args: argparse.Namespace) -> dict[str, Any]:
    uri = _resolve_uri(args)
    cases = list_mock_cases(
        uri=uri,
        momoid=args.momoid,
        app_id=args.app_id,
        g_appid=args.g_appid,
        g_env=args.g_env,
        base_url=args.base_url,
    )
    return {"uri": uri, "count": len(cases), "cases": cases}


def _cmd_case_create(args: argparse.Namespace) -> dict[str, Any]:
    uri = _resolve_uri(args)
    response_json = _resolve_response_json(args)
    payload = create_mock_case(
        uri=uri,
        momoid=args.momoid,
        response_json=response_json,
        app_id=args.app_id,
        g_appid=args.g_appid,
        g_env=args.g_env,
        index=args.index,
        name=args.name,
        enable=args.enable,
        base_url=args.base_url,
    )
    return {"uri": uri, "enable": args.enable, "result": payload}


def _cmd_case_start(args: argparse.Namespace) -> dict[str, Any]:
    uri = _resolve_uri(args)
    payload = toggle_mock_case(
        uri=uri,
        momoid=args.momoid,
        action="start",
        app_id=args.app_id,
        g_appid=args.g_appid,
        g_env=args.g_env,
        index=args.index,
        base_url=args.base_url,
    )
    return {"uri": uri, "action": "start", "index": args.index, "result": payload}


def _cmd_case_stop(args: argparse.Namespace) -> dict[str, Any]:
    uri = _resolve_uri(args)
    payload = toggle_mock_case(
        uri=uri,
        momoid=args.momoid,
        action="stop",
        app_id=args.app_id,
        g_appid=args.g_appid,
        g_env=args.g_env,
        index=args.index,
        base_url=args.base_url,
    )
    return {"uri": uri, "action": "stop", "index": args.index, "result": payload}


def _cmd_case_delete(args: argparse.Namespace) -> dict[str, Any]:
    uri = _resolve_uri(args)
    payload = delete_mock_case(
        uri=uri,
        momoid=args.momoid,
        index=args.index,
        app_id=args.app_id,
        g_appid=args.g_appid,
        g_env=args.g_env,
        base_url=args.base_url,
    )
    return {"uri": uri, "index": args.index, "result": payload}


def _cmd_param_list(args: argparse.Namespace) -> dict[str, Any]:
    uri = _resolve_uri(args)
    params = list_param_mocks(uri=uri, momoid=args.momoid, base_url=args.base_url)
    return {"uri": uri, "count": len(params), "params": params}


def _cmd_param_set(args: argparse.Namespace) -> dict[str, Any]:
    uri = _resolve_uri(args)
    payload = set_param_mock(
        uri=uri,
        momoid=args.momoid,
        param_key=args.key,
        param_value=args.value,
        base_url=args.base_url,
    )
    return {"uri": uri, "key": args.key, "value": args.value, "result": payload}


def _cmd_param_delete(args: argparse.Namespace) -> dict[str, Any]:
    uri = _resolve_uri(args)
    payload = delete_param_mock(
        uri=uri,
        momoid=args.momoid,
        param_key=args.key,
        base_url=args.base_url,
    )
    return {"uri": uri, "key": args.key, "result": payload}


def _cmd_field(args: argparse.Namespace) -> dict[str, Any]:
    return _cmd_param_set(args)


def _format_summary(result: dict[str, Any]) -> str:
    if "cases" in result:
        lines = [f"URI: {result.get('uri')}", f"mock_cases: {result.get('count', 0)}"]
        for case in result.get("cases") or []:
            if not isinstance(case, dict):
                continue
            lines.append(
                f"- index={case.get('index')} enable={case.get('enable')} "
                f"name={case.get('name')} time={case.get('time')}"
            )
        return "\n".join(lines)
    if "params" in result:
        lines = [f"URI: {result.get('uri')}", f"param_mock: {result.get('count', 0)}"]
        for row in result.get("params") or []:
            if not isinstance(row, dict):
                continue
            lines.append(f"- {row.get('param_key')} = {row.get('value')} status={row.get('status')}")
        return "\n".join(lines)
    return json.dumps(result, ensure_ascii=False, indent=2)


def main(argv: list[str] | None = None) -> int:
    load_local_env(tunnel_dir())
    args = build_parser().parse_args(argv)
    try:
        result = args.handler(args)
    except (ValueError, RuntimeError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    if args.output == "json":
        _print_json(result)
    else:
        print(_format_summary(result))
    return 0
