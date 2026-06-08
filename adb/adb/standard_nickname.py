"""QA 测试号标准昵称：133111111XX → CXX，133111112XX → C2XX。"""

from __future__ import annotations

import re

_PREFIX_111 = "133111111"
_PREFIX_112 = "133111112"


def standard_nickname(phone: str) -> str:
    """
    按 QA 手机号段生成标准昵称。

    - ``133111111XX`` → ``CXX``（如 13311111157 → C57）
    - ``133111112XX`` → ``C2XX``（如 13311111211 → C211）
    - 其他号码回退为 ``C`` + 末两位
    """
    digits = re.sub(r"\D", "", str(phone or "").strip())
    if not digits:
        raise ValueError("phone 不能为空")
    last2 = digits[-2:]
    if digits.startswith(_PREFIX_112):
        return f"C2{last2}"
    if digits.startswith(_PREFIX_111):
        return f"C{last2}"
    return f"C{last2}"
