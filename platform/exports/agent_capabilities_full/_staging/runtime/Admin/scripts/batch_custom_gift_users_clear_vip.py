#!/usr/bin/env python3
"""清除定制礼物后台列表中的全部用户 VIP 信息（delVipInfo）。"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ADMIN_DIR = REPO_ROOT / "Admin"
MOA_DIR = REPO_ROOT / "MOA"

sys.path.insert(0, str(ADMIN_DIR))
sys.path.insert(0, str(MOA_DIR))

from admin.client import http_get_json  # noqa: E402
from admin.config import defaults  # noqa: E402
from admin.custom_gift import gateway_success, parse_custom_gift_list_summary  # noqa: E402
from admin.env import load_local_env as load_admin_env  # noqa: E402
from moa.client import MoaClient, extract_ec_em_result, extract_inner_result, outer_success  # noqa: E402
from moa.env import load_local_env as load_moa_env  # noqa: E402
from moa.params import set_vip_del_params  # noqa: E402


def _resolve_gateway_base_url(cfg: dict[str, object]) -> str:
    base_url = (
        os.environ.get("ADMIN_GATEWAY_BASE_URL")
        or cfg.get("baseUrl")
        or ""
    ).strip().rstrip("/")
    if not base_url:
        raise ValueError("缺少 Gateway 域名：请设置 ADMIN_GATEWAY_BASE_URL 或 config.json")
    return base_url


def fetch_custom_gift_user_ids(*, per_page: int) -> list[str]:
    cfg = defaults("vip5_custom_gift_list")
    base_url = _resolve_gateway_base_url(cfg)
    path = str(cfg.get("path", "/yaahlan/backend/vip5UserConfig/getListConfig"))
    url = f"{base_url}{path}?{urllib.parse.urlencode({'perPage': per_page})}"
    resp = http_get_json(url, timeout_s=30.0)
    if not gateway_success(resp.get("status")):
        raise RuntimeError(f"查询定制礼物列表失败: status={resp.get('status')}, msg={resp.get('msg')}")
    summary = parse_custom_gift_list_summary(resp.get("data"))
    seen: set[str] = set()
    user_ids: list[str] = []
    for item in summary.get("items") or []:
        uid = str(item.get("userId", "")).strip()
        if uid and uid not in seen:
            seen.add(uid)
            user_ids.append(uid)
    return user_ids


def clear_vip(client: MoaClient, *, user_id: str, template_path: Path) -> tuple[bool, str]:
    with template_path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, dict):
        raise ValueError("VIP 清除模板必须是 JSON object")
    set_vip_del_params(payload, user_id)
    resp = client.post(payload)
    ec, em, _ = extract_ec_em_result(resp)
    if not outer_success(ec):
        return False, f"MOA 外层失败 ec={ec} em={em}"
    inner_ec, inner_em, _ = extract_inner_result(resp)
    if inner_ec != 0:
        return False, f"业务失败 ec={inner_ec} em={inner_em}"
    return True, "ok"


def main() -> int:
    parser = argparse.ArgumentParser(description="定制礼物后台用户批量清除 VIP")
    parser.add_argument("--per-page", type=int, default=500, help="getListConfig 每页条数")
    parser.add_argument("--dry-run", action="store_true", help="只列出 userId，不调用 MOA")
    parser.add_argument("--user-ids", help="逗号分隔 userId；指定时跳过定制礼物列表查询")
    args = parser.parse_args()

    load_admin_env(str(ADMIN_DIR))
    load_moa_env(str(MOA_DIR))

    if args.user_ids:
        user_ids = [u.strip() for u in args.user_ids.split(",") if u.strip()]
    else:
        user_ids = fetch_custom_gift_user_ids(per_page=args.per_page)

    if not user_ids:
        print("未找到任何定制礼物用户。", file=sys.stderr)
        return 2

    print(
        json.dumps({"userCount": len(user_ids), "userIds": user_ids}, ensure_ascii=False, indent=2)
    )

    if args.dry_run:
        return 0

    entry_url = os.environ.get("MOA_ENTRY_URL", "").strip()
    cookie = os.environ.get("MOA_COOKIE", "").strip()
    if not entry_url or not cookie:
        print("缺少 MOA_ENTRY_URL 或 MOA_COOKIE（请写入 MOA/.env.local）", file=sys.stderr)
        return 2

    template = MOA_DIR / "templates" / "VIP-清除信息.json"
    client = MoaClient(entry_url, cookie, 10000)
    ok_list: list[str] = []
    fail_list: list[dict[str, str]] = []

    for uid in user_ids:
        try:
            ok, msg = clear_vip(client, user_id=uid, template_path=template)
        except (ValueError, RuntimeError) as e:
            ok, msg = False, str(e)
        if ok:
            ok_list.append(uid)
            print(f"[OK] {uid}", file=sys.stderr)
        else:
            fail_list.append({"userId": uid, "error": msg})
            print(f"[FAIL] {uid}: {msg}", file=sys.stderr)

    print(
        json.dumps(
            {"successCount": len(ok_list), "failCount": len(fail_list), "failures": fail_list},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if not fail_list else 1


if __name__ == "__main__":
    raise SystemExit(main())
