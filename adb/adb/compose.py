"""组合搭建：按顺序执行多个录制片段（积木）。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from .chain import run_chain
from .macros import apply_skip_flags
from .recorded_scripts import (
    list_catalog,
    load_compose_spec,
    load_fragment,
    scripts_root,
)

CaptureMode = Literal["never", "start", "end", "both"]


def compose_dir() -> Path:
    return scripts_root() / "组合"


def list_compose_files() -> list[Path]:
    """组合 JSON（含子目录），未入索引的文件也会被扫描。"""
    d = compose_dir()
    if not d.is_dir():
        return []
    return sorted(d.glob("**/*.json"))


def load_compose(key: str) -> dict[str, Any]:
    key = key.strip()
    if not key:
        raise ValueError("组合名不能为空")
    try:
        return load_compose_spec(key)
    except ValueError:
        pass
    matches: list[tuple[Path, dict[str, Any]]] = []
    for path in list_compose_files():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        name = str(data.get("name", path.stem))
        cid = str(data.get("id", path.stem))
        if key in (name, cid, path.stem):
            matches.append((path, data))
    if not matches:
        known = "、".join(
            str(i.get("name"))
            for i in list_catalog()
            if i.get("kind") == "compose"
        ) or "（组合目录为空）"
        raise ValueError(f"未知组合 {key!r}，可选: {known}")
    if len(matches) > 1:
        raise ValueError(f"组合名 {key!r} 不唯一")
    path, data = matches[0]
    data.setdefault("id", path.stem)
    data.setdefault("name", path.stem)
    data["_file"] = str(path)
    return data


def list_compose_summary() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    indexed = [i for i in list_catalog() if i.get("kind") == "compose"]
    if indexed:
        for item in indexed:
            try:
                data = load_compose_spec(str(item["name"]))
            except ValueError:
                continue
            path = Path(str(data.get("_file", "")))
            seq = data.get("sequence") or []
            scripts = [
                b.get("script")
                for b in seq
                if isinstance(b, dict) and b.get("script")
            ]
            rel = (
                str(path.relative_to(scripts_root()))
                if path.is_file()
                else item.get("file")
            )
            out.append(
                {
                    "id": data.get("id", item.get("id")),
                    "name": data.get("name", item.get("name")),
                    "module": item.get("module"),
                    "description": data.get("description", ""),
                    "file": rel,
                    "blocks": scripts,
                }
            )
        return out
    for path in list_compose_files():
        try:
            data = load_compose(path.stem)
        except ValueError:
            continue
        seq = data.get("sequence") or []
        scripts = [
            b.get("script")
            for b in seq
            if isinstance(b, dict) and b.get("script")
        ]
        module = path.parent.name if path.parent != compose_dir() else None
        out.append(
            {
                "id": data.get("id", path.stem),
                "name": data.get("name", path.stem),
                "module": module,
                "description": data.get("description", ""),
                "file": str(path.relative_to(scripts_root())),
                "blocks": scripts,
            }
        )
    return out


def run_compose(
    *,
    name: str,
    serial: str,
    screenshot_dir: Path,
    max_screenshots: int,
    text: str | None = None,
    skip: set[str] | None = None,
    capture: CaptureMode = "end",
    verify_end: bool = False,
    use_adaptation: bool = True,
) -> dict[str, Any]:
    spec = load_compose(name)
    global_skip = skip or set()
    cap: CaptureMode = "end" if verify_end else str(spec.get("capture", capture))  # type: ignore[assignment]
    if cap not in ("never", "start", "end", "both"):
        cap = capture

    sequence = spec.get("sequence")
    if not isinstance(sequence, list) or not sequence:
        raise ValueError(f"组合 {name} 缺少 sequence 数组")

    result: dict[str, Any] = {
        "action": "compose",
        "compose": spec.get("name", name),
        "composeId": spec.get("id", name),
        "description": spec.get("description", ""),
        "capture": cap,
        "blocks": [],
    }

    last_chain: dict[str, Any] | None = None
    for index, block in enumerate(sequence):
        if not isinstance(block, dict):
            raise ValueError(f"sequence[{index}] 须为 object")
        script_key = str(block.get("script", "")).strip()
        if not script_key:
            raise ValueError(f"sequence[{index}] 缺少 script")

        block_skip = set(block.get("skip") or []) | global_skip
        frag = load_fragment(script_key, text=text)
        params = frag.get("params") or []
        if params and "text" in params and text is None:
            raise ValueError(f"组合块 {script_key!r} 需要 --text")

        steps = apply_skip_flags(list(frag.get("steps", [])), skip=block_skip)
        block_capture: CaptureMode = str(block.get("capture", "never"))  # type: ignore[assignment]
        if block_capture not in ("never", "start", "end", "both"):
            block_capture = "never"
        is_last = index == len(sequence) - 1
        run_capture: CaptureMode = cap if is_last else block_capture

        chain_out = run_chain(
            serial=serial,
            steps=steps,
            capture=run_capture,
            screenshot_dir=screenshot_dir,
            max_screenshots=max_screenshots,
            use_adaptation=use_adaptation,
            text=text,
        )
        last_chain = chain_out
        result["blocks"].append(
            {
                "index": index,
                "script": frag.get("name", script_key),
                "scriptId": frag.get("id", script_key),
                "skip": sorted(block_skip),
                "stepsExecuted": chain_out.get("stepsExecuted"),
            }
        )

    if last_chain:
        result["serial"] = last_chain.get("serial")
        result["displayWidth"] = last_chain.get("displayWidth")
        result["displayHeight"] = last_chain.get("displayHeight")
        if last_chain.get("adaptation"):
            result["adaptation"] = last_chain["adaptation"]
        if last_chain.get("screenshot"):
            result["screenshot"] = last_chain["screenshot"]
        else:
            result["screenshot"] = None
    if text is not None:
        result["text"] = text
    return result
