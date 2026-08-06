"""仓库内模块 execute / 模板 / 临时目录（随 AGENT_PROJECT 路径变化）。"""

from __future__ import annotations

from pathlib import Path

from .loader import (
    admin_config_path,
    get_repo_root,
    gift_cp_love_config_path,
    moa_generative_root,
    moa_templates_dir,
    mse_config_path,
    workflow_root,
)


def moa_runtime_dir() -> Path:
    """MOA 运行时目录（execute、Python 库、registry；不随项目 templates 路径变化）。"""
    return get_repo_root() / "MOA"


def moa_module_dir() -> Path:
    return moa_runtime_dir()


def admin_module_dir() -> Path:
    return admin_config_path().parent


def gift_module_dir() -> Path:
    return gift_cp_love_config_path().parent.parent


def mse_module_dir() -> Path:
    return mse_config_path().parent


def moa_execute_path() -> Path:
    return moa_runtime_dir() / "moa_execute.py"


def workflow_runtime_dir() -> Path:
    """workflow 运行时目录（execute、Python 库；不随项目 workflowRoot 数据路径变化）。"""
    return get_repo_root() / "workflow"


def workflow_execute_path() -> Path:
    return workflow_runtime_dir() / "workflow_execute.py"


def admin_execute_path() -> Path:
    return admin_module_dir() / "admin_execute.py"


def gift_execute_path() -> Path:
    return gift_module_dir() / "gift_execute.py"


def mse_execute_path() -> Path:
    return mse_module_dir() / "mse_execute.py"


def moa_template(name: str) -> Path:
    return moa_templates_dir() / name


def tmp_dir() -> Path:
    return get_repo_root() / ".tmp"


def gateway_dir() -> Path:
    return get_repo_root() / "platform" / "dingtalk_gateway"


def batch_progress_script() -> Path:
    return gateway_dir() / "batch_progress_report.py"


def scripts_dir() -> Path:
    return get_repo_root() / "scripts"


def dingtalk_lookup_execute() -> Path:
    return get_repo_root() / "DingTalk" / "lookup_execute.py"


def report_module_dir() -> Path:
    return get_repo_root() / "Report"


__all__ = [
    "admin_execute_path",
    "admin_module_dir",
    "batch_progress_script",
    "dingtalk_lookup_execute",
    "gateway_dir",
    "get_repo_root",
    "gift_execute_path",
    "gift_module_dir",
    "moa_execute_path",
    "moa_generative_root",
    "moa_module_dir",
    "moa_runtime_dir",
    "moa_template",
    "mse_execute_path",
    "mse_module_dir",
    "report_module_dir",
    "scripts_dir",
    "tmp_dir",
    "workflow_execute_path",
    "workflow_runtime_dir",
    "workflow_root",
]
