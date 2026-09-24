# -*- coding: utf-8 -*-
"""
公会进步奖 E2E：历史基准 → 本周期表1 → MOA1 → MOA2 → 断言 motivation_amount。

新政策近 6 / 注册后最高读 union_salary_detail.total_salary_payable。
本脚本直接改确认表造历史（测完还原），不调用区域确认 MOA3。
旧政策对照仍同时改表4.union_total_salary。

用例：data/salary/guild_progress_award/yaahlan_guild_progress_award_cases.json
冒烟：SMOKE_CASES=… 或 JSON smoke_cases。
"""
from __future__ import annotations

import calendar
import logging
import os
import sys
import time

import pytest

CASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.normpath(os.path.join(CASE_DIR, "../../.."))
sys.path.insert(0, PROJECT_ROOT)

from utils.assert_utils import AssertUtils
from utils.guild_progress_award_table import (
    baseline_from_history,
    lookup_motivation,
)
from utils.json_utils import JsonUtils
from utils.moa_utils import MoaUtils
from utils.mysql_utils import MySQLUtils
from utils.salary_report import get_collector

logger = logging.getLogger(__name__)

DATA_SUBDIR = "salary/guild_progress_award"
DEFAULT_CASES_JSON = "yaahlan_guild_progress_award_cases.json"
MOA_URI = "/service/yaahlan-cms/anchor-salary-moa"
MOA_ENV = "alpha"
MOA1_WAIT_SEC = 3
MOA2_WAIT_SEC = 30
CLONE_SKIP = {"id", "create_time", "update_time"}


def _load_env():
    env_path = os.path.join(PROJECT_ROOT, ".env")
    if not os.path.isfile(env_path):
        return
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


_load_env()


def _get_db(database: str = "anchor_salary_2") -> MySQLUtils:
    db = MySQLUtils(
        host=os.environ["MYSQL_HOST"],
        port=int(os.environ.get("MYSQL_PORT", "3306")),
        user=os.environ["MYSQL_USER"],
        password=os.environ["MYSQL_PASSWORD"],
        database=database,
    )
    db.connect()
    return db


def _load_bundle(json_name: str = DEFAULT_CASES_JSON):
    return JsonUtils.jsonfile_to_dict(DATA_SUBDIR, json_name) or {}


_BUNDLE = _load_bundle()
_CASES = _BUNDLE.get("cases") or []
_SMOKE = {
    x.strip()
    for x in (os.environ.get("SMOKE_CASES") or "").split(",")
    if x.strip()
} or set(_BUNDLE.get("smoke_cases") or [])


def _validate_cases(cases: list) -> list[str]:
    required = ["case_name", "anchor_id", "trade_id", "period_start", "setup", "policy"]
    errors = []
    for case in cases:
        for key in required:
            if key not in case:
                errors.append(f"用例 [{case.get('case_name', '未知')}] 缺少必填字段: {key}")
        if "updates" not in case.get("setup", {}):
            errors.append(f"用例 [{case.get('case_name', '未知')}] setup 缺少 updates")
        if "baseline_mode" not in (case.get("policy") or {}):
            errors.append(f"用例 [{case.get('case_name', '未知')}] policy 缺少 baseline_mode")
    return errors


_VALIDATION_ERRORS = _validate_cases(_CASES)
if os.environ.get("SMOKE_CASES", "").strip():
    _CASES = [c for c in _CASES if c.get("case_name") in _SMOKE]
_CASE_IDS = [c.get("case_name", f"case_{i}") for i, c in enumerate(_CASES)]


def _period_end(period_start: str) -> str:
    year = int(period_start[:4])
    month = int(period_start[4:6])
    day = int(period_start[6:8])
    if day == 1:
        return f"{year:04d}{month:02d}15"
    last_day = calendar.monthrange(year, month)[1]
    return f"{year:04d}{month:02d}{last_day:02d}"


def _period_start_to_date(period_start: str) -> str:
    return f"{period_start[:4]}-{period_start[4:6]}-{period_start[6:8]}"


def _float_eq(a, b, tol=0.01) -> bool:
    try:
        return abs(float(a) - float(b)) < tol
    except (TypeError, ValueError):
        return False


def _history_map(case: dict) -> dict[str, float]:
    out = {}
    for item in (case.get("policy") or {}).get("history_salaries") or []:
        out[str(item["salary_period"])] = float(item["union_total_salary"])
    return out


