#!/usr/bin/env python3
"""读取 MSE 服务配置 → 替换 JSON 参数 → 导出到钉钉 Agent 导出目录（在线表格）。"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

GATEWAY_DIR = Path(__file__).resolve().parent
REPO_ROOT = GATEWAY_DIR.parents[1]
_EXCEL_VENV = (
    REPO_ROOT / ".cursor/skills/testcase-to-excel/mcp_dingtalk_excel/venv/bin/python3.13"
)

if (
    __name__ == "__main__"
    and _EXCEL_VENV.is_file()
    and Path(sys.executable).resolve() != _EXCEL_VENV.resolve()
):
    os.execv(str(_EXCEL_VENV), [str(_EXCEL_VENV), str(Path(__file__).resolve()), *sys.argv[1:]])

if str(GATEWAY_DIR) not in sys.path:
    sys.path.insert(0, str(GATEWAY_DIR))

from export_delivery import load_export_config  # noqa: E402
from alidocs_excel_export import export_rows_to_folder  # noqa: E402

_SET_RE = re.compile(r"^([^=]+)=(.+)$")


def _parse_scalar(raw: str) -> Any:
    text = raw.strip()
    if not text:
        return ""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def _deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _apply_set_args(config: dict[str, Any], set_args: list[str]) -> tuple[dict[str, Any], list[str]]:
    updated = dict(config)
    changes: list[str] = []
    for item in set_args:
        match = _SET_RE.match(item.strip())
        if not match:
            raise ValueError(f"--set 格式错误，应为 key=value：{item!r}")
        key, raw_value = match.group(1).strip(), match.group(2)
        if not key:
            raise ValueError(f"--set 缺少 key：{item!r}")
        new_value = _parse_scalar(raw_value)
        old_value = updated.get(key, "<未设置>")
        updated[key] = new_value
        changes.append(f"{key}: {json.dumps(old_value, ensure_ascii=False)} → {json.dumps(new_value, ensure_ascii=False)}")
    return updated, changes


def _fetch_mse_config(*, namespace: str, config_key: str) -> dict[str, Any]:
    cmd = [
        "python3",
        str(REPO_ROOT / "MSE/mse_execute.py"),
        "--namespace",
        namespace,
        "--config-key",
        config_key,
        "--output",
        "json",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_ROOT)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "MSE 读取失败").strip())
    data = json.loads(proc.stdout)
    if not isinstance(data, list) or not data:
        raise RuntimeError(f"未找到配置 {namespace}/{config_key}")
    item = data[0]
    if not isinstance(item, dict):
        raise RuntimeError("MSE 返回格式异常")
    raw_value = item.get("configValue")
    if isinstance(raw_value, str):
        try:
            parsed = json.loads(raw_value)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"configValue 不是合法 JSON: {exc}") from exc
    elif isinstance(raw_value, dict):
        parsed = raw_value
    else:
        raise RuntimeError("configValue 为空或类型不支持")
    if not isinstance(parsed, dict):
        raise RuntimeError("configValue 必须是 JSON object")
    return {
        "meta": item,
        "configValue": parsed,
    }


def _build_rows(*, original: dict[str, Any], modified: dict[str, Any]) -> list[list[str]]:
    """MSE 配置导出：仅改后 JSON（上）+ 改前 JSON（下），单元格自动换行。"""
    return [
        ["改后 JSON", json.dumps(modified, ensure_ascii=False, indent=2)],
        ["改前 JSON", json.dumps(original, ensure_ascii=False, indent=2)],
    ]


def export_mse_config(
    *,
    namespace: str,
    config_key: str,
    set_args: list[str] | None = None,
    patch_file: Path | None = None,
    workbook_name: str | None = None,
    note: str = "",
) -> str:
    fetched = _fetch_mse_config(namespace=namespace, config_key=config_key)
    original = fetched["configValue"]
    modified = dict(original)
    changes: list[str] = []

    if patch_file is not None:
        patch = json.loads(patch_file.read_text(encoding="utf-8"))
        if not isinstance(patch, dict):
            raise ValueError("patch 文件必须是 JSON object")
        for key, value in patch.items():
            old = modified.get(key, "<未设置>")
            changes.append(
                f"{key}: {json.dumps(old, ensure_ascii=False)} → {json.dumps(value, ensure_ascii=False)}"
            )
        modified = _deep_merge(modified, patch)

    if set_args:
        modified, set_changes = _apply_set_args(modified, set_args)
        changes.extend(set_changes)

    del changes, note  # 变更追踪保留在流程内，导出表格仅含改前/改后 JSON
    title = workbook_name or f"MSE-{config_key}-配置"
    rows = _build_rows(original=original, modified=modified)
    cfg = load_export_config()
    return export_rows_to_folder(
        rows,
        parent_node_id=cfg.node_id,
        workbook_name=title,
        auto_wrap=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="MSE 配置改参并导出到钉钉文档")
    parser.add_argument("--namespace", default="voga-common", help="MSE namespace，默认 voga-common")
    parser.add_argument("--config-key", required=True, help="configKey，如 familyPkConfig")
    parser.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="替换顶层 JSON 字段，可多次指定；值支持 JSON 字面量",
    )
    parser.add_argument("--patch-file", type=Path, help="JSON patch 文件（object，deep merge 到 configValue）")
    parser.add_argument("--name", help="钉钉表格名称")
    parser.add_argument("--note", default="", help="变更说明（写入导出表格）")
    args = parser.parse_args()

    if not args.set and not args.patch_file:
        print("[INFO] 未指定 --set 或 --patch-file，将导出当前 MSE 配置快照", file=sys.stderr)

    try:
        url = export_mse_config(
            namespace=args.namespace.strip(),
            config_key=args.config_key.strip(),
            set_args=args.set,
            patch_file=args.patch_file,
            workbook_name=args.name,
            note=args.note.strip(),
        )
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1

    print(url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
