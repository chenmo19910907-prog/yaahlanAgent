"""从 adb/录制脚本 加载片段与流程（支持中文名与英文 id）。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_SCRIPTS_ROOT = Path(__file__).resolve().parent.parent / "录制脚本"
_INDEX_PATH = _SCRIPTS_ROOT / "索引.json"


def scripts_root() -> Path:
    return _SCRIPTS_ROOT


def _load_index() -> dict[str, Any]:
    data = json.loads(_INDEX_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("索引.json 根节点须为 object")
    return data


def _read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} 根节点须为 object")
    return data


def list_catalog() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for entry in _load_index().get("items", []):
        if not isinstance(entry, dict):
            continue
        items.append(
            {
                "id": entry.get("id"),
                "name": entry.get("name"),
                "kind": entry.get("kind"),
                "file": entry.get("file"),
                "params": entry.get("params", []),
            }
        )
    return items


def resolve_key(key: str, *, kind: str | None = None) -> tuple[str, str, Path]:
    """将中文名 / 英文 id 解析为 (id, 中文名, 文件路径)。"""
    key = key.strip()
    if not key:
        raise ValueError("脚本名不能为空")
    matches: list[tuple[dict[str, Any], Path]] = []
    for entry in _load_index().get("items", []):
        if not isinstance(entry, dict):
            continue
        if kind and entry.get("kind") != kind:
            continue
        eid = str(entry.get("id", ""))
        name = str(entry.get("name", ""))
        if key not in (eid, name):
            continue
        rel = entry.get("file")
        if not rel:
            continue
        path = _SCRIPTS_ROOT / str(rel)
        matches.append((entry, path))
    if not matches:
        hint = _format_known(kind)
        raise ValueError(f"未知脚本 {key!r}，{hint}")
    if len(matches) > 1 and kind is None:
        kinds = {m[0].get("kind") for m in matches}
        if len(kinds) > 1:
            raise ValueError(
                f"{key!r} 同时存在片段与流程，请用 macro/flow 子命令区分，"
                f"或指定 kind: {', '.join(sorted(kinds))}"
            )
    entry, path = matches[0]
    return str(entry["id"]), str(entry.get("name", entry["id"])), path


def _format_known(kind: str | None) -> str:
    names: list[str] = []
    for entry in _load_index().get("items", []):
        if isinstance(entry, dict) and (not kind or entry.get("kind") == kind):
            names.append(str(entry.get("name", entry.get("id"))))
    return "可选: " + "、".join(dict.fromkeys(names)) if names else "（索引为空）"


def _apply_params(spec: dict[str, Any], *, text: str | None) -> dict[str, Any]:
    params = spec.get("params") or []
    if not params:
        return spec
    if "text" in params:
        if text is None or not str(text).strip():
            raise ValueError(f"{spec.get('name', spec.get('id'))} 需要 --text <正文>")
        content = str(text).strip()
    else:
        content = None
    steps_out: list[dict[str, Any]] = []
    for step in spec.get("steps", []):
        if not isinstance(step, dict):
            steps_out.append(step)
            continue
        step_copy = dict(step)
        if "text" in step_copy and content is not None:
            raw = str(step_copy["text"])
            step_copy["text"] = raw.replace("{{text}}", content)
        steps_out.append(step_copy)
    out = dict(spec)
    out["steps"] = steps_out
    if content is not None:
        out["description"] = f"{spec.get('description', '')}：{content!r}"
    return out


def load_fragment(
    key: str,
    *,
    text: str | None = None,
) -> dict[str, Any]:
    _id, _name, path = resolve_key(key, kind="fragment")
    spec = _read_json(path)
    spec.setdefault("id", _id)
    spec.setdefault("name", _name)
    return _apply_params(spec, text=text)


def load_flow_file(key: str) -> dict[str, Any]:
    _id, _name, path = resolve_key(key, kind="flow")
    spec = _read_json(path)
    spec.setdefault("id", _id)
    spec.setdefault("name", _name)
    return spec


def flow_paths() -> list[Path]:
    return sorted((_SCRIPTS_ROOT / "流程").glob("*.json"))


def load_flow_by_path(path: Path) -> dict[str, Any]:
    spec = _read_json(path)
    spec.setdefault("name", path.stem)
    return spec


def list_flows_summary() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for path in flow_paths():
        try:
            flow = load_flow_by_path(path)
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        recorded = flow.get("recorded") or {}
        out.append(
            {
                "id": flow.get("id", path.stem),
                "name": flow.get("name", path.stem),
                "description": flow.get("description", ""),
                "recordedCapture": recorded.get("capture", "never"),
                "kbRef": flow.get("kbRef", []),
            }
        )
    return out
