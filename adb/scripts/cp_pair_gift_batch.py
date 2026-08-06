#!/usr/bin/env python3
"""双机批量：每对账号缔结 CP + 私信送 ≥5000 钻礼物。

用法:
  python3 adb/scripts/cp_pair_gift_batch.py --dry-run
  python3 adb/scripts/cp_pair_gift_batch.py --start-pair 13311111123
  python3 adb/scripts/cp_pair_gift_batch.py --serial-a 172.18.210.109:5555 --serial-b 172.18.208.184:5555
"""

from __future__ import annotations

import argparse
import json
import random
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from adb_script_paths import adb_execute_path, repo_root  # noqa: E402

sys.path.insert(0, str(repo_root() / "adb"))

from adb.actions import input_text, keyevent, tap  # noqa: E402
from adb.activity import get_foreground_activity  # noqa: E402
from adb.device import display_size  # noqa: E402
from adb.phone_login_status import query_phone_login_status  # noqa: E402
from adb.standard_nickname import standard_nickname  # noqa: E402
from adb.tunnel_verify import TunnelVerifyOptions, wait_for_tunnel  # noqa: E402
from adb.ui_locator import (  # noqa: E402
    LocatorNotFoundError,
    dump_ui_xml,
    resolve_tap_from_step,
)
import xml.etree.ElementTree as ET  # noqa: E402

PROGRESS_PATH = repo_root() / "adb/.state/cp_pair_gift_progress.json"
ADB_EXEC = ["python3", str(adb_execute_path())]

DEFAULT_SERIAL_A = "172.18.210.109:5555"
DEFAULT_SERIAL_B = "172.18.208.184:5555"
DEFAULT_FROM = 13311111123
DEFAULT_TO = 13311111199
SKIP_PAIRS: set[tuple[str, str]] = {("13311111121", "13311111122")}

GIFT_QTY_OPTIONS = (2, 3, 5, 7, 11, 17)


def _load_progress() -> dict[str, Any]:
    if PROGRESS_PATH.exists():
        return json.loads(PROGRESS_PATH.read_text(encoding="utf-8"))
    return {"completed": [], "failed": []}


def _save_progress(data: dict[str, Any]) -> None:
    PROGRESS_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROGRESS_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def make_pairs(from_phone: int, to_phone: int) -> list[tuple[str, str]]:
    phones = list(range(from_phone, to_phone + 1))
    pairs: list[tuple[str, str]] = []
    for i in range(0, len(phones) - 1, 2):
        a, b = str(phones[i]), str(phones[i + 1])
        if (a, b) not in SKIP_PAIRS:
            pairs.append((a, b))
    return pairs


