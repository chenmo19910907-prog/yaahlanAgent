#!/usr/bin/env python3
"""校验 录制脚本/索引.json 与 片段/**/*.json 一致。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_PKG = Path(__file__).resolve().parent.parent
_SCRIPTS = _PKG / "录制脚本"
_INDEX = _SCRIPTS / "索引.json"


def _load_json(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} 根节点须为 object")
    return data


def validate_index(*, scripts_root: Path | None = None) -> list[str]:
    root = scripts_root or _SCRIPTS
    index_path = root / "索引.json"
    errors: list[str] = []

    if not index_path.is_file():
        return [f"缺少索引: {index_path}"]

    index = _load_json(index_path)
    items = index.get("items", [])
    if not isinstance(items, list):
        return ["索引.json items 须为 array"]

    seen_ids: set[str] = set()
    seen_names: set[str] = set()
    referenced: set[Path] = set()

    for i, entry in enumerate(items):
        prefix = f"items[{i}]"
        if not isinstance(entry, dict):
            errors.append(f"{prefix} 须为 object")
            continue

        kind = entry.get("kind")
        file_rel = entry.get("file")
        entry_id = entry.get("id")
        name = entry.get("name")

        if not entry_id:
            errors.append(f"{prefix} 缺少 id")
        elif entry_id in seen_ids:
            errors.append(f"重复 id: {entry_id}")
        else:
            seen_ids.add(str(entry_id))

        if not name:
            errors.append(f"{prefix} 缺少 name")
        elif name in seen_names:
            errors.append(f"重复 name: {name}")
        else:
            seen_names.add(str(name))

        if not file_rel:
            errors.append(f"{prefix} 缺少 file")
            continue

        path = root / str(file_rel)
        referenced.add(path.resolve())
        if not path.is_file():
            errors.append(f"{prefix} 文件不存在: {file_rel}")
            continue

        try:
            frag = _load_json(path)
        except (json.JSONDecodeError, OSError, ValueError) as exc:
            errors.append(f"{prefix} 读取失败 {file_rel}: {exc}")
            continue

        if kind == "fragment":
            steps = frag.get("steps")
            if not isinstance(steps, list):
                errors.append(f"{file_rel} fragment 缺少 steps 数组")

        frag_id = frag.get("id")
        frag_name = frag.get("name")
        if frag_id and str(frag_id) != str(entry_id):
            errors.append(
                f"{file_rel} id 不一致: 索引={entry_id!r} 文件={frag_id!r}"
            )
        if frag_name and str(frag_name) != str(name):
            errors.append(
                f"{file_rel} name 不一致: 索引={name!r} 文件={frag_name!r}"
            )

    fragments_dir = root / "片段"
    if fragments_dir.is_dir():
        for json_path in sorted(fragments_dir.rglob("*.json")):
            resolved = json_path.resolve()
            if resolved not in referenced:
                rel = json_path.relative_to(root)
                errors.append(f"未收录片段: {rel}")

    return errors


def main(argv: list[str] | None = None) -> int:
    errors = validate_index()
    if errors:
        print("索引校验失败:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    print("索引校验通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
