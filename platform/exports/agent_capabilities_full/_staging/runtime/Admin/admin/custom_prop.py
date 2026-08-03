"""定制道具（头像框等）后台接口响应解析。"""

from __future__ import annotations

from typing import Any

DEFAULT_PROP_TYPE = "HEADER_FRAME"


def parse_reset_custom_prop_cooldown_summary(
    resp: dict[str, Any],
    *,
    remote_id: str,
    prop_type: str,
) -> dict[str, Any]:
    return {
        "remoteId": remote_id,
        "propType": prop_type,
        "ec": resp.get("ec"),
        "em": resp.get("em"),
        "data": resp.get("data"),
        "success": resp.get("success") is True or str(resp.get("ec")) == "200",
    }
