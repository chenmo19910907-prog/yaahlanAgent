"""日志脱敏：截断并抹掉 token / cookie 等敏感片段。"""

from __future__ import annotations

import re

_SENSITIVE_RE = re.compile(
    r"(?i)(cookie|token|secret|api[_-]?key|authorization|password|access_token)"
    r"[\s\"'=:]+[^\s,;\"']{8,}"
)
_BEARER_RE = re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-+/=]{4,}")
_LONG_HEX_RE = re.compile(r"\b[a-f0-9]{32,}\b", re.I)


def redact_for_log(text: str, *, max_len: int = 120) -> str:
    """供 logger 使用的安全摘要。"""
    body = (text or "").replace("\n", " ").strip()
    body = _SENSITIVE_RE.sub(r"\1=***", body)
    body = _BEARER_RE.sub("Bearer ***", body)
    body = _LONG_HEX_RE.sub("***", body)
    if len(body) > max_len:
        return body[: max_len - 1] + "…"
    return body