def _setup_table1(db: MySQLUtils, case: dict):
    setup = case["setup"]
    anchor_id = case["anchor_id"]
    trade_id = str(case["trade_id"])
    period_start = case["period_start"]
    period_end = _period_end(period_start)
    db.switch_database("anchor_salary_2")
    if setup.get("zero_all_guild_period", False):
        db.update(
            "UPDATE anchor_work_statistic_5 "
            "SET receive_gift_count=0, on_seat_seconds=0, is_effective_day=0 "
            "WHERE trade_id=%s AND statistic_date >= %s AND statistic_date <= %s",
            (trade_id, period_start, period_end),
        )
    if setup.get("zero_all_period", False):
        db.update(
            "UPDATE anchor_work_statistic_5 "
            "SET receive_gift_count=0, on_seat_seconds=0, is_effective_day=0 "
            "WHERE anchor_id=%s AND statistic_date >= %s AND statistic_date <= %s",
            (anchor_id, period_start, period_end),
        )
    for item in setup.get("updates", []):
        date_str = str(item["statistic_date"])
        year = int(date_str[:4])
        db.update(
            "INSERT INTO anchor_work_statistic_5 "
            "  (year, anchor_id, statistic_date, receive_gift_count, on_seat_seconds, "
            "   is_effective_day, anchor_name, trade_id) "
            "VALUES (%s, %s, %s, %s, %s, %s, '', %s) "
            "ON DUPLICATE KEY UPDATE "
            "  receive_gift_count = VALUES(receive_gift_count), "
            "  on_seat_seconds    = VALUES(on_seat_seconds), "
            "  is_effective_day   = VALUES(is_effective_day), "
            "  trade_id           = VALUES(trade_id)",
            (
                year,
                anchor_id,
                item["statistic_date"],
                item["receive_gift_count"],
                item["on_seat_seconds"],
                item["is_effective_day"],
                trade_id,
            ),
        )


def _healthy_owner_template(db: MySQLUtils, trade_id: str):
    """优先克隆 salary_level>0 的公会长行；黑名单留下的全 0 空行不能当历史基准。"""
    src = db.select(
        "SELECT * FROM salary_expected_detail "
        "WHERE trade_id=%s AND is_trade_owner=1 AND salary_level>0 "
        "ORDER BY salary_period DESC LIMIT 1",
        (trade_id,),
    )
    if src:
        return src
    return db.select(
        "SELECT * FROM salary_expected_detail "
        "WHERE trade_id=%s AND is_trade_owner=1 ORDER BY salary_period DESC LIMIT 1",
        (trade_id,),
    )


def _upsert_history_salary(db: MySQLUtils, case: dict, period: str, amount: float) -> dict:
    """先查后改 union_total_salary；无行或空壳行则克隆有效公会长行。返回还原信息。"""
    trade_id = str(case["trade_id"])
    owner_id = str(case["anchor_id"])
    db.switch_database("operation_log")
    rows = db.select(
        "SELECT id, union_total_salary, salary_level FROM salary_expected_detail "
        "WHERE trade_id=%s AND salary_period=%s AND is_trade_owner=1 LIMIT 1",
        (trade_id, period),
    )
    if rows and float(rows[0].get("salary_level") or 0) > 0:
        original = rows[0]["union_total_salary"]
        db.update(
            "UPDATE salary_expected_detail SET union_total_salary=%s WHERE id=%s",
            (amount, rows[0]["id"]),
        )
        return {"action": "update", "id": rows[0]["id"], "original": original, "period": period}

    if rows:
        db.delete("DELETE FROM salary_expected_detail WHERE id=%s", (rows[0]["id"],))
        logger.info("[历史薪资] period=%s 原行为空壳(salary_level=0)，删除后按有效行克隆", period)

    src = _healthy_owner_template(db, trade_id)
    if not src:
        db.insert(
            "INSERT INTO salary_expected_detail "
            "(salary_period, payment_uid, payment_type, trade_id, anchor_id, "
            " is_trade_owner, union_total_salary) "
            "VALUES (%s, %s, 1, %s, %s, 1, %s)",
            (period, owner_id, trade_id, owner_id, amount),
        )
        new_rows = db.select(
            "SELECT id FROM salary_expected_detail "
            "WHERE trade_id=%s AND salary_period=%s AND is_trade_owner=1 LIMIT 1",
            (trade_id, period),
        )
        return {
            "action": "insert",
            "id": new_rows[0]["id"] if new_rows else None,
            "original": None,
            "period": period,
        }

    row = dict(src[0])
    cols = [c for c in row.keys() if c not in CLONE_SKIP]
    row["salary_period"] = period
    row["union_total_salary"] = amount
    row["payment_uid"] = owner_id
    row["anchor_id"] = owner_id
    placeholders = ", ".join(["%s"] * len(cols))
    col_sql = ", ".join(f"`{c}`" for c in cols)
    db.insert(
        f"INSERT INTO salary_expected_detail ({col_sql}) VALUES ({placeholders})",
        tuple(row[c] for c in cols),
    )
    new_rows = db.select(
        "SELECT id FROM salary_expected_detail "
        "WHERE trade_id=%s AND salary_period=%s AND is_trade_owner=1 LIMIT 1",
        (trade_id, period),
    )
    return {
        "action": "clone",
        "id": new_rows[0]["id"] if new_rows else None,
        "original": None,
        "period": period,
    }


