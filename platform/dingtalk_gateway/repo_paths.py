"""钉钉网关脚本：模块 execute / 模板路径（AGENT_PROJECT 感知）。"""

from __future__ import annotations

import sys
from pathlib import Path

_PLATFORM = Path(__file__).resolve().parents[1]
if str(_PLATFORM) not in sys.path:
    sys.path.insert(0, str(_PLATFORM))

from project.loader import api_endpoint, api_family_pk_h5_path, stage_gateway_url  # noqa: E402
from project.repo_paths import (  # noqa: E402
    admin_execute_path,
    admin_module_dir,
    batch_progress_script,
    gateway_dir,
    get_repo_root,
    gift_execute_path,
    gift_module_dir,
    moa_execute_path,
    moa_module_dir,
    moa_template,
    mse_execute_path,
    mse_module_dir,
    tmp_dir,
)

__all__ = [
    "admin_execute_path",
    "admin_module_dir",
    "api_endpoint",
    "api_family_pk_h5_path",
    "batch_progress_script",
    "gateway_dir",
    "get_repo_root",
    "gift_execute_path",
    "gift_module_dir",
    "moa_execute_path",
    "moa_module_dir",
    "moa_template",
    "mse_execute_path",
    "mse_module_dir",
    "stage_gateway_url",
    "tmp_dir",
]
