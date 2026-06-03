"""ADB 设备检测与命令执行。"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass


class AdbError(RuntimeError):
    pass


@dataclass(frozen=True)
class AdbDevice:
    serial: str
    state: str


def run_adb(
    args: list[str],
    *,
    serial: str | None = None,
    timeout_s: float = 60.0,
    check: bool = True,
) -> subprocess.CompletedProcess[bytes]:
    cmd = ["adb"]
    if serial:
        cmd.extend(["-s", serial])
    cmd.extend(args)
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout_s,
            check=check,
        )
    except subprocess.TimeoutExpired as e:
        raise AdbError(f"adb 命令超时: {' '.join(cmd)}") from e
    except FileNotFoundError as e:
        raise AdbError("未找到 adb，请安装 Android platform-tools 并加入 PATH") from e
    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or b"").decode("utf-8", errors="replace").strip()
        raise AdbError(f"adb 失败: {' '.join(cmd)}\n{stderr}") from e


def list_devices(*, ready_only: bool = True) -> list[AdbDevice]:
    proc = run_adb(["devices"], check=True)
    text = proc.stdout.decode("utf-8", errors="replace")
    devices: list[AdbDevice] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("List of devices"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        serial, state = parts[0], parts[1]
        if ready_only and state != "device":
            continue
        devices.append(AdbDevice(serial=serial, state=state))
    return devices


def require_device(serial: str | None = None) -> str:
    """返回可用设备 serial；未指定且仅一台时自动选用。"""
    if serial:
        matched = [d for d in list_devices(ready_only=False) if d.serial == serial]
        if not matched:
            raise AdbError(f"未找到设备: {serial}")
        if matched[0].state != "device":
            raise AdbError(f"设备 {serial} 状态为 {matched[0].state}，需为 device")
        return serial

    devices = list_devices()
    if not devices:
        raise AdbError(
            "没有已连接的 adb 设备。请 USB 连接并开启调试，或执行 adb connect <ip>:5555"
        )
    if len(devices) > 1:
        serials = ", ".join(d.serial for d in devices)
        raise AdbError(f"连接了多台设备，请用 --serial 指定其一: {serials}")
    return devices[0].serial


def display_size(serial: str | None) -> tuple[int, int]:
    proc = run_adb(["shell", "wm", "size"], serial=serial, check=True)
    text = proc.stdout.decode("utf-8", errors="replace")
    match = re.search(r"Physical size:\s*(\d+)x(\d+)", text)
    if not match:
        match = re.search(r"Override size:\s*(\d+)x(\d+)", text)
    if not match:
        raise AdbError(f"无法解析屏幕尺寸: {text.strip()}")
    return int(match.group(1)), int(match.group(2))
