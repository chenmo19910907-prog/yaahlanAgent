#!/usr/bin/env python3
"""大R用户管理后台 API 验收：列表 / 明细 / 排序 / 搜索 smoke。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, timedelta
from typing import Any

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from admin.big_rich import (  # noqa: E402
    ENDPOINTS,
    USER_TYPE_RECHARGE,
    USER_TYPE_VIP,
    VIP_CHANGE_DOWN,
    VIP_CHANGE_UP,
    big_rich_config,
    build_big_rich_url,
    build_daily_vip4_body,
    build_page_list_body,
    build_user_detail_body,
    build_vip_change_body,
    extract_page_rows,
    month_summary_range,
    parse_detail_bundle,
    parse_page_list_summary,
    post_big_rich,
    verify_page_list_columns,
    verify_search_hit,
    verify_sort_monotonic,
)
from admin.big_r_report import format_smoke_html, format_smoke_markdown  # noqa: E402
from admin.config import defaults  # noqa: E402
from admin.env import load_local_env  # noqa: E402


def _base_url(args: argparse.Namespace) -> str:
    base = (args.base_url or os.environ.get("ADMIN_BASE_URL") or defaults("api").get("baseUrl") or "").strip()
    if not base:
        raise ValueError("缺少 Admin 域名：设置 ADMIN_BASE_URL 或传 --base-url")
    return base.rstrip("/")


def _print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _write_text(path: str, content: str) -> None:
    target = os.path.expanduser(path)
    parent = os.path.dirname(target)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(target, "w", encoding="utf-8") as f:
        f.write(content)


def _write_report_outputs(report: dict[str, Any], args: argparse.Namespace) -> dict[str, str]:
    written: dict[str, str] = {}
    title = str(getattr(args, "title", "") or "大R后台 API 冒烟验收").strip()
    if getattr(args, "out_json", ""):
        path = os.path.expanduser(args.out_json)
        _write_text(path, json.dumps(report, ensure_ascii=False, indent=2))
        written["json"] = path
    if getattr(args, "out_md", ""):
        path = os.path.expanduser(args.out_md)
        _write_text(path, format_smoke_markdown(report, title=title))
        written["md"] = path
    if getattr(args, "out_html", ""):
        path = os.path.expanduser(args.out_html)
        _write_text(path, format_smoke_html(report, title=title))
        written["html"] = path
    return written


def cmd_list_endpoints(_: argparse.Namespace) -> int:
    cfg = big_rich_config()
    base = str(defaults("api").get("baseUrl") or "https://yaahlan-admin-alpha.wemomo.com").rstrip("/")
    rows = []
    for name, _path in sorted(cfg["paths"].items()):
        rows.append({"endpoint": name, "url": build_big_rich_url(base, name)})
    _print_json(
        {
            "frontendUrl": cfg.get("frontendUrl"),
            "apiPrefix": cfg.get("apiPrefix"),
            "endpoints": rows,
        }
    )
    return 0


def cmd_call(args: argparse.Namespace) -> int:
    body = json.loads(args.body) if args.body else {}
    resp = post_big_rich(_base_url(args), args.endpoint, body, timeout_s=args.timeout_s)
    _print_json(resp if args.raw else parse_page_list_summary(resp) if args.endpoint == "page_list" else resp.get("data"))
    return 0


def cmd_page_list(args: argparse.Namespace) -> int:
    body = build_page_list_body(
        user_type=USER_TYPE_VIP if args.tab == "vip" else USER_TYPE_RECHARGE,
        user_id=args.user_id or "",
        country=args.country or "",
        query_period_type=args.period_type,
        new_start_date=args.new_start or None,
        new_end_date=args.new_end or None,
        old_start_date=args.old_start or None,
        old_end_date=args.old_end or None,
        order_by=args.order_by,
        sort=args.sort,
        index=args.index,
        limit=args.limit,
    )
    if args.dump_body:
        print(json.dumps(body, ensure_ascii=False, indent=2), file=sys.stderr)
    resp = post_big_rich(_base_url(args), "page_list", body, timeout_s=args.timeout_s)
    summary = parse_page_list_summary(resp)
    _print_json(summary if args.summary else resp)
    return 0


def cmd_user_detail(args: argparse.Namespace) -> int:
    body = build_user_detail_body(
        args.user_id,
        start_date=args.start_date or None,
        end_date=args.end_date or None,
    )
    base = _base_url(args)
    detail_keys = (
        ("disburseScene", "detail_disburse_scene"),
        ("giftTop50", "detail_gift_top50"),
        ("recvTop50", "detail_recv_top50"),
        ("gameTop", "detail_game_top"),
        ("rechargeTop20", "detail_recharge_top20"),
    )
    bundle: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for label, endpoint in detail_keys:
        try:
            bundle[label] = post_big_rich(base, endpoint, body, timeout_s=args.timeout_s)
        except RuntimeError as exc:
            errors.append(f"{label}: {exc}")
    summary = parse_detail_bundle(bundle)
    summary["userId"] = args.user_id
    summary["request"] = body
    if errors:
        summary["errors"] = errors
    _print_json(summary)
    return 1 if errors else 0


def cmd_vip_change(args: argparse.Namespace) -> int:
    body = build_vip_change_body(
        week_anchor_date=args.week_anchor or None,
        change_type=VIP_CHANGE_UP if args.change == "up" else VIP_CHANGE_DOWN,
        index=args.index,
        limit=args.limit,
    )
    resp = post_big_rich(_base_url(args), "vip_change_page", body, timeout_s=args.timeout_s)
    _print_json(parse_page_list_summary(resp) if args.summary else resp)
    return 0


def cmd_daily_vip4(args: argparse.Namespace) -> int:
    body = build_daily_vip4_body(
        start_date=args.start_date or None,
        end_date=args.end_date or None,
        index=args.index,
        limit=args.limit,
    )
    resp = post_big_rich(_base_url(args), "daily_vip4_page", body, timeout_s=args.timeout_s)
    _print_json(parse_page_list_summary(resp) if args.summary else resp)
    return 0


def cmd_verify_sort(args: argparse.Namespace) -> int:
    base = _base_url(args)
    common = dict(
        user_type=USER_TYPE_VIP if args.tab == "vip" else USER_TYPE_RECHARGE,
        query_period_type=args.period_type,
        order_by=args.order_by,
        limit=max(args.limit, 5),
        index=0,
    )
    desc_body = build_page_list_body(**common, sort="desc")
    asc_body = build_page_list_body(**common, sort="asc")
    desc_resp = post_big_rich(base, "page_list", desc_body, timeout_s=args.timeout_s)
    asc_resp = post_big_rich(base, "page_list", asc_body, timeout_s=args.timeout_s)
    desc_rows, desc_total = extract_page_rows(desc_resp)
    asc_rows, asc_total = extract_page_rows(asc_resp)
    issues = verify_sort_monotonic(desc_rows, args.order_by, descending=True)
    issues += verify_sort_monotonic(asc_rows, args.order_by, descending=False)
    result = {
        "ok": not issues,
        "orderBy": args.order_by,
        "totalCount": desc_total,
        "descSample": [row.get(args.order_by) for row in desc_rows[:5]],
        "ascSample": [row.get(args.order_by) for row in asc_rows[:5]],
        "issues": issues,
    }
    _print_json(result)
    return 0 if result["ok"] else 3


def cmd_verify_search(args: argparse.Namespace) -> int:
    if not args.user_id:
        raise ValueError("verify-search 须传 --user-id")
    body = build_page_list_body(
        user_type=USER_TYPE_VIP if args.tab == "vip" else USER_TYPE_RECHARGE,
        user_id=args.user_id,
        query_period_type=args.period_type,
        limit=args.limit,
        index=0,
    )
    resp = post_big_rich(_base_url(args), "page_list", body, timeout_s=args.timeout_s)
    rows, total = extract_page_rows(resp)
    issues = verify_search_hit(rows, args.user_id)
    result = {
        "ok": not issues,
        "userId": args.user_id,
        "totalCount": total,
        "rows": rows,
        "issues": issues,
    }
    _print_json(result)
    return 0 if result["ok"] else 3


def cmd_smoke(args: argparse.Namespace) -> int:
    base = _base_url(args)
    start, end = month_summary_range()
    checks: list[dict[str, Any]] = []

    def record(
        name: str,
        ok: bool,
        *,
        case_desc: str = "",
        endpoint: str = "",
        request_body: Any = None,
        response: Any = None,
        assertion: str = "",
        detail: Any = None,
    ) -> None:
        checks.append({
            "name": name,
            "ok": ok,
            "case": case_desc,
            "endpoint": endpoint,
            "request": request_body,
            "response": response,
            "assertion": assertion,
            "detail": detail,
        })

    # 1) VIP 列表
    try:
        vip_body = build_page_list_body(
            user_type=USER_TYPE_VIP,
            query_period_type="MONTH_SUMMARY",
            new_start_date=start,
            new_end_date=end,
            limit=args.limit,
        )
        vip_resp = post_big_rich(base, "page_list", vip_body, timeout_s=args.timeout_s)
        vip_rows, vip_total = extract_page_rows(vip_resp)
        col_issues = verify_page_list_columns(vip_rows)
        record(
            "vip_page_list",
            not col_issues and vip_total >= 0,
            case_desc="VIP用户Tab列表：userType=2，按月汇总，验证字段完整性",
            endpoint="POST /admin/big-rich/pageList",
            request_body=vip_body,
            response=vip_resp.get("data"),
            assertion=f"ec=200, totalCount≥0, 字段完整（{','.join(col_issues) if col_issues else '全部存在'}）",
            detail={"totalCount": vip_total, "returned": len(vip_rows), "columnIssues": col_issues},
        )
    except RuntimeError as exc:
        record("vip_page_list", False, case_desc="VIP用户Tab列表", detail=str(exc))
        vip_rows = []

    # 2) 充值用户 Tab
    try:
        recharge_body = build_page_list_body(
            user_type=USER_TYPE_RECHARGE,
            query_period_type="MONTH_SUMMARY",
            limit=min(args.limit, 5),
        )
        recharge_resp = post_big_rich(base, "page_list", recharge_body, timeout_s=args.timeout_s)
        recharge_rows, recharge_total = extract_page_rows(recharge_resp)
        record(
            "recharge_page_list",
            True,
            case_desc="充值用户Tab列表：userType=1，按月汇总",
            endpoint="POST /admin/big-rich/pageList",
            request_body=recharge_body,
            response=recharge_resp.get("data"),
            assertion=f"ec=200, totalCount={recharge_total}",
            detail={"totalCount": recharge_total},
        )
    except RuntimeError as exc:
        record("recharge_page_list", False, case_desc="充值用户Tab列表", detail=str(exc))

    # 3) 排序
    try:
        sort_body = build_page_list_body(order_by="rechargeUsd", sort="desc", limit=max(args.limit, 5))
        sort_resp = post_big_rich(base, "page_list", sort_body, timeout_s=args.timeout_s)
        sort_rows, _ = extract_page_rows(sort_resp)
        sort_issues = verify_sort_monotonic(sort_rows, "rechargeUsd", descending=True)
        sort_values = [row.get("rechargeUsd") for row in sort_rows[:10]]
        record(
            "sort_rechargeUsd_desc",
            not sort_issues,
            case_desc="排序校验：rechargeUsd降序，验证返回数据单调递减",
            endpoint="POST /admin/big-rich/pageList",
            request_body=sort_body,
            response={"rechargeUsd_values": sort_values, "rowCount": len(sort_rows)},
            assertion=f"降序单调: {'通过' if not sort_issues else sort_issues}",
            detail={"issues": sort_issues, "sampleValues": sort_values},
        )
    except RuntimeError as exc:
        record("sort_rechargeUsd_desc", False, case_desc="排序校验", detail=str(exc))

    # 4) 搜索指定用户或首条用户
    target_uid = (args.user_id or "").strip()
    if not target_uid and vip_rows:
        target_uid = str(vip_rows[0].get("userId") or "")
    if target_uid:
        try:
            search_body = build_page_list_body(user_type=USER_TYPE_VIP, user_id=target_uid, limit=5)
            search_resp = post_big_rich(base, "page_list", search_body, timeout_s=args.timeout_s)
            search_rows, _ = extract_page_rows(search_resp)
            search_issues = verify_search_hit(search_rows, target_uid)
            record(
                "search_user",
                not search_issues,
                case_desc=f"精确搜索：userId={target_uid}，验证仅返回1条且匹配",
                endpoint="POST /admin/big-rich/pageList",
                request_body=search_body,
                response=search_rows,
                assertion=f"返回{len(search_rows)}条, userId匹配: {'通过' if not search_issues else search_issues}",
                detail={"userId": target_uid, "issues": search_issues},
            )
        except RuntimeError as exc:
            record("search_user", False, case_desc=f"精确搜索 userId={target_uid}", detail=str(exc))

        # 5) 用户明细
        try:
            detail_body = build_user_detail_body(target_uid)
            detail_bundle: dict[str, dict[str, Any]] = {}
            for label, endpoint in (
                ("disburseScene", "detail_disburse_scene"),
                ("giftTop50", "detail_gift_top50"),
                ("gameTop", "detail_game_top"),
            ):
                detail_bundle[label] = post_big_rich(base, endpoint, detail_body, timeout_s=args.timeout_s)
            detail_summary = parse_detail_bundle(detail_bundle)
            record(
                "user_detail_partial",
                bool(detail_summary.get("sections")),
                case_desc=f"用户明细：userId={target_uid}，钻石分布/送礼TOP/游戏TOP",
                endpoint="POST /admin/big-rich/detail/*（3个接口）",
                request_body=detail_body,
                response=detail_summary.get("sections"),
                assertion=f"3个接口均返回ec=200, totalRechargeCoin={detail_summary.get('totalRechargeCoin')}, gameProfit={detail_summary.get('totalGameProfit')}",
                detail={
                    "userId": target_uid,
                    "totalRechargeCoin": detail_summary.get("totalRechargeCoin"),
                    "totalGameProfit": detail_summary.get("totalGameProfit"),
                },
            )
        except RuntimeError as exc:
            record("user_detail_partial", False, case_desc=f"用户明细 userId={target_uid}", detail=str(exc))
    else:
        record("search_user", False, case_desc="精确搜索", detail="无 userId 可测（列表为空且未传 --user-id）")

    # 6) VIP 升降级 / 每日新增
    try:
        monday = date.today() - timedelta(days=date.today().weekday())
        vc_body = build_vip_change_body(week_anchor_date=monday, change_type=VIP_CHANGE_DOWN, limit=5)
        vc_resp = post_big_rich(base, "vip_change_page", vc_body, timeout_s=args.timeout_s)
        vc_rows, vc_total = extract_page_rows(vc_resp)
        record(
            "vip_change_page",
            True,
            case_desc=f"VIP升降级列表：weekAnchor={monday.isoformat()}, changeType=DOWN",
            endpoint="POST /admin/big-rich/vip-change/page",
            request_body=vc_body,
            response=vc_resp.get("data"),
            assertion=f"ec=200, totalCount={vc_total}",
            detail={"totalCount": vc_total},
        )
    except RuntimeError as exc:
        record("vip_change_page", False, case_desc="VIP升降级列表", detail=str(exc))

    try:
        yesterday = date.today() - timedelta(days=1)
        dv_body = build_daily_vip4_body(start_date=yesterday)
        dv_resp = post_big_rich(base, "daily_vip4_page", dv_body, timeout_s=args.timeout_s)
        dv_rows, dv_total = extract_page_rows(dv_resp)
        record(
            "daily_vip4_page",
            True,
            case_desc=f"每日新增VIP4列表：date={yesterday.isoformat()}",
            endpoint="POST /admin/big-rich/daily-vip4/page",
            request_body=dv_body,
            response=dv_resp.get("data"),
            assertion=f"ec=200, totalCount={dv_total}",
            detail={"totalCount": dv_total},
        )
    except RuntimeError as exc:
        record("daily_vip4_page", False, case_desc="每日新增VIP4列表", detail=str(exc))

    failed = [item for item in checks if not item["ok"]]
    report = {
        "ok": not failed,
        "frontendUrl": big_rich_config().get("frontendUrl"),
        "baseUrl": base,
        "passed": sum(1 for item in checks if item["ok"]),
        "failed": len(failed),
        "checks": checks,
    }
    written = _write_report_outputs(report, args)
    if written:
        print(json.dumps({"ok": report["ok"], "outputs": written}, ensure_ascii=False, indent=2))
    if not getattr(args, "quiet", False):
        _print_json(report)
    return 0 if report["ok"] else 3


def cmd_report(args: argparse.Namespace) -> int:
    report_path = os.path.expanduser(args.input)
    report = json.loads(open(report_path, encoding="utf-8").read())
    if not isinstance(report, dict):
        raise ValueError("报告 JSON 须为 object")
    written = _write_report_outputs(report, args)
    print(json.dumps({"ok": report.get("ok"), "outputs": written}, ensure_ascii=False, indent=2))
    return 0


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--base-url", default="", help="Admin 域名，默认 ADMIN_BASE_URL")
    parser.add_argument("--timeout-s", type=float, default=15.0, help="HTTP 超时秒数")


def main() -> int:
    load_local_env(_REPO)
    parser = argparse.ArgumentParser(description="大R用户管理后台 API 验收")
    sub = parser.add_subparsers(dest="command", required=True)

    p_endpoints = sub.add_parser("list-endpoints", help="列出全部大R API URL")
    p_endpoints.set_defaults(func=cmd_list_endpoints)

    p_call = sub.add_parser("call", help="调用指定 endpoint（JSON body）")
    _add_common_args(p_call)
    p_call.add_argument(
        "--endpoint",
        required=True,
        choices=sorted(ENDPOINTS.keys()),
        help="registry endpoint 名",
    )
    p_call.add_argument("--body", default="{}", help="请求 JSON")
    p_call.add_argument("--raw", action="store_true", help="输出完整响应")
    p_call.set_defaults(func=cmd_call)

    p_page = sub.add_parser("page-list", help="大R主列表 pageList")
    _add_common_args(p_page)
    p_page.add_argument("--tab", choices=("vip", "recharge"), default="vip")
    p_page.add_argument("--user-id", default="")
    p_page.add_argument("--country", default="")
    p_page.add_argument(
        "--period-type",
        default="MONTH_SUMMARY",
        help="WEEK_PERIOD|WEEK_SUMMARY|MONTH_PERIOD|MONTH_SUMMARY|FIXED_PERIOD",
    )
    p_page.add_argument("--new-start", default="", help="本期开始 YYYYMMDD")
    p_page.add_argument("--new-end", default="", help="本期结束 YYYYMMDD")
    p_page.add_argument("--old-start", default="", help="上期开始")
    p_page.add_argument("--old-end", default="", help="上期结束")
    p_page.add_argument("--order-by", default="rechargeUsd")
    p_page.add_argument("--sort", choices=("asc", "desc"), default="desc")
    p_page.add_argument("--index", type=int, default=0)
    p_page.add_argument("--limit", type=int, default=20)
    p_page.add_argument("--summary", action="store_true", default=True)
    p_page.add_argument("--dump-body", action="store_true")
    p_page.set_defaults(func=cmd_page_list)

    p_detail = sub.add_parser("user-detail", help="用户明细 5 个 detail 接口")
    _add_common_args(p_detail)
    p_detail.add_argument("--user-id", required=True)
    p_detail.add_argument("--start-date", default="")
    p_detail.add_argument("--end-date", default="")
    p_detail.set_defaults(func=cmd_user_detail)

    p_vc = sub.add_parser("vip-change", help="VIP 升降级列表")
    _add_common_args(p_vc)
    p_vc.add_argument("--week-anchor", default="", help="自然周周一 YYYYMMDD")
    p_vc.add_argument("--change", choices=("up", "down"), default="down")
    p_vc.add_argument("--index", type=int, default=0)
    p_vc.add_argument("--limit", type=int, default=20)
    p_vc.add_argument("--summary", action="store_true", default=True)
    p_vc.set_defaults(func=cmd_vip_change)

    p_dv = sub.add_parser("daily-vip4", help="每日新增 VIP4 列表")
    _add_common_args(p_dv)
    p_dv.add_argument("--start-date", default="")
    p_dv.add_argument("--end-date", default="")
    p_dv.add_argument("--index", type=int, default=0)
    p_dv.add_argument("--limit", type=int, default=20)
    p_dv.add_argument("--summary", action="store_true", default=True)
    p_dv.set_defaults(func=cmd_daily_vip4)

    p_sort = sub.add_parser("verify-sort", help="校验列表排序单调性")
    _add_common_args(p_sort)
    p_sort.add_argument("--tab", choices=("vip", "recharge"), default="vip")
    p_sort.add_argument("--period-type", default="MONTH_SUMMARY")
    p_sort.add_argument("--order-by", default="rechargeUsd")
    p_sort.add_argument("--limit", type=int, default=20)
    p_sort.set_defaults(func=cmd_verify_sort)

    p_search = sub.add_parser("verify-search", help="校验 userId 精确搜索")
    _add_common_args(p_search)
    p_search.add_argument("--user-id", required=True)
    p_search.add_argument("--tab", choices=("vip", "recharge"), default="vip")
    p_search.add_argument("--period-type", default="MONTH_SUMMARY")
    p_search.add_argument("--limit", type=int, default=5)
    p_search.set_defaults(func=cmd_verify_search)

    p_smoke = sub.add_parser("smoke", help="冒烟：列表/排序/搜索/明细/VIP升降级/每日VIP4")
    _add_common_args(p_smoke)
    p_smoke.add_argument("--user-id", default="", help="可选，指定验收 userId")
    p_smoke.add_argument("--limit", type=int, default=10)
    p_smoke.add_argument("--out-json", default="", help="保存 JSON 报告，如 .tmp/big_r_smoke.json")
    p_smoke.add_argument("--out-html", default="", help="保存 HTML 可视化报告")
    p_smoke.add_argument("--out-md", default="", help="保存 Markdown 报告")
    p_smoke.add_argument("--title", default="大R后台 API 冒烟验收", help="报告标题")
    p_smoke.add_argument("--quiet", action="store_true", help="不写 stdout JSON（仅写文件时可用）")
    p_smoke.set_defaults(func=cmd_smoke)

    p_report = sub.add_parser("report", help="由 smoke JSON 生成 HTML/Markdown 可视化报告")
    p_report.add_argument("--input", required=True, help="smoke 输出的 JSON 路径")
    p_report.add_argument("--out-html", default="", help="HTML 输出路径")
    p_report.add_argument("--out-md", default="", help="Markdown 输出路径")
    p_report.add_argument("--out-json", default="", help="可选，复制/规范化 JSON")
    p_report.add_argument("--title", default="大R后台 API 冒烟验收", help="报告标题")
    p_report.set_defaults(func=cmd_report)

    args = parser.parse_args()
    try:
        return int(args.func(args))
    except (ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
