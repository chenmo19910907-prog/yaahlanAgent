# -*- coding: utf-8 -*-
"""
Yaahlan 退款黑名单算薪影响 E2E 数据驱动测试。

执行流程（每条用例）：
  1. 造数     — 清零本周期表1记录 → 按 setup.updates 写入表1
  2. 黑名单   — 按 setup.blacklist 写入 operation_log.refund_blacklist
  3. MOA1     — testUpdateSnapshotData：生成主播半月快照（表2）
  4. MOA2     — generateAnchorSalary：执行算薪，生成表3/表4
  5. 断言     — 对比表3(anchor_salary_detail) 与 expected_t3
               按 expected_t4_exists 判断表4(salary_expected_detail) 是否应有记录：
                 expected_t4_exists=false → 断言表4无记录（黑名单过滤生效）
                 expected_t4_exists=true  → 断言表4有记录并校验字段值
  6. Teardown — 将 refund_blacklist 对应记录 status 改为 0（移出），还原环境

用例数据：data/salary/refund_blacklist/yaahlan_refund_blacklist_salary_cases.json
"""
import logging
import os
import sys
import time
import calendar

import pytest

CASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.normpath(os.path.join(CASE_DIR, "../../.."))
sys.path.insert(0, PROJECT_ROOT)

from utils.assert_utils import AssertUtils
from utils.json_utils import JsonUtils
from utils.moa_utils import MoaUtils
from utils.mysql_utils import MySQLUtils

logger = logging.getLogger(__name__)

# ── 常量 ──────────────────────────────────────────────────────────────────────
DATA_SUBDIR = "salary/refund_blacklist"
DEFAULT_CASES_JSON = "yaahlan_refund_blacklist_salary_cases.json"
MOA_URI = "/service/yaahlan-cms/anchor-salary-moa"
MOA_ENV = "alpha"
MOA1_WAIT_SEC = 3
MOA2_WAIT_SEC = 30

BLACKLIST_DB = "operation_log"
BLACKLIST_TABLE = "refund_blacklist"


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
    required_keys = ["case_name", "anchor_id", "period_start", "setup", "expected_t3"]
    errors = []
    for case in cases:
        for key in required_keys:
            if key not in case:
                errors.append(f"用例 [{case.get('case_name', '未知')}] 缺少必填字段: {key}")
        if "updates" not in case.get("setup", {}):
            errors.append(f"用例 [{case.get('case_name', '未知')}] setup 缺少 updates 字段")
        if "blacklist" not in case.get("setup", {}):
            errors.append(f"用例 [{case.get('case_name', '未知')}] setup 缺少 blacklist 字段")
        if "expected_t4_exists" not in case:
            errors.append(f"用例 [{case.get('case_name', '未知')}] 缺少 expected_t4_exists 字段")
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
        logger.info("[造数] 已清零 anchor_id=%s 周期 %s~%s", anchor_id, period_start, period_end)

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
                year, anchor_id, item["statistic_date"],
                item["receive_gift_count"], item["on_seat_seconds"], item["is_effective_day"],
            ),
        )

    logger.info("[造数] anchor_id=%s 写入 %d 条记录完成", anchor_id, len(setup.get("updates", [])))


# ── Step 2：黑名单造数 ────────────────────────────────────────────────────────
def _setup_blacklist(db: MySQLUtils, case: dict) -> dict | None:
    """
    按 setup.blacklist 往 operation_log.refund_blacklist 写入记录（先查后改，幂等处理）。
    返回黑名单配置 dict 供 teardown 使用，无配置时返回 None。
    """
    bl = case.get("setup", {}).get("blacklist")
    if not bl:
        return None

    user_id = str(bl["user_id"])
    source_type = int(bl["source_type"])
    reason = str(bl.get("reason", "测试用例造数"))
    status = int(bl.get("status", 1))

    db.switch_database(BLACKLIST_DB)

    rows = db.select(
        f"SELECT id, active_status FROM {BLACKLIST_TABLE} WHERE user_id=%s LIMIT 1",
        (user_id,),
    )

    if rows:
        db.update(
            f"UPDATE {BLACKLIST_TABLE} SET source_type=%s, reason=%s, active_status=%s, "
            f"removed_at=CASE WHEN %s=0 THEN UNIX_TIMESTAMP()*1000 ELSE 0 END, "
            f"removed_by=CASE WHEN %s=0 THEN 'test_teardown' ELSE '' END "
            f"WHERE user_id=%s",
            (source_type, reason, status, status, status, user_id),
        )
        logger.info("[黑名单造数] UPDATE user_id=%s source_type=%s active_status=%s", user_id, source_type, status)
    else:
        db.insert(
            f"INSERT INTO {BLACKLIST_TABLE} "
            f"(user_id, source_type, reason, active_status, create_time, update_time) "
            f"VALUES (%s, %s, %s, %s, NOW(), NOW())",
            (user_id, source_type, reason, status),
        )
        logger.info("[黑名单造数] INSERT user_id=%s source_type=%s active_status=%s", user_id, source_type, status)

    return bl


def _teardown_blacklist(db: MySQLUtils, bl: dict | None):
    """将黑名单记录 status 改回 0（已移出），避免污染后续用例。"""
    if not bl:
        return
    user_id = str(bl["user_id"])
    db.switch_database(BLACKLIST_DB)
    db.update(
        f"UPDATE {BLACKLIST_TABLE} SET active_status=0, "
        f"removed_at=UNIX_TIMESTAMP()*1000, removed_by='test_teardown' "
        f"WHERE user_id=%s",
        (user_id,),
    )
    logger.info("[黑名单清理] user_id=%s active_status 已还原为 0", user_id)


