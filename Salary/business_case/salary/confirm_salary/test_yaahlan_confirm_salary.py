# -*- coding: utf-8 -*-
"""
确认应得薪资 E2E：表1 → MOA1 → MOA2 → 按区域确认 → 断言 union_salary_detail。

默认跳过（按大区写操作）。确认环境后：
  RUN_CONFIRM_BY_AREA=1 pytest business_case/salary/confirm_salary/test_yaahlan_confirm_salary.py -v

凭证：ADMIN_SSO_TOKEN + ADMIN_YAAHLAN_JWT，或 ~/.moa-call/gateway_credentials.json。
测完按本周期快照还原确认表。
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
from utils.cms_gateway import (
    ENV_RUN_CONFIRM,
    GatewayAuthError,
    confirm_by_area_enabled,
    confirm_salary_by_area,
    credentials_available,
)
from utils.json_utils import JsonUtils
from utils.moa_utils import MoaUtils
from utils.mysql_utils import MySQLUtils
from utils.salary_report import get_collector

logger = logging.getLogger(__name__)

DATA_SUBDIR = "salary/confirm_salary"
DEFAULT_CASES_JSON = "yaahlan_confirm_salary_cases.json"
MOA_URI = "/service/yaahlan-cms/anchor-salary-moa"
MOA_ENV = "alpha"
MOA1_WAIT_SEC = 3
MOA2_WAIT_SEC = 30
CONFIRM_ROW_WAIT_SEC = 30
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
    required = [
        "case_name",
        "anchor_id",
        "trade_id",
        "period_start",
        "setup",
        "expected_confirm",
    ]
    errors = []
    for case in cases:
        for key in required:
            if key not in case:
                errors.append(f"用例 [{case.get('case_name', '未知')}] 缺少必填字段: {key}")
        if "updates" not in case.get("setup", {}):
            errors.append(f"用例 [{case.get('case_name', '未知')}] setup 缺少 updates")
        confirm = case.get("confirm") or {}
        if not confirm.get("map_total_from_table4"):
            errors.append(f"用例 [{case.get('case_name', '未知')}] confirm 缺少 map_total_from_table4")
    return errors


_VALIDATION_ERRORS = _validate_cases(_CASES)
if _VALIDATION_ERRORS:
    logger.error("【用例表校验未通过】:\n%s", "\n".join(_VALIDATION_ERRORS))
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


def _date_str(value) -> str:
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    return str(value)[:10]


def _float_eq(a, b, tol=0.01) -> bool:
    try:
        return abs(float(a) - float(b)) < tol
    except (TypeError, ValueError):
        return False


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
            "  (year, anchor_id, statistic_date, receive_gift_count, on_seat_seconds, is_effective_day, anchor_name, trade_id) "
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


def _clear_current_period_table4(db: MySQLUtils, case: dict) -> int:
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
    return len(existing)


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


def _snapshot_confirm_period(db: MySQLUtils, start_date: str) -> dict[int, dict]:
    db.switch_database("operation_log")
    rows = db.select(
        "SELECT * FROM union_salary_detail WHERE salary_start_date=%s",
        (start_date,),
    ) or []
    out = {}
    for row in rows:
        out[int(row["id"])] = dict(row)
    return out


def _restore_confirm_period(db: MySQLUtils, start_date: str, snapshot: dict[int, dict]):
    db.switch_database("operation_log")
    current = db.select(
        "SELECT id FROM union_salary_detail WHERE salary_start_date=%s",
        (start_date,),
    ) or []
    current_ids = {int(r["id"]) for r in current}
    snap_ids = set(snapshot.keys())
    for new_id in current_ids - snap_ids:
        db.delete("DELETE FROM union_salary_detail WHERE id=%s", (new_id,))
        logger.info("[确认表还原] 删除本周期新增 id=%s", new_id)
    for row_id, original in snapshot.items():
        cols = [c for c in original.keys() if c not in CLONE_SKIP]
        if not cols:
            continue
        assignments = ", ".join(f"`{c}`=%s" for c in cols)
        db.update(
            f"UPDATE union_salary_detail SET {assignments} WHERE id=%s",
            tuple(original[c] for c in cols) + (row_id,),
        )
    logger.info("[确认表还原] 周期 %s 已按快照恢复 %s 行", start_date, len(snapshot))


class _CheckCollector:
    def __init__(self, case_name: str):
        self.case_name = case_name
        self.rows: list[dict] = []

    def check(self, label: str, expected, actual, *, cause: str = ""):
        if isinstance(expected, bool):
            passed = actual == expected
        elif isinstance(expected, str):
            passed = str(actual) == expected
        else:
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


def _api_success(result: dict) -> bool:
    if not isinstance(result, dict):
        return False
    if result.get("success") is True:
        return True
    if result.get("ec") in (0, "0") and result.get("success") is not False:
        return True
    return False


def _load_owner_table4(db: MySQLUtils, case: dict) -> dict:
    db.switch_database("operation_log")
    rows = db.select(
        "SELECT area, payment_type, is_trade_owner, salary_level, deduction_factor, "
        "union_total_salary, anchor_salary, union_commission, expected_amount, motivation_amount "
        "FROM salary_expected_detail "
        "WHERE salary_period=%s AND payment_uid=%s AND trade_id=%s AND is_trade_owner=1 "
        "LIMIT 1",
        (case["period_start"], case["anchor_id"], str(case["trade_id"])),
    ) or []
    return rows[0] if rows else {}


def _load_confirm_row(db: MySQLUtils, case: dict) -> dict:
    db.switch_database("operation_log")
    rows = db.select(
        "SELECT id, anchor_union_id, trade_uid, salary_start_date, "
        "total_salary_payable, anchor_salary_payable, union_salary_payable, payment_type "
        "FROM union_salary_detail "
        "WHERE anchor_union_id=%s AND salary_start_date=%s "
        "LIMIT 1",
        (str(case["trade_id"]), _period_start_to_date(case["period_start"])),
    ) or []
    return rows[0] if rows else {}


def _wait_confirm_row(db: MySQLUtils, case: dict, timeout_sec: int = CONFIRM_ROW_WAIT_SEC) -> dict:
    """确认接口常先返回 200，入库稍后才可见。"""
    deadline = time.time() + timeout_sec
    row = {}
    while time.time() < deadline:
        row = _load_confirm_row(db, case)
        if row:
            logger.info(
                "[确认表等待] 已读到 id=%s total_salary_payable=%s",
                row.get("id"),
                row.get("total_salary_payable"),
            )
            return row
        time.sleep(1)
    logger.warning(
        "[确认表等待] %ss 内未见公会 %s 周期 %s 行",
        timeout_sec,
        case["trade_id"],
        case["period_start"],
    )
    return row


def _assert_confirm(case: dict, table4: dict, confirm_row: dict, collector: _CheckCollector):
    cfg = case.get("confirm") or {}
    exp = case.get("expected_confirm") or {}
    collector.check_bool(
        "确认表有本公会本周期行",
        bool(confirm_row),
        error_msg=f"{case['case_name']} | 确认后 union_salary_detail 无行",
        cause="confirmSalaryByArea 未写入目标公会，或 salary_start_date 对不上。",
    )
    if not confirm_row:
        return
    total_field = cfg.get("map_total_from_table4", "union_total_salary")
    anchor_field = cfg.get("map_anchor_from_table4", "anchor_salary")
    union_field = cfg.get("map_union_from_table4", "union_commission")
    live_total = table4.get(total_field)
    live_anchor = table4.get(anchor_field)
    live_union = table4.get(union_field)
    collector.check(
        f"确认表.total_salary_payable = 表4.{total_field}",
        live_total,
        confirm_row.get("total_salary_payable"),
        cause="确认入库应写公会总薪资（主播+分成），不是含进步奖的 expected_amount。",
    )
    if live_anchor is not None:
        collector.check(
            f"确认表.anchor_salary_payable = 表4.{anchor_field}",
            live_anchor,
            confirm_row.get("anchor_salary_payable"),
        )
    if live_union is not None:
        collector.check(
            f"确认表.union_salary_payable = 表4.{union_field}",
            live_union,
            confirm_row.get("union_salary_payable"),
        )
    isolated = (case.get("expected_t4") or {}).get("union_total_salary")
    if isolated is not None and _float_eq(live_total, isolated):
        if "total_salary_payable" in exp:
            collector.check(
                "确认表.total_salary_payable（孤立公会固定预期）",
                exp["total_salary_payable"],
                confirm_row.get("total_salary_payable"),
            )
        if "anchor_salary_payable" in exp:
            collector.check(
                "确认表.anchor_salary_payable（孤立公会固定预期）",
                exp["anchor_salary_payable"],
                confirm_row.get("anchor_salary_payable"),
            )
        if "union_salary_payable" in exp:
            collector.check(
                "确认表.union_salary_payable（孤立公会固定预期）",
                exp["union_salary_payable"],
                confirm_row.get("union_salary_payable"),
            )
    collector.check(
        "确认表.anchor_union_id",
        str(case["trade_id"]),
        str(confirm_row.get("anchor_union_id") or ""),
    )
    collector.check(
        "确认表.trade_uid",
        str(case["anchor_id"]),
        str(confirm_row.get("trade_uid") or ""),
    )
    collector.check(
        "确认表.salary_start_date",
        _period_start_to_date(case["period_start"]),
        _date_str(confirm_row.get("salary_start_date")),
    )


def _assert_table4_setup(case: dict, table4: dict, collector: _CheckCollector):
    collector.check_bool(
        "表4会长行有数据",
        bool(table4),
        error_msg=f"{case['case_name']} | 表4无会长行，不能确认",
        cause="MOA2 未写入 salary_expected_detail。",
    )
    if not table4:
        return
    exp4 = case.get("expected_t4") or {}
    for col in ("salary_level", "deduction_factor", "union_total_salary", "anchor_salary", "union_commission"):
        if col in exp4:
            collector.check(f"表4.{col}", exp4[col], table4.get(col))
    collector.check_bool(
        "表4.area 非空（确认接口按大区）",
        bool(table4.get("area")),
        error_msg=f"{case['case_name']} | 表4.area 为空，无法调用 confirmSalaryByArea",
        cause="确认接口需要 area；运行时从表4会长行读取，不写死。",
    )


@pytest.mark.confirm_salary
@pytest.mark.parametrize("case", _CASES, ids=_CASE_IDS)
def test_yaahlan_confirm_salary(case):
    if _VALIDATION_ERRORS:
        pytest.fail("用例表校验未通过，中止执行:\n" + "\n".join(_VALIDATION_ERRORS))
    if not confirm_by_area_enabled():
        pytest.skip(
            "按区域确认会改写同区同周期所有公会的确认表。"
            f"确认测试环境后设置 {ENV_RUN_CONFIRM}=1 再跑。"
        )
    ready, why = credentials_available()
    if not ready:
        pytest.skip("缺少或已过期的后台凭证（sso-token + yaahlan-jwt）。\n" + why)

    logger.info("=" * 60)
    logger.info("用例: %s", case.get("case_name"))
    logger.info("说明: %s", case.get("case_name_cn", ""))

    report = get_collector()
    case_start = time.time()
    steps_log = []
    assert_payload: dict = {}
    db = _get_db()
    snapshot: dict[int, dict] | None = None
    start_date = _period_start_to_date(case["period_start"])
    status = "通过"
    failure_reason = None
    collector = _CheckCollector(case["case_name"])
    try:
        _setup_table1(db, case)
        steps_log.append({"step": "造数表1", "result": "已写入本周期收礼/时长"})
        _run_moa1(case["anchor_id"], case["period_start"])
        steps_log.append({"step": "MOA1", "result": "testUpdateSnapshotData 已调用"})
        deleted = _clear_current_period_table4(db, case)
        steps_log.append({"step": "清本周期表4", "result": f"删除 {deleted} 行后由 MOA2 重写"})
        _run_moa2(case["period_start"])
        steps_log.append({"step": "MOA2", "result": "generateAnchorSalary 已调用"})
        table4 = _load_owner_table4(db, case)
        _assert_table4_setup(case, table4, collector)
        area = table4.get("area")
        snapshot = _snapshot_confirm_period(db, start_date)
        steps_log.append(
            {"step": "确认表快照", "result": f"周期 {start_date} 备份 {len(snapshot)} 行"}
        )
        repeat = int((case.get("confirm") or {}).get("repeat") or 1)
        last_result = None
        for i in range(repeat):
            last_result = confirm_salary_by_area(case["period_start"], area)
            ok = _api_success(last_result)
            logger.info("[确认接口] area=%s 第%s次 result=%s", area, i + 1, last_result)
            steps_log.append(
                {
                    "step": f"MOA3 确认第{i + 1}次",
                    "result": f"area={area} success={ok} ec={last_result.get('ec')} body={last_result}",
                }
            )
            if i == 0 and not ok:
                AssertUtils.assert_and_log(
                    False,
                    f"{case['case_name']} | 第一次确认失败：{last_result}",
                )
            if i > 0 and not ok:
                logger.warning("重复确认接口未返回 success，继续按确认表金额断言: %s", last_result)
            confirm_row = _wait_confirm_row(db, case)
            _assert_confirm(case, table4, confirm_row, collector)
        assert_payload = {
            "check_rows": collector.rows,
            "expected_total_payable": (case.get("expected_confirm") or {}).get("total_salary_payable"),
            "actual_total_payable": (_load_confirm_row(db, case) or {}).get("total_salary_payable"),
            "snapshots": {
                "salary_expected_detail": [table4] if table4 else [],
                "union_salary_detail": [_load_confirm_row(db, case)] if _load_confirm_row(db, case) else [],
                "confirm_api": last_result,
            },
        }
    except AssertionError as e:
        status = "失败"
        failure_reason = str(e)
        raise
    except GatewayAuthError as e:
        status = "失败"
        failure_reason = str(e)
        pytest.skip("确认过程中凭证失效。\n" + str(e))
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
        if snapshot is not None:
            try:
                _restore_confirm_period(db, start_date, snapshot)
            except Exception as te:
                logger.error("确认表还原失败: %s", te)
        db.disconnect()
