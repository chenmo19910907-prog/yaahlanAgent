#!/usr/bin/env python3
"""Admin 主播管理列表无家族用户 → 单成员家族补员。"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "Admin"))
from admin.client import http_post_json  # noqa: E402
from admin.env import load_local_env  # noqa: E402

USER_KEY = "cidwuF5xkEMvaZMDWWu8BtHbg==:user:32274159141215328"
LABEL = "家族补员"
ANCHOR_LIST_URL = (
    "https://melon-gateway-alpha-stage.immomo.com"
    "/yaahlan/cms/anchor/anchorList/anchorList"
)


def run_json(cmd: list[str]) -> dict:
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    out = proc.stdout.strip()
    if proc.returncode != 0:
        raise RuntimeError(f"命令失败: {' '.join(cmd)}\n{proc.stderr or out}")
    lines = [ln for ln in out.splitlines() if not ln.startswith("请求信息:")]
    return json.loads("\n".join(lines).strip())


def report(current: int, total: int, detail: str = "", result_text: str = "") -> None:
    cmd = [
        "python3",
        "platform/dingtalk_gateway/batch_progress_report.py",
        "--user-key",
        USER_KEY,
        "--current",
        str(current),
        "--total",
        str(total),
        "--label",
        LABEL,
    ]
    if detail:
        cmd.extend(["--detail", detail])
    if result_text:
        cmd.extend(["--result-text", result_text])
    subprocess.run(cmd, cwd=ROOT, check=True)


def list_single_member_families() -> list[dict]:
    data = run_json(
        [
            "python3",
            "Admin/admin_execute.py",
            "--list-all-families",
            "--family-offset",
            "0",
            "--family-limit",
            "200",
        ]
    )
    return [item for item in data.get("items") or [] if int(item.get("familyMemberNum") or 0) == 1]


def fetch_anchors() -> list[dict]:
    load_local_env(str(ROOT / "Admin"))
    anchors: list[dict] = []
    offset = 0
    while True:
        resp = http_post_json(
            ANCHOR_LIST_URL,
            {"offset": offset, "limit": 50, "area": "MENA"},
            timeout_s=15,
        )
        if resp.get("ec") != 200:
            raise RuntimeError(f"主播列表查询失败: ec={resp.get('ec')} em={resp.get('em')}")
        data = resp.get("data") or {}
        batch = data.get("list") or []
        if not isinstance(batch, list):
            break
        anchors.extend(row for row in batch if isinstance(row, dict))
        if not data.get("has_next"):
            break
        next_offset = data.get("next_offset")
        if next_offset is None:
            break
        offset = int(next_offset)
    return anchors


def has_family(user_id: str) -> bool:
    data = run_json(
        [
            "python3",
            "MOA/moa_execute.py",
            "--payload-file",
            "MOA/templates/家族-按userId查家族id.json",
            "--family-query-joined-user-id",
            user_id,
        ]
    )
    return bool(data.get("joinedFamily"))


def add_member(family_id: str, user_id: str) -> dict:
    return run_json(
        [
            "python3",
            "Admin/admin_execute.py",
            "--add-family-member",
            "--family-id",
            family_id,
            "--family-user-id",
            user_id,
        ]
    )


def main() -> int:
    families = list_single_member_families()
    total = len(families)
    if total == 0:
        report(0, 0, result_text="当前没有仅 1 名成员的单用户家族，未执行补员。")
        return 0

    report(0, total)

    anchors = fetch_anchors()
    family_idx = 0
    results: list[dict] = []
    stopped_reason = ""

    for anchor in anchors:
        if family_idx >= total:
            stopped_reason = "单成员家族已全部分配完毕"
            break

        user_id = str(anchor.get("userId") or "").strip()
        nickname = str(anchor.get("nickname") or "")
        if not user_id:
            continue
        if has_family(user_id):
            continue

        fam = families[family_idx]
        family_id = str(fam.get("familyId", ""))
        family_name = str(fam.get("familyName", ""))

        try:
            resp = add_member(family_id, user_id)
            ok = bool(resp.get("success"))
            note = str(resp.get("msg") or ("成功" if ok else "失败"))
        except RuntimeError as exc:
            ok = False
            note = str(exc)

        if ok:
            family_idx += 1
            results.append(
                {
                    "userId": user_id,
                    "nickname": nickname,
                    "familyId": family_id,
                    "familyName": family_name,
                    "status": "成功",
                    "note": note,
                }
            )
            report(family_idx, total, detail=f"{user_id} → 家族 {family_id}")
        else:
            results.append(
                {
                    "userId": user_id,
                    "nickname": nickname,
                    "familyId": family_id,
                    "familyName": family_name,
                    "status": "失败",
                    "note": note,
                }
            )

    if not stopped_reason and family_idx < total:
        stopped_reason = "主播管理列表中无家族账号不足，提前停止"

    lines = [
        f"已从 **Admin 主播管理列表** 筛选无家族主播，向单成员家族补员 **{sum(1 for r in results if r['status'] == '成功')}** 人。",
        stopped_reason or f"共处理 **{len(results)}** 条记录。",
        "",
        "| userId | 昵称 | 家族ID | 家族名称 | 结果 | 说明 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in results:
        name = str(row["familyName"]).replace("|", "\\|")
        nick = str(row["nickname"]).replace("|", "\\|")
        note = str(row["note"]).replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| {row['userId']} | {nick} | {row['familyId']} | {name} | {row['status']} | {note} |"
        )
    if not results:
        lines.append("| （无） | | | | | 未找到可用无家族主播 |")

    report(
        family_idx if family_idx <= total else total,
        total,
        result_text="\n".join(lines),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
