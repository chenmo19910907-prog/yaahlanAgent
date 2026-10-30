"""Web 设置页：重启 Web Agent / 钉钉网关。"""

from __future__ import annotations

import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

_gateway = Path(__file__).resolve().parents[1] / "dingtalk_gateway"
if str(_gateway) not in sys.path:
    sys.path.insert(0, str(_gateway))

from env_loader import GATEWAY_DIR  # noqa: E402
from web_agent_restart import (  # noqa: E402
    _count_active_worker_runs,
    force_restart_web_agent,
)

GATEWAY_CTL = GATEWAY_DIR / "gateway_ctl.sh"
GATEWAY_RESTART_TIMEOUT_S = 90.0
WEB_AGENT_RESTART_DELAY_S = 0.6

VALID_TARGETS = frozenset({"web_agent", "dingtalk_gateway"})


@dataclass(frozen=True)
class ServiceRestartResult:
    ok: bool
    message: str
    target: str
    silent: bool


def execute_service_restart(*, target: str, silent: bool) -> ServiceRestartResult:
    t = (target or "").strip().lower()
    if t not in VALID_TARGETS:
        return ServiceRestartResult(
            ok=False,
            message="target 须为 web_agent 或 dingtalk_gateway",
            target=t,
            silent=bool(silent),
        )
    if t == "web_agent":
        return _restart_web_agent(silent=bool(silent))
    return _restart_dingtalk_gateway(silent=bool(silent))


def _restart_web_agent(*, silent: bool) -> ServiceRestartResult:
    del silent  # Web Agent 重启不向钉钉群推送启停通知
    active = _count_active_worker_runs()
    if active > 0:
        return ServiceRestartResult(
            ok=False,
            message=f"仍有 {active} 个 Agent 任务执行中，请待任务结束后再重启。",
            target="web_agent",
            silent=True,
        )

    def _worker() -> None:
        time.sleep(WEB_AGENT_RESTART_DELAY_S)
        force_restart_web_agent()

    threading.Thread(
        target=_worker,
        daemon=True,
        name="web-api-restart-web-agent",
    ).start()
    return ServiceRestartResult(
        ok=True,
        message="Web Agent 重启已提交，约数秒内完成。",
        target="web_agent",
        silent=True,
    )


def _restart_dingtalk_gateway(*, silent: bool) -> ServiceRestartResult:
    if not GATEWAY_CTL.is_file():
        return ServiceRestartResult(
            ok=False,
            message="未找到 gateway_ctl.sh，无法重启钉钉网关。",
            target="dingtalk_gateway",
            silent=silent,
        )
    cmd = "silent-restart" if silent else "restart"
    try:
        proc = subprocess.run(
            ["/bin/bash", str(GATEWAY_CTL), cmd],
            cwd=str(GATEWAY_DIR),
            capture_output=True,
            text=True,
            timeout=GATEWAY_RESTART_TIMEOUT_S,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return ServiceRestartResult(
            ok=False,
            message=f"钉钉网关重启超时（>{int(GATEWAY_RESTART_TIMEOUT_S)} 秒）。",
            target="dingtalk_gateway",
            silent=silent,
        )
    except OSError as exc:
        return ServiceRestartResult(
            ok=False,
            message=str(exc),
            target="dingtalk_gateway",
            silent=silent,
        )

    combined = (proc.stdout or "") + (proc.stderr or "")
    tail = "\n".join(line for line in combined.strip().splitlines() if line.strip())[-400:]
    if proc.returncode != 0:
        detail = tail or f"exit={proc.returncode}"
        return ServiceRestartResult(
            ok=False,
            message=f"钉钉网关重启失败：{detail}",
            target="dingtalk_gateway",
            silent=silent,
        )
    mode = "静默重启" if silent else "重启"
    detail = tail.splitlines()[-1] if tail else f"{mode}完成"
    return ServiceRestartResult(
        ok=True,
        message=f"钉钉网关已{mode}。{detail}",
        target="dingtalk_gateway",
        silent=silent,
    )


def format_service_restart_summary(outcome: ServiceRestartResult) -> str:
    if outcome.target == "web_agent":
        label = "Web Agent"
    else:
        label = "钉钉网关"
    mode = "静默" if outcome.silent else "普通"
    status = "成功" if outcome.ok else "失败"
    return f"{label} {mode}重启{status}：{outcome.message}"
