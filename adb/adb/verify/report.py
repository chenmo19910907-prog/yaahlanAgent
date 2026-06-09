"""统一从执行结果计算 CLI 退出码。"""

from __future__ import annotations

from typing import Any


def _verify_failed(result: dict[str, Any], key: str, failed_flag: str | None = None) -> bool:
    verify = result.get(key)
    if isinstance(verify, dict) and not verify.get("ok"):
        return True
    if failed_flag and result.get(failed_flag):
        return True
    return False


def chain_result_exit_code(result: dict[str, object]) -> int:
    """macro/chain/run 共用：splash / popupGate / logcat 失败 → 3。"""
    r = result  # type: ignore[assignment]
    if _verify_failed(r, "splashVerify", "splashVerifyFailed"):
        return 3
    gate = r.get("popupGate")
    if isinstance(gate, dict) and (gate.get("blocked") or not gate.get("ok")):
        return 3
    if r.get("popupGateFailed"):
        return 3
    if _verify_failed(r, "logcatVerify", "logcatVerifyFailed"):
        return 3
    return 0
