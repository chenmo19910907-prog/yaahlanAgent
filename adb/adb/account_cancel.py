"""账号注销：App 内预注销（AI）与 MOA 确认注销彼此独立。"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from .ai_operate import prepare_vision_cycle
from .device import AdbError

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MOA_TEMPLATE = _REPO_ROOT / "MOA/templates/用户-注销账号.json"
_MOA_EXECUTE = _REPO_ROOT / "MOA/moa_execute.py"

CLIENT_CANCEL_WORKFLOW = [
    "Me → 设置（齿轮）→ Account security → 底部 Delete account",
    "注销说明页等 15s 冷静期 → 勾选余额清空 → Delete Account",
    "温馨提示 → 确定 → 再次确认「确定并退出」（可 `--skip cancel_confirm_dialogs`）",
    "成功：activity hint=login；toast 账号无法注销则流程结束",
    "Me 弹窗读图点 Cancel，勿 BACK / force-stop",
]


def prepare_client_cancel(
    *,
    serial: str,
    screenshot_dir: Path,
    max_screenshots: int,
    max_edge: int | None = 1170,
    note: str | None = None,
) -> dict[str, Any]:
    """App 内预注销：仅返回 AI 读图 walkthrough（与 MOA 无关）。"""
    out = prepare_vision_cycle(
        goal="cancel_account",
        serial=serial,
        screenshot_dir=screenshot_dir,
        max_screenshots=max_screenshots,
        max_edge=max_edge,
        note=note,
    )
    out["phase"] = "client_ui"
    out["workflow"] = list(CLIENT_CANCEL_WORKFLOW)
    out["agentHint"] = (
        "读 screenshot 在 App 内走完注销预申请流程。"
        + (f" {note}" if note else "")
    )
    return out


def confirm_cancel_via_moa(user_id: str) -> dict[str, Any]:
    """
    MOA cancelUserReal：收到「确认注销」提示词即执行，**不校验** App/登录页状态。
    """
    uid = str(user_id).strip()
    if not uid:
        raise ValueError("userId 不能为空")

    if not _MOA_TEMPLATE.is_file():
        raise AdbError(f"缺少 MOA 模板: {_MOA_TEMPLATE}")
    if not _MOA_EXECUTE.is_file():
        raise AdbError(f"缺少 MOA 入口: {_MOA_EXECUTE}")

    cmd = [
        "python3",
        str(_MOA_EXECUTE),
        "--payload-file",
        str(_MOA_TEMPLATE),
        "--cancel-user",
        uid,
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(_REPO_ROOT),
            timeout=45,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise AdbError(f"MOA 注销超时: {exc}") from exc

    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    moa_body: dict[str, Any] | None = None
    if stdout:
        try:
            parsed = json.loads(stdout)
            if isinstance(parsed, dict):
                moa_body = parsed
        except json.JSONDecodeError:
            moa_body = {"rawStdout": stdout[:2000]}

    ok = proc.returncode == 0
    ec = moa_body.get("ec") if moa_body else None
    if ec is not None and ec != 0:
        ok = False

    return {
        "ok": ok,
        "action": "moaCancelUser",
        "userId": uid,
        "moaExitCode": proc.returncode,
        "moaResponse": moa_body,
        "moaStderr": stderr[-1500:] if stderr else None,
        "agentHint": (
            f"MOA 确认注销成功：cancelUserReal({uid})。"
            if ok
            else (
                f"MOA 确认注销失败（exit={proc.returncode}）。"
                "读 moaStderr / moaResponse。"
            )
        ),
    }
