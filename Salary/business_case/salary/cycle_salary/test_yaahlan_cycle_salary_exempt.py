# -*- coding: utf-8 -*-
"""
Yaahlan 主播薪资豁免 E2E（独立套件）。

与半月结主流程相同：造数(表1) → MOA1 → MOA2 → 断言(表3/表4)。
用例范围：data/salary/cycle_salary/yaahlan_cycle_salary_exempt_suite.json
用例数据：data/salary/cycle_salary/yaahlan_cycle_salary_cases.json（按套件名筛选）

入口：
  scripts/run_cycle_salary_exempt_with_report.sh
  scripts/run_cycle_salary_exempt_smoke.sh
  pytest business_case/salary/cycle_salary/test_yaahlan_cycle_salary_exempt.py
"""
from __future__ import annotations

import logging
import os
import sys

import pytest

CASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.normpath(os.path.join(CASE_DIR, "../../.."))
sys.path.insert(0, PROJECT_ROOT)

import business_case.salary.cycle_salary.test_yaahlan_cycle_salary as _cycle_salary_e2e  # noqa: E402
from utils.cycle_salary_exempt_suite import load_suite_cases  # noqa: E402

logger = logging.getLogger(__name__)

_SMOKE_ONLY = os.environ.get("CYCLE_SALARY_EXEMPT_SMOKE", "").strip().lower() in (
    "1",
    "true",
    "yes",
)
_CASES, _SUITE_META = load_suite_cases(smoke_only=_SMOKE_ONLY)
_CASE_IDS = [c.get("case_name", f"case_{i}") for i, c in enumerate(_CASES)]

from utils.cycle_salary_exempt_suite import validate_suite_against_master  # noqa: E402

_VALIDATION_ERRORS = validate_suite_against_master()
if _VALIDATION_ERRORS:
    logger.error("【豁免套件校验未通过】:\n%s", "\n".join(_VALIDATION_ERRORS))


@pytest.mark.parametrize("case", _CASES, ids=_CASE_IDS)
def test_yaahlan_cycle_salary_exempt(case):
    """
    主播豁免专项：等级豁免 + 首次主播豁免（含负向、切点、跨周期、公会长 smoke）。
    套件说明见 yaahlan_cycle_salary_exempt_suite.json
    """
    if _VALIDATION_ERRORS:
        pytest.fail("豁免套件校验未通过，中止执行:\n" + "\n".join(_VALIDATION_ERRORS))
    _cycle_salary_e2e.test_yaahlan_cycle_salary(case)
