# -*- coding: utf-8 -*-
"""
Yaahlan 算薪 E2E 数据驱动测试。

执行流程（每条用例）：
  1. 造数  — 清零本周期记录 → 按用例 setup.updates 写入表1
  2. MOA1  — testUpdateSnapshotData：生成主播半月快照（表2）
  3. MOA2  — generateAnchorSalary：执行算薪，生成表3/表4
  4. 断言  — 对比表3(anchor_salary_detail)、表4(salary_expected_detail) 与 JSON 中的 expected_t3/expected_t4
             同时验证 expected_amount = union_total_salary + sub_trade_share + motivation_amount
                                        - union_prepayment - all_anchor_prepayment 公式正确

用例数据：data/salary/cycle_salary/yaahlan_cycle_salary_cases.json
"""
import calendar
import logging
import os
import sys
import time
from datetime import datetime, timezone, timedelta

import pytest

CASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.normpath(os.path.join(CASE_DIR, "../../.."))
sys.path.insert(0, PROJECT_ROOT)

from utils.assert_utils import AssertUtils
from utils.json_utils import JsonUtils
from utils.moa_utils import MoaUtils
from utils.mysql_utils import MySQLUtils
from utils.salary_report import get_collector

logger = logging.getLogger(__name__)

# ── 常量 ──────────────────────────────────────────────────────────────────────
DATA_SUBDIR = "salary/cycle_salary"
DEFAULT_CASES_JSON = "yaahlan_cycle_salary_cases.json"
MOA_URI = "/service/yaahlan-cms/anchor-salary-moa"
MOA_ENV = "alpha"
MOA1_WAIT_SEC = 3
MOA2_WAIT_SEC = 30


# ── .env 加载 ─────────────────────────────────────────────────────────────────
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


# ── 数据库连接 ────────────────────────────────────────────────────────────────
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


# ── 用例加载 ──────────────────────────────────────────────────────────────────
def _load_cases(json_name: str = DEFAULT_CASES_JSON):
    data = JsonUtils.jsonfile_to_dict(DATA_SUBDIR, json_name) or {}
    return data.get("cases") or []


_CASES = _load_cases()
_CASE_IDS = [c.get("case_name", f"case_{i}") for i, c in enumerate(_CASES)]


# ── 用例表校验 ────────────────────────────────────────────────────────────────
def _validate_cases(cases: list):
    required_keys = ["case_name", "anchor_id", "period_start", "setup", "expected_t3", "expected_t4"]
    errors = []
    for case in cases:
        for key in required_keys:
            if key not in case:
                errors.append(f"用例 [{case.get('case_name', '未知')}] 缺少必填字段: {key}")
        if "updates" not in case.get("setup", {}):
            errors.append(f"用例 [{case.get('case_name', '未知')}] setup 缺少 updates 字段")
    return errors


_VALIDATION_ERRORS = _validate_cases(_CASES)
if _VALIDATION_ERRORS:
    logger.error("【用例表校验未通过】:\n%s", "\n".join(_VALIDATION_ERRORS))


# ── 辅助：周期日期转换 ─────────────────────────────────────────────────────────
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


# ── Step 1：造数（写表1） ──────────────────────────────────────────────────────
def _setup_table1(db: MySQLUtils, case: dict):
    setup = case["setup"]
    anchor_id = case["anchor_id"]
    period_start = case["period_start"]
    period_end = _period_end(period_start)

    db.switch_database("anchor_salary_2")

    if setup.get("zero_all_period", False):
        db.update(
            "UPDATE anchor_work_statistic_5 "
            "SET receive_gift_count=0, on_seat_seconds=0, is_effective_day=0 "
            "WHERE anchor_id=%s AND statistic_date >= %s AND statistic_date <= %s",
            (anchor_id, period_start, period_end),
        )
        logger.info("[造数] 已清零 anchor_id=%s 周期 %s~%s 所有记录", anchor_id, period_start, period_end)

    for item in setup.get("updates", []):
        date_str = str(item["statistic_date"])
        year = int(date_str[:4])
        db.update(
            "INSERT INTO anchor_work_statistic_5 "
            "  (year, anchor_id, statistic_date, receive_gift_count, on_seat_seconds, is_effective_day, anchor_name, trade_id) "
            "VALUES (%s, %s, %s, %s, %s, %s, '', '') "
            "ON DUPLICATE KEY UPDATE "
            "  receive_gift_count = VALUES(receive_gift_count), "
            "  on_seat_seconds    = VALUES(on_seat_seconds), "
            "  is_effective_day   = VALUES(is_effective_day)",
            (
                year,
                anchor_id,
                item["statistic_date"],
                item["receive_gift_count"],
                item["on_seat_seconds"],
                item["is_effective_day"],
            ),
        )

    logger.info("[造数] anchor_id=%s 写入 %d 条记录完成", anchor_id, len(setup.get("updates", [])))


