# -*- coding: utf-8 -*-
"""Web 后台配置。"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WEB_DATA_DIR = PROJECT_ROOT / "web_data"
JOBS_DIR = WEB_DATA_DIR / "jobs"


@dataclass(frozen=True)
class TestSuite:
    id: str
    name: str
    data_subdir: str
    cases_json: str
    test_module: str
    test_func: str
    report_dir: str


SUITES: tuple[TestSuite, ...] = (
    TestSuite(
        id="cycle_salary",
        name="半月结算薪",
        data_subdir="salary/cycle_salary",
        cases_json="yaahlan_cycle_salary_cases.json",
        test_module="business_case/salary/cycle_salary/test_yaahlan_cycle_salary.py",
        test_func="test_yaahlan_cycle_salary",
        report_dir="docs/yaahlan_salary/cycle_salary/reports",
    ),
    TestSuite(
        id="refund_blacklist",
        name="退款黑名单算薪",
        data_subdir="salary/refund_blacklist",
        cases_json="yaahlan_refund_blacklist_salary_cases.json",
        test_module="business_case/salary/refund_blacklist/test_yaahlan_refund_blacklist_salary.py",
        test_func="test_yaahlan_refund_blacklist_salary",
        report_dir="docs/yaahlan_salary/refund_blacklist/reports",
    ),
    TestSuite(
        id="confirm_salary",
        name="确认应得薪资",
        data_subdir="salary/confirm_salary",
        cases_json="yaahlan_confirm_salary_cases.json",
        test_module="business_case/salary/confirm_salary/test_yaahlan_confirm_salary.py",
        test_func="test_yaahlan_confirm_salary",
        report_dir="docs/yaahlan_salary/confirm_salary/reports",
    ),
    TestSuite(
        id="guild_progress_award",
        name="公会进步奖",
        data_subdir="salary/guild_progress_award",
        cases_json="yaahlan_guild_progress_award_cases.json",
        test_module="business_case/salary/guild_progress_award/test_yaahlan_guild_progress_award.py",
        test_func="test_yaahlan_guild_progress_award",
        report_dir="docs/yaahlan_salary/guild_progress_award/reports",
    ),
)


def suite_by_id(suite_id: str) -> TestSuite | None:
    for suite in SUITES:
        if suite.id == suite_id:
            return suite
    return None


def dashboard_token() -> str:
    return (os.environ.get("DASHBOARD_TOKEN") or "").strip()


def dashboard_port() -> int:
    raw = (os.environ.get("DASHBOARD_PORT") or "8088").strip()
    try:
        return max(1024, min(65535, int(raw)))
    except ValueError:
        return 8088


def auth_required() -> bool:
    """未配置 token 时仅允许本机访问（开发模式）。"""
    return bool(dashboard_token())
