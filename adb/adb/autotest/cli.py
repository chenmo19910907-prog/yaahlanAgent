"""autotest 子命令实现。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..device import require_device
from ..screenshot import screenshot_dir
from .executor import execute_case, execute_suite
from .generate import build_case_template, write_case_file
from .loader import (
    list_case_ids,
    list_requirements_summary,
    list_suites_summary,
    load_case,
    load_registry,
    normalize_requirement_id,
)
from .paths import REPORT_HTML_PATH, REPORT_JSON_PATH, REPORT_META_PATH, REPORTS_DIR
from .report import write_report


def _emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def cmd_list(
    *,
    suite_id: str | None,
    requirement_id: str | None,
    priority: str | None,
) -> int:
    if suite_id:
        case_ids = list_case_ids(suite_id=suite_id)
        _emit({"suite": suite_id, "cases": case_ids})
        return 0
    if requirement_id and not priority:
        norm_id = normalize_requirement_id(requirement_id)
        req = None
        for item in list_requirements_summary():
            if normalize_requirement_id(str(item.get("id") or "")) == norm_id:
                req = item
                break
        if req:
            _emit(
                {
                    "requirement": req,
                    "suites": list_suites_summary(requirement_id=requirement_id),
                }
            )
            return 0
    payload: dict[str, Any] = {
        "suites": list_suites_summary(
            requirement_id=requirement_id,
            priority=priority,
        )
    }
    requirements = list_requirements_summary()
    if requirements:
        payload["requirements"] = requirements
    if requirement_id or priority:
        payload["cases"] = list_case_ids(
            requirement_id=requirement_id,
            priority=priority,
        )
    _emit(payload)
    return 0


def cmd_map(*, requirement_id: str, priority: str | None) -> int:
    registry = load_registry(requirement_id)
    cases = registry.get("cases")
    if not isinstance(cases, list):
        cases = []
    priority_set = None
    if priority:
        priority_set = {p.strip().upper() for p in priority.split(",") if p.strip()}
    filtered = []
    for item in cases:
        if not isinstance(item, dict):
            continue
        if priority_set and str(item.get("priority", "")).upper() not in priority_set:
            continue
        filtered.append(item)
    summary = registry.get("summary") if isinstance(registry.get("summary"), dict) else {}
    _emit(
        {
            "requirementId": registry.get("requirementId"),
            "name": registry.get("name"),
            "totalPoints": registry.get("totalPoints"),
            "summary": summary,
            "filteredCount": len(filtered),
            "cases": filtered,
        }
    )
    return 0


def cmd_show(*, case_id: str) -> int:
    case = load_case(case_id)
    case.pop("_resolvedAccount", None)
    _emit(case)
    return 0


def cmd_run(
    *,
    case_id: str | None,
    suite_id: str | None,
    requirement_id: str | None,
    priority: str | None,
    serial: str | None,
    screenshot_dir_arg: Path | None,
    max_screenshots: int,
    force_script: bool,
    prd_ref: str,
) -> int:
    device = require_device(serial)
    shot_dir = screenshot_dir(screenshot_dir_arg)

    if case_id:
        result = execute_case(
            case_id=case_id,
            serial=device,
            shot_dir=shot_dir,
            max_screenshots=max_screenshots,
            force_script=force_script,
        )
        run_payload = result
    elif suite_id or requirement_id:
        case_ids = list_case_ids(
            suite_id=suite_id,
            requirement_id=requirement_id,
            priority=priority,
        )
        if not case_ids:
            raise ValueError("筛选结果为空，请检查 --suite / --requirement / --priority")
        suites = list_suites_summary(
            requirement_id=requirement_id,
            priority=priority,
        )
        suite_name = suite_id or requirement_id or "batch"
        suite_key = suite_id
        if not suite_key and requirement_id:
            suite_key = requirement_id
            for suite in suites:
                if len(suites) == 1:
                    suite_name = str(suite.get("name") or requirement_id)
                    break
            if priority:
                suite_name = f"{requirement_id} ({priority})"
        else:
            for suite in suites:
                if suite.get("id") == suite_id:
                    suite_name = str(suite.get("name") or suite_id)
                    break
        run_payload = execute_suite(
            case_ids=case_ids,
            serial=device,
            shot_dir=shot_dir,
            max_screenshots=max_screenshots,
            force_script=force_script,
            suite_id=suite_key,
            suite_name=suite_name,
        )
    else:
        raise ValueError("须指定 --case、--suite 或 --requirement")

    report = write_report(
        run_result=run_payload,
        meta={"prdRef": prd_ref} if prd_ref else {},
    )
    _emit(
        {
            "status": report.get("status"),
            "summary": report.get("summary"),
            "report": report,
        }
    )
    return 0 if run_payload.get("passed") else 3


def cmd_report(*, latest: bool, report_dir: Path | None) -> int:
    if latest:
        if REPORT_META_PATH.is_file():
            meta = json.loads(REPORT_META_PATH.read_text(encoding="utf-8"))
            _emit(meta)
            return 0
        if REPORT_JSON_PATH.is_file():
            _emit(
                {
                    "json": str(REPORT_JSON_PATH.resolve()),
                    "html": str(REPORT_HTML_PATH.resolve()),
                }
            )
            return 0
        raise FileNotFoundError("尚无报告，请先 autotest run")
    if report_dir and (report_dir / "report.json").is_file():
        data = json.loads((report_dir / "report.json").read_text(encoding="utf-8"))
        _emit(data)
        return 0
    if REPORT_JSON_PATH.is_file():
        data = json.loads(REPORT_JSON_PATH.read_text(encoding="utf-8"))
        _emit(data)
        return 0
    raise ValueError("须指定 --latest 或 --dir")


def cmd_generate(
    *,
    case_id: str,
    name: str,
    module: str,
    account_alias: str,
    macros: list[str],
    tunnel_keyword: str | None,
    activity_hint: str | None,
    manual_case_ref: str,
    prd_ref: str,
    priority: str,
    requirement_id: str | None,
    folder: str | None,
    overwrite: bool,
) -> int:
    case = build_case_template(
        case_id=case_id,
        name=name,
        module=module,
        account_alias=account_alias,
        manual_case_ref=manual_case_ref,
        prd_ref=prd_ref,
        macros=macros,
        tunnel_keyword=tunnel_keyword,
        activity_hint=activity_hint,
        priority=priority,
    )
    path = write_case_file(
        case,
        overwrite=overwrite,
        requirement_id=requirement_id,
        folder=folder,
    )
    _emit({"written": path, "case": case})
    return 0