# ── Step 1b：首次主播豁免造数（修改 anchor_profile.create_time） ────────────────────
def _setup_join_time(db: MySQLUtils, case: dict):
    """
    若 setup.join_time_override 存在，将 anchor_profile.create_time 临时改为指定日期（YYYYMMDD），
    配合「首次成为主播 + 入职日期达标」触发豁免逻辑。返回原始 create_time 供 teardown 还原。
    """
    join_date_str = case.get("setup", {}).get("join_time_override")
    if not join_date_str:
        return None
    anchor_id = case["anchor_id"]
    db.switch_database("operation_log")
    rows = db.select(
        "SELECT create_time FROM anchor_profile WHERE user_id=%s AND state=1 LIMIT 1",
        (anchor_id,),
    )
    if not rows:
        logger.warning("[入职豁免] anchor_profile state=1 未找到 anchor_id=%s，跳过 join_time 设置", anchor_id)
        return None
    original_ts = rows[0]["create_time"]
    dt = datetime.strptime(join_date_str, "%Y%m%d").replace(
        hour=8, minute=0, second=0, tzinfo=timezone(timedelta(hours=8))
    )
    new_ts = int(dt.timestamp() * 1000)
    db.update(
        "UPDATE anchor_profile SET create_time=%s WHERE user_id=%s AND state=1",
        (new_ts, anchor_id),
    )
    logger.info(
        "[入职豁免] anchor_id=%s create_time: %s → %s (%s)",
        anchor_id, original_ts, new_ts, join_date_str,
    )
    return original_ts


def _teardown_join_time(db: MySQLUtils, anchor_id: str, original_ts):
    """还原 anchor_profile.create_time 到测试前的原始值。"""
    if original_ts is None:
        return
    db.switch_database("operation_log")
    db.update(
        "UPDATE anchor_profile SET create_time=%s WHERE user_id=%s AND state=1",
        (original_ts, anchor_id),
    )
    logger.info("[入职豁免还原] anchor_id=%s create_time 已还原为 %s", anchor_id, original_ts)


# ── Step 1c：预提造数 ──────────────────────────────────────────────────────────
def _setup_prepayment(db: MySQLUtils, case: dict) -> list[dict]:
    """
    若 setup.prepayment 或 setup.prepayments 存在，向 salary_prepayments 插入预提记录（先清同周期残留）。
    返回 [{user_id, period, prepayment_type}, ...] 供 teardown 清理，无需操作则返回 []。
    """
    setup = case.get("setup", {})
    prepayments = setup.get("prepayments")
    if not prepayments:
        single = setup.get("prepayment")
        prepayments = [single] if single else []
    if not prepayments:
        return []

    metas: list[dict] = []

    db.switch_database("gift_pack_dispatch")
    for prepayment in prepayments:
        user_id = str(prepayment["user_id"])
        prepayment_type = int(prepayment["prepayment_type"])
        trade_id = str(prepayment["trade_id"])
        period = int(prepayment["period"])
        credit_amount = int(prepayment["credit_amount"])
        append_without_delete = bool(prepayment.get("append_without_delete", False))
        if not append_without_delete:
            db.delete(
                "DELETE FROM salary_prepayments WHERE user_id=%s AND period=%s AND prepayment_type=%s",
                (user_id, period, prepayment_type),
            )
        db.insert(
            "INSERT INTO salary_prepayments (user_id, prepayment_type, trade_id, period, credit_amount) "
            "VALUES (%s, %s, %s, %s, %s)",
            (user_id, prepayment_type, trade_id, period, credit_amount),
        )
        logger.info(
            "[预提造数] 插入 user_id=%s type=%s period=%s credit_amount=%s",
            user_id, prepayment_type, period, credit_amount,
        )
        metas.append({"user_id": user_id, "period": period, "prepayment_type": prepayment_type})
    return metas


