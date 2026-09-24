# -*- coding: utf-8 -*-
"""用例表读取与套件发现。"""
from __future__ import annotations

from web.config import PROJECT_ROOT, SUITES, TestSuite, suite_by_id
from web.models import CaseSummary, SuiteDetail, SuiteSummary
from utils.json_utils import JsonUtils


def _load_suite_cases(suite: TestSuite) -> tuple[str, list[dict]]:
    data = JsonUtils.jsonfile_to_dict(suite.data_subdir, suite.cases_json) or {}
    description = str(data.get("description") or "")
    cases = data.get("cases") or []
    if not isinstance(cases, list):
        cases = []
    return description, cases


def list_suites() -> list[SuiteSummary]:
    items: list[SuiteSummary] = []
    for suite in SUITES:
        description, cases = _load_suite_cases(suite)
        items.append(
            SuiteSummary(
                id=suite.id,
                name=suite.name,
                cases_json=suite.cases_json,
                test_module=suite.test_module,
                case_count=len(cases),
                description=description.split("\n")[0] if description else "",
            )
        )
    return items


def get_suite_detail(suite_id: str) -> SuiteDetail | None:
    suite = suite_by_id(suite_id)
    if not suite:
        return None
    description, cases = _load_suite_cases(suite)
    case_items = [
        CaseSummary(
            case_name=str(c.get("case_name") or ""),
            case_name_cn=str(c.get("case_name_cn") or ""),
            case_name_en=str(c.get("case_name_en") or ""),
            scenario_desc=str(c.get("scenario_desc") or ""),
            case_purpose=str(c.get("case_purpose") or ""),
            anchor_id=str(c.get("anchor_id")) if c.get("anchor_id") is not None else None,
            period_start=str(c.get("period_start")) if c.get("period_start") is not None else None,
        )
        for c in cases
        if c.get("case_name")
    ]
    return SuiteDetail(
        id=suite.id,
        name=suite.name,
        cases_json=suite.cases_json,
        test_module=suite.test_module,
        case_count=len(case_items),
        description=description,
        cases=case_items,
    )


def validate_case_names(suite_id: str, case_names: list[str]) -> list[str]:
    """返回非法 case_name 列表；空列表表示全部合法。"""
    if not case_names:
        return []
    detail = get_suite_detail(suite_id)
    if not detail:
        return case_names
    known = {c.case_name for c in detail.cases}
    return [name for name in case_names if name not in known]


def pytest_node_id(suite: TestSuite, case_name: str) -> str:
    return f"{suite.test_module}::{suite.test_func}[{case_name}]"
