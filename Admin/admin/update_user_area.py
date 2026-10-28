"""MDP Nova 修改用户大区（userAdmin/updateUserArea）请求体与响应解析。"""

from __future__ import annotations

from typing import Any

from .gift import mdp_gift_success as mdp_user_admin_success


def build_update_user_area_body(
    *,
    user_id: str,
    before_area: str,
    after_area: str,
    app_id: int = 2005,
) -> dict[str, object]:
    uid = str(user_id or "").strip()
    before = str(before_area or "").strip().upper()
    after = str(after_area or "").strip().upper()
    if not uid:
        raise ValueError("update-user-area-user-id 不能为空")
    if not before:
        raise ValueError("beforeArea 不能为空（可省略 --update-user-area-before，将自动 queryUserDetail 读取）")
    if not after:
        raise ValueError("必须提供 --update-user-area-after（目标大区）")
    if before == after:
        raise ValueError(f"目标大区与当前大区相同（{before}），无需修改")
    return {
        "appId": int(app_id),
        "userId": uid,
        "beforeArea": before,
        "afterArea": after,
    }


def parse_update_user_area_summary(
    resp: dict[str, Any],
    *,
    user_id: str,
    before_area: str,
    after_area: str,
) -> dict[str, Any]:
    ok = mdp_user_admin_success(resp.get("ec"))
    return {
        "userId": str(user_id).strip(),
        "beforeArea": str(before_area).strip().upper(),
        "afterArea": str(after_area).strip().upper(),
        "success": ok,
        "ec": resp.get("ec"),
        "em": resp.get("em"),
        "data": resp.get("data"),
    }
