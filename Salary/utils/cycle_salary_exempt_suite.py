# -*- coding: utf-8 -*-
"""主播薪资豁免 E2E 套件：从主用例表按 suite 清单筛选 case。"""
from __future__ import annotations

from typing import Any

from utils.json_utils import JsonUtils

DATA_SUBDIR = "salary/cycle_salary"
MASTER_CASES_JSON = "yaahlan_cycle_salary_cases.json"
SUITE_JSON = "yaahlan_cycle_salary_exempt_suite.json"


def load_suite_manifest() -> dict[str, Any]:
    data = JsonUtils.jsonfile_to_dict(DATA_SUBDIR, SUITE_JSON) or {}
    if not data.get("case_names"):
        raise ValueError(f"套件 {SUITE_JSON} 缺少 case_names")
    return data


def _index_cases_by_name(cases: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for case in cases:
        name = case.get("case_name")
        if name:
            out[str(name)] = case
    return out


def load_suite_cases(*, smoke_only: bool = False) -> tuple[list[dict], dict[str, Any]]:
    """
    返回 (用例列表, 套件元数据)。用例顺序与 suite case_names 一致。
    smoke_only=True 时仅返回 smoke_cases 子集（顺序仍按 case_names 过滤）。
    """
    manifest = load_suite_manifest()
    master = JsonUtils.jsonfile_to_dict(DATA_SUBDIR, manifest.get("source_cases_json") or MASTER_CASES_JSON) or {}
    all_cases = master.get("cases") or []
    by_name = _index_cases_by_name(all_cases)

    wanted = list(manifest["case_names"])
    if smoke_only:
        smoke = set(manifest.get("smoke_cases") or [])
        wanted = [n for n in wanted if n in smoke]

    missing = [n for n in wanted if n not in by_name]
    if missing:
        raise ValueError(f"豁免套件引用的用例在主表不存在: {missing}")

    cases = [by_name[n] for n in wanted]
    meta = {
        "suite_id": manifest.get("suite_id", "cycle_salary_exempt"),
        "title": manifest.get("title", "Yaahlan 主播薪资豁免 E2E"),
        "description": manifest.get("description", ""),
        "source_cases_json": manifest.get("source_cases_json", MASTER_CASES_JSON),
        "suite_json": SUITE_JSON,
        "case_names": wanted,
        "smoke_cases": list(manifest.get("smoke_cases") or []),
        "execution_flow": manifest.get("execution_flow") or [],
    }
    return cases, meta


def validate_suite_against_master() -> list[str]:
    """校验套件清单与主表结构；返回错误列表（空表示通过）。"""
    errors: list[str] = []
    try:
        cases, _ = load_suite_cases()
    except ValueError as e:
        return [str(e)]

    required_keys = ["case_name", "anchor_id", "period_start", "setup", "expected_t3", "expected_t4"]
    for case in cases:
        for key in required_keys:
            if key not in case:
                errors.append(f"用例 [{case.get('case_name', '未知')}] 缺少必填字段: {key}")
        if "updates" not in case.get("setup", {}):
            errors.append(f"用例 [{case.get('case_name', '未知')}] setup 缺少 updates 字段")
    return errors
