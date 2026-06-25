"""MSE namespace 别名与 API 参数映射。"""

from __future__ import annotations

PRIVATE_APPLICATION_LABEL = "Application（私有）"

# MSE 控制台「私有/application」在 API 中 nameSpace 为空字符串
_PRIVATE_APPLICATION_ALIASES = frozenset(
    {
        "application",
        "Application",
        "private/application",
        "私有/application",
        "私有",
    }
)


def resolve_namespace(name_space: str) -> tuple[str, str]:
    """返回 (API nameSpace, 展示用 namespace 标签)。"""
    raw = (name_space or "").strip()
    if raw in _PRIVATE_APPLICATION_ALIASES:
        return "", PRIVATE_APPLICATION_LABEL
    return raw, raw or "-"


def is_private_application(name_space: str) -> bool:
    return (name_space or "").strip() in _PRIVATE_APPLICATION_ALIASES