def _teardown_prepayment(db: MySQLUtils, prepayment_meta: list[dict]):
    """清理测试插入的预提记录，还原环境。"""
    if not prepayment_meta:
        return
    db.switch_database("gift_pack_dispatch")
    for meta in prepayment_meta:
        db.delete(
            "DELETE FROM salary_prepayments WHERE user_id=%s AND period=%s AND prepayment_type=%s",
            (meta["user_id"], meta["period"], meta["prepayment_type"]),
        )
        logger.info(
            "[预提清理] 已删除 user_id=%s period=%s type=%s",
            meta["user_id"], meta["period"], meta["prepayment_type"],
        )


# ── Step 2/3：执行 MOA ────────────────────────────────────────────────────────
def _run_moa1(anchor_id: str, period_start: str):
    logger.info("[MOA1] testUpdateSnapshotData anchor_id=%s period=%s", anchor_id, period_start)
    MoaUtils.moa_request(
        uri=MOA_URI, method="testUpdateSnapshotData", args=[anchor_id, period_start], env=MOA_ENV
    )
    logger.info("[MOA1] 完成，等待 %ds", MOA1_WAIT_SEC)
    time.sleep(MOA1_WAIT_SEC)


def _run_moa2(period_start: str):
    logger.info("[MOA2] generateAnchorSalary period=%s", period_start)
    MoaUtils.moa_request(
        uri=MOA_URI, method="generateAnchorSalary", args=[period_start], env=MOA_ENV
    )
    logger.info("[MOA2] 完成，等待 %ds", MOA2_WAIT_SEC)
    time.sleep(MOA2_WAIT_SEC)


# ── Step 4：断言 ──────────────────────────────────────────────────────────────
def _float_eq(a, b, tol=0.01) -> bool:
    try:
        return abs(float(a) - float(b)) < tol
    except (TypeError, ValueError):
        return False


class _CheckCollector:
    """收集逐项校验结果，供测试报告使用。"""

    def __init__(self, case_name: str):
        self.case_name = case_name
        self.rows: list[dict] = []
        self.errors: list[str] = []

    def check(self, label: str, expected, actual, *, cause: str = ""):
        passed = _float_eq(actual, expected)
        self.rows.append(
            {
                "label": label,
                "expected": expected,
                "actual": actual,
                "passed": passed,
                "cause": cause,
            }
        )
        msg = f"{self.case_name} | {label}: expected={expected}, actual={actual}"
        if passed:
            logger.info("  ✓ %s = %s", label, actual)
        else:
            self.errors.append(msg)
            AssertUtils.assert_and_log(False, msg)

    def check_bool(self, label: str, condition: bool, *, error_msg: str, cause: str = ""):
        self.rows.append(
            {
                "label": label,
                "expected": "有记录",
                "actual": "有记录" if condition else "无记录",
                "passed": condition,
                "cause": cause,
            }
        )
        if condition:
            logger.info("  ✓ %s", label)
        else:
            self.errors.append(error_msg)
            AssertUtils.assert_and_log(False, error_msg)


def _assert_table3(case: dict, row: dict, collector: _CheckCollector):
    exp = case["expected_t3"]
    field_map = {
        "salary_level": "salary_level",
        "salary_coefficient": "salary_coefficient",
        "coin_income": "coin_income",
        "effective_workday": "effective_workday",
        "in_seattime": "in_seattime",
        "anchor_salary_raw": "anchor_salary_raw",
        "union_salary_raw": "union_salary_raw",
        "anchor_salary_payable": "anchor_salary_payable",
        "union_salary_payable": "union_salary_payable",
        "total_salary_payable": "total_salary_payable",
    }
    for exp_key, col in field_map.items():
        if exp_key not in exp:
            continue
        actual = row.get(col)
        expected = exp[exp_key]
        cause = ""
        if col in ("salary_coefficient", "deduction_factor") and not _float_eq(actual, expected):
            cause = "扣减系数与预期不符；核对有效工作日、开播时长、等级/入职豁免。"
        collector.check(f"表3.{col}", expected, actual, cause=cause)


