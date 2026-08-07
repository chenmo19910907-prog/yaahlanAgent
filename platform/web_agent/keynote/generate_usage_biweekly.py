#!/usr/bin/env python3
"""从 Web Agent 打点 + 会话消息 + 钉钉 duration_history 生成 keynote 用量页数据。"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
OUTPUT = BASE / "usage_biweekly.json"

BJ = timezone(timedelta(hours=8))
OPT_DATE = date(2026, 7, 27)

CN_STAT_HOLIDAYS_2026 = {
    "2026-01-01": 1,
    "2026-01-02": 1,
    "2026-01-03": 1,
    "2026-02-15": 1,
    "2026-02-16": 1,
    "2026-02-17": 1,
    "2026-02-18": 1,
    "2026-02-19": 1,
    "2026-02-20": 1,
    "2026-02-21": 1,
    "2026-02-22": 1,
    "2026-02-23": 1,
    "2026-04-04": 1,
    "2026-04-05": 1,
    "2026-04-06": 1,
    "2026-05-01": 1,
    "2026-05-02": 1,
    "2026-05-03": 1,
    "2026-05-04": 1,
    "2026-05-05": 1,
    "2026-06-19": 1,
    "2026-06-20": 1,
    "2026-06-21": 1,
    "2026-10-01": 1,
    "2026-10-02": 1,
    "2026-10-03": 1,
    "2026-10-04": 1,
    "2026-10-05": 1,
    "2026-10-06": 1,
    "2026-10-07": 1,
    "2026-10-08": 1,
}
CN_MAKEUP = {
    "2026-01-04": 1,
    "2026-02-14": 1,
    "2026-02-28": 1,
    "2026-04-26": 1,
    "2026-09-27": 1,
    "2026-10-10": 1,
}


def is_workday(day: date) -> bool:
    ds = day.isoformat()
    if CN_MAKEUP.get(ds):
        return True
    if CN_STAT_HOLIDAYS_2026.get(ds):
        return False
    return day.weekday() < 5


def parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(BJ)


def recent_natural_week_workdays(*, today: date | None = None, weeks: int = 3) -> list[date]:
    anchor = today or datetime.now(BJ).date()
    monday = anchor - timedelta(days=anchor.weekday())
    out: list[date] = []
    for w in range(weeks):
        week_start = monday - timedelta(weeks=weeks - 1 - w)
        for offset in range(7):
            day = week_start + timedelta(days=offset)
            if day > anchor:
                break
            if is_workday(day):
                out.append(day)
    return out


def _load_old_days() -> dict[str, dict[str, object]]:
    if not OUTPUT.is_file():
        return {}
    try:
        raw = json.loads(OUTPUT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    days = raw.get("days")
    if not isinstance(days, list):
        return {}
    return {
        str(item.get("date") or ""): item
        for item in days
        if isinstance(item, dict) and item.get("date")
    }


def _collect_web_counts(workdays: list[date]) -> tuple[dict[date, int], dict[date, set[str]]]:
    msg_counts: dict[date, int] = defaultdict(int)
    msg_users: dict[date, set[str]] = defaultdict(set)
    messages_dir = ROOT / "platform" / "web_agent" / "data" / "messages"
    for path in messages_dir.glob("*.json"):
        try:
            rows = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict) or row.get("role") != "user":
                continue
            ts = row.get("timestamp")
            if not ts:
                continue
            try:
                day = parse_ts(str(ts)).date()
            except ValueError:
                continue
            if day not in workdays:
                continue
            msg_counts[day] += 1
            staff_id = str(row.get("author_id") or "").strip()
            if staff_id:
                msg_users[day].add(staff_id)

    chat_counts: dict[date, int] = defaultdict(int)
    chat_users: dict[date, set[str]] = defaultdict(set)
    analytics_path = ROOT / "platform" / "web_agent" / "data" / "analytics" / "events.jsonl"
    if analytics_path.is_file():
        for line in analytics_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("event") != "chat_send":
                continue
            try:
                day = parse_ts(str(event.get("ts") or "")).date()
            except ValueError:
                continue
            if day not in workdays:
                continue
            chat_counts[day] += 1
            staff_id = str(event.get("staff_id") or "").strip()
            if staff_id:
                chat_users[day].add(staff_id)

    web_counts: dict[date, int] = {}
    web_users: dict[date, set[str]] = defaultdict(set)
    for day in workdays:
        web_counts[day] = chat_counts[day] if chat_counts[day] else msg_counts[day]
        web_users[day] = msg_users[day] | chat_users[day]
    return web_counts, web_users


def _collect_dingtalk_counts(workdays: list[date]) -> dict[date, int]:
    counts: dict[date, int] = defaultdict(int)
    history_path = ROOT / "platform" / "dingtalk_gateway" / "data" / "duration_history.json"
    if not history_path.is_file():
        return counts
    try:
        raw = json.loads(history_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return counts
    for records in raw.values():
        if not isinstance(records, list):
            continue
        for row in records:
            if not isinstance(row, dict):
                continue
            ts = str(row.get("recordedAt") or "")
            if len(ts) < 10:
                continue
            try:
                day = date.fromisoformat(ts[:10])
            except ValueError:
                continue
            if day in workdays:
                counts[day] += 1
    return counts


def _fmt_lift(before: int, after: int) -> str:
    if before <= 0:
        return "—"
    ratio = after / before
    rounded = f"{ratio:.1f}".rstrip("0").rstrip(".")
    return f"{rounded}×"


def build_usage(*, today: date | None = None, weeks: int = 3) -> dict[str, object]:
    workdays = recent_natural_week_workdays(today=today, weeks=weeks)
    if not workdays:
        raise SystemExit("无可用工作日")

    old_map = _load_old_days()
    web_counts, web_users = _collect_web_counts(workdays)
    dt_counts = _collect_dingtalk_counts(workdays)

    days_out: list[dict[str, object]] = []
    for day in workdays:
        ds = day.isoformat()
        requests = int(web_counts.get(day, 0) + dt_counts.get(day, 0))
        users = len(web_users.get(day, set()))
        if requests > 0 and users == 0:
            users = 1
        if ds in old_map:
            requests = max(requests, int(old_map[ds].get("requests") or 0))
            users = max(users, int(old_map[ds].get("users") or 0))
        days_out.append(
            {
                "date": ds,
                "label": f"{day.month}/{day.day}",
                "requests": requests,
                "users": users,
            }
        )

    before = [row for row in days_out if str(row["date"]) < OPT_DATE.isoformat()]
    after = [row for row in days_out if str(row["date"]) >= OPT_DATE.isoformat()]

    def _avg(items: list[dict[str, object]]) -> int:
        if not items:
            return 0
        return round(sum(int(item["requests"]) for item in items) / len(items))

    def _peak_users(items: list[dict[str, object]]) -> int:
        return max((int(item["users"]) for item in items), default=0)

    before_avg = _avg(before)
    after_avg = _avg(after)
    before_peak = _peak_users(before)
    after_peak = _peak_users(after)

    return {
        "title": "Yaahlan 智能工具平台 · 近三周用量",
        "range": [days_out[0]["date"], days_out[-1]["date"]],
        "rangeLabel": f"{days_out[0]['label']} – {days_out[-1]['label']}",
        "optimizeDate": OPT_DATE.isoformat(),
        "optimizeLabel": "7/27 体验优化",
        "source": "钉钉 + Web Agent · 工作日数据",
        "days": days_out,
        "summary": {
            "beforeAvgRequests": before_avg,
            "afterAvgRequests": after_avg,
            "requestsLift": _fmt_lift(before_avg, after_avg),
            "beforePeakUsers": before_peak,
            "afterPeakUsers": after_peak,
            "usersLift": _fmt_lift(before_peak, after_peak),
        },
    }


def main() -> int:
    payload = build_usage()
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    peak_req = max(int(row["requests"]) for row in payload["days"])
    print(
        f"wrote {OUTPUT.name}: {len(payload['days'])} workdays, "
        f"range {payload['rangeLabel']}, peak {peak_req} req/day"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
