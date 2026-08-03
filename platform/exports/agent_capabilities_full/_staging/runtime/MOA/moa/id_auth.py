"""实名认证相关解析。"""

from __future__ import annotations

import json
from typing import Any


def extract_latest_id_auth_reason_list(inner_result: Any) -> list[str]:
    if not isinstance(inner_result, dict):
        raise RuntimeError("无法解析实名认证业务返回 result（不是 object）")
    data = inner_result.get("data")
    if not isinstance(data, dict):
        return []
    lst = data.get("list")
    if not isinstance(lst, list) or not lst:
        return []

    reason = lst[0].get("reason")
    if reason is None:
        return []
    if isinstance(reason, list):
        return [str(x) for x in reason if str(x).strip()]
    if isinstance(reason, str):
        s = reason.strip()
        if not s:
            return []
        try:
            parsed = json.loads(s)
            if isinstance(parsed, list):
                return [str(x) for x in parsed if str(x).strip()]
        except json.JSONDecodeError:
            pass
        return [s]
    return [str(reason)]
