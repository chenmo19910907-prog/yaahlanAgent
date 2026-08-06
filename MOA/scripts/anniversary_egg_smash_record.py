#!/usr/bin/env python3
"""3周年砸金蛋测试记录 → 追加写入钉钉表格。"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from moa_script_paths import (
    dingtalk_excel_python,
    ensure_gateway_path,
    ensure_moa_gift_paths,
    moa_template,
    tmp_dir,
)

_EXCEL_VENV = dingtalk_excel_python()
if (
    __name__ == "__main__"
    and _EXCEL_VENV.is_file()
    and Path(sys.executable).resolve() != _EXCEL_VENV.resolve()
):
    os.execv(str(_EXCEL_VENV), [str(_EXCEL_VENV), str(Path(__file__).resolve()), *sys.argv[1:]])

GATEWAY_DIR = ensure_gateway_path()

from anniversary_egg_smash_to_workbook import (  # noqa: E402
    DEFAULT_SHEET,
    aggregate_rewards,
    append_smash_record_async,
    create_workbook_with_records_async,
    format_reward_totals,
    merge_reward_totals,
    record_to_row,
)

MOA_TPL = moa_template("3周年-砸金蛋测试.json")


def _parse_json_blob(text: str) -> dict[str, Any]:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("未解析到 JSON")
    return json.loads(text[start : end + 1])


def _normalize_smash_result(payload: dict[str, Any]) -> dict[str, Any]:
    """统一 year3GiftService.smashEgg 与契约样例字段（prizes → rewards）。"""
    out = dict(payload)
    prizes = out.get("prizes")
    rewards = out.get("rewards")
    if rewards is None and isinstance(prizes, list):
        normalized: list[dict[str, Any]] = []
        for item in prizes:
            if not isinstance(item, dict):
                continue
            normalized.append(
                {
                    "name": item.get("prizeName")
                    or item.get("name")
                    or item.get("prizeId")
                    or "奖励",
                    "num": item.get("num") or item.get("count") or item.get("amount") or 1,
                    "prizeId": item.get("prizeId"),
                    "prizeType": item.get("prizeType"),
                    "icon": item.get("icon"),
                    "gotoStr": item.get("gotoStr"),
                }
            )
        out["rewards"] = normalized
        out.setdefault("prizes", prizes)
    return out


def _looks_like_smash_payload(inner: dict[str, Any]) -> bool:
    return any(
        k in inner
        for k in (
            "userSmashCount",
            "roomSmashCount",
            "rewards",
            "prizes",
            "userId",
            "mysteryPrizes",
        )
    )


def _extract_smash_result(moa_stdout: dict[str, Any]) -> dict[str, Any]:
    """从 moa_execute 输出或内层 result 提取砸蛋结果。"""

    def dig(node: Any, depth: int = 0) -> dict[str, Any] | None:
        if depth > 6 or not isinstance(node, dict):
            return None
        if _looks_like_smash_payload(node):
            # 优先更深一层（MOA 常包 result.result）
            nested = node.get("result")
            if isinstance(nested, dict) and _looks_like_smash_payload(nested):
                return _normalize_smash_result(nested)
            return _normalize_smash_result(node)
        for key in ("smashResult", "result", "data", "innerResult"):
            found = dig(node.get(key), depth + 1)
            if found is not None:
                return found
        return None

    found = dig(moa_stdout)
    if found is not None:
        return found
    steps = moa_stdout.get("steps")
    if isinstance(steps, dict):
        for step in steps.values():
            found = dig(step)
            if found is not None:
                return found
    raise ValueError(
        "MOA 响应中未找到砸蛋结果字段；请确认接口返回 userId/roomSmashCount/rewards|prizes 等，"
        "或使用 --response-json 传入完整结果"
    )


def run_moa_smash_once(
    *,
    user_id: str,
    room_id: str,
    timeout_ms: int,
    lang: str = "en",
    remaining: int | None = None,
) -> dict[str, Any]:
    """调用 smashEgg 一次；本次砸蛋次数由返回值/剩余次数差值判定。"""
    del remaining  # 次数不再依赖入参估算，统一走 getRemainChance 差值
    ensure_moa_gift_paths()
    from moa.anniversary_egg import smash_egg_once  # noqa: E402

    result = smash_egg_once(
        user_id=user_id,
        room_id=room_id,
        lang=lang,
        timeout_ms=timeout_ms,
    )
    return _normalize_smash_result(result)


def _backup_smash_result(path: Path, smash_result: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(smash_result, ensure_ascii=False) + "\n")


def _append_with_retry(
    workbook: str,
    row: list[str],
    *,
    sheet_name: str,
    attempts: int = 4,
) -> str:
    import time

    last_exc: BaseException | None = None
    for i in range(max(1, attempts)):
        try:
            return asyncio.run(
                append_smash_record_async(
                    workbook,
                    row,
                    sheet_name=sheet_name,
                )
            )
        except Exception as exc:  # noqa: BLE001 — 钉钉偶发 5xx，重试后仍失败再抛
            last_exc = exc
            wait_s = min(2 ** i, 12)
            print(
                f"  写表失败 ({i + 1}/{attempts}): {exc}；{wait_s}s 后重试",
                file=sys.stderr,
            )
            time.sleep(wait_s)
    assert last_exc is not None
    raise last_exc


def run_moa_smash_and_record(
    *,
    user_id: str,
    room_id: str,
    smash_count: int | None,
    timeout_ms: int,
    lang: str = "en",
    workbook: str | None = None,
    sheet_name: str = DEFAULT_SHEET,
    dry_run: bool = False,
    create_workbook: bool = False,
    parent_folder: str = "",
    workbook_name: str = "",
) -> dict[str, Any]:
    """砸一次 →（真实结果）写一次；次数耗尽则提前结束。"""
    ensure_moa_gift_paths()
    from moa.anniversary_egg import is_real_smash_result  # noqa: E402

    calls = 1 if smash_count is None else int(smash_count)
    if calls <= 0:
        raise ValueError("smash_count 须为正整数")

    results: list[dict[str, Any]] = []
    rows: list[list[str]] = []
    urls: list[str] = []
    skipped = 0
    running_total = merge_reward_totals()
    stamp = __import__("datetime").datetime.now(
        __import__("datetime").timezone.utc
    ).strftime("%Y%m%dT%H%M%SZ")
    backup_path = (
        tmp_dir() / f"anniversary_egg_smash_{user_id}_{stamp}.jsonl"
    )
    created_url: str | None = None

    for i in range(calls):
        print(f"砸金蛋 {i + 1}/{calls} …", file=sys.stderr)
        one = run_moa_smash_once(
            user_id=user_id,
            room_id=room_id,
            timeout_ms=timeout_ms,
            lang=lang,
        )
        print(
            f"  remain {one.get('remainBefore')}→{one.get('remainAfter')} "
            f"usedSmash {one.get('usedSmashBefore')}→{one.get('usedSmashAfter')} "
            f"roomSmash {one.get('roomSmashBefore')}→{one.get('roomSmashAfter')} "
            f"smashCount={one.get('smashCount')} "
            f"prizePoolPreview={one.get('prizePoolPreview')}",
            file=sys.stderr,
        )
        if not is_real_smash_result(one):
            skipped += 1
            print(
                "  跳过落表：无砸蛋次数/奖池预览（Celestial Twins×50000 等）或 smashCount=0",
                file=sys.stderr,
            )
            # 无次数后继续调也只会预览，提前结束
            if int(one.get("remainAfter") or one.get("remainBefore") or 0) <= 0:
                print("  剩余次数为 0，结束本轮", file=sys.stderr)
                break
            continue

        _backup_smash_result(backup_path, one)
        running_total = merge_reward_totals(
            running_total,
            aggregate_rewards(one.get("rewards")),
            aggregate_rewards(
                one.get("mysteryPrizes") or one.get("mysteryRewards")
            ),
        )
        user_summary = format_reward_totals(running_total)
        row = record_to_row(
            one,
            fallback_user_id=user_id,
            fallback_room_id=room_id,
            fallback_smash_count=one.get("smashCount"),
            user_total_summary=user_summary,
        )
        results.append(one)
        rows.append(row)

        if dry_run:
            print(f"  dry-run 行: {row}", file=sys.stderr)
            continue

        if create_workbook and created_url is None:
            created_url = asyncio.run(
                create_workbook_with_records_async(
                    parent_node_id=parent_folder,
                    workbook_name=workbook_name,
                    rows=[row],
                    sheet_name=sheet_name,
                )
            )
            urls.append(created_url)
            print(f"  已新建并写入: {created_url}", file=sys.stderr)
            continue

        target = created_url or workbook
        if not target:
            raise RuntimeError("缺少 workbook：请传 --workbook 或 --create-workbook")
        url = _append_with_retry(target, row, sheet_name=sheet_name)
        urls.append(url)
        print(f"  已写入钉钉表（本批第 {len(rows)} 行）", file=sys.stderr)

    if skipped and not results:
        print(
            f"WARNING: {skipped} 次调用均为奖池预览或未实际砸蛋，未写入表格",
            file=sys.stderr,
        )

    out: dict[str, Any] = {
        "rows": rows,
        "smashResults": results,
        "skippedCount": skipped,
        "tierReward": format_reward_totals(running_total),
        "userTotalReward": format_reward_totals(running_total),
        "backupPath": str(backup_path) if results else "",
    }
    if urls:
        out["workbookUrls"] = urls
        out["workbookUrl"] = urls[-1]
    if not results:
        out["skipped"] = True
        out["reason"] = "无砸蛋次数或返回奖池预览，未写入表格"
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="3周年砸金蛋：MOA 执行并记录到钉钉表")
    parser.add_argument("--workbook", help="钉钉表格 URL 或 nodeId（与 --create-workbook 二选一）")
    parser.add_argument(
        "--create-workbook",
        action="store_true",
        help="在 --parent-folder 下新建独立表格（不要写入家族PK表）",
    )
    parser.add_argument(
        "--parent-folder",
        default="m9bN7RYPWdlGBEgEtKPvv9gdWZd1wyK0",
        help="新建表格的父目录 nodeId（默认测试报告导出目录）",
    )
    parser.add_argument(
        "--workbook-name",
        default="3周年砸金蛋测试记录",
        help="--create-workbook 时的表格名称",
    )
    parser.add_argument("--user-id", required=True)
    parser.add_argument(
        "--room-id",
        help="房间 ID；不传则默认 Admin 查询自己的房间（ownedRoomInfo.roomId）",
    )
    parser.add_argument(
        "--smash-count",
        type=int,
        help="调用 smashEgg 的次数（「砸 N 次」）；不传默认 1。每次「本次砸蛋次数」以返回值/剩余差值为准",
    )
    parser.add_argument(
        "--remaining",
        type=int,
        help="兼容旧参数（已忽略）；剩余次数改为自动 getRemainChance",
    )
    parser.add_argument("--lang", default="en", help="smashEgg 语言参数，默认 en")
    parser.add_argument("--sheet-name", default=DEFAULT_SHEET)
    parser.add_argument("--timeout-ms", type=int, default=60000)
    parser.add_argument(
        "--response-json",
        help="跳过 MOA，直接传入砸蛋结果 JSON 文件路径（联调前可用）",
    )
    parser.add_argument("--dry-run", action="store_true", help="只解析行数据不写钉钉")
    args = parser.parse_args()

    if args.smash_count is not None and args.smash_count <= 0:
        raise SystemExit("smash-count 须为正整数")
    if args.remaining is not None and args.remaining < 0:
        raise SystemExit("remaining 不能为负数")
    if not args.dry_run and not args.create_workbook and not args.workbook:
        raise SystemExit("请提供 --workbook，或使用 --create-workbook 新建独立表格")

    room_id = (args.room_id or "").strip()
    if not room_id and not args.response_json:
        ensure_moa_gift_paths()
        from moa.anniversary_egg import resolve_own_room_id  # noqa: E402

        room_id = resolve_own_room_id(args.user_id)
        print(f"未传房间，默认自己的房间 roomId={room_id}", file=sys.stderr)
    args.room_id = room_id

    if args.response_json:
        payload = _parse_json_blob(Path(args.response_json).read_text(encoding="utf-8"))
        raw = payload.get("smashResult") or payload.get("data") or payload
        smash_results = [
            _normalize_smash_result(raw) if isinstance(raw, dict) else raw
        ]
        if not smash_results:
            out = {
                "rows": [],
                "smashResults": [],
                "skipped": True,
                "reason": "无砸蛋次数或返回奖池预览，未写入表格",
            }
            print(json.dumps(out, ensure_ascii=False, indent=2))
            return 0
        # 兼容：单条 response-json 也按「砸一次写一次」
        batch_total = merge_reward_totals(
            aggregate_rewards(smash_results[0].get("rewards")),
            aggregate_rewards(
                smash_results[0].get("mysteryPrizes")
                or smash_results[0].get("mysteryRewards")
            ),
        )
        row = record_to_row(
            smash_results[0],
            fallback_user_id=args.user_id,
            fallback_room_id=room_id or args.room_id or "",
            fallback_smash_count=smash_results[0].get("smashCount"),
            user_total_summary=format_reward_totals(batch_total),
        )
        out = {
            "rows": [row],
            "smashResults": smash_results,
            "tierReward": format_reward_totals(batch_total),
            "userTotalReward": format_reward_totals(batch_total),
        }
        if args.dry_run:
            print(json.dumps(out, ensure_ascii=False, indent=2))
            return 0
        if args.create_workbook:
            url = asyncio.run(
                create_workbook_with_records_async(
                    parent_node_id=args.parent_folder,
                    workbook_name=args.workbook_name,
                    rows=[row],
                    sheet_name=args.sheet_name,
                )
            )
        else:
            url = _append_with_retry(
                args.workbook, row, sheet_name=args.sheet_name
            )
        out["workbookUrl"] = url
        out["workbookUrls"] = [url]
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    out = run_moa_smash_and_record(
        user_id=args.user_id,
        room_id=room_id,
        smash_count=args.smash_count,
        timeout_ms=args.timeout_ms,
        lang=args.lang,
        workbook=args.workbook,
        sheet_name=args.sheet_name,
        dry_run=args.dry_run,
        create_workbook=args.create_workbook,
        parent_folder=args.parent_folder,
        workbook_name=args.workbook_name,
    )
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
