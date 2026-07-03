"""workflow 模块路径常量。"""

from __future__ import annotations

from pathlib import Path

WORKFLOW_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = WORKFLOW_DIR.parent
WORKFLOWS_DIR = WORKFLOW_DIR / "workflows"
CONFIG_DIR = WORKFLOW_DIR / "config"
REGISTRY_PATH = CONFIG_DIR / "registry.json"
USAGE_DOC_PATH = WORKFLOW_DIR / "使用方法.md"
TMP_RUNS_DIR = REPO_ROOT / ".tmp" / "workflow_runs"
