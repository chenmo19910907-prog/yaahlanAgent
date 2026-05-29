"""团队测试机统计表读取与解除设备风控维度解析。"""

from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from typing import Iterable

_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
_CELL_REF = re.compile(r"^([A-Z]+)(\d+)$")


@dataclass(frozen=True)
class TestDevice:
    asset_id: str
    brand: str
    name: str
    mmuid: str
    mmuidv3: str
    os_name: str
    project: str = ""
    owner: str = ""
    holder: str = ""

    @property
    def os_kind(self) -> str:
        raw = self.os_name.strip().lower()
        if raw in {"ios", "iphone", "ipad"}:
            return "ios"
        if raw in {"android", "安卓"}:
            return "android"
        if raw in {"鸿蒙", "harmony", "harmonyos"}:
            return "harmony"
        return raw or "unknown"

    def release_dimension_and_element(self) -> tuple[str, str]:
        """按平台返回解除设备风控所需的 dimension 与 element。

        接口 dimension 固定为 mmuid；Android/鸿蒙传 mmuidv3 字段值，iOS 传 mmuid 字段值。
        """
        if self.os_kind == "ios":
            if not self.mmuid:
                raise ValueError(
                    f"设备 {self.asset_id}（{self.name}）为 iOS，但 mmuid 为空，无法解除设备风控"
                )
            return "mmuid", self.mmuid

        if self.os_kind in {"android", "harmony"}:
            if not self.mmuidv3:
                raise ValueError(
                    f"设备 {self.asset_id}（{self.name}）为 {self.os_name or 'Android'}，"
                    "但 mmuidv3 为空，无法解除设备风控"
                )
            return "mmuid", self.mmuidv3

        raise ValueError(
            f"设备 {self.asset_id}（{self.name}）系统类型未知: {self.os_name!r}，"
            "仅支持 iOS（mmuid）与 Android/鸿蒙（mmuidv3 字段值）"
        )


def default_test_device_xlsx_path() -> str:
    env_path = os.environ.get("RISK_TEST_DEVICE_XLSX", "").strip()
    if env_path:
        return os.path.expanduser(env_path)

    try:
        from .config import load_config

        registry = load_config().get("test_device_registry")
        if isinstance(registry, dict):
            configured = str(registry.get("xlsx_path") or "").strip()
            if configured:
                return os.path.expanduser(configured)
    except (ImportError, ValueError, OSError):
        pass

    return os.path.expanduser("~/Desktop/团队测试机统计表.xlsx")


def _col_row(cell_ref: str) -> tuple[str, int]:
    match = _CELL_REF.match(cell_ref)
    if not match:
        raise ValueError(f"无效单元格引用: {cell_ref}")
    return match.group(1), int(match.group(2))


def _load_shared_strings(zf: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    shared: list[str] = []
    for si in root.findall("m:si", _NS):
        texts = [node.text or "" for node in si.findall(".//m:t", _NS)]
        shared.append("".join(texts))
    return shared


def _sheet_xml_path(zf: zipfile.ZipFile) -> str:
    names = zf.namelist()
    if "xl/worksheets/sheet1.xml" in names:
        return "xl/worksheets/sheet1.xml"
    sheets = sorted(name for name in names if name.startswith("xl/worksheets/sheet") and name.endswith(".xml"))
    if not sheets:
        raise ValueError("xlsx 中未找到 worksheet")
    return sheets[0]


def _parse_sheet_rows(zf: zipfile.ZipFile) -> dict[int, dict[str, str]]:
    shared = _load_shared_strings(zf)
    sheet = ET.fromstring(zf.read(_sheet_xml_path(zf)))
    rows: dict[int, dict[str, str]] = {}
    for cell in sheet.findall(".//m:sheetData/m:row/m:c", _NS):
        ref = cell.get("r")
        if not ref:
            continue
        col, row = _col_row(ref)
        cell_type = cell.get("t")
        value_node = cell.find("m:v", _NS)
        value = value_node.text if value_node is not None else ""
        if cell_type == "s" and value:
            value = shared[int(value)]
        rows.setdefault(row, {})[col] = str(value).strip()
    return rows


def load_test_devices(xlsx_path: str | None = None) -> list[TestDevice]:
    path = os.path.expanduser(xlsx_path or default_test_device_xlsx_path())
    if not os.path.isfile(path):
        raise ValueError(f"测试机统计表不存在: {path}")

    with zipfile.ZipFile(path) as zf:
        rows = _parse_sheet_rows(zf)

    devices: list[TestDevice] = []
    for row_num in sorted(rows):
        if row_num == 1:
            continue
        row = rows[row_num]
        asset_id = row.get("B", "").strip()
        brand = row.get("C", "").strip()
        name = row.get("D", "").strip()
        mmuid = row.get("E", "").strip()
        mmuidv3 = row.get("F", "").strip()
        os_name = row.get("G", "").strip()
        if not asset_id and not name and not mmuid and not mmuidv3:
            continue
        devices.append(
            TestDevice(
                project=row.get("A", "").strip(),
                asset_id=asset_id,
                brand=brand,
                name=name,
                mmuid=mmuid,
                mmuidv3=mmuidv3,
                os_name=os_name,
                owner=row.get("I", "").strip(),
                holder=row.get("J", "").strip(),
            )
        )
    return devices


def _normalize_query(value: str) -> str:
    return value.strip().casefold()


def find_devices(
    *,
    devices: Iterable[TestDevice],
    asset_ids: Iterable[str] | None = None,
    name_query: str | None = None,
) -> list[TestDevice]:
    asset_queries = [_normalize_query(item) for item in (asset_ids or []) if item.strip()]
    name_q = _normalize_query(name_query) if name_query else ""

    matched: list[TestDevice] = []
    seen_assets: set[str] = set()

    if asset_queries:
        by_asset = {_normalize_query(device.asset_id): device for device in devices if device.asset_id}
        for query in asset_queries:
            device = by_asset.get(query)
            if device is None:
                raise ValueError(f"未在测试机表中找到资产编号: {query}")
            if device.asset_id not in seen_assets:
                seen_assets.add(device.asset_id)
                matched.append(device)
        return matched

    if name_q:
        for device in devices:
            haystacks = (device.name, device.brand, device.asset_id)
            if any(name_q in _normalize_query(item) for item in haystacks if item):
                if device.asset_id not in seen_assets:
                    seen_assets.add(device.asset_id)
                    matched.append(device)
        if not matched:
            raise ValueError(f"未在测试机表中找到名称匹配: {name_query}")
        return matched

    raise ValueError("请提供 --device-asset 或 --device-name")


def group_release_elements(devices: Iterable[TestDevice]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    seen: dict[str, set[str]] = {}
    for device in devices:
        dimension, element = device.release_dimension_and_element()
        bucket = grouped.setdefault(dimension, [])
        seen_set = seen.setdefault(dimension, set())
        if element not in seen_set:
            seen_set.add(element)
            bucket.append(element)
    return grouped


def menu_key_for_dimension(dimension: str) -> str:
    if dimension == "mmuid":
        return "device_risk_release"
    raise ValueError(f"不支持的设备风控 dimension: {dimension}")
