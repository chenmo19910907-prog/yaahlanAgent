"""钻石账户查询结果解析。"""

from __future__ import annotations

from typing import Any


def parse_diamond_account_summary(user_id: str, inner_result: Any) -> dict[str, Any]:
    if not isinstance(inner_result, dict):
        raise RuntimeError("无法解析钻石账户业务返回 result（不是 object）")
    return {
        "userId": str(user_id),
        "diamonds": inner_result.get("diamonds"),
        "coinCount": inner_result.get("coinCount"),
        "canExchangeDiamond": inner_result.get("canExchangeDiamond"),
        "income": inner_result.get("income"),
        "numberIncome": inner_result.get("numberIncome"),
        "canCash": inner_result.get("canCash"),
    }
