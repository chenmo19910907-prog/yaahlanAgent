"""Web/钉钉 Agent：加入家族仅走 Admin 标准接口，禁止 MOA 后门。"""

from __future__ import annotations

import json
import os
import re
from typing import Any

_FAMILY_JOIN_INTENT_RE = re.compile(
    r"(加入家族|添加入族|add[- ]?family[- ]?member|家族.*添加成员|把.*加入家族|批量.*入族|入族)",
    re.I,
)

_JOIN_FAMILY_BACKDOOR_RE = re.compile(r"joinFamily\s*\(", re.I)

_AGENT_BATCH_KEY_ENVS = ("WEB_AGENT_BATCH_KEY", "DINGTALK_AGENT_BATCH_KEY")


def looks_like_family_join_request(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    return bool(_FAMILY_JOIN_INTENT_RE.search(t))


def gateway_family_join_rule_line() -> str:
    return (
        "**加入家族（硬性约束）**：把用户加入家族 / 批量入族时，"
        "**仅允许** `python3 Admin/admin_execute.py --add-family-member "
        "--family-id <familyId> --family-user-id <userId>`。"
        "**禁止** MOA 测试后门（如 `voga-mts-user-backdoor` 的 `joinFamily(...)`、"
        "复用 `家族-增加基金贡献值` 等模板）。"
        "验收可用 MOA `家族-按userId查家族id`。"
        "若 `Admin/.env.local` 缺少 `ADMIN_SSO_TOKEN` / `ADMIN_YAAHLAN_JWT`，"
        "**提示补鉴权**，禁止降级走后门。"
    )


def family_join_prompt_hint(text: str) -> str | None:
    if not looks_like_family_join_request(text):
        return None
    return (
        "【加入家族 · 硬性约束】本任务**禁止** MOA 后门 "
        "`familyService.joinFamily(...)` / `voga-mts-user-backdoor`。"
        "**必须**执行："
        "`python3 Admin/admin_execute.py --add-family-member "
        "--family-id <familyId> --family-user-id <userId>`。"
        "Admin 鉴权缺失时**提示用户补** `ADMIN_SSO_TOKEN` / `ADMIN_YAAHLAN_JWT`，"
        "**不得**改用 MOA 模板或手写 backdoor payload。"
        "验收可用 MOA `家族-按userId查家族id`。"
    )


def agent_context_blocks_family_backdoor() -> bool:
    return any(str(os.environ.get(key) or "").strip() for key in _AGENT_BATCH_KEY_ENVS)


def payload_uses_family_join_backdoor(payload: dict[str, Any]) -> bool:
    url = str(payload.get("url") or "")
    if "user-backdoor" not in url:
        return False
    blob_parts: list[str] = [url, json.dumps(payload.get("params") or [], ensure_ascii=False)]
    blob = "\n".join(blob_parts)
    return bool(_JOIN_FAMILY_BACKDOOR_RE.search(blob))


def family_join_backdoor_block_message() -> str:
    return (
        "Agent 场景禁止 MOA 后门 joinFamily；请改用 "
        "python3 Admin/admin_execute.py --add-family-member "
        "--family-id <familyId> --family-user-id <userId>"
    )
