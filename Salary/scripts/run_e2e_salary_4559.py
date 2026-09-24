#!/usr/bin/env python3
"""
E2E 验证脚本：修改表1数据 → 执行两个 MOA → 输出应得薪资表结果
anchor_id=4559, period=20260401 (上半月 2026-04-01 ~ 2026-04-15)

使用方式：
  1. 确认 .env 中已配置数据库连接信息（参考 .env.example）
  2. 在项目根目录执行：python scripts/run_e2e_salary_4559.py
"""
import logging
import os
import sys
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.normpath(os.path.join(SCRIPT_DIR, ".."))
sys.path.insert(0, PROJECT_ROOT)

from utils.moa_utils import MoaUtils
from utils.mysql_utils import MySQLUtils

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── 常量配置 ──────────────────────────────────────────────
ANCHOR_ID = "4559"
PERIOD_START = "20260401"
MOA_URI = "/service/yaahlan-cms/anchor-salary-moa"
MOA_ENV = "alpha"

# 本次造数内容
UPDATES = [
    {
        "statistic_date": "20260414",
        "receive_gift_count": 598765,
        "on_seat_seconds": 18000,
        "is_effective_day": 1,
    },
    {
        "statistic_date": "20260409",
        "receive_gift_count": 26789,
        "on_seat_seconds": 1710,
        "is_effective_day": 0,
    },
]


# ── 加载 .env ─────────────────────────────────────────────
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


def _get_db() -> MySQLUtils:
    host = os.environ.get("MYSQL_HOST", "")
    port = int(os.environ.get("MYSQL_PORT", "3306"))
    user = os.environ.get("MYSQL_USER", "")
    password = os.environ.get("MYSQL_PASSWORD", "")
    if not host or not user:
        logger.error("缺少 MYSQL_HOST / MYSQL_USER，请检查 .env 配置")
        sys.exit(1)
    db = MySQLUtils(host=host, port=port, user=user, password=password, database="anchor_salary_2")
    db.connect()
    if not db.connection:
        logger.error("数据库连接失败，请检查 .env 配置")
        sys.exit(1)
    return db


# ── Step 1：修改天级统计表 ──────────────────────────────────
def step1_update_table1(db: MySQLUtils):
    logger.info("=" * 55)
    logger.info("Step 1  修改 anchor_work_statistic_5")
    logger.info("=" * 55)
    db.switch_database("anchor_salary_2")

    for item in UPDATES:
        db.update(
            "UPDATE anchor_work_statistic_5 "
            "SET receive_gift_count=%s, on_seat_seconds=%s, is_effective_day=%s "
            "WHERE anchor_id=%s AND statistic_date=%s LIMIT 1",
            (
                item["receive_gift_count"],
                item["on_seat_seconds"],
                item["is_effective_day"],
                ANCHOR_ID,
                item["statistic_date"],
            ),
        )
        logger.info(
            "  已更新 statistic_date=%-10s  coins=%-8d  seconds=%-6d  effective=%d",
            item["statistic_date"],
            item["receive_gift_count"],
            item["on_seat_seconds"],
            item["is_effective_day"],
        )

    # 查询本周期全量天级数据，汇总用于后续预期值核对
    rows = db.select(
        "SELECT statistic_date, receive_gift_count, on_seat_seconds, is_effective_day "
        "FROM anchor_work_statistic_5 "
        "WHERE anchor_id=%s AND statistic_date >= 20260401 AND statistic_date <= 20260415 "
        "ORDER BY statistic_date",
        (ANCHOR_ID,),
    )

    total_coins = sum(r["receive_gift_count"] for r in rows)
    total_seconds = sum(r["on_seat_seconds"] for r in rows)
    total_effective_days = sum(r["is_effective_day"] for r in rows)
    total_hours = total_seconds / 3600

    logger.info("")
    logger.info("  本周期 (20260401-20260415) 全量天级汇总：")
    for r in rows:
        logger.info(
            "    date=%-10s  coins=%-8d  seconds=%-6d  effective=%d",
            r["statistic_date"],
            r["receive_gift_count"],
            r["on_seat_seconds"],
            r["is_effective_day"],
        )
    logger.info("  ─────────────────────────────────────────────")
    logger.info(
        "  合计 → 金币=%d, 开播=%.2fh, 有效工作日=%d天",
        total_coins,
        total_hours,
        total_effective_days,
    )
    return total_coins, total_hours, total_effective_days