# ── Step 3/4：执行 MOA ────────────────────────────────────────────────────────
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


# ── Step 5：断言 ──────────────────────────────────────────────────────────────
def _float_eq(a, b, tol=0.01) -> bool:
    try:
        return abs(float(a) - float(b)) < tol
    except (TypeError, ValueError):
        return False


def _assert_table3(case: dict, row: dict):
    case_name = case["case_name"]
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
        AssertUtils.assert_and_log(
            _float_eq(actual, expected),
            f"{case_name} | 表3.{col}: expected={expected}, actual={actual}",
            f"  ✓ 表3.{col} = {actual}",
        )


def _assert_results(db: MySQLUtils, case: dict):
    anchor_id = case["anchor_id"]
    period_start = case["period_start"]
    salary_start_date = _period_start_to_date(period_start)
    case_name = case["case_name"]
    expected_t4_exists = case.get("expected_t4_exists", True)

    db.switch_database(BLACKLIST_DB)

    rows3 = db.select(
        "SELECT salary_level, salary_coefficient, coin_income, effective_workday, in_seattime, "
        "anchor_salary_raw, union_salary_raw, total_salary_raw, "
        "anchor_salary_payable, union_salary_payable, total_salary_payable "
        "FROM anchor_salary_detail "
        "WHERE anchor_id=%s AND salary_start_date=%s",
        (anchor_id, salary_start_date),
    )

    rows4 = db.select(
        "SELECT payment_type, is_trade_owner, salary_level, deduction_factor, coin_income, "
        "work_hours, work_days, anchor_salary, union_commission, union_total_salary, "
        "sub_trade_share, motivation_amount, union_prepayment, "
        "anchor_prepayment, all_anchor_prepayment, expected_amount "
        "FROM salary_expected_detail "
        "WHERE salary_period=%s AND payment_uid=%s",
        (period_start, anchor_id),
    )

    # ── 表3 断言：黑名单不影响主播粒度薪资计算，应有记录 ──────────────────────
    AssertUtils.assert_and_log(
        len(rows3) > 0,
        f"{case_name} | 表3(anchor_salary_detail)无数据，MOA可能未执行成功",
        "  ✓ 表3有数据",
    )
    if rows3:
        _assert_table3(case, rows3[0])

    # ── 表4 断言：按 expected_t4_exists 判断 ────────────────────────────────
    if not expected_t4_exists:
        AssertUtils.assert_and_log(
            len(rows4) == 0,
            f"{case_name} | 【黑名单过滤失效】表4(salary_expected_detail)不应有记录，"
            f"但查到 {len(rows4)} 条（payment_uid={anchor_id}, salary_period={period_start}）",
            f"  ✓ 表4无记录（退款黑名单过滤生效）",
        )
    else:
        exp_t4 = case.get("expected_t4") or {}
        AssertUtils.assert_and_log(
            len(rows4) > 0,
            f"{case_name} | 表4(salary_expected_detail)无数据，已移出黑名单应恢复正常",
            "  ✓ 表4有数据（黑名单移出后恢复正常）",
        )
        if rows4 and exp_t4:
            row4 = rows4[0]
            field_map = {
                "salary_level": "salary_level",
                "deduction_factor": "deduction_factor",
                "coin_income": "coin_income",
                "work_hours": "work_hours",
                "work_days": "work_days",
                "anchor_salary": "anchor_salary",
                "union_commission": "union_commission",
                "union_total_salary": "union_total_salary",
            }
            for exp_key, col in field_map.items():
                if exp_key not in exp_t4:
                    continue
                actual = row4.get(col)
                expected = exp_t4[exp_key]
                AssertUtils.assert_and_log(
                    _float_eq(actual, expected),
                    f"{case_name} | 表4.{col}: expected={expected}, actual={actual}",
                    f"  ✓ 表4.{col} = {actual}",
                )


# ── 主测试函数 ────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("case", _CASES, ids=_CASE_IDS)
def test_yaahlan_refund_blacklist_salary(case):
    """
    Yaahlan 退款黑名单算薪影响 E2E：
    造数(表1) → 写黑名单 → MOA1 → MOA2 → 断言(表3有/表4按expected_t4_exists判断)
    用例说明见 case_name_cn / scenario_desc / case_purpose
    """
    if _VALIDATION_ERRORS:
        pytest.fail("用例表校验未通过，中止执行:\n" + "\n".join(_VALIDATION_ERRORS))

    logger.info("=" * 60)
    logger.info("用例: %s", case.get("case_name"))
    logger.info("说明: %s", case.get("case_name_cn", ""))
    logger.info("黑名单: user_id=%s source_type=%s status=%s",
                case.get("setup", {}).get("blacklist", {}).get("user_id"),
                case.get("setup", {}).get("blacklist", {}).get("source_type"),
                case.get("setup", {}).get("blacklist", {}).get("status"))
    logger.info("表4期望: %s", "无记录（黑名单过滤）" if not case.get("expected_t4_exists") else "有记录")

    db = _get_db()
    blacklist_meta = None
    try:
        _setup_table1(db, case)
        blacklist_meta = _setup_blacklist(db, case)
        _run_moa1(case["anchor_id"], case["period_start"])
        _run_moa2(case["period_start"])
        _assert_results(db, case)
    finally:
        _teardown_blacklist(db, blacklist_meta)
        db.disconnect()