def _confirm_start_date(period: str) -> str:
    return _period_start_to_date(period)


def _confirm_end_date(period: str) -> str:
    return _period_start_to_date(_period_end(period))


def _upsert_confirm_salary(db: MySQLUtils, case: dict, period: str, amount: float) -> dict:
    """先查后改 union_salary_detail.total_salary_payable（新政策历史基准）。"""
    trade_id = str(case["trade_id"])
    owner_id = str(case["anchor_id"])
    start = _confirm_start_date(period)
    db.switch_database("operation_log")
    rows = db.select(
        "SELECT id, total_salary_payable FROM union_salary_detail "
        "WHERE anchor_union_id=%s AND salary_start_date=%s LIMIT 1",
        (trade_id, start),
    )
    if rows:
        original = rows[0]["total_salary_payable"]
        db.update(
            "UPDATE union_salary_detail SET total_salary_payable=%s WHERE id=%s",
            (amount, rows[0]["id"]),
        )
        return {
            "table": "confirm",
            "action": "update",
            "id": rows[0]["id"],
            "original": original,
            "period": period,
        }

    tmpl = db.select(
        "SELECT * FROM union_salary_detail WHERE anchor_union_id=%s "
        "ORDER BY salary_start_date DESC LIMIT 1",
        (trade_id,),
    )
    if tmpl:
        row = dict(tmpl[0])
        cols = [c for c in row.keys() if c not in CLONE_SKIP]
        row["salary_start_date"] = start
        row["salary_end_date"] = _confirm_end_date(period)
        row["total_salary_payable"] = amount
        row["trade_uid"] = owner_id
        col_sql = ", ".join(f"`{c}`" for c in cols)
        placeholders = ", ".join(["%s"] * len(cols))
        db.insert(
            f"INSERT INTO union_salary_detail ({col_sql}) VALUES ({placeholders})",
            tuple(row[c] for c in cols),
        )
    else:
        db.insert(
            "INSERT INTO union_salary_detail "
            "(salary_start_date, salary_end_date, anchor_union_id, trade_uid, "
            " total_salary_payable, payment_type) "
            "VALUES (%s, %s, %s, %s, %s, 2)",
            (start, _confirm_end_date(period), trade_id, owner_id, amount),
        )
    new_rows = db.select(
        "SELECT id FROM union_salary_detail "
        "WHERE anchor_union_id=%s AND salary_start_date=%s LIMIT 1",
        (trade_id, start),
    )
    return {
        "table": "confirm",
        "action": "insert",
        "id": new_rows[0]["id"] if new_rows else None,
        "original": None,
        "period": period,
    }


