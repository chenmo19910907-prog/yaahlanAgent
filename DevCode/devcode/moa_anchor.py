"""MOA method → local voga-repos Java anchors + registered MOA templates."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from devcode.paths import repo_root, voga_repos_dir

_JAVA_FIELD_RE = re.compile(
    r"^\s*private\s+[\w.<>,\s]+\s+(\w+)\s*;",
    re.MULTILINE,
)
_JAVA_COMMENT_BEFORE_FIELD_RE = re.compile(
    r"/\*\*\s*\n([^*]|\*(?!/))*\*/\s*\n\s*private",
    re.MULTILINE,
)
_REQ_IMPORT_RE = re.compile(
    r"import\s+[\w.]+\.([\w]+Req(?:uest)?)\s*;"
)
def _load_moa_templates_for_method(method: str) -> list[dict[str, Any]]:
    root = Path(repo_root())
    templates_dir = root / "MOA" / "templates"
    hits: list[dict[str, Any]] = []
    if not templates_dir.is_dir():
        return hits
    for path in sorted(templates_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if str(data.get("method") or "").strip() != method:
            continue
        sample: dict[str, Any] = {}
        for block in data.get("params") or []:
            val = block.get("value") or block.get("txt")
            if isinstance(val, dict):
                sample = val
                break
        hits.append(
            {
                "template": f"MOA/templates/{path.name}",
                "url": data.get("url"),
                "sampleParams": sample,
            }
        )
    return hits


def _registry_entries_for_method(method: str) -> list[dict[str, str]]:
    reg_path = Path(repo_root()) / "MOA" / "config" / "registry.json"
    if not reg_path.is_file():
        return []
    try:
        reg = json.loads(reg_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    out: list[dict[str, str]] = []
    for item in reg.get("items") or []:
        cmd = str(item.get("command") or "")
        if method not in cmd and method not in str(item.get("description") or ""):
            continue
        if "moa_execute" not in cmd and method not in cmd:
            tmpl_hit = any(
                t.get("template", "").endswith(".json")
                for t in _load_moa_templates_for_method(method)
            )
            if not tmpl_hit:
                continue
        out.append(
            {
                "id": str(item.get("id") or ""),
                "name": str(item.get("name") or ""),
                "category": str(item.get("category") or ""),
            }
        )
    return out


def _rg_java(pattern: str, roots: list[Path], *, head_limit: int = 40) -> list[dict[str, str]]:
    hits: list[dict[str, str]] = []
    for root in roots:
        if not root.is_dir():
            continue
        try:
            proc = subprocess.run(
                [
                    "rg",
                    "-n",
                    "--glob",
                    "*.java",
                    "-m",
                    str(head_limit),
                    pattern,
                    str(root),
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            continue
        for line in proc.stdout.splitlines():
            if ":" not in line:
                continue
            path_part, rest = line.split(":", 1)
            if rest.count(":") < 1:
                continue
            ln, text = rest.split(":", 1)
            rel = os.path.relpath(path_part, repo_root())
            hits.append({"file": rel, "line": ln.strip(), "text": text.strip()})
    return hits[:head_limit]


def _find_req_fields(req_class: str, voga_root: Path) -> dict[str, Any]:
    proc = subprocess.run(
        [
            "rg",
            "-l",
            f"class {req_class}\\b",
            "--glob",
            f"**/{req_class}.java",
            str(voga_root),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    paths = [p.strip() for p in proc.stdout.splitlines() if p.strip()]
    if not paths:
        return {"reqClass": req_class, "fields": [], "source": None}
    req_path = Path(paths[0])
    try:
        src = req_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {"reqClass": req_class, "fields": [], "source": None}
    fields: list[dict[str, str]] = []
    for m in _JAVA_FIELD_RE.finditer(src):
        name = m.group(1)
        start = max(0, m.start() - 400)
        chunk = src[start : m.start()]
        comment = ""
        cm = re.search(r"/\*\*([^*]|\*(?!/))*\*/\s*$", chunk, re.MULTILINE)
        if cm:
            comment = re.sub(r"^\s*\*\s?", "", cm.group(0), flags=re.MULTILINE)
            comment = comment.replace("/**", "").replace("*/", "").strip()
        fields.append({"name": name, "note": comment[:200]})
    return {
        "reqClass": req_class,
        "fields": fields,
        "source": os.path.relpath(req_path, repo_root()),
    }


def _moa_facade_impls(method: str, voga_root: Path) -> list[dict[str, Any]]:
    iface_hits = _rg_java(
        rf"\b{re.escape(method)}\s*\(", [voga_root], head_limit=20
    )
    impls: list[dict[str, Any]] = []
    seen: set[str] = set()
    for h in iface_hits:
        if "MoaService" not in h["file"] and "MoaServiceImpl" not in h["file"]:
            continue
        key = h["file"]
        if key in seen:
            continue
        seen.add(key)
        full = Path(repo_root()) / h["file"]
        try:
            text = full.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        req_class = ""
        for im in _REQ_IMPORT_RE.finditer(text):
            if "req" in im.group(0).lower() or "Req" in im.group(1):
                req_class = im.group(1)
        if not req_class:
            sig = re.search(
                rf"public\s+[\w<>,\s]+\s+{re.escape(method)}\s*\(\s*([\w.]+)\s+",
                text,
            )
            if sig:
                req_class = sig.group(1).split(".")[-1]
        entry: dict[str, Any] = {
            "file": h["file"],
            "line": h["line"],
            "snippet": h["text"][:160],
        }
        if req_class:
            entry["request"] = _find_req_fields(req_class, voga_root)
        impls.append(entry)
    return impls


def anchor_moa_method(method: str) -> dict[str, Any]:
    method = method.strip()
    if not method:
        raise ValueError("method 不能为空")
    voga = Path(voga_repos_dir())
    templates = _load_moa_templates_for_method(method)
    registry = _registry_entries_for_method(method)
    java_hits = _rg_java(re.escape(method), [voga], head_limit=30)
    moa_impls = _moa_facade_impls(method, voga)

    branches: list[str] = []
    for impl in moa_impls:
        req = impl.get("request") or {}
        for f in req.get("fields") or []:
            note = (f.get("note") or "").strip()
            if note:
                branches.append(f"{f.get('name')}: {note}")

    return {
        "ok": True,
        "method": method,
        "moaTemplates": templates,
        "registry": registry,
        "moaFacades": moa_impls,
        "relatedJava": java_hits[:15],
        "acceptanceHints": branches[:8],
        "suggestedCommand": (
            f"python3 MOA/moa_execute.py --payload-file {templates[0]['template']}"
            if templates
            else None
        ),
    }