def _assert_table4(case: dict, row: dict, collector: _CheckCollector):
    exp = case["expected_t4"]
    field_map = {
        "salary_level": "salary_level",
        "deduction_factor": "deduction_factor",
        "coin_income": "coin_income",
        "work_hours": "work_hours",
        "work_days": "work_days",
        "anchor_salary": "anchor_salary",
        "union_commission": "union_commission",
        "union_total_salary": "union_total_salary",
        "union_prepayment": "union_prepayment",
        "anchor_prepayment": "anchor_prepayment",
        "all_anchor_prepayment": "all_anchor_prepayment",
    }
    for exp_key, col in field_map.items():
        if exp_key not in exp:
            continue
        actual = row.get(col)
        expected = exp[exp_key]
        collector.check(f"表4.{col}", expected, actual)

    # 验证 expected_amount 公式（按 payment_type / is_trade_owner 选择对应公式）
    # 场景1 payment_type=1 公会收:
    #        - is_trade_owner=1: union_total_salary + motivation + sub_trade_share - union_prepayment - all_anchor_prepayment
    #        - is_trade_owner=0: union_total_salary + motivation + sub_trade_share - union_prepayment - anchor_prepayment
    # 场景2 payment_type=2 is_trade_owner=1: union_commission + sub_trade_share + motivation + owner_anchor_salary - union_prepayment - anchor_prepayment
    # 场景3 payment_type=2 is_trade_owner=0: anchor_salary - anchor_prepayment
    case_name = case["case_name"]
    actual_expected_val = row.get("expected_amount")
    payment_type = int(row.get("payment_type") or 0)
    is_trade_owner_val = int(row.get("is_trade_owner") or 0)
    if actual_expected_val is not None:
        actual_expected = float(actual_expected_val)
        computed = None
        formula_desc = ""
        if payment_type == 1 and is_trade_owner_val == 1:
            keys = ["union_total_salary", "motivation_amount", "sub_trade_share",
                    "union_prepayment", "all_anchor_prepayment"]
            if all(row.get(k) is not None for k in keys):
                computed = (
                    float(row["union_total_salary"]) + float(row["motivation_amount"])
                    + float(row["sub_trade_share"]) - float(row["union_prepayment"])
                    - float(row["all_anchor_prepayment"])
                )
                formula_desc = (
                    f"union_total={row['union_total_salary']}, motivation={row['motivation_amount']}, "
                    f"sub_trade={row['sub_trade_share']}, union_pre={row['union_prepayment']}, "
                    f"anchor_pre_all={row['all_anchor_prepayment']}"
                )
        elif payment_type == 1 and is_trade_owner_val == 0:
            keys = ["union_total_salary", "motivation_amount", "sub_trade_share",
                    "union_prepayment", "anchor_prepayment"]
            if all(row.get(k) is not None for k in keys):
                computed = (
                    float(row["union_total_salary"]) + float(row["motivation_amount"])
                    + float(row["sub_trade_share"]) - float(row["union_prepayment"])
                    - float(row["anchor_prepayment"])
                )
                formula_desc = (
                    f"union_total={row['union_total_salary']}, motivation={row['motivation_amount']}, "
                    f"sub_trade={row['sub_trade_share']}, union_pre={row['union_prepayment']}, "
                    f"anchor_pre={row['anchor_prepayment']}"
                )
        elif payment_type == 2 and is_trade_owner_val == 1:
            keys = ["union_commission", "sub_trade_share", "motivation_amount",
                    "owner_anchor_salary", "union_prepayment", "anchor_prepayment"]
            if all(row.get(k) is not None for k in keys):
                computed = (
                    float(row["union_commission"]) + float(row["sub_trade_share"])
                    + float(row["motivation_amount"]) + float(row["owner_anchor_salary"])
                    - float(row["union_prepayment"]) - float(row["anchor_prepayment"])
                )
                formula_desc = (
                    f"union_commission={row['union_commission']}, sub_trade={row['sub_trade_share']}, "
                    f"motivation={row['motivation_amount']}, owner_anchor={row['owner_anchor_salary']}, "
                    f"union_pre={row['union_prepayment']}, anchor_pre={row['anchor_prepayment']}"
                )
        elif payment_type == 2 and is_trade_owner_val == 0:
            keys = ["anchor_salary", "anchor_prepayment"]
            if all(row.get(k) is not None for k in keys):
                computed = float(row["anchor_salary"]) - float(row["anchor_prepayment"])
                formula_desc = (
                    f"anchor_salary={row['anchor_salary']}, anchor_pre={row['anchor_prepayment']}"
                )
        if computed is not None:
            collector.check(
                f"表4.expected_amount 公式(payment_type={payment_type}, owner={is_trade_owner_val})",
                round(computed, 4),
                round(actual_expected, 4),
                cause="expected_amount 与 payment_type/is_trade_owner 对应公式不一致。",
            )


