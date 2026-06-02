"""Yaahlan Admin CLI。"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse

from .client import admin_success, http_get_json, http_post_json
from .config import defaults
from .custom_gift import gateway_success, parse_custom_gift_list_summary
from .env import load_local_env
from .user import parse_user_detail_summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Yaahlan Admin 后台接口本地调用")
    parser.add_argument(
        "--base-url",
        default=os.environ.get("ADMIN_BASE_URL"),
        help="Admin 域名，默认 ADMIN_BASE_URL",
    )
    parser.add_argument("--timeout-ms", type=int, default=10000, help="HTTP 超时（毫秒）")
    parser.add_argument("--dump-body", action="store_true", help="输出最终请求 body 到 stderr")

    src = parser.add_mutually_exclusive_group(required=False)
    src.add_argument("--payload-file", help="完整请求 JSON 文件")
    src.add_argument("--payload", help="完整请求 JSON 字符串")

    parser.add_argument("--query-user-id", help="查询用户详情 userId（queryUserDetail）")
    parser.add_argument(
        "--query-custom-gift-list",
        action="store_true",
        help="查询 VIP5 定制礼物列表（getListConfig；返回 userId ↔ giftId）",
    )
    parser.add_argument(
        "--custom-gift-user-id",
        help="定制礼物列表：按 userId 过滤（配合 --query-custom-gift-list）",
    )
    parser.add_argument(
        "--custom-gift-per-page",
        type=int,
        help="定制礼物列表 perPage（默认 config.json vip5_custom_gift_list.defaultPerPage）",
    )
    parser.add_argument(
        "--output",
        choices=["summary", "json"],
        default="summary",
        help="输出格式：summary=摘要（默认）；json=完整响应",
    )
    return parser


def _resolve_base_url(args: argparse.Namespace) -> str:
    base_url = (args.base_url or defaults("api").get("baseUrl") or "").strip().rstrip("/")
    if not base_url:
        raise ValueError("缺少 Admin 域名：请传 --base-url 或设置 ADMIN_BASE_URL")
    return base_url


def _resolve_custom_gift_list_url(args: argparse.Namespace) -> str:
    cfg = defaults("vip5_custom_gift_list")
    base_url = (
        os.environ.get("ADMIN_GATEWAY_BASE_URL")
        or cfg.get("baseUrl")
        or ""
    ).strip().rstrip("/")
    if not base_url:
        raise ValueError("缺少 Gateway 域名：请设置 ADMIN_GATEWAY_BASE_URL 或 config.json vip5_custom_gift_list.baseUrl")
    path = str(cfg.get("path", "/yaahlan/backend/vip5UserConfig/getListConfig"))
    per_page = args.custom_gift_per_page
    if per_page is None:
        per_page = int(cfg.get("defaultPerPage", 100))
    if per_page <= 0:
        raise ValueError("custom_gift_per_page 必须为正整数")
    query = urllib.parse.urlencode({"perPage": per_page})
    return f"{base_url}{path}?{query}"


def _load_body(args: argparse.Namespace) -> dict[str, object]:
    if args.payload_file:
        with open(args.payload_file, "r", encoding="utf-8") as f:
            body = json.load(f)
    elif args.payload:
        body = json.loads(args.payload)
    else:
        body = {}

    if not isinstance(body, dict):
        raise ValueError("请求 body 必须是 JSON object")
    return body


def _apply_query_user_detail(args: argparse.Namespace, body: dict[str, object]) -> tuple[str, dict[str, object]]:
    user_id = str(args.query_user_id).strip()
    if not user_id:
        raise ValueError("query_user_id 不能为空")
    path = str(defaults("query_user_detail").get("path", "/admin/user/queryUserDetail"))
    return path, {"userId": user_id}


def main() -> int:
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_local_env(base_dir)

    args = build_parser().parse_args()
    try:
        if args.query_custom_gift_list:
            url = _resolve_custom_gift_list_url(args)
            if args.dump_body:
                print(f"GET {url}", file=sys.stderr)
            resp = http_get_json(url, timeout_s=max(args.timeout_ms, 1000) / 1000.0)
        elif args.query_user_id is not None:
            base_url = _resolve_base_url(args)
            path, body = _apply_query_user_detail(args, {})
            url = f"{base_url}{path}"
            if args.dump_body:
                print(f"POST {url}", file=sys.stderr)
                print(json.dumps(body, ensure_ascii=False, indent=2), file=sys.stderr)
            resp = http_post_json(url, body, timeout_s=max(args.timeout_ms, 1000) / 1000.0)
        else:
            base_url = _resolve_base_url(args)
            body = _load_body(args)
            path = str(defaults("query_user_detail").get("path", "/admin/user/queryUserDetail"))
            url = f"{base_url}{path}"
            if args.dump_body:
                print(f"POST {url}", file=sys.stderr)
                print(json.dumps(body, ensure_ascii=False, indent=2), file=sys.stderr)
            resp = http_post_json(url, body, timeout_s=max(args.timeout_ms, 1000) / 1000.0)
    except (ValueError, RuntimeError, OSError, json.JSONDecodeError) as e:
        print(f"执行失败: {e}", file=sys.stderr)
        return 1

    if args.output == "json":
        print(json.dumps(resp, ensure_ascii=False, indent=2))
    elif args.query_custom_gift_list:
        if not gateway_success(resp.get("status")):
            print(f"Gateway 返回失败: status={resp.get('status')}, msg={resp.get('msg')}", file=sys.stderr)
            print(json.dumps(resp, ensure_ascii=False, indent=2))
            return 3
        summary = parse_custom_gift_list_summary(
            resp.get("data"),
            filter_user_id=args.custom_gift_user_id,
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    elif args.query_user_id is not None:
        if not admin_success(resp.get("ec")):
            print(f"Admin 返回失败: ec={resp.get('ec')}, em={resp.get('em')}", file=sys.stderr)
            print(json.dumps(resp, ensure_ascii=False, indent=2))
            return 3
        summary = parse_user_detail_summary(resp.get("data"))
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(resp, ensure_ascii=False, indent=2))

    if args.query_custom_gift_list:
        if not gateway_success(resp.get("status")):
            print(f"Gateway 返回失败: status={resp.get('status')}, msg={resp.get('msg')}", file=sys.stderr)
            return 3
    elif args.query_user_id is not None and not admin_success(resp.get("ec")):
        print(f"Admin 返回失败: ec={resp.get('ec')}, em={resp.get('em')}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
