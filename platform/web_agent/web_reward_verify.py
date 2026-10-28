#!/usr/bin/env python3
"""Web Agent 奖励下发验证：按会话记录/展示用户全量资产快照。"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

_AGENT_DIR = Path(__file__).resolve().parent
_REPO = _AGENT_DIR.parents[1]
_GATEWAY_VENV = _REPO / "platform" / "dingtalk_gateway" / ".venv" / "bin" / "python3"

if __name__ == "__main__" and _GATEWAY_VENV.is_file():
    if Path(sys.executable).resolve() != _GATEWAY_VENV.resolve():
        os.execv(str(_GATEWAY_VENV), [str(_GATEWAY_VENV), str(Path(__file__).resolve()), *sys.argv[1:]])
_INDEX_DIR = _AGENT_DIR / "data" / "reward_verify"
_BEIJING = ZoneInfo("Asia/Shanghai")


def _run(cmd: list[str], *, timeout: int = 600) -> tuple[int, str, str]:
    proc = subprocess.run(
        cmd,
        cwd=str(_REPO),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def _index_path(session_id: str) -> Path:
    sid = (session_id or "").strip()
    if not sid:
        raise ValueError("session_id 不能为空")
    return _INDEX_DIR / f"{sid}.json"


def _load_index(session_id: str) -> dict[str, Any]:
    path = _index_path(session_id)
    if not path.is_file():
        return {"sessionId": session_id, "slots": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"索引须为 object: {path}")
    data.setdefault("sessionId", session_id)
    data.setdefault("slots", {})
    return data


def _save_index(session_id: str, data: dict[str, Any]) -> None:
    path = _index_path(session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _resolve_user_id(user_id: str, phone: str) -> str:
    uid = (user_id or "").strip()
    if uid:
        return uid
    ph = (phone or "").strip()
    if not ph:
        raise ValueError("须提供 --user-id 或 --phone")
    rc, out, err = _run(
        [
            "python3",
            "MOA/moa_execute.py",
            "--payload-file",
            "MOA/templates/用户-按手机号查userId.json",
            "--query-user-by-phone",
            ph,
        ],
        timeout=120,
    )
    if rc != 0:
        raise RuntimeError((err or out)[-500:])
    start = out.find("{")
    if start < 0:
        raise RuntimeError("手机号查 userId 失败")
    payload = json.loads(out[start : out.rfind("}") + 1])
    resolved = payload.get("userId") or payload.get("data")
    if not resolved:
        raise RuntimeError(f"手机号 {ph} 未解析到 userId")
    return str(resolved).strip()


def cmd_record(args: argparse.Namespace) -> int:
    session_id = str(args.session_id).strip()
    slot = str(args.slot or "baseline").strip() or "baseline"
    user_id = _resolve_user_id(str(args.user_id or ""), str(args.phone or ""))
    user_label = str(args.user_label or args.phone or user_id).strip()

    snap_path = _INDEX_DIR / f"{session_id}_{slot}_{user_id}.json"
    cmd = [
        "python3",
        "workflow/scripts/reward_verify.py",
        "snapshot",
        "--user-id",
        user_id,
        "--full-inventory",
        "--include-nameplates",
        "--out",
        str(snap_path),
    ]
    if args.cp_user_id:
        cmd.extend(["--cp-user-id", str(args.cp_user_id)])
    if args.intimate_id:
        cmd.extend(["--intimate-id", str(args.intimate_id)])

    rc, out, err = _run(cmd)
    if rc != 0:
        print(err or out, file=sys.stderr)
        return rc

    index = _load_index(session_id)
    slots = index.setdefault("slots", {})
    if not isinstance(slots, dict):
        slots = {}
        index["slots"] = slots
    slots[slot] = {
        "userId": user_id,
        "userLabel": user_label,
        "snapshotPath": str(snap_path.relative_to(_REPO)),
        "recordedAtBeijing": datetime.now(_BEIJING).strftime("%Y-%m-%d %H:%M:%S"),
    }
    _save_index(session_id, index)

    result = {
        "ok": True,
        "sessionId": session_id,
        "slot": slot,
        "userId": user_id,
        "userLabel": user_label,
        "snapshotPath": str(snap_path.relative_to(_REPO)),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _slot_snapshot_entry(session_id: str, slot: str) -> tuple[dict[str, Any], Path]:
    index = _load_index(session_id)
    slots = index.get("slots") if isinstance(index.get("slots"), dict) else {}
    entry = slots.get(slot) if isinstance(slots, dict) else None
    if not isinstance(entry, dict):
        raise ValueError(f"会话 {session_id} 无 slot={slot} 快照")
    snap_path = _REPO / str(entry.get("snapshotPath") or "")
    if not snap_path.is_file():
        raise ValueError(f"快照文件不存在: {snap_path}")
    return entry, snap_path


def cmd_show(args: argparse.Namespace) -> int:
    session_id = str(args.session_id).strip()
    slot = str(args.slot or "baseline").strip() or "baseline"
    try:
        entry, snap_path = _slot_snapshot_entry(session_id, slot)
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1

    user_label = str(args.user_label or entry.get("userLabel") or entry.get("userId") or "").strip()
    snap = json.loads(snap_path.read_text(encoding="utf-8"))
    scripts_dir = _REPO / "workflow" / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from reward_verify import format_snapshot_inventory, format_snapshot_overview  # noqa: E402

    if getattr(args, "full", False):
        print(format_snapshot_inventory(snap, user_label=user_label))
    else:
        print(format_snapshot_overview(snap, user_label=user_label, slot=slot))
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    session_id = str(args.session_id).strip()
    slot = str(args.slot or "baseline").strip() or "baseline"
    try:
        entry, snap_path = _slot_snapshot_entry(session_id, slot)
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1

    user_label = str(args.user_label or entry.get("userLabel") or entry.get("userId") or "").strip()
    user_id = str(entry.get("userId") or "").strip()
    snap = json.loads(snap_path.read_text(encoding="utf-8"))

    scripts_dir = _REPO / "workflow" / "scripts"
    gateway_dir = _REPO / "platform" / "dingtalk_gateway"
    for p in (scripts_dir, gateway_dir):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))

    from reward_verify import format_snapshot_overview, snapshot_inventory_rows  # noqa: E402

    rows = snapshot_inventory_rows(snap, user_label=user_label)

    from alidocs_excel_export import export_rows_to_folder  # noqa: E402
    from export_delivery import load_export_config  # noqa: E402

    cfg = load_export_config()
    parent = str(args.parent_node_id or cfg.node_id).strip()
    stamp = datetime.now(_BEIJING).strftime("%Y%m%d_%H%M")
    workbook_name = (
        str(args.workbook_name or "").strip()
        or f"用户资产_{user_id}_{slot}_{stamp}"
    )
    file_url = export_rows_to_folder(
        rows,
        parent_node_id=parent,
        workbook_name=workbook_name,
        auto_wrap=True,
    )
    data_rows = max(0, len(rows) - 3)
    result = {
        "ok": True,
        "sessionId": session_id,
        "slot": slot,
        "userId": user_id,
        "workbookName": workbook_name,
        "rowCount": data_rows,
        "url": file_url,
        "overviewMarkdown": format_snapshot_overview(snap, user_label=user_label, slot=slot),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    session_id = str(args.session_id).strip()
    index = _load_index(session_id)
    print(json.dumps(index, ensure_ascii=False, indent=2))
    return 0


def _snap_path_for(session_id: str, slot: str, user_id: str) -> Path:
    return _INDEX_DIR / f"{session_id}_{slot}_{user_id}.json"


def cmd_round(args: argparse.Namespace) -> int:
    """发奖/抽奖后：备份上一轮 after → 拉新 after → 与 baseline 或 prev 求差 → 输出单轮摘要。"""
    session_id = str(args.session_id).strip()
    user_id = _resolve_user_id(str(args.user_id or ""), str(args.phone or ""))
    user_label = str(args.user_label or args.phone or user_id).strip()
    compare = (str(args.compare or "prev").strip() or "prev").lower()
    if compare not in ("prev", "baseline"):
        raise ValueError("--compare 须为 prev 或 baseline")

    after_path = _snap_path_for(session_id, "after", user_id)
    prev_path = _snap_path_for(session_id, "prev", user_id)
    baseline_path = _snap_path_for(session_id, "baseline", user_id)
    diff_out = _INDEX_DIR / f"{session_id}_last_round_diff_{user_id}.json"

    if after_path.is_file():
        shutil.copy2(after_path, prev_path)

    rc = cmd_record(
        argparse.Namespace(
            session_id=session_id,
            slot="after",
            user_id=user_id,
            phone="",
            user_label=user_label,
            cp_user_id=str(args.cp_user_id or ""),
            intimate_id=str(args.intimate_id or ""),
        )
    )
    if rc != 0:
        return rc

    if compare == "baseline":
        if not baseline_path.is_file():
            print(
                json.dumps(
                    {"ok": False, "error": "无 baseline，请先 record --slot baseline"},
                    ensure_ascii=False,
                )
            )
            return 1
        before_path = baseline_path
    else:
        if prev_path.is_file():
            before_path = prev_path
        elif baseline_path.is_file():
            before_path = baseline_path
        else:
            print(
                json.dumps(
                    {"ok": False, "error": "无 prev/baseline 可对比"},
                    ensure_ascii=False,
                )
            )
            return 1

    before_snap = json.loads(before_path.read_text(encoding="utf-8"))
    after_snap = json.loads(after_path.read_text(encoding="utf-8"))

    rc, out, err = _run(
        [
            "python3",
            "workflow/scripts/reward_verify.py",
            "diff",
            "--before",
            str(before_path),
            "--after",
            str(after_path),
            "--out",
            str(diff_out),
        ]
    )
    if rc != 0:
        print(err or out, file=sys.stderr)
        return rc

    start = out.find("{")
    diff = json.loads(out[start : out.rfind("}") + 1]) if start >= 0 else json.loads(
        diff_out.read_text(encoding="utf-8")
    )

    scripts_dir = _REPO / "workflow" / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from reward_verify import summarize_web_reward_round  # noqa: E402

    index = _load_index(session_id)
    round_no = int(index.get("roundCount") or 0) + 1
    index["roundCount"] = round_no
    index["lastRoundAtBeijing"] = datetime.now(_BEIJING).strftime("%Y-%m-%d %H:%M:%S")
    index["lastCompareMode"] = compare
    _save_index(session_id, index)

    summary = summarize_web_reward_round(
        diff,
        before_snap,
        after_snap,
        user_label=user_label,
        round_no=round_no,
    )
    summary["sessionId"] = session_id
    summary["compareMode"] = compare
    summary["diffPath"] = str(diff_out.relative_to(_REPO))
    summary["beforeSnapshot"] = str(before_path.relative_to(_REPO))
    summary["afterSnapshot"] = str(after_path.relative_to(_REPO))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Web Agent 奖励下发验证（会话快照）")
    sub = parser.add_subparsers(dest="command", required=True)

    p_rec = sub.add_parser("record", help="记录用户全量资产快照到本会话")
    p_rec.add_argument("--session-id", required=True)
    p_rec.add_argument("--slot", default="baseline", help="baseline / after 等")
    p_rec.add_argument("--user-id", default="")
    p_rec.add_argument("--phone", default="")
    p_rec.add_argument("--user-label", default="")
    p_rec.add_argument("--cp-user-id", default="")
    p_rec.add_argument("--intimate-id", default="")
    p_rec.set_defaults(func=cmd_record)

    p_show = sub.add_parser("show", help="展示已记录快照的资产概况（全量明细请 export 钉钉）")
    p_show.add_argument("--session-id", required=True)
    p_show.add_argument("--slot", default="baseline")
    p_show.add_argument("--user-label", default="")
    p_show.add_argument(
        "--full",
        action="store_true",
        help="输出全量分类 Markdown（默认仅概况表）",
    )
    p_show.set_defaults(func=cmd_show)

    p_st = sub.add_parser("status", help="查看本会话已记录的 slot")
    p_st.add_argument("--session-id", required=True)
    p_st.set_defaults(func=cmd_status)

    p_exp = sub.add_parser("export", help="导出已记录快照到钉钉在线表格（Agent 导出目录）")
    p_exp.add_argument("--session-id", required=True)
    p_exp.add_argument("--slot", default="baseline")
    p_exp.add_argument("--user-label", default="")
    p_exp.add_argument("--workbook-name", default="", help="表格文件名（默认 用户资产_<userId>_<slot>_<时间>）")
    p_exp.add_argument("--parent-node-id", default="", help="父目录 nodeId（默认 export_folder.json）")
    p_exp.set_defaults(func=cmd_export)

    p_round = sub.add_parser(
        "round",
        help="抽奖/发奖后单轮验收：备份 prev → 拉 after → 求差并输出摘要（装扮增量天、钻石明细）",
    )
    p_round.add_argument("--session-id", required=True)
    p_round.add_argument("--user-id", default="")
    p_round.add_argument("--phone", default="")
    p_round.add_argument("--user-label", default="")
    p_round.add_argument(
        "--compare",
        default="prev",
        choices=("prev", "baseline"),
        help="prev=相对上一轮 after（默认）；baseline=相对发奖前 baseline",
    )
    p_round.add_argument("--cp-user-id", default="")
    p_round.add_argument("--intimate-id", default="")
    p_round.set_defaults(func=cmd_round)

    args = parser.parse_args()
    try:
        return args.func(args)
    except (OSError, ValueError, json.JSONDecodeError, RuntimeError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
