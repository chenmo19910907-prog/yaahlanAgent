#!/usr/bin/env python3
"""
生成一份样例测试报告（无需连接 DB/MOA），用于验证报告模板与 MD→HTML 转换。

运行:
  python3 scripts/generate_sample_report.py
"""
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.normpath(os.path.join(SCRIPT_DIR, ".."))
sys.path.insert(0, PROJECT_ROOT)

from utils.json_utils import JsonUtils
from utils.salary_report import report_path_for_today, sync_html_report, write_report


def _sample_result(case: dict, *, status: str, actual_t3: dict, actual_t4: dict) -> dict:
    exp_t3 = case.get("expected_t3") or {}
    exp_t4 = case.get("expected_t4") or {}
    check_rows = []
    for key in exp_t3:
        check_rows.append(
            {
                "label": f"表3.{key}",
                "expected": exp_t3[key],
                "actual": actual_t3.get(key),
                "passed": str(exp_t3[key]) == str(actual_t3.get(key)),
                "cause": "",
            }
        )
    for key in exp_t4:
        check_rows.append(
            {
                "label": f"表4.{key}",
                "expected": exp_t4[key],
                "actual": actual_t4.get(key),
                "passed": str(exp_t4[key]) == str(actual_t4.get(key)),
                "cause": "",
            }
        )
    failure_reason = None
    if status == "失败":
        failed = [r for r in check_rows if not r["passed"]]
        failure_reason = (
            f"{case.get('case_name')} | {failed[0]['label']}: "
            f"expected={failed[0]['expected']}, actual={failed[0]['actual']}"
            if failed
            else "样例失败"
        )
    return {
        "case_name": case.get("case_name"),
        "case_name_cn": case.get("case_name_cn"),
        "case_name_en": case.get("case_name_en"),
        "scenario_desc": case.get("scenario_desc"),
        "status": status,
        "duration_ms": 35000,
        "remark": failure_reason,
        "failure_reason": failure_reason,
        "expected_total_payable": exp_t3.get("total_salary_payable"),
        "actual_total_payable": actual_t3.get("total_salary_payable"),
        "expected_amount": exp_t4.get("expected_amount"),
        "actual_amount": actual_t4.get("expected_amount"),
        "check_rows": check_rows,
        "steps_log": [
            {"step": "MOA1", "result": "testUpdateSnapshotData 已调用（样例）"},
            {"step": "MOA2", "result": "generateAnchorSalary 已调用（样例）"},
        ],
        "snapshots": {
            "anchor_work_statistic_5": case.get("setup", {}).get("updates", [])[:3],
            "anchor_salary_detail": [actual_t3],
            "salary_expected_detail": [actual_t4],
        },
    }


def main():
    data = JsonUtils.jsonfile_to_dict("salary/cycle_salary", "yaahlan_cycle_salary_cases.json") or {}
    cases = data.get("cases") or []
    if not cases:
        print("用例表为空", file=sys.stderr)
        return 1

    c1 = cases[0]
    c2 = cases[1] if len(cases) > 1 else cases[0]
    exp_t3_2 = c2.get("expected_t3") or {}
    exp_t4_2 = c2.get("expected_t4") or {}
    fail_t3 = dict(exp_t3_2)
    fail_t3["salary_coefficient"] = 0.6
    fail_t3["anchor_salary_payable"] = round(float(exp_t3_2.get("anchor_salary_payable", 0)) * 0.75, 2)
    fail_t4 = dict(exp_t4_2)
    fail_t4["deduction_factor"] = 0.6
    fail_t4["anchor_salary"] = fail_t3["anchor_salary_payable"]

    from utils.salary_report import scenario_brief_for_table

    results = [
        {**_sample_result(c1, status="通过", actual_t3=c1["expected_t3"], actual_t4=c1["expected_t4"]),
         "scenario_brief": scenario_brief_for_table(c1)},
        {**_sample_result(c2, status="失败", actual_t3=fail_t3, actual_t4=fail_t4),
         "scenario_brief": scenario_brief_for_table(c2)},
    ]
    sample_cases = [c1, c2]

    from datetime import datetime

    sample_md = os.path.join(
        PROJECT_ROOT,
        "docs/yaahlan_salary/cycle_salary/reports",
        f"yaahlan_cycle_salary_sample_report_{datetime.now().strftime('%Y%m%d')}.md",
    )
    md_path = write_report(
        sample_md,
        results,
        sample_cases,
        executed_count=2,
        total_duration_seconds=70,
        command="python3 scripts/generate_sample_report.py",
        project_root=PROJECT_ROOT,
    )
    html_path = sync_html_report(md_path, PROJECT_ROOT)
    print(f"样例 Markdown: {md_path}")
    if html_path:
        print(f"样例 HTML: {html_path}")

    # 样例报告默认不发钉钉，避免与 pytest 正式执行重复；需发送时设 DINGTALK_SEND_ON_SAMPLE=1
    if os.environ.get("DINGTALK_SEND_ON_SAMPLE", "").strip() in ("1", "true", "yes"):
        from utils.salary_report import send_report_brief_to_dingtalk

        send_report_brief_to_dingtalk(
            md_path, results, 2, 70, project_root=PROJECT_ROOT, html_path=html_path
        )
    elif os.environ.get("DINGTALK_BRIEF_DRY_RUN", "").strip() in ("1", "true", "yes"):
        from utils.salary_report import send_report_brief_to_dingtalk

        send_report_brief_to_dingtalk(
            md_path, results, 2, 70, project_root=PROJECT_ROOT, html_path=html_path, dry_run=True
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
