"""从 sources.json + registry 加载平台能力目录。"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_MCP_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _MCP_DIR.parent.parent
import sys

if str(_REPO_ROOT / "platform") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "platform"))

from project.catalog_paths import module_registry_path  # noqa: E402
from project.loader import get_repo_root, load_sources  # noqa: E402

_PARAM_RE = re.compile(r"<([^>]+)>")

# 无 registry、仅 CLI entry 的模块（与 sources.json 并列展示）
EXTRA_CLI_MODULES: dict[str, dict[str, str]] = {
    "adb": {
        "label": "ADB 真机",
        "subtitle": "observe / macro / flow / capture",
        "env": "test",
        "entry": "adb/adb_execute.py",
    },
    "adb-screenshot": {
        "label": "无线截图",
        "subtitle": "远程 ADB 截图",
        "env": "tool",
        "entry": "AdbScreenshot/adb_screenshot_execute.py",
    },
    "report": {
        "label": "报告",
        "subtitle": "测试报告生成",
        "env": "tool",
        "entry": "Report/report_execute.py",
    },
}


@dataclass
class Capability:
    module_id: str
    id: str
    name: str
    category: str
    description: str
    command: str
    prompts: list[str] = field(default_factory=list)
    parameters: list[str] = field(default_factory=list)

    def to_summary(self) -> dict[str, Any]:
        return {
            "module_id": self.module_id,
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "parameters": self.parameters,
            "prompts": self.prompts[:3],
        }

    def to_detail(self) -> dict[str, Any]:
        out = self.to_summary()
        out["command_template"] = self.command
        out["prompts"] = self.prompts
        return out


@dataclass
class ModuleInfo:
    id: str
    label: str
    subtitle: str
    env: str
    entry: str
    capability_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "subtitle": self.subtitle,
            "env": self.env,
            "entry": self.entry,
            "capability_count": self.capability_count,
        }


def _read_registry(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    import json

    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return []
    items = data.get("items") or data.get("capabilities")
    if not isinstance(items, list):
        return []
    return [x for x in items if isinstance(x, dict)]


def extract_parameters(command: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for match in _PARAM_RE.finditer(command or ""):
        key = match.group(1).strip()
        if key and key not in seen:
            seen.add(key)
            out.append(key)
    return out


def substitute_parameters(command: str, params: dict[str, Any]) -> str:
    missing: list[str] = []

    def repl(match: re.Match[str]) -> str:
        key = match.group(1).strip()
        if key not in params or params[key] is None or str(params[key]).strip() == "":
            missing.append(key)
            return match.group(0)
        return str(params[key])

    result = _PARAM_RE.sub(repl, command or "")
    if missing:
        raise ValueError(
            f"缺少参数: {', '.join(missing)}（占位符 <{missing[0]}> 等）"
        )
    return result


def normalize_argv(argv: list[str]) -> list[str]:
    return [a for a in argv if a]


def command_to_argv(command: str) -> list[str]:
    text = (command or "").replace("\\\n", " ").replace("\\", " ")
    text = " ".join(line.strip() for line in text.splitlines() if line.strip())
    if not text.strip():
        raise ValueError("命令为空")
    return normalize_argv(shlex.split(text))


def resolve_entry_argv(entry: str) -> list[str]:
    text = (entry or "").strip()
    if not text:
        raise ValueError("模块 entry 为空")
    if text.startswith("python3 "):
        return command_to_argv(text)
    script = text.split()[0] if text else ""
    if script.endswith("_execute.py") or script.endswith(".py"):
        return ["python3", str(get_repo_root() / script)] + shlex.split(text[len(script) :].strip())
    return command_to_argv(f"python3 {text}")


def load_catalog() -> tuple[list[ModuleInfo], dict[tuple[str, str], Capability]]:
    sources = load_sources()
    modules_cfg = sources.get("modules")
    if not isinstance(modules_cfg, list):
        modules_cfg = []

    module_entries: list[dict[str, str]] = []
    seen_ids: set[str] = set()

    for mod in modules_cfg:
        if not isinstance(mod, dict):
            continue
        mod_id = str(mod.get("id") or "").strip()
        if not mod_id:
            continue
        seen_ids.add(mod_id)
        entry = str(mod.get("entry") or "").strip()
        if entry.startswith("python3 "):
            entry = entry[len("python3 ") :].strip()
        module_entries.append(
            {
                "id": mod_id,
                "label": str(mod.get("label") or mod_id),
                "subtitle": str(mod.get("subtitle") or ""),
                "env": str(mod.get("env") or "test"),
                "entry": entry,
                "registry": str(mod.get("registry") or "").strip(),
            }
        )

    for mod_id, extra in EXTRA_CLI_MODULES.items():
        if mod_id in seen_ids:
            continue
        module_entries.append(
            {
                "id": mod_id,
                "label": extra["label"],
                "subtitle": extra["subtitle"],
                "env": extra["env"],
                "entry": extra["entry"],
                "registry": "",
            }
        )

    capabilities: dict[tuple[str, str], Capability] = {}
    modules: list[ModuleInfo] = []

    for mod in module_entries:
        mod_id = mod["id"]
        registry_rel = mod.get("registry") or ""
        items: list[dict[str, Any]] = []
        if registry_rel:
            reg_path = module_registry_path(mod_id, registry_rel)
            items = _read_registry(reg_path)

        for item in items:
            cap_id = str(item.get("id") or "").strip()
            if not cap_id:
                continue
            command = str(item.get("command") or "").strip()
            cap = Capability(
                module_id=mod_id,
                id=cap_id,
                name=str(item.get("name") or cap_id),
                category=str(item.get("category") or "未分类"),
                description=str(item.get("description") or ""),
                command=command,
                prompts=[str(p) for p in (item.get("prompts") or []) if str(p).strip()],
                parameters=extract_parameters(command),
            )
            capabilities[(mod_id, cap_id)] = cap

        modules.append(
            ModuleInfo(
                id=mod_id,
                label=mod["label"],
                subtitle=mod["subtitle"],
                env=mod["env"],
                entry=mod["entry"],
                capability_count=sum(1 for k in capabilities if k[0] == mod_id),
            )
        )

    return modules, capabilities


def get_module(module_id: str) -> ModuleInfo | None:
    modules, _ = load_catalog()
    for mod in modules:
        if mod.id == module_id:
            return mod
    return None


def get_capability(module_id: str, capability_id: str) -> Capability | None:
    _, capabilities = load_catalog()
    return capabilities.get((module_id, capability_id))


def search_capabilities(
    query: str,
    *,
    module_id: str | None = None,
    limit: int = 20,
) -> list[Capability]:
    _, capabilities = load_catalog()
    q = (query or "").strip().lower()
    results: list[Capability] = []
    for cap in capabilities.values():
        if module_id and cap.module_id != module_id:
            continue
        if not q:
            results.append(cap)
            continue
        haystack = " ".join(
            [
                cap.name,
                cap.category,
                cap.description,
                " ".join(cap.prompts),
                cap.id,
            ]
        ).lower()
        if q in haystack or all(part in haystack for part in q.split()):
            results.append(cap)
    results.sort(key=lambda x: (x.module_id, x.category, x.name))
    return results[: max(1, min(limit, 100))]


def list_module_capabilities(
    module_id: str,
    *,
    category: str | None = None,
    limit: int = 200,
) -> list[Capability]:
    _, capabilities = load_catalog()
    cat = (category or "").strip().lower()
    results = [
        cap
        for cap in capabilities.values()
        if cap.module_id == module_id and (not cat or cat in cap.category.lower())
    ]
    results.sort(key=lambda x: (x.category, x.name))
    return results[: max(1, min(limit, 500))]


def build_capability_argv(
    module_id: str,
    capability_id: str,
    params: dict[str, Any],
) -> list[str]:
    cap = get_capability(module_id, capability_id)
    if cap is None:
        raise ValueError(f"未找到能力: {module_id}/{capability_id}")
    command = substitute_parameters(cap.command, params)
    return command_to_argv(command)
