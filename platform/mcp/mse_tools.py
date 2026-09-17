"""platform MCP — MSE 改参 / 发布 / 导出工具。"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MSE_DIR = _REPO_ROOT / "MSE"
if str(_MSE_DIR) not in sys.path:
    sys.path.insert(0, str(_MSE_DIR))

from mse.mutate import mse_publish_config, mse_save_config  # noqa: E402

_MSE_SET_SCHEMA = {
    "type": "object",
    "additionalProperties": True,
    "description": "增量 patch，等价 --set k=v（可多 key）",
}

_MSE_COMMON_PROPS = {
    "config_key": {"type": "string", "description": "MSE configKey，如 activityConfig.FamilyMonster"},
    "namespace": {
        "type": "string",
        "default": "voga-common",
        "description": "命名空间：voga-common / voga-activity / Application",
    },
    "cluster": {"type": "string", "default": "stage", "description": "集群，预上线=stage"},
    "region": {"type": "string", "default": "alpha"},
    "env": {"type": "string", "default": "alpha"},
    "app_key": {
        "type": "string",
        "description": "可选；未指定时按 config 项或默认 appKey 查询",
    },
}

MSE_SAVE_CONFIG_TOOL = {
    "name": "mse_save_config",
    "description": "MSE 改参：先读当前 configValue，再增量 patch；dry_run 默认 true，false 时写入 saveOrUpdate",
    "inputSchema": {
        "type": "object",
        "properties": {
            **_MSE_COMMON_PROPS,
            "set": _MSE_SET_SCHEMA,
            "dry_run": {"type": "boolean", "default": True},
        },
        "required": ["config_key", "set"],
        "additionalProperties": False,
    },
}

MSE_EXPORT_TO_WORKBOOK_TOOL = {
    "name": "mse_export_to_workbook",
    "description": (
        "MSE 配置同步到钉钉表格。"
        "activityConfig.FamilyMonster：export_kind=config 写「怪兽挑战配置」，"
        "lottery 写「怪兽挑战奖池配置」（10 列），both 两者都写。"
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "config_key": {
                "type": "string",
                "description": "MSE configKey，如 activityConfig.FamilyMonster",
            },
            "export_kind": {
                "type": "string",
                "enum": ["config", "lottery", "both"],
                "default": "config",
            },
            "namespace": {"type": "string", "default": "voga-common"},
            "cluster": {"type": "string", "default": "alpha"},
            "env": {"type": "string", "default": "alpha"},
            "region": {"type": "string", "default": "alpha"},
            "workbook": {
                "type": "string",
                "description": "钉钉表格 URL，省略则用默认家族怪兽表",
            },
            "dry_run": {"type": "boolean", "default": False},
        },
        "required": ["config_key"],
        "additionalProperties": False,
    },
}

MSE_PUBLISH_FROM_WORKBOOK_TOOL = {
    "name": "mse_publish_from_workbook",
    "description": (
        "从钉钉表格读取配置并保存/发布到 MSE。"
        "activityConfig.FamilyMonster：读 Sheet「怪兽挑战配置」（含 configValue JSON + 基础参数行），"
        "保存到 stage 后可选 confirm_publish 全量发布。"
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "workbook": {
                "type": "string",
                "description": "钉钉表格 URL 或 nodeId",
            },
            "config_key": {
                "type": "string",
                "default": "activityConfig.FamilyMonster",
            },
            "namespace": {"type": "string", "default": "voga-common"},
            "cluster": {"type": "string", "default": "stage"},
            "env": {"type": "string", "default": "alpha"},
            "region": {"type": "string", "default": "alpha"},
            "dry_run": {"type": "boolean", "default": True},
            "confirm_publish": {"type": "boolean", "default": False},
        },
        "required": ["workbook"],
        "additionalProperties": False,
    },
}

MSE_PUBLISH_CONFIG_TOOL = {
    "name": "mse_publish_config",
    "description": "MSE 发布：createPublishRecord → 跳过灰度 → 全量发布 → complete；须 confirm_publish=true",
    "inputSchema": {
        "type": "object",
        "properties": {
            **_MSE_COMMON_PROPS,
            "confirm_publish": {"type": "boolean", "default": False},
            "config_id": {"type": "integer", "description": "可选；默认从 config_key 查询"},
            "config_value": {"type": "string", "description": "可选；默认用当前集群 configValue"},
        },
        "required": ["config_key"],
        "additionalProperties": False,
    },
}


def _load_ctx_kwargs(arguments: dict[str, Any]) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    for key, arg_key in (
        ("cluster", "cluster"),
        ("region", "region"),
        ("env", "env"),
        ("app_key", "app_key"),
    ):
        value = arguments.get(arg_key)
        if value is not None and str(value).strip():
            kwargs[key] = str(value).strip()
    return kwargs


def call_mse_save_config(arguments: dict[str, Any]) -> dict[str, Any]:
    set_values = arguments.get("set")
    if not isinstance(set_values, dict) or not set_values:
        raise ValueError("set 必须是非空 object")
    from mse.mutate import load_context  # noqa: WPS433

    ctx = load_context(**_load_ctx_kwargs(arguments))
    return mse_save_config(
        str(arguments["config_key"]).strip(),
        set_values,
        name_space=str(arguments.get("namespace") or "voga-common").strip(),
        dry_run=bool(arguments.get("dry_run", True)),
        ctx=ctx,
    )


def call_mse_export_to_workbook(arguments: dict[str, Any]) -> dict[str, Any]:
    from mse_export import mse_export_to_workbook  # noqa: WPS433

    _require_str = str(arguments.get("config_key") or "").strip()
    if not _require_str:
        raise ValueError("缺少 config_key")
    workbook = arguments.get("workbook")
    return mse_export_to_workbook(
        config_key=_require_str,
        export_kind=str(arguments.get("export_kind") or "config"),
        namespace=str(arguments.get("namespace") or "voga-common").strip(),
        cluster=str(arguments.get("cluster") or "alpha").strip(),
        env=str(arguments.get("env") or "alpha").strip(),
        region=str(arguments.get("region") or "alpha").strip(),
        workbook=str(workbook).strip() if workbook else None,
        dry_run=bool(arguments.get("dry_run", False)),
    )


def call_mse_publish_from_workbook(arguments: dict[str, Any]) -> dict[str, Any]:
    workbook = str(arguments.get("workbook") or "").strip()
    if not workbook:
        raise ValueError("缺少 workbook")
    _gateway = _REPO_ROOT / "platform" / "dingtalk_gateway"
    if str(_gateway) not in sys.path:
        sys.path.insert(0, str(_gateway))
    from family_monster_workbook_to_mse import publish_family_monster_from_workbook  # noqa: WPS433

    config_key = str(arguments.get("config_key") or "activityConfig.FamilyMonster").strip()
    if config_key != "activityConfig.FamilyMonster":
        return {
            "ok": False,
            "error": f"暂仅支持 activityConfig.FamilyMonster，收到: {config_key!r}",
        }
    return publish_family_monster_from_workbook(
        workbook,
        namespace=str(arguments.get("namespace") or "voga-common").strip(),
        config_key=config_key,
        cluster=str(arguments.get("cluster") or "stage").strip(),
        env=str(arguments.get("env") or "alpha").strip(),
        region=str(arguments.get("region") or "alpha").strip(),
        confirm_publish=bool(arguments.get("confirm_publish", False)),
        dry_run=bool(arguments.get("dry_run", True)),
    )


def call_mse_publish_config(arguments: dict[str, Any]) -> dict[str, Any]:
    from mse.mutate import load_context  # noqa: WPS433

    ctx = load_context(**_load_ctx_kwargs(arguments))
    config_id = arguments.get("config_id")
    return mse_publish_config(
        str(arguments["config_key"]).strip(),
        name_space=str(arguments.get("namespace") or "voga-common").strip(),
        confirm_publish=bool(arguments.get("confirm_publish", False)),
        config_id=int(config_id) if config_id is not None else None,
        config_value=str(arguments["config_value"]).strip() if arguments.get("config_value") else None,
        ctx=ctx,
    )
