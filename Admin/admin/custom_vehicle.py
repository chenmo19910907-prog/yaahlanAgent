"""定制座驾后台接口响应解析。"""

from __future__ import annotations

from typing import Any


def parse_reset_custom_vehicle_cooldown_summary(resp: dict[str, Any], *, remote_id: str) -> dict[str, Any]:
    return {
        "remoteId": remote_id,
        "ec": resp.get("ec"),
        "em": resp.get("em"),
        "data": resp.get("data"),
        "success": resp.get("success") is True or str(resp.get("ec")) == "200",
    }
