#!/usr/bin/env python3
"""将 MOA/templates 下未登记的新模板自动写入 config/registry.json，并刷新 使用方法.md。"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from moa.paths import moa_dir, registry_path, templates_dir

_TEMPLATE_REF_RE = re.compile(r"MOA/templates/([^\s\"'\\]+)")


def _read_json(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"{path} 必须是 JSON object")
    return data


def _write_json(path: str, data: dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _slugify(name: str) -> str:
    s = re.sub(r"[^\w\u4e00-\u9fff]+", "_", name.strip())
    s = re.sub(r"_+", "_", s).strip("_").lower()
    return s or "moa_template"


def _category_from_url(url: str) -> str:
    u = str(url or "").strip()
    if not u:
        return "MOA（未分类）"
    tail = u.rstrip("/").split("/")[-1]
    prefix = u.replace("/service/", "").split("/")[0] if "/service/" in u else u
    if "id-auth" in u:
        return f"实名认证（{prefix}）"
    if "vip" in u:
        return f"VIP（{tail or prefix}）"
    if "room-test" in u or "room/internal" in u:
        return f"房间测试（{prefix}）"
    if "room-backdoor" in u or "room" in u:
        return f"房间（{tail or prefix}）"
    if "family" in u:
        return f"家族（{prefix}）"
    if "user-login" in u or "mdp-user-login" in u:
        return "用户登录（mdp-user-login）"
    if "diamond" in u or "account" in u:
        return f"钻石/账户（{tail or prefix}）"
    return f"MOA（{prefix}）"


def _collect_registered_templates(items: list[Any]) -> set[str]:
    registered: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        cmd = item.get("command")
        if not isinstance(cmd, str):
            continue
        for match in _TEMPLATE_REF_RE.finditer(cmd):
            registered.add(match.group(1))
    return registered


def _existing_ids(items: list[Any]) -> set[str]:
    out: set[str] = set()
    for item in items:
        if isinstance(item, dict):
            item_id = item.get("id")
            if isinstance(item_id, str) and item_id.strip():
                out.add(item_id.strip())
    return out


def _unique_id(base: str, used: set[str]) -> str:
    candidate = base
    n = 2
    while candidate in used:
        candidate = f"{base}_{n}"
        n += 1
    used.add(candidate)
    return candidate


def _build_command(template_rel: str, cli_suffix: str) -> str:
    lines = [
        "python3 MOA/moa_execute.py \\",
        f"  --payload-file {template_rel}",
    ]
    for part in cli_suffix.strip().split():
        lines.append(f"  {part} \\")
    cmd = "\n".join(lines).rstrip(" \\") + "\n"
    return cmd


def _infer_registry_item(
    template_file: str,
    payload: dict[str, Any],
    *,
    used_ids: set[str],
) -> dict[str, Any]:
    base_name = os.path.splitext(template_file)[0]
    meta = payload.get("_registry")
    if not isinstance(meta, dict):
        meta = {}

    item_id = meta.get("id") if isinstance(meta.get("id"), str) else _slugify(base_name)
    item_id = _unique_id(str(item_id).strip(), used_ids)

    name = meta.get("name") if isinstance(meta.get("name"), str) else base_name
    url = str(payload.get("url") or "")
    method = str(payload.get("method") or "")
    category = meta.get("category") if isinstance(meta.get("category"), str) else _category_from_url(url)
    description = meta.get("description") if isinstance(meta.get("description"), str) else (
        f"{method}（{url}）" if method and url else f"MOA 模板 {base_name}"
    )

    prompts_raw = meta.get("prompts")
    if isinstance(prompts_raw, list) and prompts_raw:
        prompts = [str(p).strip() for p in prompts_raw if str(p).strip()]
    else:
        prompts = [f"执行 {base_name}"]

    cli_suffix = ""
    if isinstance(meta.get("cli"), str):
        cli_suffix = meta["cli"].strip()
    elif isinstance(meta.get("commandSuffix"), str):
        cli_suffix = meta["commandSuffix"].strip()

    template_rel = f"MOA/templates/{template_file}"
    return {
        "id": item_id,
        "name": name.strip(),
        "category": category.strip(),
        "description": description.strip(),
        "prompts": prompts,
        "command": _build_command(template_rel, cli_suffix),
    }


def sync_registry(*, dry_run: bool = False) -> list[dict[str, Any]]:
    registry = _read_json(registry_path())
    items = registry.get("items")
    if not isinstance(items, list):
        raise ValueError("registry.items 必须是 array")

    registered = _collect_registered_templates(items)
    used_ids = _existing_ids(items)
    added: list[dict[str, Any]] = []

    template_root = templates_dir()
    for fname in sorted(os.listdir(template_root)):
        if not fname.endswith(".json"):
            continue
        if fname in registered:
            continue
        path = os.path.join(template_root, fname)
        if not os.path.isfile(path):
            continue
        payload = _read_json(path)
        item = _infer_registry_item(fname, payload, used_ids=used_ids)
        items.append(item)
        added.append(item)
        registered.add(fname)

    if added and not dry_run:
        registry["items"] = items
        _write_json(registry_path(), registry)

    return added


def _run_generate_index() -> None:
    script = os.path.join(moa_dir(), "scripts", "generate_index.py")
    subprocess.run([sys.executable, script], check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="MOA 新模板自动入库 registry.json")
    parser.add_argument("--dry-run", action="store_true", help="仅打印将新增的条目，不写文件")
    parser.add_argument("--no-generate", action="store_true", help="入库后不刷新 使用方法.md")
    args = parser.parse_args()

    added = sync_registry(dry_run=args.dry_run)
    if not added:
        print("sync_registry: 无新模板需要入库")
    else:
        print(f"sync_registry: 新增 {len(added)} 条")
        for item in added:
            print(f"  + {item['id']}: {item['name']}")

    if not args.dry_run and not args.no_generate:
        _run_generate_index()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
