"""工作流参数占位符 {{name}} 替换。"""

from __future__ import annotations

import re
from typing import Any

_PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")


def substitute_value(value: Any, params: dict[str, str]) -> Any:
    if isinstance(value, str):
        def _repl(m: re.Match[str]) -> str:
            key = m.group(1)
            if key not in params:
                raise KeyError(f"缺少工作流参数: {key}")
            return params[key]

        return _PLACEHOLDER.sub(_repl, value)
    if isinstance(value, list):
        return [substitute_value(v, params) for v in value]
    if isinstance(value, dict):
        return {k: substitute_value(v, params) for k, v in value.items()}
    return value


def build_params(spec: dict[str, Any], cli_values: dict[str, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, meta in spec.items():
        if not isinstance(meta, dict):
            raise ValueError(f"params.{key} 必须是 object")
        if key in cli_values and cli_values[key] not in (None, ""):
            out[key] = str(cli_values[key])
            continue
        default = meta.get("default")
        if default is not None:
            out[key] = str(default)
            continue
        if meta.get("required", True):
            raise ValueError(f"缺少必填参数: {key} ({meta.get('label', key)})")
    return out
