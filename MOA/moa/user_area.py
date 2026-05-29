"""用户大区（changeAreaForTest）常量与校验。"""

from __future__ import annotations

# 大区简称与说明（与后台/MOA 一致）
USER_AREA_CODES: dict[str, dict[str, str]] = {
    "MENA": {"name": "中东区", "timezone": "UTC+3", "time_label": "沙特时间"},
    "TR": {"name": "土区", "timezone": "UTC+3", "time_label": "土耳其时间"},
    "RU": {"name": "俄区", "timezone": "UTC+5", "time_label": "哈萨克斯坦时间"},
    "SEA": {"name": "南洋区", "timezone": "UTC+8", "time_label": "北京时间"},
    "SA": {"name": "南亚区", "timezone": "UTC+5", "time_label": "巴基斯坦时间"},
    "CN": {
        "name": "中国区",
        "timezone": "UTC+8",
        "time_label": "北京时间",
        "note": "仅后台修改，隔离测试使用",
    },
}


def normalize_user_area(area: str) -> str:
    code = str(area or "").strip().upper()
    if not code:
        raise ValueError("大区代码不能为空")
    if code not in USER_AREA_CODES:
        supported = ", ".join(sorted(USER_AREA_CODES))
        raise ValueError(f"不支持的大区代码: {area}，可选: {supported}")
    return code


def describe_user_area(area: str) -> dict[str, str]:
    code = normalize_user_area(area)
    meta = dict(USER_AREA_CODES[code])
    meta["code"] = code
    return meta
