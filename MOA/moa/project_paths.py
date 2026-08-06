"""MOA 模块读取 AGENT_PROJECT 路径与 API（供 moa/* 库代码使用）。"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_PLATFORM = _REPO / "platform"
if str(_PLATFORM) not in sys.path:
    sys.path.insert(0, str(_PLATFORM))

from project.loader import (  # noqa: E402
    api_endpoint,
    api_moa_service_prefix,
    app_java_area_enum_fqcn,
    get_repo_root,
)
from project.repo_paths import (  # noqa: E402
    admin_execute_path,
    admin_module_dir,
    gift_execute_path,
    gift_module_dir,
    moa_execute_path,
    moa_template,
    moa_templates_dir,
)

__all__ = [
    "admin_execute_path",
    "admin_module_dir",
    "app_area_enum_fqcn",
    "gift_execute_path",
    "gift_module_dir",
    "get_repo_root",
    "moa_execute_path",
    "moa_service_url",
    "moa_template",
    "moa_templates_dir",
]


def moa_service_url(key: str, default: str) -> str:
    return api_endpoint(key, default)


def app_area_enum_fqcn() -> str:
    return app_java_area_enum_fqcn()
