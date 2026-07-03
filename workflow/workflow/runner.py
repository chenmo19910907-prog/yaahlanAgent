"""工作流步骤执行器。"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from workflow.json_path import set_path
from workflow.paths import REPO_ROOT, TMP_RUNS_DIR, WORKFLOWS_DIR
from workflow.schema import validate_workflow
from workflow.substitute import build_params, substitute_value


def load_workflow(workflow_id: str) -> dict[str, Any]:
    path = WORKFLOWS_DIR / f"{workflow_id}.json"
    if not path.is_file():
        raise FileNotFoundError(f"未找到工作流: {workflow_id} ({path})")
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("工作流 JSON 必须是 object")
    validate_workflow(data)
    if data.get("id") != workflow_id:
        raise ValueError(f"工作流 id 与文件名不一致: {data.get('id')} != {workflow_id}")
    return data


def list_workflows() -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    if not WORKFLOWS_DIR.is_dir():
        return items
    for path in sorted(WORKFLOWS_DIR.glob("*.json")):
        if path.name.startswith("_"):
            continue
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            continue
        items.append(
            {
                "id": str(data.get("id", path.stem)),
                "name": str(data.get("name", path.stem)),
                "description": str(data.get("description", "")),
            }
        )
    return items


def _check_expect(result: dict[str, Any], expect: dict[str, Any] | None) -> None:
    if not expect:
        return
    for key, allowed in expect.items():
        if key not in result:
            raise RuntimeError(f"步骤结果缺少字段 {key}，无法验收")
        actual = result[key]
        if isinstance(allowed, list):
            if actual not in allowed:
                raise RuntimeError(f"步骤验收失败: {key}={actual}，期望 {allowed}")
        elif actual != allowed:
            raise RuntimeError(f"步骤验收失败: {key}={actual}，期望 {allowed}")


def _run_shell(run: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    command = run["command"]
    cwd = run.get("cwd", ".")
    workdir = (repo_root / cwd).resolve()
    proc = subprocess.run(
        command,
        shell=True,
        cwd=str(workdir),
        capture_output=True,
        text=True,
    )
    return {
        "type": "shell",
        "command": command,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "ok": proc.returncode == 0,
    }


def _run_moa_template(
    run: dict[str, Any],
    repo_root: Path,
    workflow_id: str,
    step_id: str,
) -> dict[str, Any]:
    template_rel = run["template"]
    template_path = (repo_root / template_rel).resolve()
    if not template_path.is_file():
        raise FileNotFoundError(f"MOA 模板不存在: {template_path}")

    with template_path.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    patch = run.get("patch") or {}
    if not isinstance(patch, dict):
        raise ValueError("run.patch 必须是 object")
    for path, value in patch.items():
        set_path(payload, str(path), value)

    TMP_RUNS_DIR.mkdir(parents=True, exist_ok=True)
    payload_path = TMP_RUNS_DIR / f"{workflow_id}_{step_id}_payload.json"
    with payload_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    timeout_ms = int(run.get("timeout_ms", 5000))
    cmd = [
        sys.executable,
        str(repo_root / "MOA" / "moa_execute.py"),
        "--payload-file",
        str(payload_path),
        "--timeout-ms",
        str(timeout_ms),
    ]
    proc = subprocess.run(cmd, cwd=str(repo_root), capture_output=True, text=True)
    stdout = proc.stdout.strip()
    stderr = proc.stderr.strip()

    parsed: dict[str, Any] | None = None
    if stdout:
        try:
            parsed = json.loads(stdout)
        except json.JSONDecodeError:
            parsed = None

    ec = None
    if isinstance(parsed, dict):
        ec = parsed.get("ec")
        if ec is None and isinstance(parsed.get("data"), dict):
            ec = parsed["data"].get("ec")

    return {
        "type": "moa_template",
        "template": template_rel,
        "payload_path": str(payload_path),
        "returncode": proc.returncode,
        "stdout": stdout,
        "stderr": stderr,
        "ec": ec,
        "parsed": parsed,
        "ok": proc.returncode == 0,
    }


def _execute_step(
    step: dict[str, Any],
    params: dict[str, str],
    workflow_id: str,
) -> dict[str, Any]:
    run = substitute_value(step["run"], params)
    run_type = run["type"]
    if run_type == "shell":
        result = _run_shell(run, REPO_ROOT)
    elif run_type == "moa_template":
        result = _run_moa_template(run, REPO_ROOT, workflow_id, str(step["id"]))
    else:
        raise ValueError(f"不支持的步骤类型: {run_type}")

    _check_expect(result, step.get("expect"))
    expect = step.get("expect") or {}
    allowed_rc = expect.get("returncode", 0)
    if isinstance(allowed_rc, list):
        rc_ok = result.get("returncode") in allowed_rc
    else:
        rc_ok = result.get("returncode") == allowed_rc
    if not rc_ok:
        raise RuntimeError(
            f"步骤 {step.get('id')} 执行失败: returncode={result.get('returncode')}"
        )
    return result


def run_workflow(workflow_id: str, cli_values: dict[str, str]) -> dict[str, Any]:
    wf = load_workflow(workflow_id)
    params = build_params(wf.get("params") or {}, cli_values)

    started = datetime.now(timezone.utc).isoformat()
    step_results: list[dict[str, Any]] = []

    for step in wf["steps"]:
        step_results.append(
            {
                "id": step["id"],
                "name": step.get("name", step["id"]),
                "result": _execute_step(step, params, workflow_id),
            }
        )

    summary = {
        "workflowId": workflow_id,
        "name": wf.get("name"),
        "params": params,
        "startedAt": started,
        "finishedAt": datetime.now(timezone.utc).isoformat(),
        "steps": step_results,
        "ok": True,
    }

    TMP_RUNS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = TMP_RUNS_DIR / f"{workflow_id}_{stamp}.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    summary["reportPath"] = str(out_path)

    _cleanup_tmp_after_workflow()
    return summary


def _cleanup_tmp_after_workflow() -> None:
    """工作流结束后清理过期 ephemeral 与旧报告。"""
    cleanup_script = REPO_ROOT / "scripts" / "tmp_cleanup.py"
    if not cleanup_script.is_file():
        return
    try:
        subprocess.run(
            [sys.executable, str(cleanup_script)],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass
