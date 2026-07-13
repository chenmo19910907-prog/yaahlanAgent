#!/usr/bin/env python3
"""主播账号自送指定礼物获砸蛋次数（随机 1~100 次/人）。"""

from __future__ import annotations

import argparse
import json
import math
import random
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "Admin"))
sys.path.insert(0, str(REPO_ROOT / "MOA"))
sys.path.insert(0, str(REPO_ROOT / "Gift"))

from admin.client import http_post_json  # noqa: E402
from admin.env import load_local_env  # noqa: E402
from gift.send_stage import provide_diamond, query_diamond_balance, query_gift  # noqa: E402
from moa.anniversary_egg import get_egg_home  # noqa: E402

GIFT_ID = "2005057191"  # lipstick 199 钻
DIAMOND_PER_CHANCE = 500
TOP_UP_DIAMONDS = 1_000_000
ANCHOR_LIST_URL = (
    "https://melon-gateway-alpha-stage.immomo.com"
    "/yaahlan/cms/anchor/anchorList/anchorList"
)
USER_KEY_DEFAULT = "cidwuF5xkEMvaZMDWWu8BtHbg==:user:32274159141215328"


def run_json(cmd: list[str], *, timeout: int = 180) -> dict[str, Any]:
    proc = subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    text = (proc.stdout or "").strip() or (proc.stderr or "").strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise RuntimeError(f"命令无 JSON: {' '.join(cmd[-4:])} :: {text[-300:]}")
    data = json.loads(text[start : end + 1])
    if proc.returncode != 0 and not data.get("ok") and "userId" not in data:
        raise RuntimeError(f"命令失败 exit={proc.returncode}: {text[-300:]}")
    return data


def report_progress(
    user_key: str,
    *,
    current: int,
    total: int,
    detail: str = "",
    result_text: str = "",
) -> None:
    cmd = [
        sys.executable,
        str(REPO_ROOT / "platform/dingtalk_gateway/batch_progress_report.py"),
        "--user-key",
        user_key,
        "--current",
        str(current),
        "--total",
        str(total),
        "--label",
        "砸蛋获次",
    ]
    if detail:
        cmd.extend(["--detail", detail])
    if result_text:
        cmd.extend(["--result-text", result_text])
    subprocess.run(cmd, cwd=str(REPO_ROOT), check=False)


def fetch_anchor_user_ids(limit: int) -> list[str]:
    load_local_env(str(REPO_ROOT / "Admin"))
    user_ids: list[str] = []
    offset = 0
    while len(user_ids) < limit:
        resp = http_post_json(
            ANCHOR_LIST_URL,
            {"offset": offset, "limit": 50, "area": "MENA"},
            timeout_s=30,
        )
        if resp.get("ec") != 200:
            raise RuntimeError(f"主播列表失败: ec={resp.get('ec')} em={resp.get('em')}")
        data = resp.get("data") or {}
        batch = data.get("list") or []
        for row in batch:
            if not isinstance(row, dict):
                continue
            uid = str(row.get("userId") or "").strip()
            if uid and uid not in user_ids:
                user_ids.append(uid)
                if len(user_ids) >= limit:
                    break
        if not data.get("has_next") or not batch:
            break
        next_offset = data.get("next_offset")
        if next_offset is None:
            break
        offset = int(next_offset)
    return user_ids


def ensure_diamonds(user_id: str, need: int) -> int:
    bal = query_diamond_balance(user_id)
    if bal >= need:
        return 0
    provide_diamond(user_id, TOP_UP_DIAMONDS)
    bal2 = query_diamond_balance(user_id)
    if bal2 < need:
        raise RuntimeError(f"充值后仍不足: user={user_id} bal={bal2} need={need}")
    return TOP_UP_DIAMONDS


def snap(user_id: str) -> dict[str, int]:
    home = get_egg_home(user_id, "")
    return {"remain": int(home.get("remainChances") or 0)}


def send_self_gift(*, user_id: str, gift_num: int) -> dict[str, Any]:
    return run_json(
        [
            "python3",
            str(REPO_ROOT / "Gift/gift_execute.py"),
            "--scene",
            "private",
            "--sender",
            user_id,
            "--receivers",
            user_id,
            "--gift-id",
            GIFT_ID,
            "--num",
            str(gift_num),
        ]
    )


