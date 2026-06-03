#!/usr/bin/env python3
"""将外部 xlsx 导入 testcase-kb 团队测试机知识库。"""

from __future__ import annotations

import argparse
import json
import os
import sys
import zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
_CELL_REF = __import__("re").compile(r"^([A-Z]+)(\d+)$")


def _col_row(cell_ref: str) -> tuple[str, int]:
    match = _CELL_REF.match(cell_ref)
    if not match:
        raise ValueError(f"无效单元格引用: {cell_ref}")
    return match.group(1), int(match.group(2))


def _load_sheet_rows(xlsx_path: str) -> dict[int, dict[str, str]]:
    with zipfile.ZipFile(xlsx_path) as zf:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in zf.namelist():
            root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for si in root.findall("m:si", _NS):
                shared.append("".join((t.text or "") for t in si.findall(".//m:t", _NS)))

        names = zf.namelist()
        sheet_path = "xl/worksheets/sheet1.xml"
        if sheet_path not in names:
            sheets = sorted(
                name for name in names if name.startswith("xl/worksheets/sheet") and name.endswith(".xml")
            )
            if not sheets:
                raise ValueError("xlsx 中未找到 worksheet")
            sheet_path = sheets[0]

        sheet = ET.fromstring(zf.read(sheet_path))
        rows: dict[int, dict[str, str]] = {}
        for cell in sheet.findall(".//m:sheetData/m:row/m:c", _NS):
            ref = cell.get("r")
            if not ref:
                continue
            col, row = _col_row(ref)
            value_node = cell.find("m:v", _NS)
            value = value_node.text if value_node is not None else ""
            if cell.get("t") == "s" and value:
                value = shared[int(value)]
            rows.setdefault(row, {})[col] = str(value).strip()
        return rows


def _load_rows_with_remarks(xlsx_path: str) -> list[dict[str, str]]:
    rows = _load_sheet_rows(xlsx_path)
    headers = rows.get(1, {})
    header_map = {
        "A": "项目",
        "B": "资产编号",
        "C": "设备品牌",
        "D": "设备名称",
        "E": "mmuid",
        "F": "mmuidv3",
        "G": "设备系统",
        "H": "系统版本",
        "I": "归属人",
        "J": "持有人",
        "K": "备注",
    }
    for col, raw in headers.items():
        if col == "A" and raw:
            header_map["A"] = "项目" if raw.lower().startswith("yi") else raw
        elif col == "E" and raw:
            header_map["E"] = "mmuid"

    items: list[dict[str, str]] = []
    for row_num in sorted(rows):
        if row_num == 1:
            continue
        row = rows[row_num]
        if not any(row.values()):
            continue
        item = {header_map.get(col, col): row.get(col, "") for col in "ABCDEFGHIJK"}
        if item.get("资产编号") or item.get("设备名称") or item.get("mmuid") or item.get("mmuidv3"):
            items.append(item)
    return items


def _escape_md(value: str) -> str:
    return (value or "—").replace("|", "\\|").replace("\n", " ")


