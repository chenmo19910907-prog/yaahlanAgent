"""运行器：编排用例级流程（单步逻辑见 loop_cycle）。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .budget import StepBudget
from .case_model import case_flow_steps, load_case
from .fixtures import run_case_fixtures, tunnel_verify
from .perceive import perceive_activity
from .kb import load_kb_hints
from .step_hints import case_modules
from .loop_cycle import run_step_cycle
from .report import new_report, save_report


def _load_config(config: dict[str, Any] | None) -> dict[str, Any]:
    return config if isinstance(config, dict) else {}


def _run_assertions(case: dict[str, Any]) -> list[dict[str, Any]]:
    verify = case.get("verify")
    if not isinstance(verify, list):
        verify = case.get("assertions") if isinstance(case.get("assertions"), list) else []

    account = case.get("account") if isinstance(case.get("account"), dict) else {}
    user_id = str(account.get("userId") or "").strip()
    results: list[dict[str, Any]] = []

    for item in verify:
        if not isinstance(item, dict):
            continue
        vtype = str(item.get("type") or "").strip()
        if vtype == "tunnel" and user_id:
            res = tunnel_verify(
                user_id=user_id,
                keyword=str(item.get("keyword") or ""),
                since=int(item.get("since") or 3600),
            )
            results.append({"type": vtype, "ok": res.get("ok"), "detail": res})
        elif vtype == "activity":
            from .perceive import perceive_activity

            expect = str(item.get("expect") or "").strip()
            act = perceive_activity(budget=StepBudget())
            short = str(act.get("shortName") or act.get("activity") or "")
            ok = not expect or expect in short
            results.append(
                {
                    "type": vtype,
                    "ok": ok,
                    "detail": {"expect": expect, "actual": short, "activity": act},
                }
            )
    return results


def run_case(
    case_path: Path,
    *,
    config: dict[str, Any] | None = None,
    dry_run: bool = False,
    max_steps: int | None = None,
) -> dict[str, Any]:
    cfg = _load_config(config)
    budget = StepBudget.from_config(cfg)
    case = load_case(case_path)
    case_id = str(case.get("id") or case_path.stem)
    module = str(case.get("module") or "")
    modules = case_modules(case)
    kb_hints: list[str] = []
    for mod in modules:
        kb_hints.extend(load_kb_hints(mod, config=cfg))
    kb_hints = kb_hints[:15]
    flow = case_flow_steps(case)
    if max_steps is not None:
        flow = flow[: max(0, max_steps)]

    report = new_report(case_id=case_id, case_path=str(case_path))
    report["module"] = module
    report["stepBudgetMs"] = budget.step_budget_ms
    report["kbHintCount"] = len(kb_hints)

    if dry_run:
        report["status"] = "dry-run"
        report["plannedFlow"] = flow
        save_report(report)
        return report

    report["fixtures"] = run_case_fixtures(case, phase="before")

    metadata = case.get("metadata") if isinstance(case.get("metadata"), dict) else {}
    resume_when_logged_in = str(metadata.get("resumeWhenLoggedIn") or "").strip()
    login_probe_after = str(metadata.get("loginProbeAfter") or "等待4秒").strip()
    skip_login_block = False

    for index, nl_step in enumerate(flow, start=1):
        if skip_login_block and resume_when_logged_in and nl_step != resume_when_logged_in:
            report["iterations"].append(
                {
                    "index": index,
                    "step": nl_step,
                    "act": {"ok": True, "action": "skip", "skipped": True, "reason": "已登录，跳过登录段"},
                    "think": {"action": "skip", "reasoning": "已登录，跳过登录段"},
                }
            )
            continue

        if skip_login_block and nl_step == resume_when_logged_in:
            skip_login_block = False

        iteration = run_step_cycle(
            nl_step=nl_step,
            case=case,
            kb_hints=kb_hints,
            budget=budget,
        )
        iteration["index"] = index
        report["iterations"].append(iteration)

        timing = iteration.get("timingMs") if isinstance(iteration.get("timingMs"), dict) else {}
        think = iteration.get("think") if isinstance(iteration.get("think"), dict) else {}
        act = iteration.get("act") if isinstance(iteration.get("act"), dict) else {}
        post_act = iteration.get("postAct") if isinstance(iteration.get("postAct"), dict) else {}
        scene_after = iteration.get("sceneGateAfter") if isinstance(iteration.get("sceneGateAfter"), dict) else {}
        if isinstance(post_act.get("sceneGate"), dict):
            scene_after = post_act["sceneGate"]

        if think.get("action") == "scene_blocked":
            report["status"] = "failed"
            report["failureAt"] = index
            report["failureReason"] = think.get("reasoning") or "步前 scene 门禁未通过"
            report["failureKind"] = "scene_gate_before"
            break

        if think.get("action") == "need_agent" or (not act.get("ok") and act.get("action") != "skip"):
            report["status"] = "failed"
            report["failureAt"] = index
            report["failureReason"] = think.get("reasoning") or act.get("error") or "执行失败"
            break

        if scene_after and scene_after.get("ok") is False:
            report["status"] = "failed"
            report["failureAt"] = index
            report["failureKind"] = "scene_gate_after"
            actual = scene_after.get("actual") if isinstance(scene_after.get("actual"), dict) else {}
            report["failureReason"] = (
                f"{scene_after.get('reason')}；实际 {_fmt_scene(actual)}"
            )
            break

        if (
            resume_when_logged_in
            and nl_step == login_probe_after
            and act.get("ok")
        ):
            probe = perceive_activity(budget=budget)
            if str(probe.get("hint") or "") == "home":
                skip_login_block = True

        if not timing.get("withinBudget", True):
            report.setdefault("budgetWarnings", []).append(
                {"step": index, "timingMs": timing, "nlStep": nl_step}
            )

    if report.get("status") != "failed":
        assertions = _run_assertions(case)
        report["assertions"] = assertions
        report["fixturesAfter"] = run_case_fixtures(case, phase="after")
        report["status"] = "passed" if all(a.get("ok") for a in assertions) or not assertions else "failed"

    report["finishedAt"] = __import__("time").time()
    report["reportPath"] = str(save_report(report))
    return report


def _fmt_scene(actual: dict[str, Any]) -> str:
    return (
        f"hint={actual.get('hint', '—')}, scene={actual.get('scene', '—')}, "
        f"shortName={actual.get('shortName', '—')}"
    )
