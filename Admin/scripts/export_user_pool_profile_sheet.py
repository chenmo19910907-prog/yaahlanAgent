#!/usr/bin/env python3
"""导出账号池用户手机号/昵称/公会/家族到钉钉表格。"""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
ADMIN_DIR = REPO_ROOT / "Admin"
INACTIVE_KB = REPO_ROOT / "testcase-kb" / "admin_user_pool_inactive.json"
ACTIVE_KB = REPO_ROOT / "testcase-kb" / "admin_user_pool_active.json"
LEGACY_KB = REPO_ROOT / "testcase-kb" / "admin_user_pool.json"
EXPORT_CONFIG = REPO_ROOT / "platform" / "dingtalk_gateway" / "config" / "export_folder.json"
USER_KEY_DEFAULT = "cidwuF5xkEMvaZMDWWu8BtHbg==:user:32274159141215328"

sys.path.insert(0, str(ADMIN_DIR))

from admin.client import http_post_json  # noqa: E402
from admin.config import defaults  # noqa: E402
from admin.env import load_local_env  # noqa: E402
from admin.user import parse_user_detail_summary  # noqa: E402

EXCEL_VENV_PYTHON = (
    REPO_ROOT / ".cursor/skills/testcase-to-excel/mcp_dingtalk_excel/venv/bin/python3.13"
)
GATEWAY_DIR = REPO_ROOT / "platform" / "dingtalk_gateway"
CHECKPOINT_PATH = REPO_ROOT / ".tmp" / "export_user_pool_profiles_checkpoint.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _load_user_ids() -> tuple[list[str], dict[str, str]]:
    pool_map: dict[str, str] = {}
    for path, label in (
        (INACTIVE_KB, "非活跃"),
        (ACTIVE_KB, "活跃"),
        (LEGACY_KB, "非活跃"),
    ):
        if not path.is_file():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        for uid in payload.get("userIds") or []:
            text = str(uid or "").strip()
            if not text:
                continue
            if text not in pool_map:
                pool_map[text] = label
    ordered = list(pool_map.keys())
    return ordered, pool_map


def _report_progress(
    *,
    user_key: str,
    current: int,
    total: int,
    detail: str = "",
    result_text: str = "",
) -> None:
    if total < 3:
        return
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
        "查询用户信息",
    ]
    if detail:
        cmd.extend(["--detail", detail])
    if result_text:
        cmd.extend(["--result-text", result_text])
    subprocess.run(cmd, cwd=str(REPO_ROOT), check=False)


_AREA_CODES_BY_LEN = ("966", "86", "91", "90", "1")


def _format_phone_with_space(*, area_code: str, local: str) -> str:
    code = str(area_code or "").strip().lstrip("+")
    number = str(local or "").strip()
    if not code or not number:
        return number or (f"+{code}" if code else "")
    return f"+{code} {number}"


def _reformat_phone_display(phone: str) -> str:
    raw = str(phone or "").strip()
    if not raw:
        return ""
    if re.match(r"^\+\d+ \S", raw):
        return raw
    if raw.startswith("+"):
        body = raw[1:]
        for code in _AREA_CODES_BY_LEN:
            if body.startswith(code) and len(body) > len(code):
                return _format_phone_with_space(area_code=code, local=body[len(code) :])
    return raw


def _normalize_phone(phone: str | None, area_code: str | None) -> tuple[str, int | None]:
    raw = str(phone or "").strip()
    if not raw:
        return "", None
    if "|" in raw:
        _, local = raw.split("|", 1)
        display = local.strip()
    else:
        display = raw
    digits = re.sub(r"\D", "", display)
    sort_value = int(digits) if digits else None
    code = str(area_code or "").strip().lstrip("+")
    if code and display and not display.startswith("+"):
        display = _format_phone_with_space(area_code=code, local=display)
    elif display.startswith("+"):
        display = _reformat_phone_display(display)
    return display, sort_value


def _query_user_detail(user_id: str) -> dict[str, Any]:
    cfg = defaults("query_user_detail")
    base = str(cfg.get("baseUrl") or "https://yaahlan-admin-alpha.wemomo.com").rstrip("/")
    path = str(cfg.get("path", "/admin/user/queryUserDetail"))
    resp = http_post_json(f"{base}{path}", {"userId": user_id}, timeout_s=20.0)
    if resp.get("ec") != 200:
        raise RuntimeError(
            f"查询用户详情失败: userId={user_id} ec={resp.get('ec')} em={resp.get('em')}"
        )
    return parse_user_detail_summary(resp.get("data"))


def _query_family_name(user_id: str) -> str:
    cmd = [
        sys.executable,
        str(REPO_ROOT / "MOA" / "moa_execute.py"),
        "--family-detail-by-user-id",
        user_id,
    ]
    proc = subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if proc.returncode != 0 or not (proc.stdout or "").strip():
        return ""
    try:
        body = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return ""
    if not body.get("joinedFamily"):
        return ""
    admin_info = body.get("adminFamilyInfo")
    if isinstance(admin_info, dict):
        return str(admin_info.get("familyName") or admin_info.get("familyId") or "").strip()
    return str(body.get("familyId") or "").strip()


