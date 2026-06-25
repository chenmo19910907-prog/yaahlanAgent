"""MOA 能力入库意图识别：避免误走 MOA 探活快捷路由。"""

from __future__ import annotations

import re

from route_patterns import MOA_CHECK_RE

_MOA_REGISTRY_INTENT_RE = re.compile(
    r"(?:"
    r"(?:入库|登记|注册|同步).{0,24}(?:MOA|moa|模板|registry|能力清单)|"
    r"(?:MOA|moa).{0,32}(?:入库|登记|注册|sync_registry)|"
    r"sync_registry|generate_index\.py"
    r")",
    re.I,
)


def looks_like_moa_registry_intent(text: str) -> bool:
    """用户是否在要求把 MOA 模板/能力登记进 registry（非探活）。"""
    t = (text or "").strip()
    if not t:
        return False
    return bool(_MOA_REGISTRY_INTENT_RE.search(t))


def is_explicit_moa_check_command(text: str) -> bool:
    """整条消息是否为 MOA 探活口令。"""
    return bool(MOA_CHECK_RE.match((text or "").strip()))


def should_route_moa_check(text: str) -> bool:
    """是否应走 MOA 探活快捷路由（入库类任务一律排除）。"""
    t = (text or "").strip()
    if not is_explicit_moa_check_command(t):
        return False
    return not looks_like_moa_registry_intent(t)


def moa_registry_instruction() -> str:
    return (
        "【MOA 入库任务】用户要求把 MOA 接口登记进仓库（非探活）。\n"
        "**禁止**执行 MOA检查、MOA探活、doctor、credential_probe、"
        "moa_execute --vip-query-current 探活或 test_all。\n"
        "**禁止**用业务接口试跑代替入库。\n"
        "标准流程：依据附图/描述在 MOA/templates/ 建 JSON（含 key，可选 _registry）"
        "→ python3 MOA/scripts/sync_registry.py "
        "→ 确认 MOA/config/registry.json 与 MOA/使用方法.md。\n"
        "回复须含：能力名、模板路径、registry id、命令示例。"
    )
