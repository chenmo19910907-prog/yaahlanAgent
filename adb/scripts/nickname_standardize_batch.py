#!/usr/bin/env python3
"""扫描 QA 号段昵称是否符合标准，并输出 AI 读图工作流（不自动执行 UI）。

标准昵称：
  - 133111111XX → CXX
  - 133111112XX → C2XX

执行方式（每个账号 UI 不同，须 AI 读图导航，落点正确后再跑片段）：
  【Game 帧】无弹窗时不点击；有弹窗才读图处理；需进 Me 时仅点底栏 Me
  【Me 帧】只点顶部本人头像昵称行；禁止点 Viewed me 小头像
  1. macro 手机号登录 --text <phone>          # 注册登录模块，固定脚本 OK
  2. ai prepare --goal enter_me → capture/tap # 读图仅点底栏 Me，关弹窗
  3. ai prepare --goal enter_profile → …      # 读图点本人资料区进 ProfileActivity
  4. activity 验收 shortName=ProfileActivity
  5. macro 资料页进入编辑页 --force-script     # 已在资料页
  6. activity 验收 EditProfileActivity
  7. macro 资料页修改昵称为标准昵称 --text <phone> --force-script
  8. Admin --query-user-id 验收 nickname
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from adb_script_paths import admin_execute_path, repo_root  # noqa: E402

sys.path.insert(0, str(repo_root() / "adb"))

from adb.phone_login_status import query_phone_login_status  # noqa: E402
from adb.standard_nickname import standard_nickname  # noqa: E402


def run_admin(cmd: list[str], *, timeout: int = 40):
    import subprocess

    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(repo_root()),
        timeout=timeout,
        check=False,
    )


def admin_nickname(user_id: str) -> str | None:
    execute = admin_execute_path()
    proc = run_admin(["python3", str(execute), "--query-user-id", user_id])
    if proc.returncode != 0:
        return None
    try:
        body = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None
    nick = body.get("nickname")
    return str(nick).strip() if nick is not None else None


def scan_range(start: int, end: int) -> list[dict]:
    rows: list[dict] = []
    for num in range(start, end + 1):
        phone = str(num)
        expected = standard_nickname(phone)
        try:
            status = query_phone_login_status(phone)
        except Exception as exc:
            rows.append(
                {
                    "phone": phone,
                    "expected": expected,
                    "userId": None,
                    "nickname": None,
                    "action": "skip",
                    "reason": str(exc),
                }
            )
            continue
        uid = status.get("userId")
        if not uid:
            rows.append(
                {
                    "phone": phone,
                    "expected": expected,
                    "userId": None,
                    "nickname": None,
                    "action": "skip",
                    "reason": "unregistered",
                }
            )
            continue
        nick = admin_nickname(str(uid))
        action = "ok" if nick == expected else "fix"
        rows.append(
            {
                "phone": phone,
                "expected": expected,
                "userId": str(uid),
                "nickname": nick,
                "action": action,
            }
        )
    return rows


def workflow_for(row: dict) -> list[str]:
    phone = row["phone"]
    expected = row["expected"]
    uid = row.get("userId") or "<userId>"
    return [
        f"# {phone} 当前 {row.get('nickname')!r} → 目标 {expected} (userId={uid})",
        "# Game 帧：无弹窗不点击；有弹窗才处理；需进 Me 仅点底栏 Me(0.90,0.956)",
        "# Me 帧：只点顶部本人头像昵称行(0.11,0.16)；勿点 Viewed me 小头像",
        f"python3 adb/adb_execute.py macro 退出登录 --force-script --no-capture  # 或 ai prepare --goal logout",
        f"python3 adb/adb_execute.py macro 手机号登录 --text {phone} --skip login_lang --no-capture",
        "python3 adb/adb_execute.py ai prepare --goal enter_me",
        "python3 adb/adb_execute.py capture && python3 adb/adb_execute.py activity",
        "python3 adb/adb_execute.py ai prepare --goal enter_profile",
        "python3 adb/adb_execute.py capture && python3 adb/adb_execute.py activity  # 期望 ProfileActivity",
        "python3 adb/adb_execute.py macro 资料页进入编辑页 --force-script --no-capture",
        "python3 adb/adb_execute.py activity  # 期望 EditProfileActivity",
        f"python3 adb/adb_execute.py macro 资料页修改昵称为标准昵称 --text {phone} --force-script",
        f"python3 {admin_execute_path()} --query-user-id {uid}  # 期望 nickname={expected}",
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="昵称标准化：扫描 + AI 读图工作流（不自动点 UI）")
    parser.add_argument("--from-phone", type=int, default=13311111131)
    parser.add_argument("--to-phone", type=int, default=13311111220)
    parser.add_argument("--phone", help="仅输出单个号码工作流")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args()

    if args.phone:
        rows = scan_range(int(args.phone), int(args.phone))
    else:
        rows = scan_range(args.from_phone, args.to_phone)

    mismatch = [r for r in rows if r["action"] == "fix"]
    summary = {
        "registered": sum(1 for r in rows if r.get("userId")),
        "ok": sum(1 for r in rows if r["action"] == "ok"),
        "fix": len(mismatch),
        "skip": sum(1 for r in rows if r["action"] == "skip"),
        "rows": rows,
        "mismatch": mismatch,
    }

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    print(
        f"扫描 {args.from_phone if not args.phone else args.phone}-"
        f"{args.to_phone if not args.phone else args.phone}: "
        f"注册 {summary['registered']}，已标准 {summary['ok']}，待改 {summary['fix']}，跳过 {summary['skip']}"
    )
    if not mismatch:
        print("全部符合标准。")
        return 0

    print("\n待改账号（须 AI 读图导航，落点正确后再跑片段）：\n")
    for row in mismatch:
        print(f"  {row['phone']}  {row.get('nickname')!r} → {row['expected']}  userId={row['userId']}")

    if args.phone and mismatch:
        print("\n工作流：")
        for line in workflow_for(mismatch[0]):
            print(line)
    elif len(mismatch) <= 3:
        for row in mismatch:
            print(f"\n--- {row['phone']} ---")
            for line in workflow_for(row):
                print(line)

    print(f"\n截图目录: adb/screenshots/nickname_batch/<phone>/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
