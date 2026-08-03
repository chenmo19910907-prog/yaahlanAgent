"""工作流 JSON 校验。"""

from __future__ import annotations

from typing import Any


def validate_workflow(data: dict[str, Any]) -> dict[str, Any]:
    for key in ("id", "name", "steps"):
        if key not in data or not data[key]:
            raise ValueError(f"工作流缺少必填字段: {key}")
    if not isinstance(data["steps"], list) or not data["steps"]:
        raise ValueError("steps 必须是非空数组")
    params = data.get("params") or {}
    if not isinstance(params, dict):
        raise ValueError("params 必须是 object")
    for i, step in enumerate(data["steps"]):
        if not isinstance(step, dict):
            raise ValueError(f"steps[{i}] 必须是 object")
        if not step.get("id") or not step.get("run"):
            raise ValueError(f"steps[{i}] 缺少 id 或 run")
        run = step["run"]
        if not isinstance(run, dict) or not run.get("type"):
            raise ValueError(f"steps[{i}].run 缺少 type")
    return data


def scaffold_workflow(workflow_id: str, name: str | None = None) -> dict[str, Any]:
    return {
        "id": workflow_id,
        "name": name or workflow_id,
        "description": "",
        "version": 1,
        "params": {
            "exampleParam": {
                "label": "示例参数",
                "type": "string",
                "required": True,
                "prompt": "请填写示例参数",
            }
        },
        "steps": [
            {
                "id": "step_1",
                "name": "第一步",
                "run": {
                    "type": "shell",
                    "command": "echo {{exampleParam}}",
                    "cwd": ".",
                },
            }
        ],
    }