def _build_snapshots(db: MySQLUtils, case: dict) -> dict:
    anchor_id = case["anchor_id"]
    period_start = case["period_start"]
    period_end = _period_end(period_start)
    salary_start_date = _period_start_to_date(period_start)
    snapshots: dict = {}

    db.switch_database("anchor_salary_2")
    snapshots["anchor_work_statistic_5"] = db.select(
        "SELECT statistic_date, receive_gift_count, on_seat_seconds, is_effective_day "
        "FROM anchor_work_statistic_5 "
        "WHERE anchor_id=%s AND statistic_date >= %s AND statistic_date <= %s "
        "ORDER BY statistic_date",
        (anchor_id, period_start, period_end),
    ) or []

    db.switch_database("operation_log")
    snapshots["anchor_salary_detail"] = db.select(
        "SELECT salary_level, salary_coefficient, coin_income, effective_workday, in_seattime, "
        "anchor_salary_raw, union_salary_raw, anchor_salary_payable, union_salary_payable, total_salary_payable "
        "FROM anchor_salary_detail WHERE anchor_id=%s AND salary_start_date=%s",
        (anchor_id, salary_start_date),
    ) or []
    snapshots["salary_expected_detail"] = db.select(
        "SELECT payment_type, is_trade_owner, salary_level, deduction_factor, coin_income, work_hours, work_days, "
        "anchor_salary, union_commission, union_total_salary, union_prepayment, anchor_prepayment, "
        "all_anchor_prepayment, expected_amount "
        "FROM salary_expected_detail WHERE salary_period=%s AND payment_uid=%s",
        (period_start, anchor_id),
    ) or []

    setup = case.get("setup") or {}
    prepayments = setup.get("prepayments") or ([setup["prepayment"]] if setup.get("prepayment") else [])
    if prepayments:
        db.switch_database("gift_pack_dispatch")
        rows = []
        for prep in prepayments:
            rows.extend(
                db.select(
                    "SELECT user_id, prepayment_type, trade_id, period, credit_amount "
                    "FROM salary_prepayments WHERE user_id=%s AND period=%s AND prepayment_type=%s",
                    (str(prep["user_id"]), int(prep["period"]), int(prep["prepayment_type"])),
                )
                or []
            )
        snapshots["salary_prepayments"] = rows
    return snapshots