def self_gift_for_chances(*, user_id: str, target_chances: int) -> dict[str, Any]:
    gift_meta = query_gift(GIFT_ID)
    unit = int(round(float(gift_meta.get("price") or 199)))
    diamonds_needed = max(1, int(target_chances)) * DIAMOND_PER_CHANCE
    gift_num = max(1, math.ceil(diamonds_needed / unit))
    cost = unit * gift_num
    topped = ensure_diamonds(user_id, cost)

    before = snap(user_id)
    gift_out = send_self_gift(user_id=user_id, gift_num=gift_num)
    if not gift_out.get("ok"):
        raise RuntimeError(f"送礼失败: {gift_out.get('error') or gift_out}")

    gained = 0
    after = before
    for _ in range(12):
        time.sleep(0.5)
        after = snap(user_id)
        gained = after["remain"] - before["remain"]
        if gained > 0:
            break

    return {
        "targetChances": target_chances,
        "gainedChances": max(0, gained),
        "remainBefore": before["remain"],
        "remainAfter": after["remain"],
        "giftNum": gift_num,
        "cost": cost,
        "topUpDiamonds": topped,
    }


def build_result_markdown(rows: list[dict[str, Any]], *, gift_name: str) -> str:
    ok = sum(1 for r in rows if r.get("status") == "成功")
    fail = len(rows) - ok
    lines = [
        "## 主播自送获砸蛋次数完成",
        "",
        f"- 礼物：**{gift_name}**（`{GIFT_ID}`），规则每 **{DIAMOND_PER_CHANCE}** 钻 +1 次",
        f"- 账号数：**{len(rows)}**，成功 **{ok}**，失败 **{fail}**",
        f"- 每人目标次数：**随机 1~100**",
        "",
        "| userId | 目标次数 | 实得次数 | 剩余次数 | 礼物数 | 消耗钻 | 结果 | 说明 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for row in rows:
        note = str(row.get("note") or "").replace("|", "\\|").replace("\n", " ")[:80]
        lines.append(
            f"| {row['userId']} | {row.get('target', '')} | {row.get('gained', '')} | "
            f"{row.get('remainAfter', '')} | {row.get('giftNum', '')} | {row.get('cost', '')} | "
            f"{row.get('status', '')} | {note} |"
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--user-key", default=USER_KEY_DEFAULT)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.seed:
        random.seed(args.seed)

    user_ids = fetch_anchor_user_ids(args.limit)
    total = len(user_ids)
    gift_meta = query_gift(GIFT_ID)
    gift_name = str(gift_meta.get("productName") or "lipstick")

    if total >= 3:
        report_progress(args.user_key, current=0, total=total)

    rows: list[dict[str, Any]] = []
    for index, user_id in enumerate(user_ids, start=1):
        target = random.randint(1, 100)
        row: dict[str, Any] = {"userId": user_id, "target": target, "status": "失败"}
        try:
            if args.dry_run:
                row.update({"status": "跳过", "note": "dry-run"})
            else:
                result = self_gift_for_chances(
                    user_id=user_id,
                    target_chances=target,
                )
                row.update(
                    {
                        "status": "成功" if result["gainedChances"] > 0 else "部分",
                        "gained": result["gainedChances"],
                        "remainAfter": result["remainAfter"],
                        "giftNum": result["giftNum"],
                        "cost": result["cost"],
                        "note": (
                            "私聊自送"
                            if result["gainedChances"] > 0
                            else "送礼后次数未到账"
                        ),
                    }
                )
        except (RuntimeError, ValueError, OSError) as exc:
            row["note"] = str(exc)[:120]

        rows.append(row)
        if total >= 3:
            is_last = index == total
            report_progress(
                args.user_key,
                current=index,
                total=total,
                detail=user_id,
                result_text=build_result_markdown(rows, gift_name=gift_name) if is_last else "",
            )
        print(json.dumps({"index": index, "total": total, **row}, ensure_ascii=False), flush=True)

    print(build_result_markdown(rows, gift_name=gift_name))
    return 0 if all(r.get("status") in ("成功", "部分", "跳过") for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
