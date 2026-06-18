"""知识库：按模块缓存摘要，避免每步重复读盘。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from .paths import repo_root


def _read_hints(path: Path, *, max_lines: int = 8, max_chars: int = 900) -> str:
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8")[:max_chars]
    lines: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("- ") and len(line) < 72:
            lines.append(line[2:].strip())
        if len(lines) >= max_lines:
            break
    return "\n".join(lines)


@lru_cache(maxsize=32)
def _cached_module_hints(module: str, testcase_rel: str, verified_rel: str) -> tuple[str, ...]:
    root = repo_root()
    hints: list[str] = []
    for rel in (testcase_rel, verified_rel):
        path = root / rel / f"{module}.md"
        snippet = _read_hints(path)
        if snippet:
            hints.extend(snippet.splitlines())
    return tuple(hints[:10])


def load_kb_hints(module: str, *, config: dict | None = None) -> list[str]:
    """加载思考层用短提示（缓存，单步仅内存查找）。"""
    module_key = (module or "").strip()
    if not module_key:
        return []

    kb_cfg = {}
    if isinstance(config, dict) and isinstance(config.get("knowledge"), dict):
        kb_cfg = config["knowledge"]

    testcase_rel = str(kb_cfg.get("testcaseKb") or "testcase-kb")
    verified_rel = str(kb_cfg.get("verifiedKb") or "verified-kb")
    return list(_cached_module_hints(module_key, testcase_rel, verified_rel))


def load_module_context(module: str, *, config: dict | None = None) -> dict[str, str]:
    """兼容旧接口：仅返回 hints 聚合。"""
    hints = load_kb_hints(module, config=config)
    if not hints:
        return {}
    return {"hints": "\n".join(hints)}