def _assert_results(db: MySQLUtils, case: dict) -> dict:
    anchor_id = case["anchor_id"]
    period_start = case["period_start"]
    salary_start_date = _period_start_to_date(period_start)

    db.switch_database("operation_log")

    rows3 = db.select(
        "SELECT salary_level, salary_coefficient, coin_income, effective_workday, in_seattime, "
        "anchor_salary_raw, union_salary_raw, total_salary_raw, "
        "anchor_salary_payable, union_salary_payable, total_salary_payable "
        "FROM anchor_salary_detail "
        "WHERE anchor_id=%s AND salary_start_date=%s",
        (anchor_id, salary_start_date),
    )

    rows4 = db.select(
        "SELECT payment_type, is_trade_owner, salary_level, deduction_factor, coin_income, work_hours, work_days, "
        "anchor_salary, union_commission, union_total_salary, owner_anchor_salary, "
        "sub_trade_share, motivation_amount, union_prepayment, "
        "anchor_prepayment, all_anchor_prepayment, expected_amount "
        "FROM salary_expected_detail "
        "WHERE salary_period=%s AND payment_uid=%s",
        (period_start, anchor_id),
    )

    case_name = case["case_name"]
    collector = _CheckCollector(case_name)
    collector.check_bool(
        "表3(anchor_salary_detail)有数据",
        len(rows3) > 0,
        error_msg=f"{case_name} | 表3(anchor_salary_detail)无数据，MOA可能未执行成功",
        cause="MOA2 未写入 anchor_salary_detail；检查 MOA 可达性与冷却锁。",
    )
    collector.check_bool(
        "表4(salary_expected_detail)有数据",
        len(rows4) > 0,
        error_msg=f"{case_name} | 表4(salary_expected_detail)无数据，MOA可能未执行成功",
        cause="MOA2 未写入 salary_expected_detail；检查 MOA 可达性与冷却锁。",
    )

    if rows3:
        _assert_table3(case, rows3[0], collector)
    if rows4:
        _assert_table4(case, rows4[0], collector)

    # 暴露口径差异：payment_type=2 且 is_trade_owner=1 时，
    # 表4.union_commission/union_total_salary 常为公会聚合口径，
    # 与表3单主播口径可能不一致。这里显式打日志，避免“静默放过”。
    if rows3 and rows4:
        row3 = rows3[0]
        row4 = rows4[0]
        payment_type = int(row4.get("payment_type") or 0)
        is_trade_owner = int(row4.get("is_trade_owner") or 0)
        if payment_type == 2 and is_trade_owner == 1:
            t3_union_single = row3.get("union_salary_payable")
            t3_total_single = row3.get("total_salary_payable")
            t4_union_agg = row4.get("union_commission")
            t4_total_agg = row4.get("union_total_salary")
            if (
                t3_union_single is not None and t4_union_agg is not None
                and not _float_eq(t3_union_single, t4_union_agg)
            ):
                logger.warning(
                    "[口径差异暴露] %s: 表4.union_commission 为聚合口径，"
                    "与表3单主播 union_salary_payable 不一致 "
                    "(t3.single=%s, t4.agg=%s)",
                    case.get("case_name"),
                    t3_union_single,
                    t4_union_agg,
                )
            if (
                t3_total_single is not None and t4_total_agg is not None
                and not _float_eq(t3_total_single, t4_total_agg)
            ):
                logger.warning(
                    "[口径差异暴露] %s: 表4.union_total_salary 为聚合口径，"
                    "与表3单主播 total_salary_payable 不一致 "
                    "(t3.single=%s, t4.agg=%s)",
                    case.get("case_name"),
                    t3_total_single,
                    t4_total_agg,
                )
        # payment_type=2 且 is_trade_owner=0 时，expected_amount 按 anchor_salary - anchor_prepayment 计算。
        # 这里对关键字段口径做显式暴露，避免异常被静默掩盖。
        if payment_type == 2 and is_trade_owner == 0:
            t3_anchor_single = row3.get("anchor_salary_payable")
            t4_anchor = row4.get("anchor_salary")
            t3_total_single = row3.get("total_salary_payable")
            t4_union_total = row4.get("union_total_salary")
            if (
                t3_anchor_single is not None and t4_anchor is not None
                and not _float_eq(t3_anchor_single, t4_anchor)
            ):
                logger.warning(
                    "[口径差异暴露] %s: 表4.anchor_salary 与表3单主播 anchor_salary_payable 不一致 "
                    "(t3.single=%s, t4=%s)",
                    case.get("case_name"),
                    t3_anchor_single,
                    t4_anchor,
                )
            if (
                t3_total_single is not None and t4_union_total is not None
                and not _float_eq(t3_total_single, t4_union_total)
            ):
                logger.warning(
                    "[口径差异暴露] %s: 表4.union_total_salary 与表3单主播 total_salary_payable 不一致 "
                    "(t3.single=%s, t4=%s)",
                    case.get("case_name"),
                    t3_total_single,
                    t4_union_total,
                )

    # 某些历史样本存在“系数字段未同步，但应发金额已按豁免全额发放”的服务口径不一致现象。
    # 对这类用例仅保留告警，不阻断执行（业务结果以 payable 为主断言）。
    if case.get("coefficient_mismatch_warn_only") and rows3 and rows4:
        row3 = rows3[0]
        row4 = rows4[0]
        coef_t3 = row3.get("salary_coefficient")
        factor_t4 = row4.get("deduction_factor")
        full_payable = (
            _float_eq(row3.get("anchor_salary_raw"), row3.get("anchor_salary_payable"))
            and _float_eq(row3.get("union_salary_raw"), row3.get("union_salary_payable"))
            and _float_eq(row3.get("total_salary_payable"), row4.get("union_total_salary"))
        )
        coeff_is_one = _float_eq(coef_t3, 1.0) and _float_eq(factor_t4, 1.0)
        if not coeff_is_one and full_payable:
            logger.warning(
                "[告警] %s 系数字段与金额口径不一致："
                "t3.salary_coefficient=%s, t4.deduction_factor=%s, "
                "但 payable 已全额发放(anchor=%s, union=%s, total=%s)",
                case.get("case_name"),
                coef_t3,
                factor_t4,
                row3.get("anchor_salary_payable"),
                row3.get("union_salary_payable"),
                row3.get("total_salary_payable"),
            )

    row4 = rows4[0] if rows4 else {}
    row3 = rows3[0] if rows3 else {}
    return {
        "check_rows": collector.rows,
        "expected_total_payable": (case.get("expected_t3") or {}).get("total_salary_payable"),
        "actual_total_payable": row3.get("total_salary_payable"),
        "expected_amount": (case.get("expected_t4") or {}).get("expected_amount", row4.get("expected_amount")),
        "actual_amount": row4.get("expected_amount"),
        "snapshots": _build_snapshots(db, case),
    }