def _build_holder_summary(items: list[dict[str, str]]) -> list[tuple[str, int, str]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for item in items:
        holder = item.get("持有人") or item.get("归属人") or "未指定"
        label = f"{item.get('设备品牌', '')} {item.get('设备名称', '')}".strip()
        asset = item.get("资产编号", "")
        grouped[holder].append(f"{asset}（{label}）" if label else asset)
    summary = [(holder, len(devices), "；".join(devices)) for holder, devices in sorted(grouped.items())]
    return summary


def build_markdown(items: list[dict[str, str]], *, source_path: str, synced_at: str) -> str:
    holder_summary = _build_holder_summary(items)

    lines = [
        "# 团队测试机统计",
        "",
        "> **文档类型**：测试资源知识库（团队测试机台账）",
        "> **数据来源**：`testcase-kb/test_devices.json`（知识库 JSON，运行时唯一数据源）",
        f"> **最近导入源**：`{source_path}`",
        f"> **最近同步**：{synced_at}",
        "",
        "| 项 | 说明 |",
        "|---|---|",
        "| 用途 | 按 mmuid / mmuidv3 / 资产编号反查设备归属与持有人 |",
        "| 关联工具 | `Risk/risk_execute.py --list-test-devices`；Admin `queryUserDetail` 登录设备字段 |",
        "| 维护命令 | `python3 scripts/sync_test_devices_kb.py --xlsx <外部xlsx>`（可选，从 xlsx 更新知识库） |",
        "",
        "---",
        "",
        "## 字段说明",
        "",
        "| 列 | 含义 | 备注 |",
        "|---|---|---|",
        "| 项目 | 业务线 | 当前均为 yaahlan |",
        "| 资产编号 | 公司资产编号 | 如 GZ3021030074 |",
        "| mmuid | Device ID | **iOS 解除设备风控**时使用此字段 |",
        "| mmuidv3 | Android/鸿蒙设备指纹 | **Android/鸿蒙解除设备风控**时传此值（接口 dimension 仍为 mmuid） |",
        "| 归属人 | 资产归属 | 台账登记 |",
        "| 持有人 | 当前实际持有人 | 可能与归属人不同 |",
        "| 备注 | 补充说明 | 如设备状态、未找到 mmuid 等 |",
        "",
        "## 查询指引",
        "",
        "- **Admin 查到用户最后登录 mmuid** → 在本表 mmuid 列精确匹配，读「持有人」",
        "- **Admin 查到 mmuidv3** → 在本表 mmuidv3 列匹配（测试环境部分设备 mmuidv3 可能重复，需结合 mmuid 与 UA 机型交叉验证）",
        "- **按资产编号** → 资产编号列匹配，用于 `Risk/risk_execute.py --release-test-device --device-asset <编号>`",
        "",
        "## 按持有人汇总",
        "",
        "| 持有人 | 台数 | 设备 |",
        "|---|---:|---|",
    ]
    for holder, count, devices in holder_summary:
        lines.append(f"| {_escape_md(holder)} | {count} | {_escape_md(devices)} |")

    lines.extend(
        [
            "",
            "## 设备清单",
            "",
            f"共 **{len(items)}** 台。",
            "",
            "| 项目 | 资产编号 | 品牌 | 名称 | 系统 | 版本 | mmuid | mmuidv3 | 归属人 | 持有人 | 备注 |",
            "|---|---|---|---|---|---|---|---|---|---|---|",
        ]
    )
    for item in items:
        lines.append(
            "| "
            + " | ".join(
                _escape_md(item.get(key, ""))
                for key in (
                    "项目",
                    "资产编号",
                    "设备品牌",
                    "设备名称",
                    "设备系统",
                    "系统版本",
                    "mmuid",
                    "mmuidv3",
                    "归属人",
                    "持有人",
                    "备注",
                )
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="从外部 xlsx 导入团队测试机到 testcase-kb 知识库")
    parser.add_argument(
        "--xlsx",
        default=os.environ.get("RISK_TEST_DEVICE_XLSX", "").strip() or None,
        help="外部 xlsx 路径（需显式指定，或通过 RISK_TEST_DEVICE_XLSX 环境变量）",
    )
    parser.add_argument(
        "--output-dir",
        default=str(ROOT / "testcase-kb"),
        help="知识库输出目录（默认 testcase-kb/）",
    )
    args = parser.parse_args()

    if not args.xlsx:
        print("错误: 请通过 --xlsx 指定外部 xlsx 路径", file=sys.stderr)
        return 1

    xlsx_path = os.path.expanduser(args.xlsx)
    if not os.path.isfile(xlsx_path):
        print(f"错误: 找不到 xlsx: {xlsx_path}", file=sys.stderr)
        return 1

    items = _load_rows_with_remarks(xlsx_path)
    synced_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    md_path = output_dir / "测试机.md"
    json_path = output_dir / "test_devices.json"

    md_path.write_text(build_markdown(items, source_path=xlsx_path, synced_at=synced_at), encoding="utf-8")
    json_path.write_text(
        json.dumps(
            {
                "kbPath": str(json_path.relative_to(ROOT)),
                "importSource": xlsx_path,
                "syncedAt": synced_at,
                "count": len(items),
                "devices": items,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"已同步 {len(items)} 台设备 → {md_path}")
    print(f"JSON 索引 → {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
