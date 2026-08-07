"""Web Agent 外部 Agent 配置（settings 勾选 + prompt 注入）。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CONFIG_PATH = Path(__file__).resolve().parent / "config.json"


def load_web_config() -> dict[str, Any]:
    if not CONFIG_PATH.is_file():
        return {}
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def external_agents_from_config(cfg: dict[str, Any] | None = None) -> list[dict[str, str | bool]]:
    data = cfg if cfg is not None else load_web_config()
    raw = data.get("externalAgents")
    agents: list[dict[str, str | bool]] = []
    if not isinstance(raw, list):
        return agents
    for item in raw:
        if not isinstance(item, dict):
            continue
        agent_id = str(item.get("id") or "").strip()
        if not agent_id:
            continue
        agents.append(
            {
                "id": agent_id,
                "label": str(item.get("label") or agent_id).strip(),
                "description": str(item.get("description") or "").strip(),
                "url": str(item.get("url") or "").strip(),
                "queryScript": str(item.get("queryScript") or "").strip(),
                "tokenEnvKey": str(item.get("tokenEnvKey") or "").strip(),
                "targetEnvironment": str(item.get("targetEnvironment") or "").strip().lower(),
                "defaultEnabled": bool(item.get("defaultEnabled", False)),
            }
        )
    return agents


def default_enabled_external_agent_ids(cfg: dict[str, Any] | None = None) -> list[str]:
    return [
        str(item["id"])
        for item in external_agents_from_config(cfg)
        if item.get("defaultEnabled")
    ]


def resolve_enabled_external_agent_ids(
    raw: object,
    cfg: dict[str, Any] | None = None,
) -> list[str]:
    allowed = {str(item["id"]) for item in external_agents_from_config(cfg)}
    if not allowed:
        return []
    if raw is None:
        return default_enabled_external_agent_ids(cfg)
    if not isinstance(raw, list):
        return default_enabled_external_agent_ids(cfg)
    resolved: list[str] = []
    seen: set[str] = set()
    for item in raw:
        agent_id = str(item or "").strip()
        if not agent_id or agent_id not in allowed or agent_id in seen:
            continue
        seen.add(agent_id)
        resolved.append(agent_id)
    return resolved


def external_agents_by_id(cfg: dict[str, Any] | None = None) -> dict[str, dict[str, str | bool]]:
    return {str(item["id"]): item for item in external_agents_from_config(cfg)}
