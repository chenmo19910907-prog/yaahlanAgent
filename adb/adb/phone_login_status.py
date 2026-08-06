"""MOA queryLoginStatusV2：手机号是否已注册 / 关联 userId。"""

from __future__ import annotations

import json
import subprocess
from typing import Any

from .device import AdbError
from .project_paths import moa_execute_path, moa_template, repo_root

_MOA_TEMPLATE = moa_template("用户-按手机号查userId.json")


def query_phone_login_status(
    phone: str,
    *,
    area_code: str = "86",
) -> dict[str, Any]:
    """
    按手机号查登录态。registered=false 且 userId 为空 → 走注册；否则走登录。
    """
    mobile = str(phone or "").strip()
    if not mobile:
        raise ValueError("phone 不能为空")

    if not _MOA_TEMPLATE.is_file():
        raise AdbError(f"缺少 MOA 模板: {_MOA_TEMPLATE}")
    execute = moa_execute_path()
    if not execute.is_file():
        raise AdbError(f"缺少 MOA 入口: {execute}")

    cmd = [
        "python3",
        str(execute),
        "--payload-file",
        str(_MOA_TEMPLATE),
        "--query-user-by-phone",
        mobile,
        "--phone-area-code",
        str(area_code).lstrip("+"),
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(repo_root()),
            timeout=25,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise AdbError(f"MOA 查手机号登录态超时: {exc}") from exc

    stderr = (proc.stderr or "").strip()
    if proc.returncode != 0:
        raise AdbError(
            f"MOA queryLoginStatusV2 失败（exit={proc.returncode}）"
            + (f": {stderr[-500:]}" if stderr else "")
        )

    stdout = (proc.stdout or "").strip()
    if not stdout:
        raise AdbError("MOA queryLoginStatusV2 无 stdout")

    try:
        body = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise AdbError(f"MOA 返回非 JSON: {stdout[:200]}") from exc

    if not isinstance(body, dict):
        raise AdbError("MOA 返回须为 object")

    registered = bool(body.get("registered"))
    user_id = body.get("userId")
    uid = str(user_id).strip() if user_id is not None and str(user_id).strip() else None
    if uid and not registered:
        registered = True

    return {
        "ok": True,
        "phone": mobile,
        "areaCode": str(body.get("areaCode") or area_code),
        "fullNumber": body.get("fullNumber") or f"+{area_code}{mobile}",
        "registered": registered,
        "userId": uid,
        "route": "login" if registered else "register",
        "moaResponse": body,
    }
