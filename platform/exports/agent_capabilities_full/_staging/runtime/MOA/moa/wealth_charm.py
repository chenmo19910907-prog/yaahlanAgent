"""财富/魅力等级查询结果解析。"""

from __future__ import annotations

from typing import Any


def build_wealth_charm_query_expr(method: str, user_id: str) -> str:
    method = str(method).strip()
    user_id = str(user_id).strip()
    if not method:
        raise ValueError("wealth/charm query method 不能为空")
    if not user_id:
        raise ValueError("查询财富/魅力等级时 userId 不能为空")
    return f'context.getBean("userWealthAndCharmServiceImpl").{method}("{user_id}")'


def parse_charm_info_summary(user_id: str, inner_result: Any) -> dict[str, Any]:
    if not isinstance(inner_result, dict):
        raise RuntimeError("无法解析魅力等级业务返回 result（不是 object）")
    return {
        "userId": str(user_id),
        "level": inner_result.get("lv"),
        "charmValue": inner_result.get("charmValue"),
        "nextLevelNeedScore": inner_result.get("nextLevelNeedScore"),
        "hide": inner_result.get("hide"),
    }


def parse_wealth_info_summary(user_id: str, inner_result: Any) -> dict[str, Any]:
    if not isinstance(inner_result, dict):
        raise RuntimeError("无法解析财富等级业务返回 result（不是 object）")
    return {
        "userId": str(user_id),
        "level": inner_result.get("lv"),
        "userWealthValue": inner_result.get("userWealthValue"),
        "curLevelWealthValue": inner_result.get("curLevelWealthValue"),
        "nextLevelWealthValue": inner_result.get("nextLevelWealthValue"),
        "nextLevelNeedScore": inner_result.get("nextLevelNeedScore"),
        "hide": inner_result.get("hide"),
    }
