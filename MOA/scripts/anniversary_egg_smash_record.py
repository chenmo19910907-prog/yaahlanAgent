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

REPO_ROOT = Path(__file__).resolve().parents[2]
GATEWAY_DIR = REPO_ROOT / "platform" / "dingtalk_gateway"
_EXCEL_VENV = (
    REPO_ROOT / ".cursor/skills/testcase-to-excel/mcp_dingtalk_excel/venv/bin/python3.13"
)

if (
    __name__ == "__main__"
    and _EXCEL_VENV.is_file()
    and Path(sys.executable).resolve() != _EXCEL_VENV.resolve()
):
    os.execv(str(_EXCEL_VENV), [str(_EXCEL_VENV), str(Path(__file__).resolve()), *sys.argv[1:]])

if str(GATEWAY_DIR) not in sys.path:
    sys.path.insert(0, str(GATEWAY_DIR))

from anniversary_egg_smash_to_workbook import (  # noqa: E402
    DEFAULT_SHEET,
    append_smash_record_async,
    record_to_row,
)

MOA_TPL = REPO_ROOT / "MOA/templates/3周年-砸金蛋测试.json"


def _parse_json_blob(text: str) -> dict[str, Any]:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("未解析到 JSON")
    return json.loads(text[start : end + 1])


def _extract_smash_result(moa_stdout: dict[str, Any]) -> dict[str, Any]:
    """从 moa_execute 输出或内层 result 提取砸蛋结果。"""
    for key in ("smashResult", "result", "data"):
        inner = moa_stdout.get(key)
        if isinstance(inner, dict) and any(
            k in inner for k in ("userSmashCount", "roomSmashCount", "rewards", "userId")
        ):
            return inner
    steps = moa_stdout.get("steps")
    if isinstance(steps, dict):
        for step in steps.values():
            if isinstance(step, dict):
                inner = step.get("innerResult") or step.get("result")
                if isinstance(inner, dict) and (
                    "userSmashCount" in inner or "rewards" in inner or "userId" in inner
                ):
                    return inner
    # MOA 平台双层 ec/result
    raw = moa_stdout.get("rawResponse") or moa_stdout.get("response")
    if isinstance(raw, dict):
        data = raw.get("data")
        if isinstance(data, dict):
            return data
    if any(k in moa_stdout for k in ("userSmashCount", "roomSmashCount", "rewards")):
        return moa_stdout
    raise ValueError(
        "MOA 响应中未找到砸蛋结果字段；请确认接口返回 userId/roomSmashCount/rewards 等，"
        "或使用 --response-json 传入完整结果"
    )


def run_moa_smash(*, user_id: str, room_id: str, smash_count: int, timeout_ms: int) -> dict[str, Any]:
    import subprocess

    if not MOA_TPL.is_file():
        raise FileNotFoundError(f"缺少 MOA 模板: {MOA_TPL}")
    body = {
        "userId": str(user_id).strip(),
        "roomId": str(room_id).strip(),
        "smashCount": int(smash_count),
    }
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "MOA/moa_execute.py"),
            "--payload-file",
            str(MOA_TPL),
            "--anniversary-egg-user-id",
            body["userId"],
            "--anniversary-egg-room-id",
            body["roomId"],
            "--anniversary-egg-smash-count",
            str(body["smashCount"]),
            "--timeout-ms",
            str(timeout_ms),
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=max(timeout_ms // 1000 + 90, 120),
        check=False,
    )
    text = (proc.stdout or proc.stderr or "").strip()
    if proc.returncode != 0:
        raise RuntimeError(text[-800:] if text else f"MOA 退出码 {proc.returncode}")
    return _extract_smash_result(_parse_json_blob(text))


def main() -> int:
    parser = argparse.ArgumentParser(description="3周年砸金蛋：MOA 执行并记录到钉钉表")
    parser.add_argument("--workbook", required=True, help="钉钉表格 URL 或 nodeId")
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--room-id", required=True)
    parser.add_argument("--smash-count", type=int, required=True, help="本次砸蛋次数 N")
    parser.add_argument("--sheet-name", default=DEFAULT_SHEET)
    parser.add_argument("--timeout-ms", type=int, default=60000)
    parser.add_argument(
        "--response-json",
        help="跳过 MOA，直接传入砸蛋结果 JSON 文件路径（联调前可用）",
    )
    parser.add_argument("--dry-run", action="store_true", help="只解析行数据不写钉钉")
    args = parser.parse_args()

    if args.smash_count <= 0:
        raise SystemExit("smash-count 须为正整数")

    if args.response_json:
        payload = _parse_json_blob(Path(args.response_json).read_text(encoding="utf-8"))
        smash_result = payload.get("smashResult") or payload.get("data") or payload
    else:
        smash_result = run_moa_smash(
            user_id=args.user_id,
            room_id=args.room_id,
            smash_count=args.smash_count,
            timeout_ms=args.timeout_ms,
        )

    row = record_to_row(
        smash_result,
        fallback_user_id=args.user_id,
        fallback_room_id=args.room_id,
        fallback_smash_count=args.smash_count,
    )
    out: dict[str, Any] = {"row": row, "smashResult": smash_result}
    if args.dry_run:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    url = asyncio.run(
        append_smash_record_async(
            args.workbook,
            row,
            sheet_name=args.sheet_name,
        )
    )
    out["workbookUrl"] = url
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
