#!/usr/bin/env python3
"""大R后台 Stage 造数全流程：生成Excel → 上传CDN → MOA导入 → MOA重建。

用法：
    # 生成并导入指定日期的数据（默认1000用户）
    python Admin/scripts/big_r_import_data.py --dates 20260804 20260805

    # 生成整月数据
    python Admin/scripts/big_r_import_data.py --month 2026-06

    # 只生成Excel不导入
    python Admin/scripts/big_r_import_data.py --dates 20260804 20260805 --no-import

    # 指定用户数量
    python Admin/scripts/big_r_import_data.py --dates 20260804 --user-count 500

    # 使用已有CDN文件直接导入+重建
    python Admin/scripts/big_r_import_data.py --cdn-url https://s.momocdn.com/xxx.xlsx --dates 20260804 20260805
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parent.parent.parent
_ADMIN = _REPO / "Admin"
sys.path.insert(0, str(_ADMIN))

from admin.env import load_local_env

load_local_env(str(_ADMIN))


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

STATIC_UPLOAD_URL = "https://static.wemomo.com/api/file/upload"
MOA_ENTRY_URL = "https://mse.wemomo.com/apirest/httpproxy/moa/test"
MOA_SERVICE_URL = "/service/yaahlan-big-rich-query-service"
MOA_KEY = "momo.live.fproject.api.fproject-api"

TMP_DIR = _REPO / ".tmp"
TMP_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# Step 0: 获取测试环境用户
# ---------------------------------------------------------------------------

def fetch_stage_users(count: int, cookie: str) -> dict[str, dict]:
    """从 MDP ops-admin 获取测试环境用户列表。"""
    import requests

    headers = {"Cookie": cookie, "User-Agent": "Mozilla/5.0"}
    all_users: dict[str, dict] = {}
    page_no = 1
    page_size = 100

    while len(all_users) < count and page_no <= (count // page_size + 2):
        # 通过 Admin 模块的接口获取
        os.environ["MDP_AEGIS_TOKEN"] = _extract_cookie_value(cookie, "alpha_mdp_aegis_token")
        os.environ["MDP_CLOUD_AEGIS_TOKEN"] = _extract_cookie_value(cookie, "mdp_aegis_token")

        from admin.user_list import build_query_user_profile_list_body, fetch_user_profile_list

        body = build_query_user_profile_list_body(app_id=2005, page_no=page_no, page_size=page_size)
        try:
            summary = fetch_user_profile_list(body)
            records = summary.get("records") or []
            for r in records:
                uid = str(r.get("userId", ""))
                if uid and uid not in all_users:
                    all_users[uid] = {
                        "nickname": r.get("nickname", ""),
                        "country": r.get("countryCode", "") or r.get("area", ""),
                    }
            if len(records) < page_size:
                break
        except Exception as e:
            print(f"  ⚠️ 获取用户列表失败 page {page_no}: {e}", file=sys.stderr)
            break
        page_no += 1

    print(f"  获取到 {len(all_users)} 个测试环境用户")
    return dict(list(all_users.items())[:count])


def _extract_cookie_value(cookie: str, key: str) -> str:
    for part in cookie.split(";"):
        part = part.strip()
        if part.startswith(f"{key}="):
            return part[len(key) + 1:]
    return ""


def load_or_fetch_users(count: int, cookie: str) -> dict[str, dict]:
    """优先从缓存读取用户列表，不够再拉取。"""
    cache_file = TMP_DIR / "stage_users_mdp.json"
    if cache_file.exists():
        with open(cache_file, "r", encoding="utf-8") as f:
            cached = json.load(f)
        if len(cached) >= count:
            print(f"  从缓存加载 {count} 个用户")
            return dict(list(cached.items())[:count])

    users = fetch_stage_users(count, cookie)
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)
    return users


# ---------------------------------------------------------------------------
# Step 1: 生成 Excel
# ---------------------------------------------------------------------------

def generate_excel(
    users: dict[str, dict],
    dates: list[int],
    output_path: Path,
    seed: int = 42,
) -> Path:
    """生成符合天级宽表规范的 Excel 文件。"""
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "天级汇总数据"

    headers = [
        "user_id", "belong_date", "recharge_usd", "recharge_coin",
        "non_game_disburse_coin", "game_bet_coin", "gift_disburse_coin",
        "self_gift_coin", "history_vip_level", "history_is_vip4",
        "history_wealth_level", "last_recharge_time", "last_online_time",
        "register_time", "nickname", "country", "register_app",
    ]
    ws.append(headers)

    random.seed(seed)
    uids = list(users.keys())
    rows_written = 0

    for idx, uid in enumerate(uids):
        info = users[uid]

        # 按比例分配用户场景
        if idx < len(uids) * 0.1:
            vip_level = random.choice([4, 5, 6, 7, 8])
            is_vip4 = 1
            wealth_level = random.randint(12, 20)
            base_recharge = random.uniform(50, 500)
        elif idx < len(uids) * 0.25:
            vip_level = 4
            is_vip4 = 1
            wealth_level = random.randint(8, 15)
            base_recharge = random.uniform(10, 100)
        elif idx < len(uids) * 0.5:
            vip_level = random.choice([1, 2, 3])
            is_vip4 = 0
            wealth_level = random.randint(3, 10)
            base_recharge = random.uniform(5, 50)
        elif idx < len(uids) * 0.75:
            vip_level = random.choice([2, 3, 4])
            is_vip4 = 1 if vip_level >= 4 else 0
            wealth_level = random.randint(5, 12)
            base_recharge = random.uniform(0, 20)
        else:
            vip_level = random.choice([1, 2, 3])
            is_vip4 = 0
            wealth_level = random.randint(1, 8)
            base_recharge = random.uniform(0, 10)

        # 升降级模拟
        upgrade_range = range(int(len(uids) * 0.05), int(len(uids) * 0.07))
        downgrade_range = range(int(len(uids) * 0.15), int(len(uids) * 0.17))
        vip_changes = [0] * len(dates)
        if idx in upgrade_range and len(dates) > 1:
            vip_changes[-1] = 1
        elif idx in downgrade_range and len(dates) > 1:
            vip_changes[-1] = -1

        register_time_ms = random.randint(1600000000000, 1750000000000)
        register_app = random.choice([1, 2])

        country = info.get("country", "SA")
        if not country or country == "MENA":
            country = random.choice(["SA", "IQ", "EG", "AE", "KW", "QA", "TR", "LB"])

        for day_idx, belong_date in enumerate(dates):
            day_factor = 1 + random.uniform(-0.3, 0.5)

            recharge_usd = round(base_recharge * day_factor, 2) if random.random() > 0.2 else 0
            recharge_coin = round(recharge_usd * 520, 2) if recharge_usd > 0 else 0

            non_game = round(random.uniform(100, 5000) * day_factor, 2) if random.random() > 0.3 else 0
            game_bet = round(random.uniform(500, 50000) * day_factor, 2) if random.random() > 0.4 else 0
            gift_disburse = round(random.uniform(100, 3000) * day_factor, 2) if random.random() > 0.3 else 0
            self_gift = round(gift_disburse * random.uniform(0, 0.3), 2) if gift_disburse > 0 else 0

            current_vip = max(1, vip_level + sum(vip_changes[: day_idx + 1]))

            last_recharge = belong_date if recharge_usd > 0 else 0
            last_online = belong_date

            ws.append([
                uid, belong_date, recharge_usd, recharge_coin,
                non_game, game_bet, gift_disburse, self_gift,
                current_vip, is_vip4, wealth_level,
                last_recharge, last_online, register_time_ms,
                info["nickname"], country, register_app,
            ])
            rows_written += 1

    wb.save(str(output_path))
    print(f"  ✅ Excel 已生成: {output_path}")
    print(f"     {len(uids)} 用户 × {len(dates)} 天 = {rows_written} 行")
    return output_path


# ---------------------------------------------------------------------------
# Step 2: 上传到 CDN
# ---------------------------------------------------------------------------

def upload_to_cdn(file_path: Path, cookie: str) -> str:
    """上传文件到 static.wemomo.com，返回 CDN URL。"""
    import requests
    from datetime import datetime

    headers = {"Cookie": cookie, "User-Agent": "Mozilla/5.0"}

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_name = f"big_r_data_{ts}.xlsx"

    with open(file_path, "rb") as f:
        files = {"file": (unique_name, f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
        resp = requests.post(STATIC_UPLOAD_URL, headers=headers, files=files, timeout=30)

    data = resp.json()
    if data.get("ec") == 200 and data.get("data"):
        file_info = data["data"][0]
        if file_info.get("status") == 1:
            cdn_url = f"https://s.momocdn.com/{file_info['parentRsyncPath']}/{file_info['fileName']}"
            print(f"  ✅ 上传成功: {cdn_url}")
            return cdn_url

    # 文件已存在的情况
    if data.get("data") and data["data"][0].get("errorCode") == 4009:
        file_info = data["data"][0]
        cdn_url = f"https://s.momocdn.com/{file_info['parentRsyncPath']}/{file_info['fileName']}"
        print(f"  ⚠️ 文件已存在，使用已有URL: {cdn_url}")
        return cdn_url

    raise RuntimeError(f"上传失败: ec={data.get('ec')}, em={data.get('em')}, data={data.get('data')}")


# ---------------------------------------------------------------------------
# Step 3: MOA 导入天级数据
# ---------------------------------------------------------------------------

def moa_import(cdn_url: str, moa_cookie: str) -> dict:
    """调用 importUserDayIndexSummary 导入天级数据。"""
    sys.path.insert(0, str(_REPO / "MOA"))
    from moa.client import http_post_json

    os.environ["MOA_REQUEST_SOURCE"] = "moaProxy"
    os.environ["MOA_ORIGIN"] = "https://mse.wemomo.com"
    os.environ["MOA_REFERER"] = "https://mse.wemomo.com/"

    payload = {
        "type": "moa",
        "key": MOA_KEY,
        "url": MOA_SERVICE_URL,
        "method": "importUserDayIndexSummary",
        "header": "",
        "params": [{
            "title": "参数1", "name": "1", "txt": "",
            "json": json.dumps({"url": cdn_url, "lang": "en"}),
            "type": "json",
            "value": {"url": cdn_url, "lang": "en"},
        }],
        "settings": {"time": "120000", "group": "default", "host": "", "headerType": "TXT"},
        "region": "alpha", "env": "alpha", "cluster": "stage", "server": "config",
        "momoId": "df4c6f364f9fcae3", "momoName": "e88aa376b29864ad",
    }

    resp = http_post_json(MOA_ENTRY_URL, moa_cookie, payload, timeout_s=120)
    outer_ec = resp.get("ec")
    if outer_ec != 200:
        raise RuntimeError(f"MOA 外层失败: ec={outer_ec}, em={resp.get('em')}")

    result = resp.get("result", {})
    inner_ec = result.get("ec")
    if inner_ec != 0:
        raise RuntimeError(f"MOA 业务失败: ec={inner_ec}, em={result.get('em')}")

    inner_result = result.get("result", {})
    data = inner_result.get("data", {})
    print(f"  ✅ 导入成功: total={data.get('totalRows')}, success={data.get('successRows')}, failed={data.get('failedRows')}")
    if data.get("errors"):
        print(f"     errors: {data['errors'][:5]}")
    return data


# ---------------------------------------------------------------------------
# Step 4: MOA 重建大R主表
# ---------------------------------------------------------------------------

def moa_rebuild(start_date: int, end_date: int, moa_cookie: str) -> dict:
    """调用 rebuildBigRichFromWideTableRange 重建主表+周月表。"""
    sys.path.insert(0, str(_REPO / "MOA"))
    from moa.client import http_post_json

    os.environ["MOA_REQUEST_SOURCE"] = "moaProxy"
    os.environ["MOA_ORIGIN"] = "https://mse.wemomo.com"
    os.environ["MOA_REFERER"] = "https://mse.wemomo.com/"

    payload = {
        "type": "moa",
        "key": MOA_KEY,
        "url": MOA_SERVICE_URL,
        "method": "rebuildBigRichFromWideTableRange",
        "header": "",
        "params": [{
            "title": "参数1", "name": "1", "txt": "",
            "json": json.dumps({"startDate": start_date, "endDate": end_date}),
            "type": "json",
            "value": {"startDate": start_date, "endDate": end_date},
        }],
        "settings": {"time": "120000", "group": "default", "host": "", "headerType": "TXT"},
        "region": "alpha", "env": "alpha", "cluster": "stage", "server": "config",
        "momoId": "df4c6f364f9fcae3", "momoName": "e88aa376b29864ad",
    }

    resp = http_post_json(MOA_ENTRY_URL, moa_cookie, payload, timeout_s=120)
    outer_ec = resp.get("ec")
    if outer_ec != 200:
        raise RuntimeError(f"MOA 外层失败: ec={outer_ec}, em={resp.get('em')}")

    result = resp.get("result", {})
    inner_ec = result.get("ec")
    if inner_ec != 0:
        raise RuntimeError(f"MOA 业务失败: ec={inner_ec}, em={result.get('em')}")

    inner_result = result.get("result", {})
    data = inner_result.get("data", {})
    days = data.get("days", [])
    print(f"  ✅ 重建成功: {start_date}~{end_date} ({data.get('dayCount')} 天)")
    for d in days:
        print(f"     {d['belongDate']}: updated={d.get('updated')}, "
              f"migrated={d.get('migrated')}, restored={d.get('restored')}, "
              f"removed={d.get('removed')}")
    return data


# ---------------------------------------------------------------------------
# 解析日期参数
# ---------------------------------------------------------------------------

def parse_dates(args) -> list[int]:
    """从参数解析日期列表。"""
    if args.month:
        year, month = map(int, args.month.split("-"))
        start = date(year, month, 1)
        if month == 12:
            end = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            end = date(year, month + 1, 1) - timedelta(days=1)
        dates = []
        d = start
        while d <= end:
            dates.append(int(d.strftime("%Y%m%d")))
            d += timedelta(days=1)
        return dates
    elif args.dates:
        return [int(d) for d in args.dates]
    else:
        today = date.today()
        return [int(today.strftime("%Y%m%d"))]


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="大R后台 Stage 造数全流程")
    parser.add_argument("--dates", nargs="+", help="日期列表，如 20260804 20260805")
    parser.add_argument("--month", help="整月，如 2026-06")
    parser.add_argument("--user-count", type=int, default=1000, help="用户数量（默认1000）")
    parser.add_argument("--no-import", action="store_true", help="只生成Excel不执行导入")
    parser.add_argument("--cdn-url", help="已有CDN URL，跳过生成和上传步骤")
    parser.add_argument("--static-cookie", help="static.wemomo.com 的 Cookie")
    parser.add_argument("--moa-cookie", help="mse.wemomo.com 的 Cookie")
    parser.add_argument("--seed", type=int, default=42, help="随机种子")
    args = parser.parse_args()

    dates = parse_dates(args)
    print(f"📋 大R后台造数流程")
    print(f"   日期: {dates[0]} ~ {dates[-1]} ({len(dates)} 天)")
    print(f"   用户数: {args.user_count}")

    # 获取 Cookie（优先命令行参数，其次环境变量）
    static_cookie = args.static_cookie or os.environ.get("STATIC_WEMOMO_COOKIE", "")
    moa_cookie = args.moa_cookie or os.environ.get("MOA_MSE_COOKIE", "")

    if args.cdn_url:
        # 跳过生成和上传，直接导入
        cdn_url = args.cdn_url
        print(f"\n⏩ 使用已有CDN URL: {cdn_url}")
    else:
        # Step 0: 获取用户
        print(f"\n[0/4] 获取测试环境用户...")
        if static_cookie:
            users = load_or_fetch_users(args.user_count, static_cookie)
        else:
            cache_file = TMP_DIR / "stage_users_mdp.json"
            if cache_file.exists():
                with open(cache_file, "r", encoding="utf-8") as f:
                    cached = json.load(f)
                users = dict(list(cached.items())[:args.user_count])
                print(f"  从缓存加载 {len(users)} 个用户")
            else:
                print("  ❌ 无缓存且未提供 --static-cookie，无法获取用户", file=sys.stderr)
                return 1

        # Step 1: 生成 Excel
        print(f"\n[1/4] 生成 Excel...")
        date_range = f"{dates[0]}_{dates[-1]}" if len(dates) > 1 else str(dates[0])
        output_path = TMP_DIR / f"big_r_stage_data_{date_range}.xlsx"
        generate_excel(users, dates, output_path, seed=args.seed)

        if args.no_import:
            print(f"\n✅ 仅生成Excel完成: {output_path}")
            return 0

        # Step 2: 上传 CDN
        print(f"\n[2/4] 上传到 CDN...")
        if not static_cookie:
            print("  ❌ 未提供 --static-cookie，无法上传", file=sys.stderr)
            print(f"  请手动上传 {output_path} 到 https://static.wemomo.com/category/all")
            return 1
        cdn_url = upload_to_cdn(output_path, static_cookie)

    # Step 3: MOA 导入
    print(f"\n[3/4] MOA 导入天级数据...")
    if not moa_cookie:
        print("  ❌ 未提供 --moa-cookie，无法调用MOA", file=sys.stderr)
        print(f"  请使用以下CDN URL手动导入: {cdn_url}")
        return 1
    moa_import(cdn_url, moa_cookie)

    # Step 4: MOA 重建
    print(f"\n[4/4] MOA 重建主表+周月表...")
    start_date = dates[0]
    end_date = dates[-1]
    moa_rebuild(start_date, end_date, moa_cookie)

    print(f"\n🎉 全流程完成！数据已导入 Stage 大R后台。")
    print(f"   可在后台 pageList 验证: {dates[0]}~{dates[-1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