def _phone_sort_key(row: dict[str, Any]) -> tuple[int, int]:
    sort_value = row.get("phoneSort")
    if sort_value is None:
        return (1, 0)
    return (0, int(sort_value))


def _load_checkpoint() -> dict[str, Any] | None:
    if not CHECKPOINT_PATH.is_file():
        return None
    try:
        payload = json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    rows = payload.get("rows")
    processed_count = payload.get("processedCount")
    if not isinstance(rows, list) or not isinstance(processed_count, int):
        return None
    return payload


def _save_checkpoint(*, rows: list[dict[str, Any]], processed_count: int, total: int) -> None:
    CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
    CHECKPOINT_PATH.write_text(
        json.dumps(
            {
                "processedCount": processed_count,
                "total": total,
                "rows": rows,
                "savedAt": _utc_now(),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _clear_checkpoint() -> None:
    if CHECKPOINT_PATH.is_file():
        CHECKPOINT_PATH.unlink()


def _export_csv_to_dingtalk(csv_path: Path, *, workbook_name: str) -> str:
    if not EXCEL_VENV_PYTHON.is_file():
        raise RuntimeError(f"钉钉导出 venv 不存在: {EXCEL_VENV_PYTHON}")
    export_cfg = json.loads(EXPORT_CONFIG.read_text(encoding="utf-8"))
    code = f"""
import json
import sys
from pathlib import Path
sys.path.insert(0, {json.dumps(str(GATEWAY_DIR))})
from alidocs_excel_export import export_csv_to_folder
cfg = json.loads(Path({json.dumps(str(EXPORT_CONFIG))}).read_text(encoding="utf-8"))
url = export_csv_to_folder(
    {json.dumps(str(csv_path))},
    parent_node_id=cfg["nodeId"],
    workbook_name={json.dumps(workbook_name)},
    text_column_indexes={{0, 1}},
)
print(url)
"""
    proc = subprocess.run(
        [str(EXCEL_VENV_PYTHON), "-c", code],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip()[-500:]
        raise RuntimeError(f"导出钉钉表格失败: {tail}")
    url = (proc.stdout or "").strip().splitlines()[-1].strip()
    if not url.startswith("http"):
        raise RuntimeError(f"导出钉钉表格未返回链接: {proc.stdout[:200]}")
    return url


def build_result_markdown(
    *,
    total: int,
    with_phone: int,
    without_phone: int,
    sheet_url: str,
    synced_at: str,
) -> str:
    return "\n".join(
        [
            "## 账号池用户信息导出完成",
            "",
            f"- 合计账号：**{total}**",
            f"- 有手机号：**{with_phone}**",
            f"- 无手机号：**{without_phone}**（已排到最后）",
            f"- 排序规则：按手机号数值升序，无手机号置底",
            f"- 导出时间：{synced_at}",
            f"- 在线表格：{sheet_url}",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="导出账号池用户资料到钉钉表格")
    parser.add_argument("--user-key", default=USER_KEY_DEFAULT)
    parser.add_argument("--no-progress", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="只查询不导出钉钉")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="从 .tmp/export_user_pool_profiles_checkpoint.json 断点续跑",
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="忽略断点，从头查询",
    )
    parser.add_argument(
        "--from-kb",
        action="store_true",
        help="从 testcase-kb/admin_user_pool_profiles.json 重排手机号格式并重新导出",
    )
    args = parser.parse_args()

    load_local_env(str(ADMIN_DIR))

    local_path = REPO_ROOT / "testcase-kb" / "admin_user_pool_profiles.json"
    if args.from_kb:
        if not local_path.is_file():
            print(f"本地快照不存在: {local_path}", file=sys.stderr)
            return 1
        payload = json.loads(local_path.read_text(encoding="utf-8"))
        records = payload.get("records") or []
        if not records:
            print("本地快照无 records", file=sys.stderr)
            return 1
        rows: list[dict[str, Any]] = []
        for record in records:
            phone_display = _reformat_phone_display(str(record.get("phone") or ""))
            digits = re.sub(r"\D", "", phone_display)
            rows.append(
                {
                    "userId": str(record.get("userId") or "").strip(),
                    "phone": phone_display,
                    "phoneSort": int(digits) if digits else None,
                    "nickname": str(record.get("nickname") or "").strip(),
                    "guild": str(record.get("guild") or "").strip(),
                    "family": str(record.get("family") or "").strip(),
                    "pool": str(record.get("pool") or "").strip(),
                }
            )
        rows.sort(key=_phone_sort_key)
        total = len(rows)
        with_phone = sum(1 for row in rows if row.get("phone"))
        without_phone = total - with_phone
        synced_at = _utc_now()
        header = ["userId", "手机号", "昵称", "所属公会", "所属家族", "池类型"]
        sheet_rows = [header]
        for row in rows:
            sheet_rows.append(
                [
                    row["userId"],
                    row["phone"],
                    row["nickname"],
                    row["guild"],
                    row["family"],
                    row["pool"],
                ]
            )
        csv_path = (
            REPO_ROOT
            / ".tmp"
            / f"admin_user_pool_profiles_{datetime.now().strftime('%Y%m%d-%H%M%S')}.csv"
        )
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerows(sheet_rows)
        local_payload = {
            "kbPath": str(local_path.relative_to(REPO_ROOT)),
            "description": "账号池用户资料快照（手机号/昵称/公会/家族）",
            "syncedAt": synced_at,
            "count": total,
            "withPhone": with_phone,
            "withoutPhone": without_phone,
            "records": rows,
        }
        local_path.write_text(
            json.dumps(local_payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        workbook_name = f"账号池用户信息-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        sheet_url = _export_csv_to_dingtalk(csv_path, workbook_name=workbook_name)
        print(json.dumps({"count": total, "sheetUrl": sheet_url}, ensure_ascii=False))
        return 0

    user_ids, pool_map = _load_user_ids()
    if not user_ids:
        print("账号池为空", file=sys.stderr)
        return 1

    total = len(user_ids)
    report = not args.no_progress
    checkpoint = None if args.fresh else _load_checkpoint()
    rows: list[dict[str, Any]] = []
    start_index = 0
    if checkpoint and checkpoint.get("total") == total:
        rows = list(checkpoint.get("rows") or [])
        start_index = int(checkpoint.get("processedCount") or 0)
    elif args.resume and not checkpoint:
        print("未找到可续跑断点，将从头查询", file=sys.stderr)

    if report and total >= 3:
        if start_index > 0:
            _report_progress(
                user_key=args.user_key,
                current=start_index,
                total=total,
                detail=f"断点续跑，已完成 {start_index}/{total}",
            )
        else:
            _report_progress(
                user_key=args.user_key,
                current=0,
                total=total,
                detail=f"开始查询 {total} 个账号",
            )

    for index, uid in enumerate(user_ids, start=1):
        if index <= start_index:
            continue
        detail = _query_user_detail(uid)
        phone_display, phone_sort = _normalize_phone(
            str(detail.get("phone") or ""),
            str(detail.get("areaCode") or ""),
        )
        family_name = _query_family_name(uid)
        guild_name = str(detail.get("guildName") or "").strip()
        if not guild_name and detail.get("guildId"):
            guild_name = str(detail.get("guildId"))
        rows.append(
            {
                "userId": uid,
                "phone": phone_display,
                "phoneSort": phone_sort,
                "nickname": str(detail.get("nickname") or "").strip(),
                "guild": guild_name,
                "family": family_name,
                "pool": pool_map.get(uid, ""),
            }
        )
        _save_checkpoint(rows=rows, processed_count=index, total=total)
        if report and total >= 3:
            _report_progress(
                user_key=args.user_key,
                current=index,
                total=total,
                detail=f"{uid} · {phone_display or '无手机号'}",
            )

    rows.sort(key=_phone_sort_key)
    with_phone = sum(1 for row in rows if row.get("phone"))
    without_phone = total - with_phone
    synced_at = _utc_now()

    header = ["userId", "手机号", "昵称", "所属公会", "所属家族", "池类型"]
    sheet_rows = [header]
    for row in rows:
        sheet_rows.append(
            [
                row["userId"],
                row["phone"],
                row["nickname"],
                row["guild"],
                row["family"],
                row["pool"],
            ]
        )

    csv_path = REPO_ROOT / ".tmp" / f"admin_user_pool_profiles_{datetime.now().strftime('%Y%m%d-%H%M%S')}.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerows(sheet_rows)

    local_path = REPO_ROOT / "testcase-kb" / "admin_user_pool_profiles.json"
    local_payload = {
        "kbPath": str(local_path.relative_to(REPO_ROOT)),
        "description": "账号池用户资料快照（手机号/昵称/公会/家族）",
        "syncedAt": synced_at,
        "count": total,
        "withPhone": with_phone,
        "withoutPhone": without_phone,
        "records": rows,
    }
    local_path.write_text(
        json.dumps(local_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    sheet_url = ""
    if not args.dry_run:
        workbook_name = f"账号池用户信息-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        sheet_url = _export_csv_to_dingtalk(csv_path, workbook_name=workbook_name)

    result_md = build_result_markdown(
        total=total,
        with_phone=with_phone,
        without_phone=without_phone,
        sheet_url=sheet_url or "(dry-run)",
        synced_at=synced_at,
    )
    _clear_checkpoint()
    if report and total >= 3:
        _report_progress(
            user_key=args.user_key,
            current=total,
            total=total,
            detail="导出完成",
            result_text=result_md,
        )

    print(
        json.dumps(
            {
                "count": total,
                "withPhone": with_phone,
                "withoutPhone": without_phone,
                "localKbPath": str(local_path.relative_to(REPO_ROOT)),
                "sheetUrl": sheet_url,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
