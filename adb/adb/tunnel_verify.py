"""ADB 操作后结合 Tunnel 抓包校验。"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .recorded_scripts import scripts_root


@dataclass(frozen=True)
class TunnelVerifyOptions:
    momoid: str
    keyword: str = ""
    wait_seconds: int = 30
    poll_interval_ms: int = 2000
    expect_http_status: int | None = 200
    expect_response_ec: int | None = None
    since_buffer_seconds: int = 5
    g_appid: str = "All"
    g_env: str = "alpha"
    min_matches: int = 1


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _ensure_tunnel_import() -> Any:
    root = str(_repo_root())
    if root not in sys.path:
        sys.path.insert(0, root)
    from Tunnel.tunnel.client import (  # noqa: WPS433
        list_requests,
        normalize_request_list,
        tunnel_success,
    )
    from Tunnel.tunnel.env import load_local_env  # noqa: WPS433

    load_local_env(str(_repo_root() / "Tunnel"))
    return list_requests, normalize_request_list, tunnel_success


def load_test_accounts() -> dict[str, Any]:
    index_path = scripts_root() / "索引.json"
    data = json.loads(index_path.read_text(encoding="utf-8"))
    accounts = data.get("testAccounts")
    if not isinstance(accounts, dict):
        return {}
    return accounts


def resolve_momoid(
    *,
    momoid: str | None = None,
    account: str | None = None,
) -> str:
    if momoid and momoid.strip():
        return momoid.strip()
    if not account or not account.strip():
        raise ValueError("须指定 --tunnel-momoid 或 --tunnel-account")

    key = account.strip()
    accounts = load_test_accounts()
    entry = accounts.get(key)
    if not isinstance(entry, dict):
        known = "、".join(sorted(accounts.keys())) or "（无）"
        raise ValueError(f"未知 tunnel-account {key!r}，可选: {known}")
    uid = str(entry.get("userId", "")).strip()
    if not uid:
        raise ValueError(f"testAccounts.{key} 缺少 userId")
    return uid


def parse_tunnel_verify_spec(spec: dict[str, Any] | None) -> TunnelVerifyOptions | None:
    if not isinstance(spec, dict):
        return None
    momoid = str(spec.get("momoid", "")).strip()
    account = str(spec.get("account", "")).strip()
    if not momoid and not account:
        momoid_key = str(spec.get("momoidKey", "")).strip()
        if momoid_key:
            account = momoid_key
    if not momoid and not account:
        return None

    keyword = str(spec.get("keyword", "")).strip()
    wait_seconds = int(spec.get("waitSeconds", 30))
    poll_interval_ms = int(spec.get("pollIntervalMs", 2000))
    since_buffer_seconds = int(spec.get("sinceBufferSeconds", 5))
    g_appid = str(spec.get("gAppid", "All")).strip() or "All"
    g_env = str(spec.get("gEnv", "alpha")).strip() or "alpha"
    min_matches = int(spec.get("minMatches", 1))

    expect_http_status = spec.get("expectHttpStatus", 200)
    if expect_http_status is None:
        http_status: int | None = None
    else:
        http_status = int(expect_http_status)

    expect_response_ec = spec.get("expectResponseEc")
    response_ec: int | None
    if expect_response_ec is None:
        response_ec = None
    else:
        response_ec = int(expect_response_ec)

    return TunnelVerifyOptions(
        momoid=resolve_momoid(momoid=momoid or None, account=account or None),
        keyword=keyword,
        wait_seconds=max(1, wait_seconds),
        poll_interval_ms=max(500, poll_interval_ms),
        expect_http_status=http_status,
        expect_response_ec=response_ec,
        since_buffer_seconds=max(0, since_buffer_seconds),
        g_appid=g_appid,
        g_env=g_env,
        min_matches=max(1, min_matches),
    )


def tunnel_options_from_args(
    args: Any,
    *,
    compose_spec: dict[str, Any] | None = None,
) -> TunnelVerifyOptions | None:
    cli_enabled = bool(
        getattr(args, "tunnel_momoid", None)
        or getattr(args, "tunnel_account", None)
        or getattr(args, "tunnel_keyword", None)
    )
    if cli_enabled:
        momoid = getattr(args, "tunnel_momoid", None)
        account = getattr(args, "tunnel_account", None)
        if not momoid and not account:
            raise ValueError("已传 --tunnel-keyword 时须同时指定 --tunnel-momoid 或 --tunnel-account")
        keyword = str(getattr(args, "tunnel_keyword", "") or "").strip()
        raw_status = getattr(args, "tunnel_expect_status", 200)
        http_status: int | None
        if raw_status is None or int(raw_status) < 0:
            http_status = None
        else:
            http_status = int(raw_status)

        return TunnelVerifyOptions(
            momoid=resolve_momoid(
                momoid=str(momoid).strip() if momoid else None,
                account=str(account).strip() if account else None,
            ),
            keyword=keyword,
            wait_seconds=max(1, int(getattr(args, "tunnel_wait", 30))),
            poll_interval_ms=max(500, int(getattr(args, "tunnel_poll_ms", 2000))),
            expect_http_status=http_status,
            expect_response_ec=(
                None
                if getattr(args, "tunnel_expect_ec", None) is None
                else int(args.tunnel_expect_ec)
            ),
            since_buffer_seconds=max(0, int(getattr(args, "tunnel_since_buffer", 5))),
            g_appid=str(getattr(args, "tunnel_g_appid", "All") or "All"),
            g_env=str(getattr(args, "tunnel_g_env", "alpha") or "alpha"),
            min_matches=max(1, int(getattr(args, "tunnel_min_matches", 1))),
        )

    if compose_spec is not None:
        return parse_tunnel_verify_spec(compose_spec.get("tunnelVerify"))
    return None


def _url_matches(item: dict[str, Any], keyword: str) -> bool:
    if not keyword:
        return True
    url = str(item.get("url", "")).lower()
    return keyword.lower() in url


def _response_ec(item: dict[str, Any]) -> Any:
    response = item.get("response")
    if isinstance(response, dict):
        return response.get("ec")
    return None


def _item_matches(
    item: dict[str, Any],
    *,
    keyword: str,
    expect_http_status: int | None,
    expect_response_ec: int | None,
) -> bool:
    if not _url_matches(item, keyword):
        return False
    if expect_http_status is not None:
        try:
            if int(item.get("status", -1)) != expect_http_status:
                return False
        except (TypeError, ValueError):
            return False
    if expect_response_ec is not None:
        ec = _response_ec(item)
        try:
            if int(ec) != expect_response_ec:
                return False
        except (TypeError, ValueError):
            return False
    return True


def _summarize_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "_id": item.get("_id"),
        "time": item.get("time"),
        "method": item.get("method"),
        "status": item.get("status"),
        "time_cost": item.get("time_cost"),
        "url": item.get("url"),
        "responseEc": _response_ec(item),
    }


def filter_tunnel_items(
    items: list[dict[str, Any]],
    options: TunnelVerifyOptions,
) -> list[dict[str, Any]]:
    matched = [
        item
        for item in items
        if _item_matches(
            item,
            keyword=options.keyword,
            expect_http_status=options.expect_http_status,
            expect_response_ec=options.expect_response_ec,
        )
    ]
    return sorted(matched, key=lambda x: str(x.get("time", "")), reverse=True)


def wait_for_tunnel(
    options: TunnelVerifyOptions,
    *,
    start_time: int,
    base_url: str = "https://tunnel.wemomo.com",
) -> dict[str, Any]:
    list_requests, normalize_request_list, tunnel_success = _ensure_tunnel_import()

    deadline = time.time() + options.wait_seconds
    last_error = ""
    latest_items: list[dict[str, Any]] = []
    polls = 0

    while time.time() <= deadline:
        polls += 1
        try:
            payload = list_requests(
                base_url=base_url,
                momoid=options.momoid,
                start_time=start_time,
                keyword="",
                g_appid=options.g_appid,
                g_env=options.g_env,
            )
        except (ValueError, RuntimeError) as e:
            last_error = str(e)
            time.sleep(options.poll_interval_ms / 1000.0)
            continue

        if not tunnel_success(payload.get("ec")):
            last_error = f"Tunnel ec={payload.get('ec')} em={payload.get('em')}"
            time.sleep(options.poll_interval_ms / 1000.0)
            continue

        latest_items = normalize_request_list(payload)
        matched = filter_tunnel_items(latest_items, options)
        if len(matched) >= options.min_matches:
            return {
                "ok": True,
                "momoid": options.momoid,
                "keyword": options.keyword,
                "startTime": start_time,
                "polls": polls,
                "matchedCount": len(matched),
                "matches": [_summarize_item(x) for x in matched[:10]],
                "screenshotHint": "结合 result.screenshot.path 读图核对 UI",
            }

        time.sleep(options.poll_interval_ms / 1000.0)

    matched = filter_tunnel_items(latest_items, options)
    return {
        "ok": False,
        "momoid": options.momoid,
        "keyword": options.keyword,
        "startTime": start_time,
        "polls": polls,
        "matchedCount": len(matched),
        "matches": [_summarize_item(x) for x in matched[:10]],
        "recentUrls": [
            str(x.get("url", ""))
            for x in sorted(
                latest_items,
                key=lambda i: str(i.get("time", "")),
                reverse=True,
            )[:8]
        ],
        "error": last_error or f"等待 {options.wait_seconds}s 内未匹配到期望请求",
        "screenshotHint": "结合 result.screenshot.path 读图核对 UI",
    }


def attach_tunnel_verify(
    result: dict[str, Any],
    options: TunnelVerifyOptions | None,
    *,
    start_time: int | None = None,
) -> tuple[dict[str, Any], bool]:
    """将 tunnelVerify 写入 result；返回 (result, tunnel_ok)。"""
    if options is None:
        return result, True

    if start_time is None:
        start_time = int(time.time()) - options.since_buffer_seconds

    verify = wait_for_tunnel(options, start_time=start_time)
    result["tunnelVerify"] = verify
    return result, bool(verify.get("ok"))


def add_tunnel_arguments(parser: argparse.ArgumentParser) -> None:
    group = parser.add_argument_group("Tunnel 抓包校验（操作后自动轮询 tunnel.wemomo.com）")
    group.add_argument("--tunnel-momoid", help="抓包 userId（momoid）")
    group.add_argument(
        "--tunnel-account",
        help="索引 testAccounts 键名，如 guildLeader / familyLeader",
    )
    group.add_argument(
        "--tunnel-keyword",
        help="URL 关键字（客户端过滤；如 sendGift、heartbeat、moment）",
    )
    group.add_argument("--tunnel-wait", type=int, default=30, help="最长等待秒数（默认 30）")
    group.add_argument("--tunnel-poll-ms", type=int, default=2000, help="轮询间隔毫秒")
    group.add_argument(
        "--tunnel-expect-status",
        type=int,
        default=200,
        help="期望 HTTP status；传 -1 表示不校验",
    )
    group.add_argument("--tunnel-expect-ec", type=int, help="期望 response.ec（可选）")
    group.add_argument("--tunnel-since-buffer", type=int, default=5, help="操作前回溯秒数")
    group.add_argument("--tunnel-g-appid", default="All", help="g_appid，默认 All")
    group.add_argument("--tunnel-g-env", default="alpha", help="g_env，默认 alpha")
    group.add_argument("--tunnel-min-matches", type=int, default=1, help="至少匹配条数")
