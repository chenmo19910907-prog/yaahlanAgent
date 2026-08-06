"""workflow 模块路径（随 AGENT_PROJECT 变化）。"""

from __future__ import annotations

import sys
from pathlib import Path

_WORKFLOW_PKG = Path(__file__).resolve().parent
_REPO_ROOT = _WORKFLOW_PKG.parent
_PLATFORM = _REPO_ROOT / "platform"
if str(_PLATFORM) not in sys.path:
    sys.path.insert(0, str(_PLATFORM))

from project.loader import get_repo_root, workflow_root  # noqa: E402
from project.repo_paths import tmp_dir  # noqa: E402

WORKFLOW_DIR = workflow_root()
REPO_ROOT = get_repo_root()
WORKFLOWS_DIR = WORKFLOW_DIR / "workflows"
CONFIG_DIR = WORKFLOW_DIR / "config"
REGISTRY_PATH = CONFIG_DIR / "registry.json"
USAGE_DOC_PATH = WORKFLOW_DIR / "使用方法.md"
TMP_RUNS_DIR = tmp_dir() / "workflow_runs"
