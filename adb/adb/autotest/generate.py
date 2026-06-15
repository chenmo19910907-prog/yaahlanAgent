"""从手工用例信息生成自动化用例 JSON 模板。"""

from __future__ import annotations

import json
from typing import Any

from .loader import folder_for_requirement
from .paths import AUTOTEST_ROOT, LEGACY_CASES_DIR, ensure_requirement_cases_dir


def build_case_template(
    *,
    case_id: str,
    name: str,
    module: str,
    account_alias: str,
    manual_case_ref: str = "",
    prd_ref: str = "",
    macros: list[str],
    tunnel_keyword: str | None = None,
    activity_hint: str | None = None,
    priority: str = "P0",
) -> dict[str, Any]:
    operations: list[dict[str, Any]] = [
        {
            "step": 1,
            "description": "确认测试账号空闲（Tunnel 近 300s 无心跳）",
            "action": "account_check",
            "account": account_alias,
            "expectInUse": False,
            "sinceSeconds": 300,
        }
    ]
    step = 2
    for index, macro in enumerate(macros):
        op: dict[str, Any] = {
            "step": step,
            "description": f"执行片段：{macro}",
            "action": "macro",
            "script": macro,
        }
        if "登录" in macro:
            op["textFrom"] = "account.phone"
            op["popupScene"] = "login"
            op["popupAutoDismiss"] = True
        if "发布" in macro and "动态" in macro:
            op["text"] = "autotest8888"
        is_last = index == len(macros) - 1
        if tunnel_keyword and ("登录" in macro or is_last):
            op["tunnel"] = {
                "account": account_alias,
                "keyword": tunnel_keyword,
                "waitSeconds": 30,
                "expectEc": 200,
            }
        step += 1
        operations.append(op)

    verify_points: list[dict[str, Any]] = []
    if tunnel_keyword:
        verify_points.append(
            {
                "id": "VP-TUNNEL",
                "name": f"抓包验收 {tunnel_keyword}",
                "method": "tunnel",
                "account": account_alias,
                "keyword": tunnel_keyword,
                "expectEc": 200,
                "waitSeconds": 30,
            }
        )
    if activity_hint:
        verify_points.append(
            {
                "id": "VP-ACTIVITY",
                "name": f"Activity 验收 {activity_hint}",
                "method": "activity",
                "expectHint": activity_hint,
            }
        )
    verify_points.append(
        {
            "id": "VP-SCREENSHOT",
            "name": "留存结束截图",
            "method": "screenshot",
            "required": True,
        }
    )

    return {
        "id": case_id,
        "priority": priority,
        "name": name,
        "module": module,
        "source": {
            "manualCaseRef": manual_case_ref,
            "prdRef": prd_ref,
        },
        "account": {
            "alias": account_alias,
            "precondition": "账号空闲；真机已连接 adb devices=device",
        },
        "operationFlowDoc": [f"{op['step']}. {op['description']}" for op in operations],
        "operations": operations,
        "verifyPoints": verify_points,
        "stopOnFailure": True,
        "skipVerifyOnFailure": True,
    }


def resolve_cases_dir(*, requirement_id: str | None = None, folder: str | None = None):
    if folder:
        return ensure_requirement_cases_dir(folder.strip())
    if requirement_id:
        req_folder = folder_for_requirement(requirement_id)
        if req_folder:
            return ensure_requirement_cases_dir(req_folder)
        raise ValueError(f"未知 requirement id: {requirement_id}")
    if LEGACY_CASES_DIR.is_dir():
        LEGACY_CASES_DIR.mkdir(parents=True, exist_ok=True)
        return LEGACY_CASES_DIR
    raise ValueError("须指定 --requirement 或 --folder 以确定用例写入目录")


def write_case_file(
    case: dict[str, Any],
    *,
    overwrite: bool = False,
    requirement_id: str | None = None,
    folder: str | None = None,
) -> str:
    case_id = str(case.get("id") or "").strip()
    if not case_id:
        raise ValueError("case.id 不能为空")

    req_from_source = None
    source = case.get("source")
    if isinstance(source, dict):
        req_from_source = source.get("requirementId")

    cases_dir = resolve_cases_dir(
        requirement_id=requirement_id or (str(req_from_source) if req_from_source else None),
        folder=folder,
    )
    path = cases_dir / f"{case_id}.json"
    if path.exists() and not overwrite:
        raise FileExistsError(f"用例已存在: {path}（加 --overwrite）")
    path.write_text(json.dumps(case, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path.resolve())
