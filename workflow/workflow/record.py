"""工作流录制与 registry 同步。"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from workflow.paths import REGISTRY_PATH, WORKFLOWS_DIR, WORKFLOW_DIR
from workflow.schema import scaffold_workflow, validate_workflow


def _read_registry() -> dict[str, Any]:
    if not REGISTRY_PATH.is_file():
        return {"items": []}
    with REGISTRY_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("registry.json 必须是 object")
    if "items" not in data or not isinstance(data["items"], list):
        data["items"] = []
    return data


def _write_registry(data: dict[str, Any]) -> None:
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with REGISTRY_PATH.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _registry_id(workflow_id: str) -> str:
    return workflow_id.replace("-", "_")


def _param_cli_flags(params: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in params:
        flag = "--" + _kebab(key)
        parts.append(f"{flag} <{key}>")
    return " ".join(parts)


def _kebab(name: str) -> str:
    out: list[str] = []
    for i, ch in enumerate(name):
        if ch.isupper() and i > 0:
            out.append("-")
        out.append(ch.lower())
    return "".join(out)


def _build_command(workflow: dict[str, Any]) -> str:
    wf_id = workflow["id"]
    params = workflow.get("params") or {}
    flags = _param_cli_flags(params) if params else ""
    base = f"python3 workflow/workflow_execute.py run {wf_id}"
    return f"{base} {flags}".strip()


def _build_prompts(workflow: dict[str, Any]) -> list[str]:
    wf_id = workflow["id"]
    name = workflow.get("name", wf_id)
    params = workflow.get("params") or {}
    placeholders = " ".join(f"<{k}>" for k in params)
    prompts = [f"执行工作流 {name}"]
    if placeholders:
        prompts.append(f"工作流 {wf_id} {placeholders}")
    return prompts


def upsert_registry_item(workflow: dict[str, Any]) -> None:
    registry = _read_registry()
    item_id = _registry_id(workflow["id"])
    item = {
        "id": item_id,
        "name": workflow.get("name", workflow["id"]),
        "category": workflow.get("category", "通用"),
        "description": workflow.get("description", ""),
        "prompts": _build_prompts(workflow),
        "command": _build_command(workflow),
    }
    items: list[dict[str, Any]] = registry["items"]
    replaced = False
    for i, existing in enumerate(items):
        if existing.get("id") == item_id:
            items[i] = item
            replaced = True
            break
    if not replaced:
        items.append(item)
    _write_registry(registry)


def save_workflow(data: dict[str, Any], register: bool = True) -> Path:
    validate_workflow(data)
    workflow_id = str(data["id"])
    path = WORKFLOWS_DIR / f"{workflow_id}.json"
    WORKFLOWS_DIR.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    if register:
        upsert_registry_item(data)
        _run_generate_index()
    return path


def init_workflow(workflow_id: str, name: str | None = None, register: bool = False) -> Path:
    data = scaffold_workflow(workflow_id, name)
    return save_workflow(data, register=register)


def record_from_file(path: Path, register: bool = True) -> Path:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("工作流 JSON 必须是 object")
    return save_workflow(data, register=register)


def record_from_stdin(register: bool = True) -> Path:
    data = json.load(sys.stdin)
    if not isinstance(data, dict):
        raise ValueError("工作流 JSON 必须是 object")
    return save_workflow(data, register=register)


def _run_generate_index() -> None:
    script = WORKFLOW_DIR / "scripts" / "generate_index.py"
    subprocess.run([sys.executable, str(script)], check=True)