def _zero_other_confirm_rows(db: MySQLUtils, case: dict, keep_periods: set[str]) -> list[dict]:
    """不满7 / 新公会：把未列入 history 的确认表行先置 0，避免环境里更高历史抢基准。"""
    trade_id = str(case["trade_id"])
    keep_dates = {_confirm_start_date(p) for p in keep_periods}
    db.switch_database("operation_log")
    rows = db.select(
        "SELECT id, total_salary_payable, salary_start_date FROM union_salary_detail "
        "WHERE anchor_union_id=%s",
        (trade_id,),
    ) or []
    metas = []
    current_start = _confirm_start_date(str(case["period_start"]))
    for row in rows:
        start = row["salary_start_date"]
        start_s = start.strftime("%Y-%m-%d") if hasattr(start, "strftime") else str(start)[:10]
        if start_s == current_start or start_s in keep_dates:
            continue
        original = row["total_salary_payable"]
        db.update(
            "UPDATE union_salary_detail SET total_salary_payable=%s WHERE id=%s",
            (0, row["id"]),
        )
        metas.append(
            {
                "table": "confirm",
                "action": "update",
                "id": row["id"],
                "original": original,
                "period": start_s.replace("-", ""),
            }
        )
        logger.info("[确认表清其它周期] id=%s date=%s original=%s → 0", row["id"], start_s, original)
    return metas


def _setup_history(db: MySQLUtils, case: dict) -> list[dict]:
    policy = case.get("policy") or {}
    history = policy.get("history_salaries") or []
    metas = []
    write_confirm = policy.get("write_confirm_history", True)
    write_table4 = policy.get("write_table4_history", True)
    replace_confirm = policy.get("replace_confirm_history", False)
    if replace_confirm and write_confirm:
        keep = {str(item["salary_period"]) for item in history}
        metas.extend(_zero_other_confirm_rows(db, case, keep))
    for item in history:
        period = str(item["salary_period"])
        amount = float(item["union_total_salary"])
        if write_table4:
            meta4 = _upsert_history_salary(db, case, period, amount)
            meta4["table"] = "table4"
            metas.append(meta4)
            logger.info(
                "[历史表4] period=%s union_total_salary=%s action=%s",
                period,
                amount,
                meta4["action"],
            )
        if write_confirm:
            metac = _upsert_confirm_salary(db, case, period, amount)
            metas.append(metac)
            logger.info(
                "[历史确认表] period=%s total_salary_payable=%s action=%s",
                period,
                amount,
                metac["action"],
            )
    return metas


def _teardown_history(db: MySQLUtils, metas: list[dict]):
    if not metas:
        return
    db.switch_database("operation_log")
    for meta in reversed(metas):
        if not meta.get("id"):
            continue
        table = meta.get("table") or "table4"
        if table == "confirm":
            if meta["action"] == "update" and meta.get("original") is not None:
                db.update(
                    "UPDATE union_salary_detail SET total_salary_payable=%s WHERE id=%s",
                    (meta["original"], meta["id"]),
                )
            elif meta["action"] == "insert":
                db.delete("DELETE FROM union_salary_detail WHERE id=%s", (meta["id"],))
            continue
        if meta["action"] == "update" and meta.get("original") is not None:
            db.update(
                "UPDATE salary_expected_detail SET union_total_salary=%s WHERE id=%s",
                (meta["original"], meta["id"]),
            )
        elif meta["action"] in ("insert", "clone"):
            db.delete("DELETE FROM salary_expected_detail WHERE id=%s", (meta["id"],))


def _clear_current_period_table4(db: MySQLUtils, case: dict) -> int:
    """MOA2 对已存在的表4行通常不再更新。先查后删本公会本周期行，才能写入本次造数后的应得薪资。"""
    db.switch_database("operation_log")
    trade_id = str(case["trade_id"])
    period = case["period_start"]
    existing = db.select(
        "SELECT id FROM salary_expected_detail WHERE trade_id=%s AND salary_period=%s",
        (trade_id, period),
    ) or []
    if existing:
        db.delete(
            "DELETE FROM salary_expected_detail WHERE trade_id=%s AND salary_period=%s",
            (trade_id, period),
        )
    n = len(existing)
    logger.info("[清表4] trade_id=%s period=%s deleted=%s", trade_id, period, n)
    return n


def _run_moa1(anchor_id: str, period_start: str):
    MoaUtils.moa_request(
        uri=MOA_URI, method="testUpdateSnapshotData", args=[anchor_id, period_start], env=MOA_ENV
    )
    time.sleep(MOA1_WAIT_SEC)


def _run_moa2(period_start: str):
    MoaUtils.moa_request(
        uri=MOA_URI, method="generateAnchorSalary", args=[period_start], env=MOA_ENV
    )
    time.sleep(MOA2_WAIT_SEC)


class _CheckCollector:
    def __init__(self, case_name: str):
        self.case_name = case_name
        self.rows: list[dict] = []

    def check(self, label: str, expected, actual, *, cause: str = ""):
        passed = _float_eq(actual, expected)
        self.rows.append(
            {"label": label, "expected": expected, "actual": actual, "passed": passed, "cause": cause}
        )
        msg = f"{self.case_name} | {label}: expected={expected}, actual={actual}"
        if passed:
            logger.info("  ✓ %s = %s", label, actual)
        else:
            AssertUtils.assert_and_log(False, msg + (f"；{cause}" if cause else ""))

    def check_bool(self, label: str, condition: bool, *, error_msg: str, cause: str = ""):
        self.rows.append(
            {
                "label": label,
                "expected": True,
                "actual": condition,
                "passed": condition,
                "cause": cause,
            }
        )
        if condition:
            logger.info("  ✓ %s", label)
        else:
            AssertUtils.assert_and_log(False, error_msg + (f"；{cause}" if cause else ""))


def _assert_table3(case: dict, row: dict, collector: _CheckCollector):
    exp = case.get("expected_t3") or {}
    for col in (
        "salary_level",
        "salary_coefficient",
        "coin_income",
        "effective_workday",
        "in_seattime",
        "anchor_salary_raw",
        "union_salary_raw",
        "anchor_salary_payable",
        "union_salary_payable",
        "total_salary_payable",
    ):
        if col not in exp:
            continue
        collector.check(f"表3.{col}", exp[col], row.get(col))


def _assert_motivation(case: dict, row4: dict, collector: _CheckCollector):
    policy = case["policy"]
    actual = row4.get("motivation_amount")
    if policy.get("expect_regular_no_award"):
        collector.check(
            "表4.motivation_amount（普通主播不得领取进步奖）",
            0.0,
            actual,
            cause="主播收-普通主播的应得薪资不含公会进步奖，motivation_amount 应为 0。",
        )
        return
    history = _history_map(case)
    current = float(row4.get("union_total_salary") or 0)
    mode = policy["baseline_mode"]
    base = baseline_from_history(mode, case["period_start"], history)
    expected = lookup_motivation(base, current)
    actual = row4.get("motivation_amount")
    collector.check(
        "表4.motivation_amount（按政策查表）",
        expected,
        actual,
        cause=(
            f"基准口径 {mode}，基准={base}，本周期 union_total_salary={current}，"
            f"增长={current - base}"
        ),
    )
    json_mot = (case.get("expected_t4") or {}).get("motivation_amount")
    isolated_total = (case.get("expected_t3") or {}).get("total_salary_payable")
    if json_mot is not None and isolated_total is not None and _float_eq(current, isolated_total):
        collector.check("表4.motivation_amount（孤立公会固定预期）", json_mot, actual)
    elif json_mot is not None and isolated_total is not None and not _float_eq(current, isolated_total):
        logger.warning(
            "[聚合口径] %s 本周期 union_total_salary=%s 与单人 total=%s 不同，"
            "固定 motivation=%s 不作为失败依据，已按实际薪资查表",
            case["case_name"],
            current,
            isolated_total,
            json_mot,
        )
    alt_mode = policy.get("assert_not_baseline_mode")
    if alt_mode:
        alt_base = baseline_from_history(alt_mode, case["period_start"], history)
        alt_expected = lookup_motivation(alt_base, current)
        if not _float_eq(expected, alt_expected):
            collector.check_bool(
                f"进步奖不得等于 {alt_mode} 口径（{alt_expected}）",
                not _float_eq(actual, alt_expected),
                error_msg=(
                    f"{case['case_name']} | 实际 motivation={actual} 与错误口径 {alt_mode} "
                    f"(基准={alt_base}) 查表 {alt_expected} 相同"
                ),
                cause="服务端可能用了错误的历史基准（上周期 vs 近6周期最高）。",
            )
        else:
            logger.warning(
                "[无法区分] %s 本周期薪资 %s 下 %s 与 %s 查表同为 %s，跳过反例断言",
                case["case_name"],
                current,
                mode,
                alt_mode,
                expected,
            )


