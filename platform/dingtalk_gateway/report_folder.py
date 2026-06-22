"""测试报告上传目录配置。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from env_loader import GATEWAY_DIR

REPORT_CONFIG = GATEWAY_DIR / "config" / "report_folder.json"


@dataclass
class ReportFolderConfig:
    node_id: str
    folder_url: str
    name: str = "测试报告导出"


def load_report_folder_config() -> ReportFolderConfig:
    data = json.loads(REPORT_CONFIG.read_text(encoding="utf-8"))
    return ReportFolderConfig(
        node_id=str(data["nodeId"]),
        folder_url=str(data["folderUrl"]),
        name=str(data.get("name") or "测试报告导出"),
    )
