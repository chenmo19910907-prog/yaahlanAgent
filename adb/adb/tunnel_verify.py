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


def _response_dict(item: dict[str, Any]) -> dict[str, Any]:
    response = item.get("response")
    return response if isinstance(response, dict) else {}


def _response_ec(item: dict[str, Any]) -> Any:
    return _response_dict(item).get("ec")


def _response_em(item: dict[str, Any]) -> Any:
    return _response_dict(item).get("em")


def _failure_reason(item: dict[str, Any]) -> str | None:
    """业务失败说明：优先 response.em，其次 data 内 reason/msg。"""
    resp = _response_dict(item)
    ec = resp.get("ec")
    try:
        if int(ec) == 200:
            return None
    except (TypeError, ValueError):
        pass
    em = str(resp.get("em") or "").strip()
    if em:
        return em
    data = resp.get("data")
    if isinstance(data, dict):
        for key in ("reason", "msg", "message", "errorMsg", "toast"):
            val = data.get(key)
            if val:
                return str(val).strip()
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
    resp = _response_dict(item)
    data = resp.get("data")
    out: dict[str, Any] = {
        "_id": item.get("_id"),
        "time": item.get("time"),
        "method": item.get("method"),
        "status": item.get("status"),
        "time_cost": item.get("time_cost"),
        "url": item.get("url"),
        "responseEc": _response_ec(item),
        "responseEm": _response_em(item),
        "failureReason": _failure_reason(item),
    }
    if isinstance(data, dict):
        out["responseData"] = data
    return out


def _items_by_keyword(
    items: list[dict[str, Any]],
    keyword: str,
) -> list[dict[str, Any]]:
    if not keyword:
        return list(items)
    matched = [item for item in items if _url_matches(item, keyword)]
    return sorted(matched, key=lambda x: str(x.get("time", "")), reverse=True)


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
        keyword_hits = _items_by_keyword(latest_items, options.keyword)
        if len(keyword_hits) >= options.min_matches:
            summaries = [_summarize_item(x) for x in keyword_hits[:10]]
            latest = summaries[0]
            if options.expect_response_ec is not None:
                try:
                    ec_ok = int(latest.get("responseEc")) == int(options.expect_response_ec)
                except (TypeError, ValueError):
                    ec_ok = False
                if ec_ok:
                    return {
                        "ok": True,
                        "momoid": options.momoid,
                        "keyword": options.keyword,
                        "startTime": start_time,
                        "polls": polls,
                        "matchedCount": len(keyword_hits),
                        "matches": summaries,
                        "screenshotHint": "抓包已通过；不必读图",
                    }
                reason = latest.get("failureReason") or latest.get("responseEm")
                return {
                    "ok": False,
                    "momoid": options.momoid,
                    "keyword": options.keyword,
                    "startTime": start_time,
                    "polls": polls,
                    "matchedCount": len(keyword_hits),
                    "matches": summaries,
                    "businessFailure": True,
                    "error": (
                        f"已抓到请求但 response.ec={latest.get('responseEc')}；"
                        f"失败原因: {reason or '（见 matches[0].responseData）'}"
                    ),
                    "screenshotHint": "优先读 matches[0].failureReason / responseEm，再读图",
                }
            return {
                "ok": True,
                "momoid": options.momoid,
                "keyword": options.keyword,
                "startTime": start_time,
                "polls": polls,
                "matchedCount": len(keyword_hits),
                "matches": summaries,
                "screenshotHint": "读 matches[0].responseEc / failureReason 判定业务成败",
            }

        time.sleep(options.poll_interval_ms / 1000.0)

    keyword_hits = _items_by_keyword(latest_items, options.keyword)
    summaries = [_summarize_item(x) for x in keyword_hits[:10]]
    return {
        "ok": False,
        "momoid": options.momoid,
        "keyword": options.keyword,
        "startTime": start_time,
        "polls": polls,
        "matchedCount": len(keyword_hits),
        "matches": summaries,
        "recentUrls": [
            str(x.get("url", ""))
            for x in sorted(
                latest_items,
                key=lambda i: str(i.get("time", "")),
                reverse=True,
            )[:8]
        ],
        "error": last_error or f"等待 {options.wait_seconds}s 内未匹配到期望请求",
        "screenshotHint": "未发出请求时读图排查；已发出则 tunnel last 读 failureReason",
    }


def fetch_latest_tunnel_match(
    *,
    momoid: str,
    keyword: str,
    since_seconds: int = 300,
    g_appid: str = "All",
    g_env: str = "alpha",
    base_url: str = "https://tunnel.wemomo.com",
) -> dict[str, Any]:
    """读取最近一条 URL 匹配关键字的抓包，含 response.em 等业务失败原因。"""
    list_requests, normalize_request_list, tunnel_success = _ensure_tunnel_import()
    start_time = int(time.time()) - max(1, since_seconds)
    payload = list_requests(
        base_url=base_url,
        momoid=momoid,
        start_time=start_time,
        keyword="",
        g_appid=g_appid,
        g_env=g_env,
    )
    meta = {
        "tunnelEc": payload.get("ec"),
        "tunnelEm": payload.get("em"),
        "tunnelOk": tunnel_success(payload.get("ec")),
        "startTime": start_time,
        "itemCount": 0,
    }
    if not tunnel_success(payload.get("ec")):
        return {
            "ok": False,
            "momoid": momoid,
            "keyword": keyword,
            "sinceSeconds": since_seconds,
            "tunnelMeta": meta,
            "error": f"Tunnel ec={payload.get('ec')} em={payload.get('em')}",
        }
    items = normalize_request_list(payload)
    meta["itemCount"] = len(items)
    hits = _items_by_keyword(items, keyword)
    if not hits:
        return {
            "ok": False,
            "momoid": momoid,
            "keyword": keyword,
            "sinceSeconds": since_seconds,
            "tunnelMeta": meta,
            "matchedCount": 0,
            "error": f"最近 {since_seconds}s 内无 URL 含 {keyword!r} 的请求",
        }
    summary = _summarize_item(hits[0])
    ec = summary.get("responseEc")
    try:
        business_ok = int(ec) == 200
    except (TypeError, ValueError):
        business_ok = False
    return {
        "ok": business_ok,
        "momoid": momoid,
        "keyword": keyword,
        "sinceSeconds": since_seconds,
        "tunnelMeta": meta,
        "matchedCount": len(hits),
        "latest": summary,
        "failureReason": summary.get("failureReason"),
        "agentHint": (
            "送礼等写操作：读 latest.responseEc；非 200 时 failureReason / responseEm 即失败原因。"
        ),
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