def _assert_results(db: MySQLUtils, case: dict) -> dict:
    anchor_id = case["anchor_id"]
    period_start = case["period_start"]
    salary_start_date = _period_start_to_date(period_start)
    db.switch_database("operation_log")
    rows3 = db.select(
        "SELECT salary_level, salary_coefficient, coin_income, effective_workday, in_seattime, "
        "anchor_salary_raw, union_salary_raw, "
        "anchor_salary_payable, union_salary_payable, total_salary_payable "
        "FROM anchor_salary_detail WHERE anchor_id=%s AND salary_start_date=%s",
        (anchor_id, salary_start_date),
    )
    rows4 = db.select(
        "SELECT payment_type, is_trade_owner, salary_level, deduction_factor, "
        "union_total_salary, motivation_amount, expected_amount "
        "FROM salary_expected_detail WHERE salary_period=%s AND payment_uid=%s AND trade_id=%s",
        (period_start, anchor_id, str(case["trade_id"])),
    )
    collector = _CheckCollector(case["case_name"])
    collector.check_bool(
        "表3有数据",
        bool(rows3),
        error_msg=f"{case['case_name']} | 表3无数据",
        cause="MOA2 未写入 anchor_salary_detail。",
    )
    collector.check_bool(
        "表4有数据",
        bool(rows4),
        error_msg=f"{case['case_name']} | 表4无数据",
        cause="MOA2 未写入 salary_expected_detail。",
    )
    if rows3:
        _assert_table3(case, rows3[0], collector)
    if rows4:
        exp4 = case.get("expected_t4") or {}
        if "salary_level" in exp4:
            collector.check("表4.salary_level", exp4["salary_level"], rows4[0].get("salary_level"))
        if "deduction_factor" in exp4:
            collector.check("表4.deduction_factor", exp4["deduction_factor"], rows4[0].get("deduction_factor"))
        _assert_motivation(case, rows4[0], collector)
    row4 = rows4[0] if rows4 else {}
    row3 = rows3[0] if rows3 else {}
    return {
        "check_rows": collector.rows,
        "expected_amount": row4.get("motivation_amount"),
        "actual_amount": row4.get("motivation_amount"),
        "expected_total_payable": (case.get("expected_t3") or {}).get("total_salary_payable"),
        "actual_total_payable": row3.get("total_salary_payable"),
        "snapshots": {
            "salary_expected_detail": rows4 or [],
            "anchor_salary_detail": rows3 or [],
        },
    }


@pytest.mark.guild_progress_new
@pytest.mark.parametrize("case", _CASES, ids=_CASE_IDS)
def test_yaahlan_guild_progress_award(case):
    if _VALIDATION_ERRORS:
        pytest.fail("用例表校验未通过，中止执行:\n" + "\n".join(_VALIDATION_ERRORS))

    logger.info("=" * 60)
    logger.info("用例: %s", case.get("case_name"))
    logger.info("说明: %s", case.get("case_name_cn", ""))

    report = get_collector()
    case_start = time.time()
    steps_log = []
    assert_payload: dict = {}
    db = _get_db()
    history_meta: list[dict] = []
    status = "通过"
    failure_reason = None
    try:
        history_meta = _setup_history(db, case)
        steps_log.append(
            {"step": "历史基准", "result": f"写入/还原点 {len(history_meta)} 条（表4+确认表）"}
        )
        _setup_table1(db, case)
        steps_log.append({"step": "造数表1", "result": "已写入本周期收礼/时长"})
        _run_moa1(case["anchor_id"], case["period_start"])
        steps_log.append({"step": "MOA1", "result": "testUpdateSnapshotData 已调用"})
        deleted = _clear_current_period_table4(db, case)
        steps_log.append({"step": "清本周期表4", "result": f"删除 {deleted} 行后由 MOA2 重写"})
        _run_moa2(case["period_start"])
        steps_log.append({"step": "MOA2", "result": "generateAnchorSalary 已调用"})
        assert_payload = _assert_results(db, case)
    except AssertionError as e:
        status = "失败"
        failure_reason = str(e)
        raise
    except Exception as e:
        status = "失败"
        failure_reason = str(e)
        raise
    finally:
        duration_ms = int((time.time() - case_start) * 1000)
        if report.enabled:
            report.record_result(
                case,
                {
                    "status": status,
                    "duration_ms": duration_ms,
                    "remark": failure_reason,
                    "failure_reason": failure_reason,
                    "steps_log": steps_log,
                    **assert_payload,
                },
            )
        try:
            _teardown_history(db, history_meta)
        except Exception as te:
            logger.error("历史薪资还原失败: %s", te)
        db.disconnect()
