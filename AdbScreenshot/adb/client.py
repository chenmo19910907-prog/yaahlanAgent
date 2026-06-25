"""ADB 命令封装。"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass

from .config import adb_binary


class AdbError(RuntimeError):
    """ADB 命令执行失败。"""


@dataclass(frozen=True)
class AdbDevice:
    serial: str
    state: str


def _run_adb(args: list[str], *, timeout_sec: float = 30.0) -> subprocess.CompletedProcess[bytes]:
    command = [adb_binary(), *args]
    try:
        return subprocess.run(
            command,
            capture_output=True,
            timeout=timeout_sec,
            check=False,
        )
    except FileNotFoundError as exc:
        raise AdbError(
            f"未找到 adb 命令: {adb_binary()}。请安装 Android Platform Tools 并加入 PATH，"
            "或在 AdbScreenshot/.env.local 设置 ADB_BINARY。"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise AdbError(f"adb 命令超时: {' '.join(command)}") from exc


def _decode_stderr(result: subprocess.CompletedProcess[bytes]) -> str:
    if not result.stderr:
        return ""
    return result.stderr.decode("utf-8", errors="replace").strip()


def list_devices() -> list[AdbDevice]:
    result = _run_adb(["devices", "-l"])
    if result.returncode != 0:
        raise AdbError(_decode_stderr(result) or "adb devices 执行失败")

    devices: list[AdbDevice] = []
    lines = result.stdout.decode("utf-8", errors="replace").splitlines()
    for line in lines[1:]:
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split()
        if len(parts) < 2:
            continue
        devices.append(AdbDevice(serial=parts[0], state=parts[1]))
    return devices


def connect_wireless(address: str) -> str:
    normalized = address.strip()
    if not normalized:
        raise ValueError("无线地址不能为空")

    result = _run_adb(["connect", normalized], timeout_sec=15.0)
    output = result.stdout.decode("utf-8", errors="replace").strip()
    error = _decode_stderr(result)
    message = output or error
    if result.returncode != 0:
        raise AdbError(message or f"adb connect {normalized} 失败")

    lowered = message.casefold()
    if "unable to connect" in lowered or "failed to connect" in lowered:
        raise AdbError(message)

    serial = _resolve_serial(normalized)
    return serial


def disconnect_wireless(address: str | None = None) -> str:
    args = ["disconnect"] if address is None else ["disconnect", address.strip()]
    result = _run_adb(args, timeout_sec=15.0)
    output = result.stdout.decode("utf-8", errors="replace").strip()
    if result.returncode != 0:
        raise AdbError(_decode_stderr(result) or output or "adb disconnect 失败")
    return output


def _resolve_serial(target: str) -> str:
    normalized = target.strip()
    devices = list_devices()
    for device in devices:
        if device.serial == normalized and device.state == "device":
            return device.serial

    for device in devices:
        if device.state != "device":
            continue
        if normalized in device.serial:
            return device.serial

    online = [item.serial for item in devices if item.state == "device"]
    raise AdbError(
        f"未找到可用设备: {normalized}。当前在线: {online or '无'}。"
        "请确认手机已开启无线调试，且电脑与手机网络互通。"
    )


def capture_screen(serial: str) -> bytes:
    resolved = _resolve_serial(serial)
    result = _run_adb(["-s", resolved, "exec-out", "screencap", "-p"], timeout_sec=45.0)
    if result.returncode != 0:
        raise AdbError(_decode_stderr(result) or f"截屏失败: {resolved}")

    if not result.stdout:
        raise AdbError(f"截屏结果为空: {resolved}")

    if not result.stdout.startswith(b"\x89PNG\r\n\x1a\n"):
        raise AdbError(f"截屏返回非 PNG 数据: {resolved}")

    return result.stdout
