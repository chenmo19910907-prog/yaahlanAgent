# -*- coding: utf-8 -*-
"""
Yaahlan 半月结算薪数据驱动测试报告生成。

报告结构对齐 docs/common/测试报告生成规范.md 附录 A，业务列与快照表按本项目特性定制：
- 金额单位：美元（表3/表4 字段）
- 关键表：anchor_work_statistic_5、anchor_salary_detail、salary_expected_detail
- 执行流程：造数 → MOA1 → MOA2 → 断言（表3/表4）
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime
from typing import Any

REPORT_DIR = "docs/yaahlan_salary/cycle_salary/reports"
REPORT_DIR_EXEMPT = "docs/yaahlan_salary/cycle_salary/exempt_reports"
DATA_SUBDIR = "salary/cycle_salary"
DEFAULT_CASES_JSON = "yaahlan_cycle_salary_cases.json"
EXEMPT_SUITE_JSON = "yaahlan_cycle_salary_exempt_suite.json"
REPORT_TITLE = "Yaahlan 半月结算薪数据驱动测试报告"
REPORT_TITLE_EXEMPT = "Yaahlan 主播薪资豁免 E2E 测试报告"

T3_FIELD_LABELS = [
    ("salary_level", "表3.salary_level"),
    ("salary_coefficient", "表3.salary_coefficient"),
    ("coin_income", "表3.coin_income"),
    ("effective_workday", "表3.effective_workday"),
    ("in_seattime", "表3.in_seattime"),
    ("anchor_salary_raw", "表3.anchor_salary_raw($)"),
    ("union_salary_raw", "表3.union_salary_raw($)"),
    ("anchor_salary_payable", "表3.anchor_salary_payable($)"),
    ("union_salary_payable", "表3.union_salary_payable($)"),
    ("total_salary_payable", "表3.total_salary_payable($)"),
]

T4_FIELD_LABELS = [
    ("salary_level", "表4.salary_level"),
    ("deduction_factor", "表4.deduction_factor"),
    ("coin_income", "表4.coin_income"),
    ("work_hours", "表4.work_hours"),
    ("work_days", "表4.work_days"),
    ("anchor_salary", "表4.anchor_salary($)"),
    ("union_commission", "表4.union_commission($)"),
    ("union_total_salary", "表4.union_total_salary($)"),
    ("union_prepayment", "表4.union_prepayment($)"),
    ("anchor_prepayment", "表4.anchor_prepayment($)"),
    ("all_anchor_prepayment", "表4.all_anchor_prepayment($)"),
    ("expected_amount", "表4.expected_amount($)"),
]

YAAHLAN_STEP_EXPECTATIONS = [
    {
        "step": "1. 造数",
        "rule": "按用例 setup 写入 anchor_work_statistic_5；可选 join_time / prepayment",
        "action": "INSERT … ON DUPLICATE KEY UPDATE 表1；可选改 anchor_profile.create_time 或写 salary_prepayments",
        "purpose": "构造周期内金币、时长、有效日及预提/首次主播豁免前置",
        "inputs": "anchor_id, period_start, setup.updates",
        "outputs": "表1 记录就绪",
    },
    {
        "step": "2. MOA1",
        "rule": "testUpdateSnapshotData 生成主播半月快照（表2）",
        "action": "调用 /service/yaahlan-cms/anchor-salary-moa.testUpdateSnapshotData",
        "purpose": "服务端读取表1并落快照",
        "inputs": "anchor_id, period_start",
        "outputs": "快照生成完成",
    },
    {
        "step": "3. MOA2",
        "rule": "generateAnchorSalary 执行算薪，写入表3/表4",
        "action": "调用 /service/yaahlan-cms/anchor-salary-moa.generateAnchorSalary",
        "purpose": "触发半月结算薪主流程",
        "inputs": "period_start",
        "outputs": "anchor_salary_detail、salary_expected_detail 有记录",
    },
    {
        "step": "4. 断言",
        "rule": "对比表3/表4 与 expected_t3/expected_t4；校验 expected_amount 公式",
        "action": "SELECT 表3/表4 并逐项断言",
        "purpose": "验证扣减系数、等级、应发金额与预提扣减",
        "inputs": "expected_t3, expected_t4",
        "outputs": "全部校验项通过",
    },
]


class ReportCollector:
    """会话级用例结果收集器，供 pytest 结束后写报告。"""

    def __init__(self):
        self.enabled = False
        self.results: list[dict[str, Any]] = []
        self.cases: list[dict[str, Any]] = []
        self.run_start: float | None = None
        self.executed_count = 0
        self.command = ""
        self.validation_errors: list[str] = []
        self.dingtalk_brief_sent = False
        self.report_title: str = REPORT_TITLE
        self.report_dir: str = REPORT_DIR
        self.cases_data_label: str = f"data/{DATA_SUBDIR}/{DEFAULT_CASES_JSON}"

    def reset(self):
        self.results = []
        self.cases = []
        self.run_start = None
        self.executed_count = 0
        self.command = ""
        self.validation_errors = []
        self.dingtalk_brief_sent = False
        self.report_title = REPORT_TITLE
        self.report_dir = REPORT_DIR
        self.cases_data_label = f"data/{DATA_SUBDIR}/{DEFAULT_CASES_JSON}"

    def begin_session(
        self,
        cases: list[dict],
        command: str = "",
        *,
        report_title: str | None = None,
        report_dir: str | None = None,
        cases_data_label: str | None = None,
    ):
        self.enabled = True
        self.cases = cases
        self.command = command
        self.run_start = datetime.now().timestamp()
        if report_title:
            self.report_title = report_title
        if report_dir:
            self.report_dir = report_dir
        if cases_data_label:
            self.cases_data_label = cases_data_label

    def record_skip(self, case: dict, reason: str):
        self.results.append(
            {
                "case_name": case.get("case_name", "-"),
                "case_name_cn": case.get("case_name_cn", "-"),
                "case_name_en": case.get("case_name_en", "-"),
                "scenario_desc": case.get("scenario_desc", "-"),
                "scenario_brief": scenario_brief_for_table(case),
                "status": "跳过",
                "duration_ms": 0,
                "remark": reason,
                "failure_reason": None,
                "expected_total_payable": None,
                "actual_total_payable": None,
                "expected_amount": None,
                "actual_amount": None,
                "check_rows": [],
                "snapshots": {},
                "steps_log": [],
            }
        )

    def record_result(self, case: dict, result: dict):
        self.executed_count += 1
        row = {
            "case_name": case.get("case_name", "-"),
            "case_name_cn": case.get("case_name_cn", "-"),
            "case_name_en": case.get("case_name_en", "-"),
            "scenario_desc": case.get("scenario_desc", "-"),
            "scenario_brief": scenario_brief_for_table(case),
            "status": result.get("status", "失败"),
            "duration_ms": result.get("duration_ms", 0),
            "remark": result.get("remark"),
            "failure_reason": result.get("failure_reason"),
            "expected_total_payable": result.get("expected_total_payable"),
            "actual_total_payable": result.get("actual_total_payable"),
            "expected_amount": result.get("expected_amount"),
            "actual_amount": result.get("actual_amount"),
            "check_rows": result.get("check_rows") or [],
            "snapshots": result.get("snapshots") or {},
            "steps_log": result.get("steps_log") or [],
        }
        self.results.append(row)


_collector = ReportCollector()


def get_collector() -> ReportCollector:
    return _collector


def _escape_pipe(text: str) -> str:
    return (text or "").replace("|", "\\|").replace("\n", "<br>")


def _segment_long_text(text: str, max_seg: int = 48) -> str:
    if len(text) <= max_seg:
        return text
    parts = []
    rest = text
    while rest:
        if len(rest) <= max_seg:
            parts.append(rest)
            break
        cut = rest.rfind("；", 0, max_seg)
        if cut < max_seg // 2:
            cut = rest.rfind("，", 0, max_seg)
        if cut < max_seg // 2:
            cut = max_seg
        parts.append(rest[:cut])
        rest = rest[cut:].lstrip("；，")
    return "<br>".join(parts)


def _verification_point(vs: dict) -> str:
    return (vs.get("验证点") or vs.get("point") or "").strip()


def _verification_construction(vs: dict) -> str:
    return (vs.get("场景构造") or vs.get("construction") or "").strip()


def scenario_brief_for_table(case: dict, max_len: int = 72) -> str:
    vs = case.get("verification_scenarios") or []
    if vs:
        points = []
        for v in vs[:4]:
            p = _verification_point(v)
            if p:
                points.append(p[:18] + "…" if len(p) > 18 else p)
        if points:
            s = "验证：" + "；".join(points)
            return s[:max_len] + "…" if len(s) > max_len else s
    desc = (case.get("scenario_desc") or "").strip()
    if desc:
        return desc[:max_len] + "…" if len(desc) > max_len else desc
    return (case.get("case_name_cn") or "-").strip()


def _json_default(obj):
    if isinstance(obj, datetime):
        return obj.isoformat(sep=" ", timespec="seconds")
    # pymysql 金额/系数字段常为 Decimal
    if type(obj).__name__ == "Decimal":
        return float(obj)
    return str(obj)


def _format_json_for_display(obj, indent: int = 2) -> str:
    if obj is None:
        return "null"
    if isinstance(obj, (dict, list)):
        return json.dumps(obj, ensure_ascii=False, indent=indent, default=_json_default)
    return str(obj)


def _mermaid_node_text(text: str, newline_to_br: bool = True) -> str:
    s = str(text or "")
    if newline_to_br:
        s = s.replace("\n", "<br>")
    return s.replace('"', "'")


def _build_flow_diagrams(case: dict, case_result: dict | None) -> list[tuple[str, str]]:
    """按脚本执行顺序生成 Mermaid 流程图（每步一图）。"""
    diagrams: list[tuple[str, str]] = []
    anchor_id = case.get("anchor_id", "-")
    period_start = case.get("period_start", "-")
    setup = case.get("setup") or {}
    steps_log = (case_result or {}).get("steps_log") or []

    def emit(title: str, process: str, result: str):
        idx = len(diagrams) + 1
        node_id = f"P{idx}"
        c1 = f"C1_{idx}"
        c2 = f"C2_{idx}"
        mermaid = (
            f"flowchart TB\n"
            f'    {node_id}["{_mermaid_node_text(title)}"]\n'
            f'    {c1}["过程: {_mermaid_node_text(process)}"]\n'
            f'    {c2}["结果: {_mermaid_node_text(result)}"]\n'
            f"    {node_id} --> {c1}\n"
            f"    {node_id} --> {c2}"
        )
        diagrams.append((f"图 {idx}：{title}", mermaid))

    if setup.get("zero_all_period"):
        emit(
            "【清理】清零本周期表1历史数据",
            f"UPDATE anchor_work_statistic_5 SET receive_gift_count=0, on_seat_seconds=0, is_effective_day=0 "
            f"WHERE anchor_id={anchor_id} AND statistic_date IN 周期[{period_start}~period_end]",
            "周期内表1字段已清零，避免跨用例污染",
        )

    updates = setup.get("updates") or []
    for i, item in enumerate(updates, 1):
        emit(
            f"【构造】写入表1第{i}条 statistic_date={item.get('statistic_date')}",
            (
                "INSERT INTO anchor_work_statistic_5 "
                "(year, anchor_id, statistic_date, receive_gift_count, on_seat_seconds, is_effective_day) "
                f"VALUES ({str(item.get('statistic_date', ''))[:4]}, {anchor_id}, {item.get('statistic_date')}, "
                f"{item.get('receive_gift_count')}, {item.get('on_seat_seconds')}, {item.get('is_effective_day')}) "
                "ON DUPLICATE KEY UPDATE receive_gift_count=VALUES(receive_gift_count), "
                "on_seat_seconds=VALUES(on_seat_seconds), is_effective_day=VALUES(is_effective_day)"
            ),
            _format_json_for_display(item),
        )

    if setup.get("join_time_override"):
        emit(
            "【构造】首次主播豁免：修改 anchor_profile.create_time",
            f"UPDATE anchor_profile SET create_time=… WHERE user_id={anchor_id} AND state=1 "
            f"(join_time_override={setup.get('join_time_override')})",
            "配合「首次成为主播 + 入职日期达标」后 MOA 读取入职时间",
        )

    prepayments = setup.get("prepayments") or ([setup["prepayment"]] if setup.get("prepayment") else [])
    for i, prep in enumerate(prepayments, 1):
        emit(
            f"【构造】预提记录第{i}条",
            (
                "INSERT INTO salary_prepayments (user_id, prepayment_type, trade_id, period, credit_amount) "
                f"VALUES ({prep.get('user_id')}, {prep.get('prepayment_type')}, {prep.get('trade_id')}, "
                f"{prep.get('period')}, {prep.get('credit_amount')})"
            ),
            _format_json_for_display(prep),
        )

    emit(
        "【调用】MOA1 testUpdateSnapshotData",
        f"MOA /service/yaahlan-cms/anchor-salary-moa.testUpdateSnapshotData args=[{anchor_id}, {period_start}]",
        steps_log[0]["result"] if steps_log else "等待快照生成（约3s）",
    )
    emit(
        "【调用】MOA2 generateAnchorSalary",
        f"MOA /service/yaahlan-cms/anchor-salary-moa.generateAnchorSalary args=[{period_start}]",
        steps_log[1]["result"] if len(steps_log) > 1 else "等待算薪完成（约30s）",
    )

    snapshots = (case_result or {}).get("snapshots") or {}
    t3 = snapshots.get("anchor_salary_detail") or []
    t4 = snapshots.get("salary_expected_detail") or []
    emit(
        "【校验】表3 anchor_salary_detail",
        "SELECT * FROM anchor_salary_detail WHERE anchor_id=? AND salary_start_date=?",
        _format_json_for_display(t3[0] if t3 else "无记录"),
    )
    expected_t3 = case.get("expected_t3") or {}
    expected_t4 = case.get("expected_t4") or {}
    actual_t3 = t3[0] if t3 else {}
    actual_t4 = t4[0] if t4 else {}
    verify_lines = []
    for key, label in T3_FIELD_LABELS:
        if key in expected_t3:
            verify_lines.append(f"{label}: 预期={expected_t3.get(key)} 实际={actual_t3.get(key)}")
    emit(
        "【校验】表3 预期 vs 实际",
        "对比 expected_t3 与 anchor_salary_detail 查询结果",
        "<br>".join(verify_lines) if verify_lines else "见校验结果表",
    )
    emit(
        "【校验】表4 salary_expected_detail",
        "SELECT * FROM salary_expected_detail WHERE salary_period=? AND payment_uid=?",
        _format_json_for_display(t4[0] if t4 else "无记录"),
    )
    verify_lines4 = []
    for key, label in T4_FIELD_LABELS:
        if key in expected_t4:
            verify_lines4.append(f"{label}: 预期={expected_t4.get(key)} 实际={actual_t4.get(key)}")
    emit(
        "【校验】表4 预期 vs 实际",
        "对比 expected_t4 与 salary_expected_detail；校验 expected_amount 公式",
        "<br>".join(verify_lines4) if verify_lines4 else "见校验结果表",
    )
    return diagrams


def _build_root_cause_analysis(case_result: dict) -> tuple[list[dict], str]:
    if not case_result or case_result.get("status") != "失败":
        return [], ""

    rows: list[dict] = []
    reasons: list[str] = []

    def _add(field: str, exp, act, cause: str):
        rows.append({"校验项": field, "预期值": exp, "实际值": act, "可能根因": cause})
        if cause and cause not in reasons:
            reasons.append(cause)

    for check in case_result.get("check_rows") or []:
        if check.get("passed"):
            continue
        _add(
            check.get("label", "-"),
            check.get("expected", "-"),
            check.get("actual", "-"),
            check.get("cause") or "字段值与预期不符，需核对造数与服务端算薪逻辑。",
        )

    fr = (case_result.get("failure_reason") or "") or (case_result.get("remark") or "")
    if "无数据" in fr or "MOA可能未执行成功" in fr:
        _add(
            "表3/表4 记录",
            "有记录",
            "无记录",
            "MOA 未成功写入结果表；可能 MOA2 冷却锁（同周期 90s）、网络/MOA 不可达或造数未生效。",
        )
    if "公式校验失败" in fr:
        _add(
            "表4.expected_amount",
            "公式计算值",
            "库中值",
            "expected_amount 与 payment_type/is_trade_owner 对应公式不一致；核对预提、子公会分成、激励字段。",
        )
    if "冷却" in fr.lower() or "moa2" in fr.lower():
        _add(
            "MOA2 执行",
            "重新算薪",
            "冷却跳过",
            "同 salary_period 在 90s 内重复调用 generateAnchorSalary 为 no-op；需隔离周期或延长等待。",
        )

    if not rows:
        summary = "失败原因暂无结构化数据可分析，请结合「失败原因」原文与数据快照排查。"
    elif any("无记录" in r["可能根因"] or "MOA" in r["可能根因"] for r in rows):
        summary = (
            "综合上述对比：存在**未查到算薪结果或 MOA 未生效**。建议排查："
            "(1) anchor_work_statistic_5 造数是否 UPSERT 成功；"
            "(2) MOA1/MOA2 是否可达且等待时间充足；"
            "(3) 同周期 MOA2 冷却锁是否导致读到旧数据。"
        )
    elif any("公式" in r["可能根因"] for r in rows):
        summary = (
            "综合上述对比：应得金额公式与库中 expected_amount 不一致。"
            "请核对 payment_type、is_trade_owner 及预提/分成字段是否与用例构造一致。"
        )
    elif any("系数" in r.get("校验项", "") or "coefficient" in r.get("校验项", "") for r in rows):
        summary = (
            "综合上述对比：扣减系数或等级与预期不符。"
            "请核对有效工作日、开播时长、等级豁免、入职豁免等规则与造数是否一致。"
        )
    else:
        summary = "综合上述对比：请结合关键数据对比表与数据快照，优先核对造数、MOA 执行顺序与服务端算薪逻辑。"
    return rows, summary


def _format_remark_failure_for_table(r: dict) -> tuple[str, str]:
    status = r.get("status")
    if status == "通过":
        return "-", "-"
    if status == "跳过":
        return _escape_pipe(r.get("remark") or "-"), "-"
    failure = r.get("failure_reason") or r.get("remark") or "-"
    data_parts = []
    exp_t = r.get("expected_total_payable")
    act_t = r.get("actual_total_payable")
    if exp_t is not None or act_t is not None:
        data_parts.append(f"total_salary_payable 预期={exp_t} 实际={act_t}")
    exp_a = r.get("expected_amount")
    act_a = r.get("actual_amount")
    if exp_a is not None or act_a is not None:
        data_parts.append(f"expected_amount 预期={exp_a} 实际={act_a}")
    data_str = "；".join(data_parts) if data_parts else failure[:80]
    problem = ""
    _, summary = _build_root_cause_analysis(r)
    if summary:
        problem = summary[:120] + ("…" if len(summary) > 120 else "")
    failure_cell = f"**数据**：{data_str}"
    if problem:
        failure_cell += f"<br>**问题分析**：{problem}"
    return "-", _escape_pipe(failure_cell)


def append_results_table(lines: list[str], results: list[dict]):
    lines.append("## 执行结果明细")
    lines.append(
        "| 序号 | 用例 | 中文名 | 场景说明 | 期望total<br>($) | 实际total<br>($) | 期望expected_amount<br>($) | 实际expected_amount<br>($) | 耗时<br>(ms) | 结论 | 备注 | 失败原因 |"
    )
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for idx, r in enumerate(results, 1):
        name = r.get("case_name") or "-"
        cn = (r.get("case_name_cn") or "-")[:24]
        scenario_raw = (r.get("scenario_brief") or r.get("scenario_desc") or "-").strip()
        scenario = _escape_pipe(
            _segment_long_text(scenario_raw, max_seg=48) if len(scenario_raw) > 48 else scenario_raw
        )
        exp_t = r.get("expected_total_payable") if r.get("expected_total_payable") is not None else "-"
        act_t = r.get("actual_total_payable") if r.get("actual_total_payable") is not None else "-"
        exp_a = r.get("expected_amount") if r.get("expected_amount") is not None else "-"
        act_a = r.get("actual_amount") if r.get("actual_amount") is not None else "-"
        duration = r.get("duration_ms") if r.get("duration_ms") is not None else "-"
        status = r.get("status") or "-"
        remark, failure_reason = _format_remark_failure_for_table(r)
        lines.append(
            f"| {idx} | {name} | {cn} | {scenario} | {exp_t} | {act_t} | {exp_a} | {act_a} | {duration} | {status} | {remark} | {failure_reason} |"
        )
    lines.append("")


def append_snapshots(lines: list[str], snapshots: dict):
    if not snapshots:
        return
    if snapshots.get("anchor_work_statistic_5"):
        lines.append("**anchor_work_statistic_5（表1）**")
        rows = snapshots["anchor_work_statistic_5"]
        cols = list(rows[0].keys()) if rows else []
        if cols:
            lines.append("| " + " | ".join(cols) + " |")
            lines.append("| " + " | ".join(["---"] * len(cols)) + " |")
            for row in rows:
                lines.append("| " + " | ".join(str(row.get(c, "")) for c in cols) + " |")
        lines.append("")
    if snapshots.get("anchor_salary_detail"):
        lines.append("**anchor_salary_detail（表3）**")
        rows = snapshots["anchor_salary_detail"]
        cols = list(rows[0].keys()) if rows else []
        if cols:
            lines.append("| " + " | ".join(cols) + " |")
            lines.append("| " + " | ".join(["---"] * len(cols)) + " |")
            for row in rows:
                lines.append("| " + " | ".join(str(row.get(c, "")) for c in cols) + " |")
        lines.append("")
    if snapshots.get("salary_expected_detail"):
        lines.append("**salary_expected_detail（表4）**")
        rows = snapshots["salary_expected_detail"]
        cols = list(rows[0].keys()) if rows else []
        if cols:
            lines.append("| " + " | ".join(cols) + " |")
            lines.append("| " + " | ".join(["---"] * len(cols)) + " |")
            for row in rows:
                lines.append("| " + " | ".join(str(row.get(c, "")) for c in cols) + " |")
        lines.append("")
    if snapshots.get("salary_prepayments"):
        lines.append("**salary_prepayments（预提，若涉及）**")
        rows = snapshots["salary_prepayments"]
        cols = list(rows[0].keys()) if rows else []
        if cols:
            lines.append("| " + " | ".join(cols) + " |")
            lines.append("| " + " | ".join(["---"] * len(cols)) + " |")
            for row in rows:
                lines.append("| " + " | ".join(str(row.get(c, "")) for c in cols) + " |")
        lines.append("")


def append_case_calc_details(lines: list[str], cases: list[dict], results: list[dict]):
    lines.append("## 用例计算明细（步骤与数值）")
    lines.append("")
    result_by_name = {r.get("case_name"): r for r in results}
    for idx, case in enumerate(cases, 1):
        case_name = case.get("case_name") or "unnamed"
        case_cn = case.get("case_name_cn") or "-"
        case_en = case.get("case_name_en") or "-"
        case_result = result_by_name.get(case_name)
        lines.append("---")
        lines.append("")
        lines.append(f"### 用例 {idx}：{case_name}")
        lines.append("")
        lines.append(f"**{case_cn}** / *{case_en}*")
        lines.append("")

        verification_scenarios = case.get("verification_scenarios") or []
        if verification_scenarios:
            lines.append("#### 覆盖场景（验证点与场景构造）")
            lines.append("| 验证点 | 场景构造 |")
            lines.append("| --- | --- |")
            for vs in verification_scenarios:
                point = _escape_pipe(_verification_point(vs) or "-")
                construction = _escape_pipe(_verification_construction(vs) or "-")
                lines.append(f"| {point} | {construction} |")
            lines.append("")

        lines.append("#### 计算过程（流程图）")
        lines.append("以下按**脚本实际执行顺序**纵向排列，每步一图（父节点 + 两子节点），便于定位问题。")
        lines.append("")
        for title, mermaid in _build_flow_diagrams(case, case_result):
            lines.append(f"**{title}**")
            lines.append("")
            lines.append("```mermaid")
            lines.append(mermaid)
            lines.append("```")
            lines.append("")

        lines.append("#### 计算过程（按步骤）")
        lines.append(
            "下表按步骤列出本步验证的规则与输入输出，与上文「覆盖场景」互为补充（覆盖场景为验证点维度，本表为步骤维度）。"
        )
        lines.append("")
        lines.append("| 步骤 | 本步验证的规则 | 本步操作 | 本步目的 | 输入数据 | 期望结果 |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for item in YAAHLAN_STEP_EXPECTATIONS:
            lines.append(
                f"| {item['step']} | {_escape_pipe(item['rule'])} | {_escape_pipe(item['action'])} | "
                f"{_escape_pipe(item['purpose'])} | {_escape_pipe(item['inputs'])} | {_escape_pipe(item['outputs'])} |"
            )
        lines.append("")

        lines.append("#### 校验结果")
        lines.append("| 校验项 | 预期值 | 实际值 | 是否通过 |")
        lines.append("| --- | --- | --- | --- |")
        if case_result:
            check_rows = case_result.get("check_rows") or []
            if check_rows:
                for check in check_rows:
                    passed = "通过" if check.get("passed") else "失败"
                    exp = check.get("expected", "-")
                    act = check.get("actual", "-")
                    if check.get("skipped"):
                        exp = act = "不校验"
                        passed = "通过"
                    lines.append(
                        f"| {_escape_pipe(check.get('label', '-'))} | {exp} | {act} | {passed} |"
                    )
            else:
                lines.append("| - | - | - | 未记录明细 |")
            lines.append("")
            if case_result.get("status") == "失败":
                root_rows, root_summary = _build_root_cause_analysis(case_result)
                if root_rows:
                    lines.append("**根因分析（关键数据 + 可能原因）**")
                    lines.append("| 校验项 | 预期值 | 实际值 | 可能根因 |")
                    lines.append("| --- | --- | --- | --- |")
                    for row in root_rows:
                        lines.append(
                            f"| {_escape_pipe(row['校验项'])} | {row['预期值']} | {row['实际值']} | {_escape_pipe(row['可能根因'])} |"
                        )
                    lines.append("")
                    lines.append("**综合结论**：")
                    lines.append("")
                    lines.append(root_summary)
            if case_result.get("snapshots"):
                lines.append("")
                lines.append("#### 数据快照")
                append_snapshots(lines, case_result["snapshots"])
        else:
            lines.append("| - | - | - | 未执行 |")
        lines.append("")


def append_failure_section(lines: list[str], results: list[dict], failed_count: int):
    lines.append("## 失败说明与排查建议")
    if failed_count <= 0:
        lines.append("无失败用例。")
        lines.append("")
        return
    lines.append("### 每个失败用例：直接原因与根因结论")
    lines.append("")
    lines.append("| 用例 | 直接原因 | 根因结论 |")
    lines.append("| --- | --- | --- |")
    for r in results:
        if r.get("status") != "失败":
            continue
        case_name = _escape_pipe(r.get("case_name") or "-")
        direct = _escape_pipe(r.get("remark") or r.get("failure_reason") or "-")
        _, root_summary = _build_root_cause_analysis(r)
        s = (root_summary or "").strip()
        root = _escape_pipe(s[:200] + "…" if len(s) > 200 else (s or "-"))
        lines.append(f"| {case_name} | {direct} | {root} |")
    lines.append("")
    lines.append("### 根因分析（关键数据 + 可能原因）")
    lines.append("")
    for r in results:
        if r.get("status") != "失败":
            continue
        case_name = r.get("case_name") or "unnamed"
        case_cn = r.get("case_name_cn") or ""
        lines.append(f"#### {case_name} {case_cn}")
        rows, summary = _build_root_cause_analysis(r)
        if rows:
            lines.append("**关键数据对比**")
            lines.append("")
            lines.append("| 校验项 | 预期值 | 实际值 | 可能根因 |")
            lines.append("| --- | --- | --- | --- |")
            for row in rows:
                lines.append(
                    f"| {_escape_pipe(row['校验项'])} | {row['预期值']} | {row['实际值']} | {_escape_pipe(row['可能根因'])} |"
                )
            lines.append("")
            lines.append("**综合结论**")
            lines.append("")
            lines.append(summary)
        else:
            lines.append("（暂无结构化数据，请结合上方失败原因与数据快照排查。）")
        lines.append("")
    lines.append("### 失败原因（已识别）")
    for r in results:
        if r.get("status") != "失败":
            continue
        lines.append(f"- **{r.get('case_name')}**：{r.get('failure_reason') or r.get('remark') or '-'}")
    lines.append("")


def write_report(
    report_path: str,
    results: list[dict],
    cases: list[dict],
    executed_count: int,
    *,
    total_duration_seconds: int | None = None,
    command: str = "",
    validation_errors: list[str] | None = None,
    project_root: str | None = None,
) -> str:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total_count = len(cases)
    passed_count = len([r for r in results if r.get("status") == "通过"])
    failed_count = len([r for r in results if r.get("status") == "失败"])
    skipped_count = len([r for r in results if r.get("status") == "跳过"])

    collector = get_collector()
    title = collector.report_title if collector.enabled else REPORT_TITLE
    data_label = collector.cases_data_label if collector.enabled else f"data/{DATA_SUBDIR}/{DEFAULT_CASES_JSON}"

    lines = [
        f"# {title}",
        "",
        "## 概要",
        f"- 执行时间：{now_str}",
        f"- 执行方式：`{command or 'pytest business_case/salary/cycle_salary/test_yaahlan_cycle_salary.py'}`",
        f"- 用例数据：`{data_label}`",
        f"- 用例表条数：{total_count}",
    ]
    if validation_errors:
        lines.append(f"- **用例表校验**：未通过（{len(validation_errors)} 项），见日志")
    if total_duration_seconds is not None:
        lines.append(f"- 总耗时：{total_duration_seconds}s")
    lines.append(
        f"- 结果：{executed_count}/{total_count} 执行，{passed_count} 通过，{failed_count} 失败"
        + (f"，{skipped_count} 跳过" if skipped_count else "")
    )
    lines.append("")
    lines.append("**业务说明**")
    lines.append("")
    lines.append(
        "本项目为 **Yaahlan 半月结算薪** E2E：造数写入 `anchor_work_statistic_5`（表1）→ "
        "MOA `testUpdateSnapshotData`（快照/表2）→ MOA `generateAnchorSalary`（表3 `anchor_salary_detail` + 表4 `salary_expected_detail`）→ 断言。"
        "完整业务链在表4 之后还有确认应得薪资 MOA `confirmSalaryByArea`（`/service/yaahlan-cms/anchor-salary-api`），"
        "写入 `union_salary_detail`；新政策近 6 周期基准读该表 `total_salary_payable`。本套半月结用例不调用确认。"
        "金额单位为**美元**；同 `salary_period` 的 MOA2 存在约 90s 冷却锁。"
    )
    lines.append("")

    append_results_table(lines, results)
    executed_cases = _cases_executed_in_session(cases, results)
    append_case_calc_details(lines, executed_cases, results)
    append_failure_section(lines, results, failed_count)

    root = project_root or os.getcwd()
    if not os.path.isabs(report_path):
        abs_path = os.path.join(root, report_path)
    else:
        abs_path = report_path
    report_dir = os.path.dirname(abs_path)
    if report_dir:
        os.makedirs(report_dir, exist_ok=True)
    with open(abs_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return abs_path


def report_path_for_today(project_root: str | None = None) -> str:
    root = project_root or os.getcwd()
    date_str = datetime.now().strftime("%Y%m%d")
    collector = get_collector()
    report_dir = collector.report_dir if collector.enabled else REPORT_DIR
    prefix = "yaahlan_cycle_salary_exempt_test_report" if report_dir == REPORT_DIR_EXEMPT else "yaahlan_cycle_salary_test_report"
    return os.path.join(root, report_dir, f"{prefix}_{date_str}.md")


def sync_html_report(md_path: str, project_root: str | None = None) -> str | None:
    import subprocess
    import sys

    root = project_root or os.getcwd()
    script = os.path.join(root, "scripts", "md_report_to_html.py")
    if not os.path.isfile(script):
        return None
    ret = subprocess.run(
        [sys.executable, script, md_path],
        cwd=root,
        timeout=60,
        capture_output=True,
        text=True,
    )
    if ret.returncode != 0:
        return None
    return os.path.splitext(md_path)[0] + ".html"


def _cases_executed_in_session(cases: list[dict], results: list[dict]) -> list[dict]:
    """报告明细仅展开本次实际执行的用例，避免未跑用例撑大报告与拖慢 HTML 生成。"""
    names = {r.get("case_name") for r in results if r.get("case_name")}
    if not names:
        return cases
    return [c for c in cases if c.get("case_name") in names]


def _brief_cell(text: str, max_len: int = 36) -> str:
    s = (text or "-").replace("|", "\\|").replace("\n", " ").strip()
    if len(s) > max_len:
        return s[: max_len - 1] + "…"
    return s


def _format_duration_brief(seconds: int | None) -> str:
    if seconds is None:
        return "-"
    if seconds < 60:
        return f"{seconds} 秒"
    mins, secs = divmod(seconds, 60)
    return f"{seconds} 秒（约 {mins} 分 {secs} 秒）"


def get_dingtalk_webhook() -> str:
    """优先 DINGTALK_REPORT_WEBHOOK，其次 DINGTALK_WEBHOOK（与 soulchill-api-test 一致）。"""
    return (
        (os.environ.get("DINGTALK_REPORT_WEBHOOK") or "").strip()
        or (os.environ.get("DINGTALK_WEBHOOK") or "").strip()
    )


def _dingtalk_brief_fingerprint(
    report_path: str,
    results: list[dict],
    executed_count: int,
) -> str:
    """按报告文件 + 用例结果生成指纹（不含执行时间，避免同轮重复发送）。"""
    parts = [os.path.basename(report_path or ""), str(executed_count)]
    for r in results:
        parts.append(
            "|".join(
                [
                    str(r.get("case_name") or ""),
                    str(r.get("status") or ""),
                    str(r.get("failure_reason") or r.get("remark") or ""),
                ]
            )
        )
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()[:20]


def _dingtalk_lock_dir(project_root: str) -> str:
    return os.path.join(project_root, REPORT_DIR, ".dingtalk_sent")


def _dingtalk_lock_ttl_seconds() -> int:
    raw = (os.environ.get("DINGTALK_BRIEF_DEDUPE_TTL") or "300").strip()
    try:
        return max(30, int(raw))
    except ValueError:
        return 300


def _claim_dingtalk_brief_send(project_root: str, fingerprint: str) -> bool:
    """
    跨进程占位：同指纹在 TTL 内仅允许发送一次。
    返回 True 表示获得发送权；False 表示近期已发送应跳过。
    """
    if os.environ.get("DINGTALK_FORCE_SEND", "").strip() in ("1", "true", "yes"):
        return True
    lock_dir = _dingtalk_lock_dir(project_root)
    os.makedirs(lock_dir, exist_ok=True)
    lock_path = os.path.join(lock_dir, f"{fingerprint}.lock")
    now = time.time()
    ttl = _dingtalk_lock_ttl_seconds()
    if os.path.isfile(lock_path):
        try:
            if now - os.path.getmtime(lock_path) < ttl:
                return False
            os.remove(lock_path)
        except OSError:
            return False
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(f"{now}\n{os.getpid()}\n")
        return True
    except FileExistsError:
        return False


def _release_dingtalk_brief_send(project_root: str, fingerprint: str) -> None:
    lock_path = os.path.join(_dingtalk_lock_dir(project_root), f"{fingerprint}.lock")
    try:
        if os.path.isfile(lock_path):
            os.remove(lock_path)
    except OSError:
        pass


def build_dingtalk_brief_markdown(
    report_path: str,
    results: list[dict],
    executed_count: int,
    total_duration_seconds: int | None = None,
    *,
    html_path: str | None = None,
) -> str:
    """
    构建钉钉群简报 Markdown（表格化，标题含「测试报告」以满足机器人关键词）。
    仅展示本次实际执行的用例；失败项含直接原因 + 根因建议。
    """
    passed = sum(1 for r in results if r.get("status") == "通过")
    failed = sum(1 for r in results if r.get("status") == "失败")
    skipped = sum(1 for r in results if r.get("status") == "跳过")
    failure_list = [r for r in results if r.get("status") == "失败" and r.get("case_name")]
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        "## 测试报告",
        "",
        "**【Yaahlan 半月结算薪自动化】**",
        "",
        "### 1. 执行概要",
        "",
        "| 项目 | 内容 |",
        "| --- | --- |",
        f"| 执行时间 | {now_str} |",
        f"| 执行用例数 | {executed_count} |",
        f"| 通过 | {passed} |",
        f"| 失败 | {failed} |",
        f"| 跳过 | {skipped} |",
        f"| 总耗时 | {_format_duration_brief(total_duration_seconds)} |",
        f"| Markdown 报告 | {_brief_cell(report_path, 80)} |",
    ]
    if html_path:
        lines.append(f"| HTML 报告 | {_brief_cell(html_path, 80)} |")
    lines.append("")

    lines.extend(
        [
            "### 2. 用例结果一览",
            "",
            "| 序号 | 用例名 | 中文说明 | 结论 | 耗时 |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for idx, r in enumerate(results, 1):
        status = r.get("status") or "-"
        ms = r.get("duration_ms")
        duration = f"{int(ms / 1000)} 秒" if ms is not None else "-"
        lines.append(
            "| {idx} | {name} | {cn} | {status} | {duration} |".format(
                idx=idx,
                name=_brief_cell(r.get("case_name") or "-", 28),
                cn=_brief_cell(r.get("case_name_cn") or "-", 20),
                status=status,
                duration=duration,
            )
        )
    lines.append("")

    if failure_list:
        lines.extend(
            [
                "### 3. 失败说明（需关注）",
                "",
                "| 用例名 | 直接原因（摘要） | 处理建议（摘要） |",
                "| --- | --- | --- |",
            ]
        )
        for r in failure_list:
            _, root_summary = _build_root_cause_analysis(r)
            direct = r.get("failure_reason") or r.get("remark") or "-"
            lines.append(
                "| {name} | {direct} | {advice} |".format(
                    name=_brief_cell(r.get("case_name") or "-", 24),
                    direct=_brief_cell(direct, 40),
                    advice=_brief_cell(root_summary or "详见完整测试报告", 40),
                )
            )
        lines.append("")
        lines.append("> 完整根因对比表与数据快照见 Markdown/HTML 报告。")
    else:
        lines.extend(["### 3. 失败说明", "", "本次无失败用例。", ""])

    lines.append("> 说明：单条用例主要耗时在 MOA 算薪等待（约 30s/次），详见项目文档。")
    return "\n".join(lines).strip()


def send_report_brief_to_dingtalk(
    report_path: str,
    results: list[dict],
    executed_count: int,
    total_duration_seconds: int | None = None,
    *,
    project_root: str | None = None,
    html_path: str | None = None,
    dry_run: bool = False,
) -> bool:
    """
    用例执行结束后向钉钉「自动化测试报告群」发送简报。
    机器人关键词须为「测试报告」。未配置 Webhook 时跳过并返回 False。
    设置 DINGTALK_BRIEF_DRY_RUN=1 或 dry_run=True 时仅打印简报、不实际发送。
    """
    import logging
    import subprocess
    import sys

    from utils.env_utils import load_env_file

    logger = logging.getLogger(__name__)
    root = project_root or os.getcwd()
    load_env_file(root)

    collector = get_collector()
    if collector.dingtalk_brief_sent and not dry_run:
        print("[钉钉] 本会话简报已发送，跳过重复发送")
        return True

    if executed_count <= 0 and not dry_run:
        print("[钉钉] 本次无执行用例，跳过简报发送")
        return False

    is_dry_run = dry_run or os.environ.get("DINGTALK_BRIEF_DRY_RUN", "").strip() in ("1", "true", "yes")
    content = build_dingtalk_brief_markdown(
        report_path,
        results,
        executed_count,
        total_duration_seconds,
        html_path=html_path,
    )
    if is_dry_run:
        print("\n[钉钉简报 dry-run]\n")
        print(content)
        return True

    webhook = get_dingtalk_webhook()
    if not webhook:
        print("（未配置 DINGTALK_REPORT_WEBHOOK 或 DINGTALK_WEBHOOK，未向钉钉报告群发送简报）")
        print("  配置其一即可；机器人关键词须为「测试报告」。可运行: python3 scripts/check_dingtalk_webhook.py")
        return False

    fingerprint = _dingtalk_brief_fingerprint(report_path, results, executed_count)
    if not _claim_dingtalk_brief_send(root, fingerprint):
        collector.dingtalk_brief_sent = True
        print(f"[钉钉] 近期已发送相同简报（指纹 {fingerprint}），跳过重复发送")
        return True

    send_script = os.path.join(root, "scripts", "send_dingtalk_robot.py")
    if not os.path.isfile(send_script):
        logger.warning("DingTalk report brief skip: scripts/send_dingtalk_robot.py not found")
        _release_dingtalk_brief_send(root, fingerprint)
        return False
    try:
        collector.dingtalk_brief_sent = True
        ret = subprocess.run(
            [
                sys.executable,
                send_script,
                "--markdown",
                "--title",
                "测试报告",
                "--dedupe-id",
                fingerprint,
            ],
            env={**os.environ, "DINGTALK_WEBHOOK": webhook},
            cwd=root,
            timeout=15,
            check=False,
            input=content,
            text=True,
            capture_output=True,
        )
        if ret.returncode == 0:
            print("[钉钉] 简报发送成功")
            return True
        collector.dingtalk_brief_sent = False
        _release_dingtalk_brief_send(root, fingerprint)
        err = (ret.stderr or ret.stdout or "").strip()
        logger.warning("DingTalk report brief send failed (exit=%s): %s", ret.returncode, err)
        print(f"[钉钉] 简报发送失败 (exit={ret.returncode}): {err or '见日志'}")
        return False
    except Exception as e:
        collector.dingtalk_brief_sent = False
        _release_dingtalk_brief_send(root, fingerprint)
        logger.warning("DingTalk report brief send failed: %s", e)
        print(f"[钉钉] 简报发送异常: {e}")
        return False
