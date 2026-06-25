"""无线设备登记表：资产编号 / mmuid → adb 地址。"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from typing import Iterable

from .config import default_wireless_registry_path, package_dir


@dataclass(frozen=True)
class WirelessDevice:
    asset_id: str
    name: str
    wireless: str
    mmuid: str = ""
    mmuidv3: str = ""
    serial: str = ""
    note: str = ""

    def resolved_serial(self) -> str:
        return (self.serial or self.wireless).strip()


def _normalize(value: str) -> str:
    return value.strip().casefold()


def _risk_test_devices_module():
    risk_dir = os.path.join(os.path.dirname(package_dir()), "Risk")
    if risk_dir not in sys.path:
        sys.path.insert(0, risk_dir)
    from risk.test_devices import find_devices, load_test_devices

    return load_test_devices, find_devices


def load_wireless_devices(registry_path: str | None = None) -> list[WirelessDevice]:
    path = os.path.expanduser(registry_path or default_wireless_registry_path())
    if not os.path.isfile(path):
        raise ValueError(
            f"无线设备登记表不存在: {path}\n"
            f"请复制 wireless_devices.example.json 为 wireless_devices.json 并填写无线地址。"
        )

    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)

    raw_devices = data.get("devices") if isinstance(data, dict) else data
    if not isinstance(raw_devices, list):
        raise ValueError("登记表格式错误: 需要 devices 数组")

    devices: list[WirelessDevice] = []
    for item in raw_devices:
        if not isinstance(item, dict):
            continue
        wireless = str(item.get("wireless") or "").strip()
        serial = str(item.get("serial") or "").strip()
        if not wireless and not serial:
            continue
        devices.append(
            WirelessDevice(
                asset_id=str(item.get("asset_id") or "").strip(),
                name=str(item.get("name") or "").strip(),
                wireless=wireless,
                mmuid=str(item.get("mmuid") or "").strip(),
                mmuidv3=str(item.get("mmuidv3") or "").strip(),
                serial=serial,
                note=str(item.get("note") or "").strip(),
            )
        )
    return devices


def find_wireless_device(
    *,
    devices: Iterable[WirelessDevice],
    asset_id: str | None = None,
    mmuid: str | None = None,
    name_query: str | None = None,
    address: str | None = None,
) -> WirelessDevice:
    if address:
        normalized = address.strip()
        return WirelessDevice(asset_id="", name="direct", wireless=normalized)

    if asset_id:
        query = _normalize(asset_id)
        for device in devices:
            if device.asset_id and _normalize(device.asset_id) == query:
                return device
        try:
            load_test_devices, find_devices = _risk_test_devices_module()
            matched = find_devices(devices=load_test_devices(), asset_ids=[asset_id])
            if len(matched) == 1:
                test_device = matched[0]
                for device in devices:
                    if device.asset_id and _normalize(device.asset_id) == _normalize(test_device.asset_id):
                        return device
        except (ImportError, ValueError, OSError):
            pass
        raise ValueError(f"未在无线登记表中找到资产编号: {asset_id}")

    if mmuid:
        query = _normalize(mmuid)
        for device in devices:
            candidates = (device.mmuid, device.mmuidv3)
            if any(item and _normalize(item) == query for item in candidates):
                return device
            if any(item and query in _normalize(item) for item in candidates if item):
                return device
        raise ValueError(f"未在无线登记表中找到 mmuid/mmuidv3: {mmuid}")

    if name_query:
        query = _normalize(name_query)
        matched = [
            device
            for device in devices
            if any(query in _normalize(field) for field in (device.name, device.asset_id) if field)
        ]
        if len(matched) == 1:
            return matched[0]
        if not matched:
            raise ValueError(f"未在无线登记表中找到名称匹配: {name_query}")
        names = ", ".join(item.asset_id or item.name for item in matched)
        raise ValueError(f"名称匹配到多台设备，请指定资产编号: {names}")

    raise ValueError("请提供 --address、--asset、--mmuid 或 --name 之一")
