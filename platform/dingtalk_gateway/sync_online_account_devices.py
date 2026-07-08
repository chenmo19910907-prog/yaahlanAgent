#!/usr/bin/env python3
"""从钉钉「全部测试账号」读取线上账号，同步历史登录设备到 testcase-kb。"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "Admin"))
sys.path.insert(0, str(REPO_ROOT / "Risk"))
sys.path.insert(0, str(REPO_ROOT / "platform" / "dingtalk_gateway"))

from admin.client import http_post_json  # noqa: E402
from admin.config import defaults  # noqa: E402
from admin.env import load_local_env, load_online_env  # noqa: E402
from admin.user import parse_user_history_device_summary  # noqa: E402
from mse_workbook_utils import fetch_workbook_sheets_async  # noqa: E402
from risk.device_kb import upsert_login_device_record  # noqa: E402

DEFAULT_WORKBOOK_URL = (
    "https://alidocs.dingtalk.com/i/nodes/dQPGYqjpJYgLbY0YCxOYmbg3Wakx1Z5N"
)
DEFAULT_KB_PATH = REPO_ROOT / "testcase-kb" / "test_devices.json"


@dataclass
class AccountRow:
    user_id: str
    phone: str = ""
    owner: str = ""


@dataclass
class SyncStats:
    accounts_total: int = 0
    accounts_ok: int = 0
    accounts_failed: int = 0
    devices_seen: int = 0
    devices_added: int = 0
    devices_updated: int = 0
    devices_unchanged: int = 0
    failures: list[str] = field(default_factory=list)


def _cell_str(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    if text.replace(".", "", 1).isdigit() and "." in text:
        return str(int(float(text)))
    return text


def parse_accounts_from_sheet(rows: list[list[Any]]) -> list[AccountRow]:
    accounts: list[AccountRow] = []
    for row in rows[1:]:
        if not row:
            continue
        col0 = _cell_str(row[0] if len(row) > 0 else "")
        col1 = _cell_str(row[1] if len(row) > 1 else "")
        owner = _cell_str(row[5] if len(row) > 5 else "")
        if not col0 and not col1:
            continue

        user_id = ""
        phone = ""
        if col0.isdigit() and len(col0) <= 9:
            user_id = col0
            phone = col1
        elif col0.isdigit() and len(col0) >= 10:
            phone = col0
        elif col1.isdigit() and len(col1) <= 9:
            user_id = col1
            phone = col0

        if not user_id:
            continue
        accounts.append(AccountRow(user_id=user_id, phone=phone, owner=owner))
    return accounts


async def load_accounts(workbook_url: str) -> list[AccountRow]:
    sheets = await fetch_workbook_sheets_async(workbook_url)
    if "全部测试账号" not in sheets:
        raise ValueError("工作簿缺少 sheet「全部测试账号」")
    return parse_accounts_from_sheet(sheets["全部测试账号"])


def fetch_user_history_devices(user_id: str, *, page_size: int = 100) -> list[dict[str, Any]]:
    base_url = os.environ.get("ADMIN_ONLINE_BASE_URL", "https://yaahlan-admin.wemomo.com").strip()
    path = str(
        defaults("query_user_history_device_list").get(
            "path", "/yaahlan/backend/deviceHistory/queryUserHistoryDeviceList"
        )
    )
    url = f"{base_url}{path}"

    page = 1
    items: list[dict[str, Any]] = []
    total: int | None = None
    while True:
        body = {"userId": user_id, "page": page, "pageSize": page_size}
        resp = http_post_json(url, body, auth="yaahlan_online", timeout_s=30.0)
        if resp.get("ec") != 200:
            raise RuntimeError(f"Admin ec={resp.get('ec')} em={resp.get('em')}")
        summary = parse_user_history_device_summary(resp.get("data"))
        batch = summary.get("items") or []
        if not isinstance(batch, list):
            raise RuntimeError("历史设备 items 格式错误")
        items.extend(batch)
        if total is None:
            try:
                total = int(summary.get("total") or 0)
            except (TypeError, ValueError):
                total = len(items)
        if len(items) >= total or not batch:
            break
        page += 1
    return items


def upsert_devices_for_account(
    kb_path: Path,
    account: AccountRow,
    devices: list[dict[str, Any]],
) -> tuple[int, int, int]:
    added = updated = unchanged = 0
    for device in devices:
        mmuid = str(device.get("mmuid") or "").strip()
        mmuidv3 = str(device.get("mmuidv3") or "").strip()
        if not mmuid and not mmuidv3:
            continue
        result = upsert_login_device_record(
            kb_path,
            device,
            phone=account.phone,
            user_id=account.user_id,
        )
        action = result.get("action")
        if action == "added":
            added += 1
        elif action == "updated":
            updated += 1
        else:
            unchanged += 1
    return added, updated, unchanged


def report_progress(
    user_key: str,
    *,
    current: int,
    total: int,
    detail: str,
    label: str = "同步设备库",
    result_text: str = "",
    result_file: str = "",
) -> None:
    cmd = [
        sys.executable,
        str(REPO_ROOT / "platform" / "dingtalk_gateway" / "batch_progress_report.py"),
        "--user-key",
        user_key,
        "--current",
        str(current),
        "--total",
        str(total),
        "--label",
        label,
        "--detail",
        detail,
    ]
    if result_text:
        cmd.extend(["--result-text", result_text])
    if result_file:
        cmd.extend(["--result-file", result_file])
    subprocess.run(cmd, cwd=str(REPO_ROOT), check=False)


def build_result_markdown(stats: SyncStats) -> str:
    lines = [
        "## 线上测试账号设备库同步完成",
        "",
        f"- 账号总数：**{stats.accounts_total}**",
        f"- 成功：**{stats.accounts_ok}**，失败：**{stats.accounts_failed}**",
        f"- 历史设备条目：**{stats.devices_seen}**",
        f"- 新增：**{stats.devices_added}**，更新：**{stats.devices_updated}**，无变化：**{stats.devices_unchanged}**",
    ]
    if stats.failures:
        lines.extend(["", "### 失败账号", ""])
        for item in stats.failures[:30]:
            lines.append(f"- {item}")
        if len(stats.failures) > 30:
            lines.append(f"- … 另有 {len(stats.failures) - 30} 条")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="同步钉钉全部测试账号历史设备到设备库")
    parser.add_argument("--workbook-url", default=DEFAULT_WORKBOOK_URL)
    parser.add_argument("--kb-path", default=str(DEFAULT_KB_PATH))
    parser.add_argument("--user-key", default="", help="钉钉 batch_key，用于进度上报")
    parser.add_argument("--limit", type=int, default=0, help="仅处理前 N 个账号（调试用）")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    load_local_env(str(REPO_ROOT / "Admin"))
    load_online_env(str(REPO_ROOT / "Admin"))

    kb_path = Path(args.kb_path)
    accounts = asyncio.run(load_accounts(args.workbook_url))
    if args.limit > 0:
        accounts = accounts[: args.limit]

    stats = SyncStats(accounts_total=len(accounts))
    total = len(accounts)

    for index, account in enumerate(accounts, start=1):
        detail = account.phone or account.user_id
        try:
            devices = fetch_user_history_devices(account.user_id)
            stats.devices_seen += len(devices)
            if not args.dry_run:
                added, updated, unchanged = upsert_devices_for_account(kb_path, account, devices)
                stats.devices_added += added
                stats.devices_updated += updated
                stats.devices_unchanged += unchanged
            stats.accounts_ok += 1
        except (RuntimeError, ValueError, OSError) as exc:
            stats.accounts_failed += 1
            stats.failures.append(f"{detail} (userId={account.user_id}): {exc}")

        if args.user_key and total >= 3:
            is_last = index == total
            report_progress(
                args.user_key,
                current=index,
                total=total,
                detail=detail,
                result_text=build_result_markdown(stats) if is_last else "",
            )

        print(
            json.dumps(
                {
                    "index": index,
                    "total": total,
                    "userId": account.user_id,
                    "phone": account.phone,
                    "devices": stats.devices_seen,
                    "ok": stats.accounts_ok,
                    "failed": stats.accounts_failed,
                },
                ensure_ascii=False,
            ),
            flush=True,
        )

    if args.user_key and total < 3:
        report_progress(
            args.user_key,
            current=total,
            total=total,
            detail="完成",
            result_text=build_result_markdown(stats),
        )

    print(build_result_markdown(stats))
    return 0 if stats.accounts_failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