# ── Step 2：MOA1 生成半月周期快照 ───────────────────────────
def step2_moa_snapshot():
    logger.info("")
    logger.info("=" * 55)
    logger.info("Step 2  MOA - testUpdateSnapshotData")
    logger.info("=" * 55)
    result = MoaUtils.moa_request(
        uri=MOA_URI,
        method="testUpdateSnapshotData",
        args=[ANCHOR_ID, PERIOD_START],
        env=MOA_ENV,
    )
    logger.info("  MOA 返回: %s", result)


# ── Step 3：MOA2 算薪 ──────────────────────────────────────
def step3_moa_salary():
    logger.info("")
    logger.info("=" * 55)
    logger.info("Step 3  MOA - generateAnchorSalary")
    logger.info("=" * 55)
    result = MoaUtils.moa_request(
        uri=MOA_URI,
        method="generateAnchorSalary",
        args=[PERIOD_START],
        env=MOA_ENV,
    )
    logger.info("  MOA 返回: %s", result)


# ── Step 4：查询并输出结果 ──────────────────────────────────
def step4_verify(db: MySQLUtils):
    logger.info("")
    logger.info("=" * 55)
    logger.info("Step 4  验证薪资结果")
    logger.info("=" * 55)
    db.switch_database("operation_log")

    # 表3：主播薪资明细
    rows3 = db.select(
        "SELECT salary_level, salary_coefficient, coin_income, "
        "effective_workday, in_seattime, "
        "anchor_salary_raw, union_salary_raw, total_salary_raw, "
        "anchor_salary_payable, union_salary_payable, total_salary_payable "
        "FROM anchor_salary_detail "
        "WHERE anchor_id=%s AND salary_start_date='2026-04-01'",
        (ANCHOR_ID,),
    )
    logger.info("  [表3] anchor_salary_detail:")
    if rows3:
        for row in rows3:
            for k, v in row.items():
                logger.info("    %-28s = %s", k, v)
    else:
        logger.warning("  表3 无数据，请确认 MOA 是否执行成功")

    # 表4：应得薪资明细
    rows4 = db.select(
        "SELECT payment_uid, payment_type, is_trade_owner, is_sub_trade, "
        "salary_level, deduction_factor, coin_income, work_hours, work_days, "
        "anchor_salary, union_commission, union_total_salary, "
        "sub_trade_share, motivation_amount, "
        "union_prepayment, anchor_prepayment, all_anchor_prepayment, "
        "expected_amount "
        "FROM salary_expected_detail "
        "WHERE salary_period=%s AND payment_uid=%s",
        (PERIOD_START, ANCHOR_ID),
    )
    logger.info("")
    logger.info("  [表4] salary_expected_detail:")
    if rows4:
        for row in rows4:
            for k, v in row.items():
                logger.info("    %-28s = %s", k, v)
    else:
        logger.warning("  表4 无数据，请确认 MOA 是否执行成功")

    return rows3, rows4


# ── Main ──────────────────────────────────────────────────
def main():
    db = _get_db()
    try:
        step1_update_table1(db)

        step2_moa_snapshot()
        logger.info("  等待 3s...")
        time.sleep(3)

        step3_moa_salary()
        logger.info("  等待 5s 后查询结果...")
        time.sleep(5)

        step4_verify(db)

        logger.info("")
        logger.info("脚本执行完毕，请核对 Step 4 输出与预期值是否一致。")
    finally:
        db.disconnect()


if __name__ == "__main__":
    main()