def run_cli(serial: str, *args: str, timeout: int = 180) -> dict[str, Any]:
    cmd = [*ADB_EXEC, "-s", serial, *args]
    proc = subprocess.run(
        cmd,
        cwd=str(repo_root()),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    out = proc.stdout.strip()
    payload: dict[str, Any] = {"exitCode": proc.returncode, "stderr": proc.stderr}
    if out:
        idx = out.rfind("{")
        if idx >= 0:
            try:
                payload["result"] = json.loads(out[idx:])
            except json.JSONDecodeError:
                payload["raw"] = out
        else:
            payload["raw"] = out
    return payload


def sleep_ms(ms: int) -> None:
    time.sleep(ms / 1000.0)


def _find_text_node(
    xml_text: str,
    text: str,
    *,
    contains: bool = False,
    prefer_clickable: bool = True,
) -> dict[str, Any] | None:
    root = ET.fromstring(xml_text)
    matches: list[dict[str, Any]] = []

    def walk(node: ET.Element) -> None:
        t = (node.attrib.get("text") or "").strip()
        b = node.attrib.get("bounds") or ""
        m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", b)
        if not m:
            for child in node:
                walk(child)
            return
        hit = (text in t) if contains else (t == text)
        if hit:
            x1, y1, x2, y2 = map(int, m.groups())
            matches.append(
                {
                    "text": t,
                    "center": ((x1 + x2) // 2, (y1 + y2) // 2),
                    "clickable": node.attrib.get("clickable") == "true",
                }
            )
        for child in node:
            walk(child)

    walk(root)
    if prefer_clickable:
        clickable = [m for m in matches if m["clickable"]]
        if clickable:
            matches = clickable
    return matches[0] if matches else None


def tap_rid(serial: str, resource_id: str, *, index: int = 0) -> None:
    w, h = display_size(serial)
    hit = resolve_tap_from_step(
        {"resourceId": resource_id, "index": index},
        serial=serial,
        width=w,
        height=h,
    )
    tap(x=int(hit["x"]), y=int(hit["y"]), serial=serial)


def tap_text_clickable(serial: str, text: str, *, contains: bool = False) -> bool:
    xml = dump_ui_xml(serial=serial)
    node = _find_text_node(xml, text, contains=contains, prefer_clickable=True)
    if not node or not node.get("center"):
        return False
    cx, cy = node["center"]
    tap(x=cx, y=cy, serial=serial)
    return True


def tap_nickname_row(serial: str, nickname: str) -> bool:
    xml = dump_ui_xml(serial=serial)
    node = _find_text_node(xml, nickname, contains=False, prefer_clickable=False)
    if not node or not node.get("center"):
        return False
    cx, cy = node["center"]
    # 消息列表行：昵称偏上，点行中部
    tap(x=cx, y=cy + 60, serial=serial)
    return True


def _back_to_home(serial: str, *, max_steps: int = 8) -> None:
    for _ in range(max_steps):
        fa = get_foreground_activity(serial=serial)
        if fa.get("hint") in ("login", "home"):
            return
        keyevent(code=4, serial=serial)
        sleep_ms(600)
    fa = get_foreground_activity(serial=serial)
    if fa.get("hint") not in ("login", "home"):
        # 兜底：点底栏 Me 再退出
        try:
            tap_rid(serial, "tab_profile")
        except LocatorNotFoundError:
            tap(x=972, y=2237, serial=serial)
        sleep_ms(800)


def ensure_logout(serial: str) -> None:
    fa = get_foreground_activity(serial=serial)
    if fa.get("hint") == "login":
        return
    _back_to_home(serial)
    fa = get_foreground_activity(serial=serial)
    if fa.get("hint") == "login":
        return
    # 直接点 Me → 设置 → Log out（避免 macro popup_gate 触发 uiautomator dump 失败）
    try:
        tap_rid(serial, "tab_profile")
    except LocatorNotFoundError:
        tap(x=972, y=2237, serial=serial)
    sleep_ms(800)
    try:
        tap_rid(serial, "iv_setting")
    except LocatorNotFoundError:
        tap(x=996, y=159, serial=serial)
    sleep_ms(800)
    tap(x=540, y=2205, serial=serial)
    sleep_ms(2000)
    fa2 = get_foreground_activity(serial=serial)
    if fa2.get("hint") != "login":
        raise RuntimeError(f"{serial} 退出登录失败，当前 {fa2.get('shortName')}")


def login_phone(serial: str, phone: str) -> str:
    ensure_logout(serial)
    out = run_cli(serial, "accounts", "enter", "--text", phone, timeout=120)
    result = out.get("result") or {}
    if not result.get("ok"):
        raise RuntimeError(f"{serial} 登录 {phone} 失败: {out}")
    status = result.get("phoneLoginStatus") or query_phone_login_status(phone)
    uid = status.get("userId")
    if not uid:
        raise RuntimeError(f"无法获取 {phone} 的 userId")
    sleep_ms(800)
    return str(uid)


def navigate_relationship_tab(serial: str) -> None:
    run_cli(serial, "macro", "我的页进入MyRelationship", "--force-script", "--no-popup-gate", "--no-capture")
    sleep_ms(1000)
    run_cli(serial, "macro", "资料页切换RelationshipTab", "--force-script", "--no-popup-gate", "--no-capture")
    sleep_ms(800)


def cp_invite(serial: str, *, b_user_id: str, b_nick: str) -> None:
    navigate_relationship_tab(serial)
    # CP「+」
    tap(x=890, y=790, serial=serial)
    sleep_ms(1200)
    # 搜索 userId
    tap(x=300, y=350, serial=serial)
    sleep_ms(400)
    input_text(str(b_user_id), serial=serial)
    sleep_ms(400)
    tap(x=960, y=350, serial=serial)
    sleep_ms(1500)
    # Invite 按钮
    xml = dump_ui_xml(serial=serial)
    invite = _find_text_node(xml, "Invite", contains=False, prefer_clickable=True)
    if invite and invite.get("center"):
        cx, cy = invite["center"]
        tap(x=cx, y=cy, serial=serial)
    else:
        tap(x=967, y=1943, serial=serial)
    sleep_ms(1500)
    # Send Invitation（组成关系弹窗）
    if not tap_text_clickable(serial, "Send Invitation"):
        tap(x=540, y=2180, serial=serial)
    sleep_ms(2500)


def cp_accept(serial: str, *, a_nick: str) -> None:
    # Message 底栏
    try:
        tap_rid(serial, "tab_message")
    except LocatorNotFoundError:
        tap(x=540, y=2200, serial=serial)
    sleep_ms(1000)
    if not tap_nickname_row(serial, a_nick):
        raise RuntimeError(f"{serial} 未找到 {a_nick} 私聊入口")
    sleep_ms(1500)
    if not tap_text_clickable(serial, "View"):
        raise RuntimeError(f"{serial} 未找到 View 按钮")
    sleep_ms(1500)
    if not tap_text_clickable(serial, "Accept"):
        raise RuntimeError(f"{serial} 未找到 Accept 按钮")
    sleep_ms(2000)


def send_gift_in_chat(serial: str, *, momoid: str, peer_nick: str) -> dict[str, Any]:
    # 确保在 Message 列表
    try:
        tap_rid(serial, "tab_message")
    except LocatorNotFoundError:
        tap(x=540, y=2200, serial=serial)
    sleep_ms(800)
    if get_foreground_activity(serial=serial).get("shortName") != "ChatActivity":
        if not tap_nickname_row(serial, peer_nick):
            raise RuntimeError(f"{serial} 私信未找到 {peer_nick}")
        sleep_ms(1500)
    # 礼物图标（非 img_game）
    try:
        tap_rid(serial, "gift_layout")
    except LocatorNotFoundError:
        tap(x=455, y=2269, serial=serial)
    sleep_ms(2000)
    # 选可见高价礼物：Romantic TOP2 5000 或 Twin Necklace 6000
    xml = dump_ui_xml(serial=serial)
    gift_hit = None
    for price in ("6000", "5000", "3000"):
        node = _find_text_node(xml, price, contains=False, prefer_clickable=False)
        if node and node.get("center"):
            gift_hit = node
            break
    if gift_hit and gift_hit.get("center"):
        cx, cy = gift_hit["center"]
        tap(x=cx, y=cy - 180, serial=serial)
    else:
        tap(x=412, y=1794, serial=serial)
    sleep_ms(800)
    qty = random.choice(GIFT_QTY_OPTIONS)
    qty_node = _find_text_node(
        dump_ui_xml(serial=serial), str(qty), contains=False, prefer_clickable=True
    )
    if qty_node and qty_node.get("center"):
        cx, cy = qty_node["center"]
        tap(x=cx, y=cy, serial=serial)
    else:
        for fallback in ("7", "1"):
            if tap_text_clickable(serial, fallback):
                break
    sleep_ms(500)
    if not tap_text_clickable(serial, "Send"):
        tap(x=979, y=2227, serial=serial)
    start = int(time.time())
    sleep_ms(3000)
    opts = TunnelVerifyOptions(
        momoid=momoid,
        keyword="gift/send",
        wait_seconds=25,
        poll_interval_ms=1500,
        expect_http_status=200,
        expect_response_ec=200,
        since_buffer_seconds=0,
    )
    tv = wait_for_tunnel(opts, start_time=start)
    return {"qty": qty, "tunnelVerify": tv}


def process_pair(
    *,
    serial_a: str,
    serial_b: str,
    phone_a: str,
    phone_b: str,
    dry_run: bool,
) -> dict[str, Any]:
    a_nick = standard_nickname(phone_a)
    b_nick = standard_nickname(phone_b)
    row: dict[str, Any] = {
        "phoneA": phone_a,
        "phoneB": phone_b,
        "nickA": a_nick,
        "nickB": b_nick,
        "ok": False,
    }
    if dry_run:
        row["ok"] = True
        row["dryRun"] = True
        return row

    b_status = query_phone_login_status(phone_b)
    b_uid = str(b_status.get("userId") or "")
    if not b_uid:
        raise RuntimeError(f"{phone_b} 无 userId")

    print(f"\n=== 登录 A={phone_a}({a_nick}) B={phone_b}({b_nick}) ===", flush=True)
    a_uid = login_phone(serial_a, phone_a)
    row["userIdA"] = a_uid
    b_uid_confirmed = login_phone(serial_b, phone_b)
    row["userIdB"] = b_uid_confirmed

    print(f"=== A 邀请 CP → {b_nick} ({b_uid}) ===", flush=True)
    cp_invite(serial_a, b_user_id=b_uid, b_nick=b_nick)

    print(f"=== B 接受 CP ← {a_nick} ===", flush=True)
    cp_accept(serial_b, a_nick=a_nick)

    print(f"=== A 私信送礼 → {b_nick} ===", flush=True)
    a_uid2 = login_phone(serial_a, phone_a)
    gift = send_gift_in_chat(serial_a, momoid=a_uid2, peer_nick=b_nick)
    row["gift"] = gift
    tv = gift.get("tunnelVerify") or {}
    row["ok"] = bool(tv.get("ok"))
    if not row["ok"]:
        row["error"] = "gift/send 验收失败"
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description="批量 CP 缔结 + 私信送礼（双机）")
    parser.add_argument("--from-phone", type=int, default=DEFAULT_FROM)
    parser.add_argument("--to-phone", type=int, default=DEFAULT_TO)
    parser.add_argument("--serial-a", default=DEFAULT_SERIAL_A)
    parser.add_argument("--serial-b", default=DEFAULT_SERIAL_B)
    parser.add_argument("--start-pair", help="从该手机号（A 方）开始")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    pairs = make_pairs(args.from_phone, args.to_phone)
    if args.start_pair:
        pairs = [p for p in pairs if p[0] >= args.start_pair]

    progress = _load_progress()
    done = set(tuple(x) for x in progress.get("completed", []))

    results: list[dict[str, Any]] = []
    for phone_a, phone_b in pairs:
        key = (phone_a, phone_b)
        if key in done:
            print(f"跳过已完成: {phone_a} / {phone_b}", flush=True)
            continue
        try:
            row = process_pair(
                serial_a=args.serial_a,
                serial_b=args.serial_b,
                phone_a=phone_a,
                phone_b=phone_b,
                dry_run=args.dry_run,
            )
            row["pair"] = list(key)
            results.append(row)
            if row.get("ok"):
                progress.setdefault("completed", []).append(list(key))
            else:
                progress.setdefault("failed", []).append({**row, "pair": list(key)})
            _save_progress(progress)
        except Exception as exc:
            err = {"pair": list(key), "ok": False, "error": str(exc)}
            results.append(err)
            progress.setdefault("failed", []).append(err)
            _save_progress(progress)
            print(f"失败 {phone_a}/{phone_b}: {exc}", file=sys.stderr, flush=True)

    summary = {
        "total": len(pairs),
        "processed": len(results),
        "ok": sum(1 for r in results if r.get("ok")),
        "failed": sum(1 for r in results if not r.get("ok")),
        "results": results,
    }
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(
            f"\n完成: {summary['ok']}/{summary['processed']} 成功 "
            f"（共 {summary['total']} 对，进度见 {PROGRESS_PATH}）"
        )
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
