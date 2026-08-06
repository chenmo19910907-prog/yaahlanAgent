#!/usr/bin/env python3
"""主播管理账号批量砸金蛋（每账号调用 smashEgg 一次）。"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

from repo_paths import (
    admin_execute_path,
    admin_module_dir,
    batch_progress_script,
    get_repo_root,
    gift_execute_path,
    gift_module_dir,
    moa_execute_path,
    moa_module_dir,
    moa_template,
    mse_execute_path,
    mse_module_dir,
    stage_gateway_url,
    tmp_dir,
)
sys.path.insert(0, str(admin_module_dir()))
sys.path.insert(0, str(moa_module_dir()))

from admin.client import http_post_json  # noqa: E402
from admin.env import load_local_env  # noqa: E402
from moa.anniversary_egg import (  # noqa: E402
    get_egg_home,
    resolve_own_room_id,
    smash_egg_once,
)

ANCHOR_LIST_URL = stage_gateway_url(
    "anchorList", "/yaahlan/cms/anchor/anchorList/anchorList"
)
USER_KEY_DEFAULT = "cidwuF5xkEMvaZMDWWu8BtHbg==:user:32274159141215328"


def fetch_anchor_user_ids(limit: int) -> list[str]:
    load_local_env(str(admin_module_dir()))
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


def resolve_smash_room(user_id: str) -> str:
    try:
        return resolve_own_room_id(user_id)
    except (RuntimeError, ValueError):
        home = get_egg_home(user_id, "0")
        room_egg = home.get("roomEgg") if isinstance(home.get("roomEgg"), dict) else {}
        room_id = str(room_egg.get("roomId") or "0").strip() or "0"
        return room_id


def reward_brief(smash: dict[str, Any]) -> str:
    prizes = smash.get("prizes") or smash.get("rewards") or []
    if not isinstance(prizes, list) or not prizes:
        if smash.get("prizePoolPreview"):
            return "无次数(奖池预览)"
        return "-"
    parts: list[str] = []
    for item in prizes[:3]:
        if not isinstance(item, dict):
            continue
        name = str(item.get("prizeName") or item.get("name") or item.get("prizeId") or "奖励")
        num = item.get("num") or item.get("count") or 1
        parts.append(f"{name}×{num}")
    if len(prizes) > 3:
        parts.append("…")
    return "、".join(parts) if parts else "-"


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
        str(REPO_ROOT / "platform" / "dingtalk_gateway/batch_progress_report.py"),
        "--user-key",
        user_key,
        "--current",
        str(current),
        "--total",
        str(total),
        "--label",
        "砸蛋",
    ]
    if detail:
        cmd.extend(["--detail", detail])
    if result_text:
        cmd.extend(["--result-text", result_text])
    subprocess.run(cmd, cwd=str(REPO_ROOT), check=False)


def build_result_markdown(rows: list[dict[str, Any]]) -> str:
    ok = sum(1 for r in rows if r.get("status") == "成功")
    skip = sum(1 for r in rows if r.get("status") == "跳过")
    fail = len(rows) - ok - skip
    lines = [
        "## 主播批量砸蛋完成",
        "",
        f"- 账号数：**{len(rows)}**，成功 **{ok}**，跳过 **{skip}**，失败 **{fail}**",
        "- 说明：每账号调用 smashEgg **1 次**；剩余>10 时接口默认连砸 **10** 次",
        "",
        "| userId | 房间 | 砸前剩余 | 砸后剩余 | 本次砸蛋 | 奖励摘要 | 结果 | 说明 |",
        "| --- | --- | ---: | ---: | ---: | --- | --- | --- |",
    ]
    for row in rows:
        note = str(row.get("note") or "").replace("|", "\\|").replace("\n", " ")[:60]
        lines.append(
            f"| {row['userId']} | {row.get('roomId', '')} | {row.get('remainBefore', '')} | "
            f"{row.get('remainAfter', '')} | {row.get('smashCount', '')} | "
            f"{row.get('reward', '')} | {row.get('status', '')} | {note} |"
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--user-key", default=USER_KEY_DEFAULT)
    args = parser.parse_args()

    user_ids = fetch_anchor_user_ids(args.limit)
    total = len(user_ids)
    if total >= 3:
        report_progress(args.user_key, current=0, total=total)

    rows: list[dict[str, Any]] = []
    for index, user_id in enumerate(user_ids, start=1):
        row: dict[str, Any] = {"userId": user_id, "status": "失败"}
        try:
            room_id = resolve_smash_room(user_id)
            smash = smash_egg_once(user_id=user_id, room_id=room_id)
            smash_count = int(smash.get("smashCount") or 0)
            if smash.get("prizePoolPreview") or smash_count <= 0:
                row.update(
                    {
                        "status": "跳过",
                        "roomId": room_id,
                        "remainBefore": smash.get("remainBefore"),
                        "remainAfter": smash.get("remainAfter"),
                        "smashCount": 0,
                        "reward": reward_brief(smash),
                        "note": smash.get("skipReason") or "无砸蛋次数",
                    }
                )
            else:
                row.update(
                    {
                        "status": "成功",
                        "roomId": room_id,
                        "remainBefore": smash.get("remainBefore"),
                        "remainAfter": smash.get("remainAfter"),
                        "smashCount": smash_count,
                        "reward": reward_brief(smash),
                        "note": f"金蛋Lv{smash.get('eggLevel') or '-'}",
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
                result_text=build_result_markdown(rows) if is_last else "",
            )
        print(json.dumps({"index": index, "total": total, **row}, ensure_ascii=False), flush=True)

    print(build_result_markdown(rows))
    return 0 if all(r.get("status") in ("成功", "跳过") for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