# ── 主测试函数 ────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("case", _CASES, ids=_CASE_IDS)
def test_yaahlan_cycle_salary(case):
    """
    Yaahlan 算薪 E2E：造数(表1) → MOA1 → MOA2 → 断言(表3/表4)
    用例说明见 case_name_cn / scenario_desc / case_purpose
    """
    if _VALIDATION_ERRORS:
        pytest.fail("用例表校验未通过，中止执行:\n" + "\n".join(_VALIDATION_ERRORS))

    logger.info("=" * 60)
    logger.info("用例: %s", case.get("case_name"))
    logger.info("说明: %s", case.get("case_name_cn", ""))

    collector = get_collector()
    case_start = time.time()
    steps_log = []
    assert_payload: dict = {}
    db = _get_db()
    original_join_ts = None
    prepayment_meta = None
    status = "通过"
    failure_reason = None
    try:
        _setup_table1(db, case)
        original_join_ts = _setup_join_time(db, case)
        prepayment_meta = _setup_prepayment(db, case)
        _run_moa1(case["anchor_id"], case["period_start"])
        steps_log.append({"step": "MOA1", "result": "testUpdateSnapshotData 已调用"})
        pre_moa2_wait_sec = int(case.get("pre_moa2_wait_sec", 0) or 0)
        if pre_moa2_wait_sec > 0:
            logger.info("[MOA2前冷却等待] case=%s, wait=%ss", case.get("case_name"), pre_moa2_wait_sec)
            time.sleep(pre_moa2_wait_sec)
        _run_moa2(case["period_start"])
        steps_log.append({"step": "MOA2", "result": "generateAnchorSalary 已调用"})
        assert_payload = _assert_results(db, case)
        if case.get("rerun_moa2_and_reassert"):
            second_wait_sec = int(case.get("second_moa2_wait_sec", 0) or 0)
            if second_wait_sec > 0:
                logger.info("[二次MOA2前等待] case=%s, wait=%ss", case.get("case_name"), second_wait_sec)
                time.sleep(second_wait_sec)
            logger.info("[二次MOA2探针] case=%s 再次触发 generateAnchorSalary", case.get("case_name"))
            _run_moa2(case["period_start"])
            steps_log.append({"step": "MOA2-rerun", "result": "二次 generateAnchorSalary 已调用"})
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
        if collector.enabled:
            collector.record_result(
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
        _teardown_join_time(db, case["anchor_id"], original_join_ts)
        _teardown_prepayment(db, prepayment_meta)
        db.disconnect()
