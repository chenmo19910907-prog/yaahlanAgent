"""Web/钉钉 Agent：加入家族仅走 Admin 标准接口，禁止 MOA 后门。"""

from __future__ import annotations

import re

_FAMILY_JOIN_INTENT_RE = re.compile(
    r"(加入家族|添加入族|add[- ]?family[- ]?member|家族.*添加成员|把.*加入家族|批量.*入族|入族)",
    re.I,
)


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
