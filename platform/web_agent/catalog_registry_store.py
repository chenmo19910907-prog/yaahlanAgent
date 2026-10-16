"""Web Agent：按 registry 项更新快捷提示语（prompts）并刷新模块 index / catalog。"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

WEB_AGENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = WEB_AGENT_DIR.parent.parent
if str(REPO_ROOT / "platform") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "platform"))

from project.catalog_paths import module_registry_path  # noqa: E402
from project.loader import load_sources  # noqa: E402


def _read_registry(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} 必须是 JSON object")
    return data


def _write_registry(path: Path, data: dict[str, Any]) -> None:
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    path.write_text(text, encoding="utf-8")


def _module_for_source_id(source_id: str) -> dict[str, Any]:
    sid = str(source_id or "").strip()
    if not sid:
        raise ValueError("缺少 source_id")
    sources = load_sources()
    modules = sources.get("modules")
    if not isinstance(modules, list):
        raise ValueError("sources.modules 无效")
    for mod in modules:
        if not isinstance(mod, dict):
            continue
        if str(mod.get("id") or "").strip() == sid:
            return mod
    raise ValueError(f"未知模块 source_id: {sid}")


def _registry_path_for_module(mod: dict[str, Any]) -> Path:
    mod_id = str(mod.get("id") or "").strip()
    registry_rel = str(mod.get("registry") or "").strip()
    if not mod_id or not registry_rel:
        raise ValueError("模块未配置 registry")
    return module_registry_path(mod_id, registry_rel)


def _find_registry_item(items: list[Any], registry_id: str) -> dict[str, Any] | None:
    rid = str(registry_id or "").strip()
    if not rid:
        return None
    for raw in items:
        if not isinstance(raw, dict):
            continue
        if str(raw.get("id") or "").strip() == rid:
            return raw
    return None


def _normalize_prompts(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        raise ValueError("prompts 必须是字符串数组")
    out: list[str] = []
    for p in raw:
        if not isinstance(p, str):
            raise ValueError("prompts 项必须是字符串")
        text = p.strip()
        if text:
            out.append(text)
    if not out:
        raise ValueError("至少保留一条快捷提示语")
    return out


def _run_module_generate_index(registry_path: Path) -> None:
    script = registry_path.parent.parent / "scripts" / "generate_index.py"
    if not script.is_file():
        raise FileNotFoundError(f"缺少 generate_index: {script}")
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(detail or f"generate_index 失败 ({proc.returncode})")


def _pop_registry_item(items: list[Any], registry_id: str) -> dict[str, Any]:
    rid = str(registry_id or "").strip()
    kept: list[Any] = []
    removed: dict[str, Any] | None = None
    for raw in items:
        if not isinstance(raw, dict):
            kept.append(raw)
            continue
        if str(raw.get("id") or "").strip() == rid:
            removed = raw
            continue
        kept.append(raw)
    if removed is None:
        raise ValueError(f"未找到能力 registry_id={registry_id}")
    items[:] = kept
    return removed


def _apply_source_tag(item: dict[str, Any], owner_source_id: str, source_tag: str | None) -> None:
    """来源标签仅影响工具台徽章，不迁移 registry 文件。"""
    if source_tag is None:
        return
    owner = str(owner_source_id or "").strip()
    tag = str(source_tag or "").strip()
    if not tag or tag == owner:
        item.pop("source_tag", None)
        return
    _module_for_source_id(tag)
    item["source_tag"] = tag


def update_registry_item_name(
    *,
    source_id: str,
    registry_id: str,
    name: str,
    source_tag: str | None = None,
    target_source_id: str | None = None,
) -> dict[str, str]:
    """更新 registry 项 name / 来源标签；target_source_id 仅兼容旧客户端，Web Agent 勿用。"""
    text = str(name or "").strip()
    if not text:
        raise ValueError("能力名称不能为空")
    src_sid = str(source_id or "").strip()
    tgt_sid = str(target_source_id or "").strip() or src_sid
    if tgt_sid == src_sid or source_tag is not None:
        mod = _module_for_source_id(src_sid)
        registry_path = _registry_path_for_module(mod)
        if not registry_path.is_file():
            raise FileNotFoundError(f"缺少 registry: {registry_path}")

        data = _read_registry(registry_path)
        items = data.get("items")
        if not isinstance(items, list):
            raise ValueError(f"{registry_path} items 必须是数组")

        item = _find_registry_item(items, registry_id)
        if item is None:
            raise ValueError(f"未找到能力 registry_id={registry_id}")

        item["name"] = text
        _apply_source_tag(item, src_sid, source_tag)
        _write_registry(registry_path, data)
        _run_module_generate_index(registry_path)
        return {
            "name": text,
            "source_id": src_sid,
            "registry_id": str(registry_id or "").strip(),
        }

    _module_for_source_id(tgt_sid)
    src_mod = _module_for_source_id(src_sid)
    src_path = _registry_path_for_module(src_mod)
    tgt_mod = _module_for_source_id(tgt_sid)
    tgt_path = _registry_path_for_module(tgt_mod)
    if not src_path.is_file():
        raise FileNotFoundError(f"缺少 registry: {src_path}")
    if not tgt_path.is_file():
        raise FileNotFoundError(f"缺少 registry: {tgt_path}")

    src_data = _read_registry(src_path)
    src_items = src_data.get("items")
    if not isinstance(src_items, list):
        raise ValueError(f"{src_path} items 必须是数组")
    item = _pop_registry_item(src_items, registry_id)
    item = dict(item)
    item["name"] = text

    tgt_data = _read_registry(tgt_path)
    tgt_items = tgt_data.get("items")
    if not isinstance(tgt_items, list):
        raise ValueError(f"{tgt_path} items 必须是数组")

    rid = str(item.get("id") or registry_id or "").strip()
    used = {
        str(it.get("id") or "").strip()
        for it in tgt_items
        if isinstance(it, dict) and str(it.get("id") or "").strip()
    }
    if rid not in used:
        item["id"] = rid
    else:
        item["id"] = _unique_item_id(rid or _slugify_id(text), tgt_items)

    tgt_items.append(item)
    tgt_data["items"] = tgt_items
    src_data["items"] = src_items
    _write_registry(src_path, src_data)
    _write_registry(tgt_path, tgt_data)
    _run_module_generate_index(src_path)
    _run_module_generate_index(tgt_path)
    return {
        "name": text,
        "source_id": tgt_sid,
        "registry_id": str(item.get("id") or "").strip(),
    }


def update_registry_item_prompts(
    *,
    source_id: str,
    registry_id: str,
    prompts: list[str] | None = None,
    prompt_index: int | None = None,
    prompt: str | None = None,
    append_prompt: str | None = None,
    delete_prompt_index: int | None = None,
) -> list[str]:
    """更新 registry 项 prompts，跑 generate_index，返回最新 prompts。"""
    mod = _module_for_source_id(source_id)
    registry_path = _registry_path_for_module(mod)
    if not registry_path.is_file():
        raise FileNotFoundError(f"缺少 registry: {registry_path}")

    data = _read_registry(registry_path)
    items = data.get("items")
    if not isinstance(items, list):
        raise ValueError(f"{registry_path} items 必须是数组")

    item = _find_registry_item(items, registry_id)
    if item is None:
        raise ValueError(f"未找到能力 registry_id={registry_id}")

    current = [
        str(p).strip()
        for p in (item.get("prompts") or [])
        if isinstance(p, str) and str(p).strip()
    ]

    if prompts is not None:
        new_prompts = _normalize_prompts(prompts)
    elif append_prompt is not None:
        text = str(append_prompt).strip()
        if not text:
            raise ValueError("快捷提示语不能为空")
        new_prompts = current + [text]
    elif prompt_index is not None and prompt is not None:
        idx = int(prompt_index)
        text = str(prompt).strip()
        if not text:
            raise ValueError("快捷提示语不能为空")
        if idx < 0 or idx >= len(current):
            raise ValueError("prompt_index 超出范围")
        new_prompts = list(current)
        new_prompts[idx] = text
    elif delete_prompt_index is not None:
        idx = int(delete_prompt_index)
        if idx < 0 or idx >= len(current):
            raise ValueError("prompt_index 超出范围")
        new_prompts = [p for i, p in enumerate(current) if i != idx]
    else:
        raise ValueError(
            "请提供 prompts、append_prompt、delete_prompt_index 或 prompt_index+prompt"
        )

    item["prompts"] = new_prompts
    _write_registry(registry_path, data)
    _run_module_generate_index(registry_path)
    return new_prompts


def _slugify_id(name: str) -> str:
    s = re.sub(r"[^\w\u4e00-\u9fff]+", "_", str(name or "").strip())
    s = re.sub(r"_+", "_", s).strip("_").lower()
    return s or "new_capability"


def _unique_item_id(base: str, items: list[Any]) -> str:
    used = {
        str(it.get("id") or "").strip()
        for it in items
        if isinstance(it, dict) and str(it.get("id") or "").strip()
    }
    candidate = base
    n = 2
    while candidate in used:
        candidate = f"{base}_{n}"
        n += 1
    return candidate


def _safe_template_basename(name: str) -> str:
    base = re.sub(r'[\\/:*?"<>|]', "_", str(name or "").strip())
    return base or "新能力"


def _moa_template_from_command(command: str) -> Path | None:
    if not isinstance(command, str):
        return None
    m = re.search(r"--payload-file\s+(\S+\.json)", command)
    if not m:
        return None
    rel = m.group(1).strip()
    if rel.startswith("MOA/templates/"):
        path = REPO_ROOT / rel
        if path.is_file():
            return path
    return None


def _module_entry_command(mod: dict[str, Any], name: str) -> str:
    entry = str(mod.get("entry") or "").strip()
    if not entry:
        raise ValueError("模块未配置 entry")
    return f"{entry}  # TODO: 配置 {name}\n"


def add_registry_item(
    *,
    source_id: str,
    category: str,
    name: str,
    source_tag: str | None = None,
    moa_generative: bool = False,
) -> dict[str, Any]:
    """在 registry 中新增能力条目；MOA 会创建占位模板并 sync_registry。"""
    text = str(name or "").strip()
    cat = str(category or "").strip()
    if not text:
        raise ValueError("能力名称不能为空")
    if not cat:
        raise ValueError("分类不能为空")
    mod = _module_for_source_id(source_id)
    mod_id = str(mod.get("id") or "").strip()
    registry_path = _registry_path_for_module(mod)
    if not registry_path.is_file():
        raise FileNotFoundError(f"缺少 registry: {registry_path}")

    data = _read_registry(registry_path)
    items = data.get("items")
    if not isinstance(items, list):
        raise ValueError(f"{registry_path} items 必须是数组")

    if mod_id == "moa" and not moa_generative:
        templates_dir = REPO_ROOT / "MOA" / "templates"
        templates_dir.mkdir(parents=True, exist_ok=True)
        base_file = _safe_template_basename(text)
        file_name = base_file
        n = 2
        while (templates_dir / f"{file_name}.json").exists():
            file_name = f"{base_file}_{n}"
            n += 1
        template_path = templates_dir / f"{file_name}.json"
        item_id = _unique_item_id(_slugify_id(text), items)
        payload = {
            "type": "moa",
            "url": "/service/TODO",
            "method": "TODO",
            "params": [],
            "_registry": {
                "id": item_id,
                "name": text,
                "category": cat,
                "description": "待配置 MOA 模板（Web Agent 添加）",
                "prompts": [f"执行 {text}"],
            },
        }
        template_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        sync_script = REPO_ROOT / "MOA" / "scripts" / "sync_registry.py"
        if not sync_script.is_file():
            raise FileNotFoundError(f"缺少 {sync_script}")
        proc = subprocess.run(
            [
                sys.executable,
                str(sync_script),
                "--allow-unverified",
                "--template",
                f"{file_name}.json",
            ],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip()
            raise RuntimeError(detail or "sync_registry 失败")
        _run_module_generate_index(registry_path)
        return {"id": item_id, "name": text, "category": cat}

    item_id = _unique_item_id(_slugify_id(text), items)
    item = {
        "id": item_id,
        "name": text,
        "category": cat,
        "description": "待配置（Web Agent 添加）",
        "prompts": [f"执行 {text}"],
        "command": _module_entry_command(mod, text),
    }
    _apply_source_tag(item, mod_id, source_tag)
    items.append(item)
    data["items"] = items
    _write_registry(registry_path, data)
    _run_module_generate_index(registry_path)
    return item


def delete_registry_item(*, source_id: str, registry_id: str) -> None:
    """从 registry 删除能力；MOA 会尝试删除关联 templates JSON。"""
    mod = _module_for_source_id(source_id)
    registry_path = _registry_path_for_module(mod)
    if not registry_path.is_file():
        raise FileNotFoundError(f"缺少 registry: {registry_path}")

    data = _read_registry(registry_path)
    items = data.get("items")
    if not isinstance(items, list):
        raise ValueError(f"{registry_path} items 必须是数组")

    rid = str(registry_id or "").strip()
    kept: list[Any] = []
    removed: dict[str, Any] | None = None
    for raw in items:
        if not isinstance(raw, dict):
            kept.append(raw)
            continue
        if str(raw.get("id") or "").strip() == rid:
            removed = raw
            continue
        kept.append(raw)
    if removed is None:
        raise ValueError(f"未找到能力 registry_id={registry_id}")

    template_path = _moa_template_from_command(str(removed.get("command") or ""))
    data["items"] = kept
    _write_registry(registry_path, data)
    if template_path is not None:
        try:
            template_path.unlink()
        except OSError as exc:
            raise RuntimeError(f"已删 registry 项，但删除模板失败：{template_path} ({exc})") from exc
    _run_module_generate_index(registry_path)


def normalize_catalog_prompt_save_body(body: Any) -> dict[str, Any] | None:
    if not isinstance(body, dict):
        return None
    source_id = str(body.get("source_id") or "").strip()
    if not source_id:
        return None
    if "add_item" in body and isinstance(body.get("add_item"), dict):
        add = body.get("add_item") or {}
        category = str(add.get("category") or "").strip()
        name = str(add.get("name") or "").strip()
        if not category or not name:
            return None
        out_add: dict[str, Any] = {
            "category": category,
            "name": name,
            "moa_generative": bool(add.get("moa_generative")),
        }
        if "source_tag" in add:
            out_add["source_tag"] = add.get("source_tag")
        return {
            "source_id": source_id,
            "registry_id": "",
            "add_item": out_add,
        }
    registry_id = str(body.get("registry_id") or "").strip()
    if not registry_id:
        return None
    out: dict[str, Any] = {"source_id": source_id, "registry_id": registry_id}
    if "prompts" in body:
        out["prompts"] = body.get("prompts")
        return out
    if "append_prompt" in body:
        out["append_prompt"] = body.get("append_prompt")
        return out
    if "delete_prompt_index" in body:
        out["delete_prompt_index"] = body.get("delete_prompt_index")
        return out
    if "name" in body:
        out["name"] = body.get("name")
        if "source_tag" in body:
            out["source_tag"] = body.get("source_tag")
        tgt = str(body.get("target_source_id") or "").strip()
        if tgt:
            out["target_source_id"] = tgt
        return out
    if "prompt_index" in body and "prompt" in body:
        out["prompt_index"] = body.get("prompt_index")
        out["prompt"] = body.get("prompt")
        return out
    if body.get("delete_item") is True:
        out["delete_item"] = True
        return out
    return None
